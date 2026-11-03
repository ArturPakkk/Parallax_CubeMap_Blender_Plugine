# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "Parallax_CubeMap",
    "author": "ArturPakkk",
    "version": (2, 0, 0),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > Parallax",
    "description": "Direct UV parallax with a room/debug texture switch",
    "category": "Material",
}
from pathlib import Path
import bpy
from .translations import tr, CONTEXT
from bpy.types import Operator, Panel
from .shader import (create_material, material_node, MATERIAL_NAME, VERSION, OWNER,
                     is_managed, debug_enabled, switch_node)
from .mesh import (prepare_selection, commit_selection, release_selection,
                   finish_in_object_mode)
from . import backup, translations

ASSETS = ("T_Parallax_02.exr", "Parallax_Debug.exr")


def atlas_path(filename=ASSETS[0]):
    bundled = Path(__file__).parent / "assets" / filename
    if bundled.is_file():
        return bundled
    raise ValueError(tr("Missing bundled file: %s. Reinstall the addon ZIP") % filename)


def canonical_material():
    # Resolve on every operation/draw. Undo may invalidate all prior RNA refs.
    matches = [m for m in bpy.data.materials if m.name == MATERIAL_NAME]
    return next((m for m in matches if m.library is None), matches[0] if matches else None)



def context_has_material(context, material):
    if material is None:
        return False
    objects = context.objects_in_mode if context.mode == "EDIT_MESH" else context.selected_objects
    return any(o.type == "MESH" and any(slot.material == material for slot in o.material_slots)
               for o in objects)


def material_on_faces(material):
    # Called by operators, not panel drawing. Shared materials keep their mode
    # while any instance still displays the material on a face.
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        slots = {i for i, slot in enumerate(obj.material_slots) if slot.material == material}
        if slots and any(p.material_index in slots for p in obj.data.polygons):
            return True
    return False


def validate_material(material):
    if not material.is_editable or material.library:
        raise ValueError(tr("Debug_Parallax is read-only (Linked Library)"))
    if not is_managed(material):
        raise ValueError(tr("Debug_Parallax belongs to another or modified material. Rename it; the addon preserves user materials"))


def remove_created_material(material):
    groups = [n.node_tree for n in material.node_tree.nodes if n.type == "GROUP"]
    bpy.data.materials.remove(material)
    for group in groups:
        if group.users == 0:
            bpy.data.node_groups.remove(group)


def get_material():
    material = canonical_material()
    if material:
        validate_material(material)
        return material, False
    # Resolve both files before importing anything.
    paths = [atlas_path(name) for name in ASSETS]
    images, created = [], []
    old_images = {image.as_pointer() for image in bpy.data.images}
    try:
        for path in paths:
            image = bpy.data.images.load(str(path), check_existing=True)
            if image.as_pointer() not in old_images:
                image.name = path.stem
                created.append(image)
            images.append(image)
            if tuple(image.size) != (2048, 2048) or image.channels != 4:
                raise ValueError(tr("Invalid EXR: %s. Expected RGBA 2048×2048") % path.name)
        for image in images:
            if not image.packed_file:
                image.pack()
        return create_material(images[0], debug_image=images[1]), True
    except Exception:
        for image in created:
            if image.users == 0:
                bpy.data.images.remove(image)
        raise


class PCM_OT_assign(Operator):
    bl_idname = "parallax_cubemap.assign_material"
    bl_label = "Assign Material"
    bl_description = "Save original materials and assign Debug_Parallax using UV 0–1; finish in Object Mode for Ctrl+Z"
    bl_translation_context = CONTEXT
    bl_options = {"UNDO"}

    def execute(self, context):
        stages, material, created, saved, previous_mode = [], None, False, [], None
        try:
            stages = prepare_selection(context)
            backup.preflight(stages)
            material, created = get_material()
            if any(s.edit for s in stages):
                finish_in_object_mode(context, stages)
            start_in_room = not material_on_faces(material)
            saved, unknown = backup.remember(stages, material)
            count = commit_selection(stages, material)
            if start_in_room:
                previous_mode = switch_node(material).inputs[0].default_value
                switch_node(material).inputs[0].default_value = 0.0
        except (ValueError, RuntimeError) as error:
            backup.rollback(saved)
            if previous_mode is not None and not created:
                switch_node(material).inputs[0].default_value = previous_mode
            if created:
                remove_created_material(material)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        finally:
            release_selection(stages)
        self.report({"INFO"}, tr("Debug_Parallax assigned to %d faces") % count)
        if unknown:
            self.report({"WARNING"}, tr("%d faces have no previous assignment history (before version 1.3)") % unknown)
        return {"FINISHED"}

    def invoke(self, context, event):
        # Ctrl/Shift/Alt do not alter assignment or Blender keymaps.
        return self.execute(context)


class PCM_OT_toggle_debug(Operator):
    bl_idname = "parallax_cubemap.toggle_debug"
    bl_label = "Debug Texture"
    bl_description = "Room / Debug for all windows; finish in Object Mode for correct Ctrl+Z"
    bl_translation_context = CONTEXT
    bl_options = {"UNDO"}

    def execute(self, context):
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report({"ERROR"}, tr("Switch to Object Mode or Edit Mode"))
            return {"CANCELLED"}
        material = canonical_material()
        if material is None:
            self.report({"ERROR"}, tr("Assign Debug_Parallax first"))
            return {"CANCELLED"}
        try:
            validate_material(material)
            if not context_has_material(context, material):
                raise ValueError(tr("Assign Debug_Parallax to the selected objects first"))
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        # Only one value inside the Material datablock changes. No Scene state,
        # callbacks, image reloads, group rebuilding, handlers or cached refs.
        edit = context.mode == "EDIT_MESH"
        if edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        switch = switch_node(material)
        switch.inputs[0].default_value = 0.0 if debug_enabled(material) else 1.0

        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class PCM_OT_restore(Operator):
    bl_idname = "parallax_cubemap.restore_materials"
    bl_label = "Restore Materials"
    bl_description = "Restore saved materials on selected objects/faces while keeping later modelling edits"
    bl_translation_context = CONTEXT
    bl_options = {"UNDO"}

    def execute(self, context):
        stages = []
        try:
            stages = prepare_selection(context, for_restore=True)
            plans, skipped, missing = backup.restore_plans(stages)
            if not plans:
                if missing:
                    raise ValueError(tr("Original materials were deleted. Restoring by name alone is unsafe"))
                if skipped:
                    raise ValueError(tr("Materials on the saved faces were changed manually; those faces were skipped"))
                raise ValueError(tr("No saved materials. Backups are created by assignments made in version 1.3 or later"))
            # Backups contain ID references; Edit Mesh Undo alone cannot record them.
            if any(s.edit for s in stages):
                finish_in_object_mode(context, stages)
            count, skipped, missing = backup.restore(stages)
        except (ValueError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        finally:
            release_selection(stages)
        self.report({"INFO"}, tr("Original materials restored on %d faces") % count)
        if skipped or missing:
            self.report({"WARNING"}, tr("Skipped: manually changed — %d, deleted original materials — %d") % (skipped, missing))
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class PCM_PT_panel(Panel):
    bl_label = "Parallax_CubeMap"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Parallax"

    def draw(self, context):
        self.layout.operator("parallax_cubemap.assign_material", text="Assign Material", text_ctxt=CONTEXT, icon="MATERIAL")
        material = canonical_material()
        row = self.layout.row()
        row.enabled = bool(context.mode in {"OBJECT", "EDIT_MESH"} and is_managed(material)
                           and material.is_editable and not material.library
                           and context_has_material(context, material))
        row.operator("parallax_cubemap.toggle_debug", text="Debug Texture", text_ctxt=CONTEXT,
                     icon="SHADING_TEXTURE", depress=bool(row.enabled and debug_enabled(material)))
        row = self.layout.row()
        row.enabled = context.mode in {"OBJECT", "EDIT_MESH"} and backup.has_backup(context)
        row.operator("parallax_cubemap.restore_materials", text="Restore Materials", text_ctxt=CONTEXT, icon="LOOP_BACK")


CLASSES = (PCM_OT_assign, PCM_OT_toggle_debug, PCM_OT_restore, PCM_PT_panel)


def registered_class(cls):
    if issubclass(cls, Operator):
        prefix, name = cls.bl_idname.split(".")
        return Operator.bl_rna_get_subclass_py(prefix.upper() + "_OT_" + name, None)
    return Panel.bl_rna_get_subclass_py(cls.__name__, None)


def register():
    if bpy.app.version < (4, 5, 0):
        raise RuntimeError(tr("Parallax_CubeMap requires Blender 4.5 or newer"))
    legacy = Operator.bl_rna_get_subclass_py("PX_WINDOWS_OT_assign_material", None)
    if legacy:
        raise RuntimeError(tr("Disable PX CubeMap Windows before enabling Parallax_CubeMap"))
    # Detect another enabled legacy/extension copy before replacing any RNA.
    for cls in CLASSES:
        existing = registered_class(cls)
        if existing and existing.__module__ != __name__:
            raise RuntimeError(tr("Another copy of Parallax_CubeMap is already enabled. Disable the duplicate (legacy/extension), then enable this copy"))
    added = []
    try:
        for cls in CLASSES:
            existing = registered_class(cls)
            if existing is cls:
                continue
            if existing:  # Same module reloaded by Blender's development reload.
                bpy.utils.unregister_class(existing)
            bpy.utils.register_class(cls)
            added.append(cls)
        translations.register(__name__)
    except Exception:
        for cls in reversed(added):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    translations.unregister(__name__)
    for cls in reversed(CLASSES):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
