# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender integration checks for persistent material restoration."""
import bpy
import bmesh
import json
import sys
import faulthandler
faulthandler.enable()
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, SCENES, prepare_verification
prepare_verification()
OUT = REPORTS
import parallax_cubemap as addon
from parallax_cubemap import backup, mesh as mesh_module
addon.register()
checks = []

def check(ok, label):
    assert ok, label
    checks.append(label)
    print("PASS", label, flush=True)

def select(*objects):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

def fixture(name, count=3, empty=False):
    vertices, faces = [], []
    for i in range(count):
        n = len(vertices)
        vertices.extend(((i*3,0,0),(i*3+2,0,0),(i*3+2,2,0),(i*3,2,0)))
        faces.append((n,n+1,n+2,n+3))
    mesh = bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name="UserUV")
    for p in mesh.polygons:
        for i, co in zip(p.loop_indices, ((0,0),(1,0),(1,1),(0,1))):
            mesh.uv_layers["UserUV"].uv[i].vector = co
    # Use the current UV API; the deprecated MeshUVLoop.pin_uv setter can
    # corrupt a freshly-created multi-face fixture in Blender 4.5.
    # Blender 5 exposes absent pin flags lazily; create the native boolean
    # corner attribute explicitly before setting pins.
    if len(mesh.uv_layers["UserUV"].pin) == 0:
        mesh.attributes.new(".pn.UserUV", "BOOLEAN", "CORNER")
    mesh.uv_layers["UserUV"].pin.foreach_set("value", [True]*len(mesh.loops))
    if not empty:
        for i in range(count):
            mesh.materials.append(bpy.data.materials.new(name+"Material"+str(i)))
            mesh.polygons[i].material_index = i
    select(obj)
    return obj

def materials(obj):
    return [obj.material_slots[p.material_index].material
            if p.material_index < len(obj.material_slots) else None for p in obj.data.polygons]

def model(mesh):
    return ([tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons],
            [(u.name, [(tuple(d.uv),d.pin_uv) for d in u.data]) for u in mesh.uv_layers])

def assign():
    assert bpy.ops.parallax_cubemap.assign_material() == {"FINISHED"}

def restore():
    assert bpy.ops.parallax_cubemap.restore_materials() == {"FINISHED"}

def cancel(op):
    try:
        return op() == {"CANCELLED"}
    except RuntimeError:
        return True

obj = fixture("Basic")
original = materials(obj)
obj.shape_key_add(name="Basis")
obj.shape_key_add(name="UserShape").data[0].co.z = .7
before = model(obj.data)
assign()
state = backup.read_state(obj.data)
check(len(state["records"]) == 3, "Every original face material is remembered")
for i in range(10):
    assign()
    bpy.ops.parallax_cubemap.toggle_debug()
check(state == backup.read_state(obj.data), "Repeated assign/toggle preserves the first backup without growth")
check(before == model(obj.data) and obj.data.shape_keys.key_blocks["UserShape"].data[0].co.z > .69,
      "Backup does not alter UV pins, geometry or shape keys")
obj.data.vertices[0].co.z = .4
obj.data.uv_layers.active.data[0].uv.x = 1.4
obj.location.x = 7
later = bpy.data.materials.new("LaterUnrelated")
obj.data.materials.append(later)
obj.data.polygons[1].hide = True
edited = model(obj.data)
restore()
check(materials(obj) == original, "Restore returns multiple original materials including faces hidden later")
check(addon.canonical_material() not in list(obj.data.materials),
      "Full restore removes Debug from the object material slots")
check(model(obj.data) == edited and obj.location.x == 7 and later in list(obj.data.materials),
      "Restore preserves later geometry, invalid UV, transforms, shape keys and extra slots")
check(backup.KEY not in obj.data and backup.OBJECT_KEY not in obj and not any(a.name.startswith(".px_restore_") for a in obj.data.attributes),
      "Completed restore removes its own metadata and face attribute")
check(cancel(bpy.ops.parallax_cubemap.restore_materials), "Second restore with no backup is a harmless cancellation")

obj = fixture("Manual")
original = materials(obj)
assign()
manual = bpy.data.materials.new("LaterManualAssignment")
obj.data.materials.append(manual)
obj.data.polygons[1].material_index = len(obj.data.materials)-1
restore()
check(materials(obj) == [original[0], manual, original[2]], "Later manual face assignment is not overwritten")
assign()
restore()
check(materials(obj) == [original[0], manual, original[2]], "New assignment after restore captures the current materials")

obj = fixture("Partial")
original = materials(obj)
assign()
bpy.ops.object.mode_set(mode="EDIT")
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()
for f in bm.faces:
    f.select_set(False)
bm.faces[1].select_set(True)
bm.verts.ensure_lookup_table()
bm.verts[0].co.z = .83
bmesh.update_edit_mesh(obj.data)
restore()
check(obj.mode == "OBJECT" and materials(obj)[1] == original[1]
      and materials(obj)[0] == addon.canonical_material()
      and abs(obj.data.vertices[0].co.z-.83) < 1e-5,
      "Edit restore affects only selected faces and preserves unflushed mesh edits")
restore()
check(materials(obj) == original, "Partial restore retains backups for remaining faces")
check(addon.canonical_material() not in list(obj.data.materials),
      "Last partial restore removes the now-unused Debug slot")

obj = fixture("Renamed", count=1)
original = materials(obj)[0]
assign()
original.name = "OriginalRenamedLater"
debug = addon.canonical_material()
debug.name = "DebugRenamedLater"
restore()
check(materials(obj) == [original], "Original and debug material renames do not break ID-based restore")
debug.name = addon.MATERIAL_NAME

obj = fixture("Slots", count=2)
original = materials(obj)
assign()
obj.data.materials.pop(index=0)
obj.data.materials.pop(index=0)
later = bpy.data.materials.new("LaterSlot")
obj.data.materials.append(later)
restore()
check(materials(obj) == original and later in list(obj.data.materials),
      "Removed original slots are recreated without replacing later-added slots")

obj = fixture("DeletedOriginal", count=1)
original = materials(obj)[0]
old_name = original.name
assign()
bpy.data.materials.remove(original)
replacement = bpy.data.materials.new(old_name)
check(cancel(bpy.ops.parallax_cubemap.restore_materials) and materials(obj) == [addon.canonical_material()]
      and backup.KEY in obj.data, "Deleted original material is reported; same-name material is never guessed")

obj = fixture("NoMaterial", count=1, empty=True)
assign()
restore()
check(materials(obj) == [None], "Originally unassigned faces return to an empty material binding")
check(addon.canonical_material() not in list(obj.data.materials),
      "Originally empty object has no Debug slot after restore")

obj = fixture("Shared", count=1)
original = materials(obj)[0]
other = bpy.data.objects.new("SharedInstance", obj.data)
bpy.context.scene.collection.objects.link(other)
override = bpy.data.materials.new("OriginalObjectOverride")
other.material_slots[0].link = "OBJECT"
other.material_slots[0].material = override
select(obj, other)
assign()
restore()
check(materials(obj) == [original] and materials(other) == [override]
      and other.material_slots[0].link == "OBJECT", "Shared Mesh restores distinct DATA and OBJECT bindings")
assign()
obj.active_material_index = 0
bpy.ops.object.material_slot_remove()
restore()
check(materials(obj) == [original] and materials(other) == [override],
      "Deleted shared slot is recreated with all original Object overrides")

select(obj, other)
assign()
slot = obj.data.polygons[0].material_index
other.material_slots[slot].link = "OBJECT"
other.material_slots[slot].material = later
select(obj)
check(cancel(bpy.ops.parallax_cubemap.restore_materials) and materials(other) == [later],
      "Later override on an unselected shared instance is preserved")

obj = fixture("Copied", count=1)
original = materials(obj)
assign()
copy = obj.copy()
copy.data = obj.data.copy()
bpy.context.scene.collection.objects.link(copy)
select(copy)
restore()
check(materials(copy) == original and materials(obj) == [addon.canonical_material()],
      "Single-user copied mesh can restore without changing its source")

obj = fixture("Topology", count=2)
original = materials(obj)
assign()
state = backup.read_state(obj.data)
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=2, use_grid_fill=True)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES")
bm.faces.sort(key=lambda f: -f.calc_center_median().x)
bm.to_mesh(obj.data)
bm.free()
state = backup.read_state(obj.data)
ids = backup.values(obj.data, state)
check(len(obj.data.polygons) > 2 and all(i > 0 for i in ids),
      "Subdivision and face deletion preserve per-face backup provenance")
expected = [state["records"][str(i)].get("material") for i in ids]
edited = model(obj.data)
restore()
check(materials(obj) == expected and model(obj.data) == edited,
      "Restore follows subdivided/reordered faces without rolling topology back")

# Corrupt metadata must fail before overwriting a foreign attribute.
obj = fixture("Corrupt", count=1)
obj.data[backup.KEY] = {"schema": 98, "attribute": "UserAttribute", "records": {}}
check(cancel(bpy.ops.parallax_cubemap.assign_material) and materials(obj)[0].name.startswith("CorruptMaterial"),
      "Unknown backup schema is rejected before assignment")

# Assignment rollback must include persistent backup, not only material indices.
a, b = fixture("AtomicA",1), fixture("AtomicB",1)
select(a,b)
before = [materials(o) for o in (a,b)]
old = mesh_module.set_faces
calls = 0
def fail_second(stage, indices):
    global calls
    calls += 1
    if calls == 2:
        raise RuntimeError("Injected assignment failure")
    return old(stage, indices)
mesh_module.set_faces = fail_second
try:
    cancelled = cancel(bpy.ops.parallax_cubemap.assign_material)
finally:
    mesh_module.set_faces = old
check(cancelled and before == [materials(o) for o in (a,b)]
      and all(backup.KEY not in o.data and backup.OBJECT_KEY not in o for o in (a,b)), "Assignment failure rolls back backup metadata on every mesh")

assign()
old = backup.write_state
calls = 0
before_states = [backup.read_state(o.data) for o in (a,b)]
before_slots = [list(o.data.materials) for o in (a,b)]
def fail_restore(mesh, state, ids):
    global calls
    calls += 1
    if calls == 2:
        raise RuntimeError("Injected restore failure")
    return old(mesh,state,ids)
backup.write_state = fail_restore
try:
    cancelled = cancel(bpy.ops.parallax_cubemap.restore_materials)
finally:
    backup.write_state = old
check(cancelled and all(materials(o)==[addon.canonical_material()] for o in (a,b))
      and before_states == [backup.read_state(o.data) for o in (a,b)]
      and before_slots == [list(o.data.materials) for o in (a,b)],
      "Restore failure rolls back bindings, slots and metadata atomically")

obj = fixture("NewCanonical", count=2)
original = materials(obj)
assign()
first_debug = addon.canonical_material()
first_debug.name = "RenamedDebugThenReassigned"
assign()
restore()
check(materials(obj) == original, "Assigning a new canonical debug after renaming preserves the original backup")
bpy.data.materials.remove(addon.canonical_material())
first_debug.name = addon.MATERIAL_NAME

obj = fixture("DeletedObject", count=1)
assign()
obj_name = obj.name
mesh_name = obj.data.name
check(obj.users == 1, "Backup stores no Object references and does not add object users")
bpy.ops.object.delete(use_global=False)
check(obj_name not in bpy.data.objects, "Deleting a debug-assigned object removes it normally")

obj = fixture("OldVersion", count=1)
obj.data.materials.append(addon.canonical_material())
obj.data.polygons[0].material_index = 1
assign()
check(backup.KEY not in obj.data and cancel(bpy.ops.parallax_cubemap.restore_materials),
      "Assignments predating backups are reported without guessing originals")

# Removing a middle slot must preserve later Object overrides on every user.
obj = fixture("MiddleSlot", count=2)
original = materials(obj)
other = obj.copy()
other.name = "MiddleSlotOther"
bpy.context.scene.collection.objects.link(other)
select(obj, other)
assign()
debug = addon.canonical_material()
tail = bpy.data.materials.new("TailData")
override = bpy.data.materials.new("TailOverride")
obj.data.materials.append(tail)
last = len(obj.data.materials)-1
other.material_slots[last].link = "OBJECT"
other.material_slots[last].material = override
obj.data.polygons[1].material_index = last
other.active_material_index = last
select(obj)
restore()
check(list(obj.data.materials) == [*original, tail]
      and materials(obj) == [original[0], tail] and materials(other) == [original[0], override]
      and other.material_slots[2].link == "OBJECT" and other.active_material_index == 2,
      "Middle-slot removal preserves later face assignments, Object overrides and active slot on an unselected instance")
keeper = fixture("KeepDebug", count=1)
assign()
select(obj)
check(keeper.active_material == debug and addon.canonical_material() == debug,
      "Removing a slot does not delete the shared Debug material datablock")

a, b = fixture("CleanupAtomicA",1), fixture("CleanupAtomicB",1)
select(a,b)
assign()
before_slots = [backup.slot_snapshot(o.data) for o in (a,b)]
before_states = [backup.read_state(o.data) for o in (a,b)]
old_cleanup = backup.remove_unused_debug_slots
calls = 0
def fail_cleanup(mesh, debug_materials):
    global calls
    calls += 1
    old_cleanup(mesh, debug_materials)
    if calls == 2:
        raise RuntimeError("Injected failure after Debug slots were removed")
backup.remove_unused_debug_slots = fail_cleanup
try:
    cancelled = cancel(bpy.ops.parallax_cubemap.restore_materials)
finally:
    backup.remove_unused_debug_slots = old_cleanup
check(cancelled and before_slots == [backup.slot_snapshot(o.data) for o in (a,b)]
      and before_states == [backup.read_state(o.data) for o in (a,b)],
      "Failure after slot deletion restores original slot order, face indices, Object overrides and backup on all meshes")

obj = fixture("PortableRestore", count=2)
original = materials(obj)
assign()
# Delete every original slot. ID property references must keep materials alive.
obj.data.materials.pop(index=0)
obj.data.materials.pop(index=0)
check(all(m.users > 0 for m in original), "Persistent references retain original materials without fake-user changes")
obj.data.vertices[0].co.z = .654
addon.unregister()
bpy.ops.wm.save_as_mainfile(filepath=str(SCENES/"Restore_Persistence_Test.blend"))
(OUT/"restore_verification.json").write_text(json.dumps({"success":True,"version":"2.0.0",
    "blender":bpy.app.version_string,"checks":checks},ensure_ascii=False,indent=2),encoding="utf-8")
print("RESTORE_CHECKS_PASSED", len(checks), flush=True)
