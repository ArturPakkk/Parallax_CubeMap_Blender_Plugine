# SPDX-License-Identifier: GPL-3.0-or-later
"""Conflict and non-destructive behavior checks for v1.2."""
import bpy
import json
import sys
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, SCENES, prepare_verification
prepare_verification()
OUT = REPORTS
import parallax_cubemap as addon
from parallax_cubemap.shader import debug_enabled, switch_node, MATERIAL_NAME, material_node
addon.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add()
a=bpy.context.object
a.name="Modeler_A"
checks=[]
def check(value,label):
    assert value,label
    checks.append(label)
    print("PASS",label,flush=True)
def select(*objects):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
def counts():
    return tuple(len(x) for x in (bpy.data.materials,bpy.data.node_groups,bpy.data.images))
def uv_data(o):
    # Use actual UV and boolean attributes; Blender 5 removed the deprecated
    # MeshUVLoop.select/select_edge API used by the original test harness.
    result=[]
    for uv in o.data.uv_layers:
        names={prefix+uv.name for prefix in (".pn.",".vs.",".es.")}
        flags={attr.name: [d.value for d in attr.data] for attr in o.data.attributes
               if attr.name in names and attr.data_type=="BOOLEAN"}
        result.append((uv.name,uv.active_render,[tuple(d.vector) for d in uv.uv],flags))
    return result
def cancel(op,label):
    try:
        result=op()
        check(result=={"CANCELLED"},label)
    except RuntimeError:
        check(True,label)

before=uv_data(a)
bpy.ops.parallax_cubemap.assign_material()
material=addon.canonical_material()
check(material.name==MATERIAL_NAME and not debug_enabled(material),"New material defaults to full room")
initial=counts()
for i in range(30):
    bpy.ops.parallax_cubemap.toggle_debug()
    bpy.ops.parallax_cubemap.assign_material()
check(counts()==initial and a.active_material==material and uv_data(a)==before,
      "30 assign/toggle cycles allocate no material, image, group or UV duplicates")
check(len([m for m in bpy.data.materials if m.name.startswith(MATERIAL_NAME)])==1,
      "No Debug_Parallax.001 exists")
# Both users share mesh data; one has an object-specific material override.
b=bpy.data.objects.new("Modeler_B",a.data)
bpy.context.scene.collection.objects.link(b)
foreign=bpy.data.materials.new("UserOverride")
b.material_slots[0].link="OBJECT"
b.material_slots[0].material=foreign
select(a,b)
bpy.ops.parallax_cubemap.assign_material()
check(a.active_material==material and b.active_material==material,
      "Shared mesh + Object material override assigns the intended material to both objects")
check(b.material_slots[0].link=="OBJECT" and b.material_slots[0].material==foreign,
      "Existing Object override is preserved")
slots=len(a.data.materials)
bpy.ops.parallax_cubemap.assign_material()
check(len(a.data.materials)==slots,"Mixed Object/Data slots are reused on repeat")
# Named foreign material is never overwritten or auto-suffixed.
material.name="ManagedBackup"
collision=bpy.data.materials.new(MATERIAL_NAME)
collision.diffuse_color=(.2,.4,.6,1)
foreign_color=tuple(collision.diffuse_color)
state=(counts(),uv_data(a),[m.name if m else None for m in a.data.materials])
cancel(lambda:bpy.ops.parallax_cubemap.assign_material(),"Foreign exact-name conflict cancels safely")
check(state==(counts(),uv_data(a),[m.name if m else None for m in a.data.materials])
      and tuple(collision.diffuse_color)==foreign_color,
      "Name collision changes no assignments, UVs or datablock counts")
cancel(lambda:bpy.ops.parallax_cubemap.toggle_debug(),"Foreign material cannot be toggled")
bpy.data.materials.remove(collision)
material.name=MATERIAL_NAME
# Validate all selected UVs before any material mutation.
bpy.ops.mesh.primitive_plane_add(location=(3,0,0))
bad=bpy.context.object
bad.data.uv_layers.active.data[0].uv.x=1.2
select(a,bad)
state=(counts(),uv_data(a),uv_data(bad),len(bad.data.materials))
cancel(lambda:bpy.ops.parallax_cubemap.assign_material(),"One invalid UV cancels the entire multi-object assignment")
check(state==(counts(),uv_data(a),uv_data(bad),len(bad.data.materials)),
      "Invalid UV failure is atomic")
# Inject a commit failure after the first mesh to exercise rollback.
import parallax_cubemap.mesh as mesh_module
bad.data.uv_layers.active.data[0].uv.x=0
user=bpy.data.materials.new("ExistingUserSurface")
bad.data.materials.append(user)
select(a,bad)
stages=mesh_module.prepare_selection(bpy.context)
old_set=mesh_module.set_faces
calls=0
def fail_second(stage,indices):
    global calls
    calls+=1
    if calls==2: raise RuntimeError("Injected assignment failure")
    return old_set(stage,indices)
old_slots=[list(o.data.materials) for o in (a,bad)]
old_faces=[[p.material_index for p in o.data.polygons] for o in (a,bad)]
mesh_module.set_faces=fail_second
try:
    try: mesh_module.commit_selection(stages,material)
    except RuntimeError: pass
finally:
    mesh_module.set_faces=old_set
    mesh_module.release_selection(stages)
check(old_slots==[list(o.data.materials) for o in (a,bad)]
      and old_faces==[[p.material_index for p in o.data.polygons] for o in (a,bad)],
      "Unexpected mid-assignment failure rolls back slots and face assignments")
# Missing bundled file is checked before any data is imported.
material.name="ManagedBackup"
old_path=addon.atlas_path
def missing(name=addon.ASSETS[0]):
    if name==addon.ASSETS[1]: raise ValueError("Missing debug fixture")
    return old_path(name)
addon.atlas_path=missing
state=counts()
try:
    try: addon.get_material()
    except ValueError: pass
finally:
    addon.atlas_path=old_path
check(state==counts(),"Missing debug asset creates no partial material or loaded images")
material.name=MATERIAL_NAME
# Read-only linked meshes and same-name library materials stay untouched.
library_path=SCENES/"conflict_library.blend"
bpy.data.libraries.write(str(library_path),{bad,material})
with bpy.data.libraries.load(str(library_path),link=True) as (src,dst):
    dst.objects=[bad.name]
    dst.materials=[MATERIAL_NAME]
linked=dst.objects[0]
linked_material=dst.materials[0]
bpy.context.scene.collection.objects.link(linked)
bpy.context.view_layer.update()
select(linked)
cancel(lambda:bpy.ops.parallax_cubemap.assign_material(),"Read-only linked mesh is rejected")
check(addon.canonical_material()==material,"Local material wins over a same-name linked-library material")
linked_mode=debug_enabled(linked_material)
select(a)
bpy.ops.parallax_cubemap.toggle_debug()
check(debug_enabled(linked_material)==linked_mode,"Toggle never changes same-name linked material")
# A user-rewired graph is treated as a conflict, never silently overwritten.
switch=switch_node(material)
old_link=switch.inputs[1].links[0]
socket=old_link.from_socket
material.node_tree.links.remove(old_link)
state=counts()
cancel(lambda:bpy.ops.parallax_cubemap.toggle_debug(),"Rewired material is rejected without overwriting user graph")
check(counts()==state and not switch.inputs[1].is_linked,"Damaged-graph conflict creates no replacement IDs")
material.node_tree.links.new(socket,switch.inputs[1])

# Another enabled extension/legacy copy cannot replace the registered operators.
spec=importlib.util.spec_from_file_location("px_conflict_copy",ROOT/"parallax_cubemap"/"__init__.py",
                                          submodule_search_locations=[str(ROOT/"parallax_cubemap")])
copy=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=copy
spec.loader.exec_module(copy)
try:
    copy.register()
    raise AssertionError("Second copy should be rejected")
except RuntimeError:
    pass
check(addon.PCM_OT_assign.is_registered and addon.PCM_OT_toggle_debug.is_registered
      and not copy.PCM_OT_assign.is_registered,
      "A second enabled addon copy is rejected without disabling the first")
addon.register()
check(addon.PCM_OT_assign.is_registered,"Register twice is harmless")
addon.unregister()
addon.unregister()
addon.register()
check(addon.PCM_OT_assign.is_registered and not hasattr(bpy.types.Scene,"px_windows"),
      "Disable/re-enable leaves no duplicate classes, handlers or old settings")
(OUT/"conflict_verification.json").write_text(json.dumps({"version":"2.0.0","checks":checks,
    "count":len(checks),"success":True},ensure_ascii=False,indent=2),encoding="utf-8")
print("CONFLICT_CHECKS_PASSED",len(checks),flush=True)
