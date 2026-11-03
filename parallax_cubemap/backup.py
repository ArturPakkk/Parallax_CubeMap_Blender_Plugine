# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent, per-face material bindings. No topology snapshots or Undo handlers.

Native ID properties hold real datablock references, so renaming and saving work
even with the addon disabled. A private FACE INT attribute follows ordinary mesh
edits; face indices are used only within a single operator transaction.
"""
from uuid import uuid4
import bpy
import bmesh
from .translations import tr, CONTEXT

KEY = "_px_windows_material_restore"
OBJECT_KEY = "_px_windows_original_bindings"
SCHEMA = 1
MAX_SLOTS = 32767


def mesh_users(mesh):
    return [o for o in bpy.data.objects if o.type == "MESH" and o.data == mesh]


def read_state(mesh):
    raw = mesh.get(KEY)
    if raw is None:
        return None
    if not hasattr(raw, "to_dict"):
        raise ValueError(tr("Material restore data conflict: ") + mesh.name)
    state = raw.to_dict()
    name = state.get("attribute", "")
    # Inspect attributes on their owning representation in the current mode.
    if mesh.is_editmode:
        valid_attribute = isinstance(name, str) and bmesh.from_edit_mesh(mesh).faces.layers.int.get(name) is not None
    else:
        attr = mesh.attributes.get(name) if isinstance(name, str) else None
        valid_attribute = attr is not None and attr.domain == "FACE" and attr.data_type == "INT"
    if (state.get("schema") != SCHEMA or not isinstance(name, str) or not name.startswith(".px_restore_")
            or not isinstance(state.get("records"), dict) or not valid_attribute):
        raise ValueError(tr("Material restore data is damaged: ") + mesh.name)
    for key, record in state["records"].items():
        if (not key.isdigit() or not 0 < int(key) < 2**31 or not isinstance(record, dict)
                or not isinstance(record.get("slot"), int) or not 0 <= record["slot"] < MAX_SLOTS
                or not isinstance(record.get("binding_key"), str) or len(record["binding_key"]) != 32
                or not isinstance(record.get("empty"), (bool, int))
                or record.get("material") is not None and not isinstance(record["material"], bpy.types.Material)
                or record.get("debug") is not None and not isinstance(record["debug"], bpy.types.Material)):
            raise ValueError(tr("Material restore data is damaged: ") + mesh.name)
    return state


def has_backup(context):
    objects = context.objects_in_mode if context.mode == "EDIT_MESH" else context.selected_objects
    return any(o.type == "MESH" and KEY in o.data for o in objects)


def object_state(obj):
    raw = obj.get(OBJECT_KEY)
    if raw is None:
        return {}
    if not hasattr(raw, "to_dict"):
        raise ValueError(tr("Restore data conflict: ") + obj.name)
    state = raw.to_dict()
    if any(not isinstance(binding, dict) or binding.get("link") not in {"DATA", "OBJECT"}
           or not isinstance(binding.get("empty"), (bool, int))
           or binding.get("material") is not None and not isinstance(binding["material"], bpy.types.Material)
           for binding in state.values()):
        raise ValueError(tr("Restore data conflict: ") + obj.name)
    return state


def write_object(obj, state):
    if state:
        obj[OBJECT_KEY] = state
    elif OBJECT_KEY in obj:
        del obj[OBJECT_KEY]
    obj.update_tag()


def edit_object_states(mesh, states, snapshots):
    for obj in mesh_users(mesh):
        if obj not in states:
            original = object_state(obj)
            snapshots.append((obj, original))
            states[obj] = dict(original)


def discard_bindings(mesh, before, after, states, snapshots):
    old_keys = {r["binding_key"] for r in before["records"].values()} if before else set()
    new_keys = {r["binding_key"] for r in after["records"].values()} if after else set()
    removed = old_keys - new_keys
    if removed:
        edit_object_states(mesh, states, snapshots)
        for obj in mesh_users(mesh):
            for key in removed:
                states[obj].pop(key, None)


def preflight(stages):
    for s in stages:
        if s.faces:
            read_state(s.mesh)
            for obj in mesh_users(s.mesh):
                if not obj.is_editable:
                    raise ValueError(tr("Mesh instance is read-only: ") + obj.name)
                object_state(obj)


def values(mesh, state):
    return [d.value for d in mesh.attributes[state["attribute"]].data] if state else [0]*len(mesh.polygons)


def snapshot(mesh):
    state = read_state(mesh)
    return (mesh, state, values(mesh, state))


def write_state(mesh, state, ids):
    old = mesh.get(KEY)
    old_name = old.get("attribute") if old else None
    if state is None:
        if old_name and old_name in mesh.attributes:
            mesh.attributes.remove(mesh.attributes[old_name])
        if KEY in mesh:
            del mesh[KEY]
        return
    name = state["attribute"]
    attr = mesh.attributes.get(name)
    if attr is None:
        active_name = mesh.attributes.active.name if mesh.attributes.active else None
        attr = mesh.attributes.new(name, "INT", "FACE")
        if active_name:
            mesh.attributes.active_index = list(mesh.attributes.keys()).index(active_name)
    # Attribute allocation can invalidate earlier RNA wrappers.
    mesh.attributes[name].data.foreach_set("value", ids)
    mesh[KEY] = state


def rollback(snapshots):
    for entry in reversed(snapshots):
        if len(entry) == 2:
            write_object(*entry)
        else:
            write_state(*entry)


def slot_binding(obj, index):
    if index >= len(obj.material_slots):
        return {"link": "DATA", "empty": True}
    slot = obj.material_slots[index]
    result = {"link": slot.link, "empty": slot.material is None}
    if slot.material:
        result["material"] = slot.material
    return result


def capture(mesh, index, debug, states, snapshots):
    material = mesh.materials[index] if index < len(mesh.materials) else None
    key = uuid4().hex
    result = {"slot": index, "empty": material is None, "debug": debug, "binding_key": key}
    if material:
        result["material"] = material
    edit_object_states(mesh, states, snapshots)
    for obj in mesh_users(mesh):
        states[obj][key] = slot_binding(obj, index)
    return result


def current_debug(mesh, index, record, users=None):
    debug = record.get("debug")
    return (debug is not None and index < len(mesh.materials) and mesh.materials[index] == debug
            and all(o.material_slots[index].material == debug for o in (mesh_users(mesh) if users is None else users)))


def prune(state, ids):
    used = {str(i) for i in ids if i > 0}
    state["records"] = {k: v for k, v in state["records"].items() if k in used}
    return state if state["records"] else None


def remember(stages, material):
    """Prepare all backups before touching any mesh; return rollback snapshots."""
    plans, snapshots, unknown, object_states = [], [], 0, {}
    for s in stages:
        if not s.faces:
            continue
        mesh, state, ids = snapshot(s.mesh)
        snapshots.append((mesh, state, list(ids)))
        state = ({"schema": SCHEMA, "attribute": ".px_restore_" + uuid4().hex, "records": {}}
                 if state is None else {**state, "records": dict(state["records"])})
        records = state["records"]
        captured, debug_cache = {}, {}
        users = mesh_users(mesh)
        def still_debug(index, candidate):
            key = (index, candidate.get("debug"))
            if key not in debug_cache:
                debug_cache[key] = current_debug(mesh, index, candidate, users)
            return debug_cache[key]
        for face in s.faces:
            previous = records.get(str(ids[face.index]))
            if previous and still_debug(face.material_index, previous):
                record = {**previous, "debug": material}
            elif still_debug(face.material_index, {"debug": material}):
                # A pre-1.3 assignment has no recoverable original binding.
                unknown += 1
                continue
            else:
                if face.material_index not in captured:
                    captured[face.material_index] = capture(mesh, face.material_index, material, object_states, snapshots)
                record = captured[face.material_index]
            found = next((int(k) for k, v in records.items() if v == record), None)
            if found is None:
                found = max((int(k) for k in records), default=0) + 1
                records[str(found)] = record
            ids[face.index] = found
        prior = read_state(mesh)
        state = prune(state, ids)
        discard_bindings(mesh, prior, state, object_states, snapshots)
        plans.append((mesh, state, ids))
    try:
        for obj, state in object_states.items():
            write_object(obj, state)
        for mesh, state, ids in plans:
            write_state(mesh, state, ids)
    except Exception:
        rollback(snapshots)
        raise
    return snapshots, unknown


def original_bindings(mesh, record):
    if not record.get("empty") and record.get("material") is None:
        return None  # Material explicitly deleted, never match by its old name.
    result = []
    for obj in mesh_users(mesh):
        saved = object_state(obj).get(record["binding_key"])
        if saved is None:
            # New instances inherit the still-existing original slot, including
            # Object overrides. If that slot is gone, only DATA is knowable.
            index = record["slot"]
            if index < len(mesh.materials) and mesh.materials[index] == record.get("material"):
                saved = slot_binding(obj, index)
            else:
                saved = {"link": "DATA", "empty": record.get("empty"),
                         "material": record.get("material")}
        if saved["link"] == "OBJECT" and not saved.get("empty") and saved.get("material") is None:
            return None
        result.append((obj, saved["link"], saved.get("material")))
    return result


def matching_slot(mesh, material, bindings, preferred):
    indices = list(range(len(mesh.materials)))
    if preferred in indices:
        indices.remove(preferred)
        indices.insert(0, preferred)
    for i in indices:
        if mesh.materials[i] != material:
            continue
        if all(o.material_slots[i].link == link
               and o.material_slots[i].material == (mat if link == "OBJECT" else material)
               for o, link, mat in bindings):
            return i
    return None


def restore_plans(stages):
    plans, skipped, missing = [], 0, 0
    for s in stages:
        state = read_state(s.mesh)
        if not state:
            continue
        if s.edit:
            layer = s.bm.faces.layers.int.get(state["attribute"])
            ids = {f.index: f[layer] for f in s.faces}
        else:
            all_ids = values(s.mesh, state)
            ids = {f.index: all_ids[f.index] for f in s.faces}
        by_record, debug_cache, unavailable = {}, {}, set()
        users = mesh_users(s.mesh)
        for face in s.faces:
            record_id = str(ids[face.index])
            record = state["records"].get(record_id)
            if not record:
                continue
            key = (face.material_index, record.get("debug"))
            if key not in debug_cache:
                debug_cache[key] = current_debug(s.mesh, face.material_index, record, users)
            if not debug_cache[key]:
                skipped += 1
                continue
            if record_id in unavailable:
                missing += 1
                continue
            if record_id not in by_record:
                bindings = original_bindings(s.mesh, record)
                if bindings is None:
                    unavailable.add(record_id)
                    missing += 1
                    continue
                slot = matching_slot(s.mesh, record.get("material"), bindings, record["slot"])
                by_record[record_id] = [record, bindings, slot, []]
            by_record[record_id][3].append(face.index)
        additions = sum(item[2] is None for item in by_record.values())
        if len(s.mesh.materials) + additions > MAX_SLOTS:
            raise ValueError(tr("Not enough material slots for restoration: ") + s.mesh.name)
        if by_record and any(not o.is_editable for o in mesh_users(s.mesh)):
            raise ValueError(tr("Mesh instance is read-only: ") + s.mesh.name)
        if by_record:
            plans.append((s, state, list(by_record.values())))
    return plans, skipped, missing



def slot_snapshot(mesh):
    return (list(mesh.materials),
            [(obj, [slot_binding(obj, i) for i in range(len(mesh.materials))],
              obj.active_material_index) for obj in mesh_users(mesh)],
            [p.material_index for p in mesh.polygons])


def apply_slot_snapshot(mesh, materials, users, indices):
    # Rebuild only slot bindings, never geometry. Explicitly restore Object
    # overrides: IDMaterials.pop alone does not reliably shift them in 4.5.
    while len(mesh.materials) > len(materials):
        mesh.materials.pop(index=len(mesh.materials)-1)
    if not materials:
        mesh.materials.clear()
    while len(mesh.materials) < len(materials):
        mesh.materials.append(None)
    for i, material in enumerate(materials):
        mesh.materials[i] = material
    for obj, bindings, active in users:
        for i, binding in enumerate(bindings):
            obj.material_slots[i].link = binding["link"]
            if binding["link"] == "OBJECT":
                obj.material_slots[i].material = binding.get("material")
        obj.active_material_index = min(active, max(0, len(materials)-1))
        obj.update_tag()
    for polygon, index in zip(mesh.polygons, indices):
        polygon.material_index = index
    mesh.update()


def remove_unused_debug_slots(mesh, debug_materials):
    materials, users, indices = slot_snapshot(mesh)
    used = set(indices)
    remove = {i for i, material in enumerate(materials)
              if material is not None and material in debug_materials and i not in used
              and all(bindings[i].get("material") == material for _, bindings, _ in users)}
    if not remove:
        return
    keep = [i for i in range(len(materials)) if i not in remove]
    remap = {old: new for new, old in enumerate(keep)}
    # Descending removal avoids index drift. Keep every unrelated binding and
    # the material datablock itself, which can still be used by other meshes.
    for i in sorted(remove, reverse=True):
        mesh.materials.pop(index=i)
    adjusted = [(obj, [bindings[i] for i in keep],
                 remap.get(active, min(active, max(0, len(keep)-1))))
                for obj, bindings, active in users]
    apply_slot_snapshot(mesh, [materials[i] for i in keep], adjusted,
                        [remap.get(i, i) for i in indices])
    if KEY in mesh:
        for record in mesh[KEY]["records"].values():
            record["slot"] = remap.get(record["slot"], record["slot"])

def restore(stages):
    plans, skipped, missing = restore_plans(stages)
    snapshots, changes, count, object_states = [], [], 0, {}
    try:
        for s, state, groups in plans:
            mesh = s.mesh
            snapshots.append(snapshot(mesh))
            changes.append((mesh, slot_snapshot(mesh),
                            {r.get("debug") for r in state["records"].values()}))
            ids = values(mesh, state)
            first_slot = None
            for record, bindings, slot, faces in groups:
                if slot is None:
                    # Another group may already have recreated the same binding.
                    slot = matching_slot(mesh, record.get("material"), bindings, record["slot"])
                if slot is None:
                    slot = len(mesh.materials)
                    mesh.materials.append(record.get("material"))
                    for obj, link, mat in bindings:
                        obj.material_slots[slot].link = link
                        if link == "OBJECT":
                            obj.material_slots[slot].material = mat
                if first_slot is None:
                    first_slot = slot
                for i in faces:
                    mesh.polygons[i].material_index = slot
                    ids[i] = 0
                    count += 1
            for obj in s.objects:
                obj.active_material_index = first_slot
            before = read_state(mesh)
            state = prune(state, ids)
            discard_bindings(mesh, before, state, object_states, snapshots)
            write_state(mesh, state, ids)
            mesh.update()
        for obj, state in object_states.items():
            write_object(obj, state)
        for mesh, _, debug_materials in changes:
            remove_unused_debug_slots(mesh, debug_materials)
    except Exception:
        for mesh, slots, _ in reversed(changes):
            apply_slot_snapshot(mesh, *slots)
        rollback(snapshots)
        raise
    return count, skipped, missing
