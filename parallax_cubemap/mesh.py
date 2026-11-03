# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only preflight and atomic material assignment; UV/geometry stay intact."""
from dataclasses import dataclass, field
import math
import bpy
from .translations import tr, CONTEXT
import bmesh
from .shader import MATERIAL_NAME

EPSILON = 1e-6
MAX_SLOTS = 32767


@dataclass
class Stage:
    objects: list
    bm: object
    edit: bool
    faces: list = field(default_factory=list)

    @property
    def mesh(self):
        return self.objects[0].data


def release_selection(stages):
    for stage in stages:
        if not stage.edit:
            stage.bm.free()


def choose_slot(stage, material):
    # A DATA slot can be overridden per object. Reuse only a slot that resolves
    # to this material for EVERY selected instance of the shared mesh.
    if material:
        for i, item in enumerate(stage.mesh.materials):
            if item == material and all(obj.material_slots[i].material == material
                                        for obj in stage.objects):
                return i
    selected = {face.index for face in stage.faces}
    # Untouched faces may refer to a slot which does not exist yet. Padding it
    # with None avoids assigning the new material to those faces implicitly.
    count = len(stage.mesh.materials)
    untouched = [f.material_index for f in stage.bm.faces if f.index not in selected]
    slot = max(count, max(untouched, default=-1) + 1)
    if slot >= MAX_SLOTS:
        raise ValueError(tr("Material slot limit reached: ") + stage.objects[0].name)
    return slot


def prepare_selection(context, for_restore=False):
    if context.mode == "EDIT_MESH":
        objects = list(context.objects_in_mode)
    elif context.mode == "OBJECT":
        objects = [o for o in context.selected_objects if o.type == "MESH"]
    else:
        objects = []
    if not objects:
        raise ValueError(tr("Select window mesh objects or faces in Edit Mode"))
    grouped = {}
    for obj in objects:
        grouped.setdefault(obj.data.as_pointer(), []).append(obj)
    stages = []
    try:
        for instances in grouped.values():
            obj = instances[0]
            mesh = obj.data
            if mesh.library or not mesh.is_editable or any(not o.is_editable for o in instances):
                raise ValueError(tr("Object or Mesh is read-only: ") + obj.name)
            edit = obj.mode == "EDIT"
            bm = bmesh.from_edit_mesh(mesh) if edit else bmesh.new()
            stage = Stage(instances, bm, edit)
            stages.append(stage)
            if not edit:
                bm.from_mesh(mesh)
            bm.faces.index_update()
            stage.faces = [f for f in bm.faces
                           if (for_restore and not edit) or (not f.hide and (not edit or f.select))]
            if not stage.faces or for_restore:
                continue
            render_name = next((layer.name for layer in mesh.uv_layers if layer.active_render), None)
            uv = bm.loops.layers.uv.get(render_name) if render_name else bm.loops.layers.uv.active
            if uv is None:
                raise ValueError(tr("No UV map: %s. Create UVs within 0–1") % obj.name)
            for face in stage.faces:
                coords = [loop[uv].uv[:] for loop in face.loops]
                if any(not math.isfinite(c) or c < -EPSILON or c > 1 + EPSILON
                       for point in coords for c in point):
                    raise ValueError(tr("UV coordinates are outside 0–1: ") + obj.name)
                area = abs(sum(a[0]*b[1]-b[0]*a[1]
                               for a, b in zip(coords, coords[1:]+coords[:1]))) / 2
                if area <= 1e-12 or face.calc_area() <= 1e-12:
                    raise ValueError(tr("Degenerate face or UV map: ") + obj.name)
            choose_slot(stage, bpy.data.materials.get(MATERIAL_NAME))
        if not any(s.faces for s in stages):
            raise ValueError(tr("No window faces selected"))
    except Exception:
        release_selection(stages)
        raise
    return stages


def set_faces(stage, indices):
    for face, index in indices:
        if stage.edit:
            face.material_index = index
        else:
            stage.mesh.polygons[face.index].material_index = index
    if stage.edit:
        bmesh.update_edit_mesh(stage.mesh, loop_triangles=False, destructive=False)
    else:
        stage.mesh.update()


def commit_selection(stages, material):
    plans = []
    for stage in stages:
        if not stage.faces:
            continue
        plans.append((stage, choose_slot(stage, material), len(stage.mesh.materials),
                      [(f, f.material_index) for f in stage.faces],
                      [(o, o.active_material_index) for o in stage.objects]))
    try:
        for stage, slot, old_count, _, _ in plans:
            if slot >= old_count:
                while len(stage.mesh.materials) < slot:
                    stage.mesh.materials.append(None)
                stage.mesh.materials.append(material)
                for obj in stage.objects:
                    obj.material_slots[slot].link = "DATA"
            set_faces(stage, [(f, slot) for f in stage.faces])
            for obj in stage.objects:
                obj.active_material_index = slot
    except Exception:
        # Restore only fields this operator owns. Never rebuild the mesh.
        for stage, _, old_count, faces, active in reversed(plans):
            set_faces(stage, faces)
            while len(stage.mesh.materials) > old_count:
                stage.mesh.materials.pop(index=len(stage.mesh.materials)-1)
            if old_count == 0:
                # Native pop can leave a phantom Object slot after Edit Mode.
                stage.mesh.materials.clear()
            for obj, index in active:
                obj.active_material_index = index
        raise
    return sum(len(s.faces) for s in stages)

def finish_in_object_mode(context, stages):
    # Blender 4.5 Edit Mesh undo omits Material/NodeTree IDs and material slots.
    # Preserve exact selected-face indices, flush edit meshes using Blender,
    # then let the operator's normal UNDO flag record a Global Undo step.
    specs = [(s.objects, [f.index for f in s.faces]) for s in stages]
    bpy.ops.object.mode_set(mode="OBJECT")
    release_selection(stages)
    stages.clear()
    for objects, indices in specs:
        bm = bmesh.new()
        stage = Stage(objects, bm, False)
        stages.append(stage)
        bm.from_mesh(objects[0].data)
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        stage.faces = [bm.faces[i] for i in indices]
