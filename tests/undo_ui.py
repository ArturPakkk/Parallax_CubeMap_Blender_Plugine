# SPDX-License-Identifier: GPL-3.0-or-later
"""Run in a separate hidden Blender UI process, not -b, for real undo history."""
import bpy
import bmesh
import json
import sys
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, PROFILES, prepare_verification
prepare_verification()
OUT = REPORTS
import parallax_cubemap as addon
from parallax_cubemap.shader import debug_enabled, MATERIAL_NAME
addon.register()
bpy.context.preferences.edit.use_global_undo=True
bpy.context.preferences.edit.undo_steps=64
bpy.context.preferences.filepaths.temporary_directory=str(PROFILES/"undo"/"temp")
bpy.context.preferences.view.use_save_prompt=False
checks=[]
stage=0
baseline=None

def obj():
    return bpy.data.objects["UndoWindow"]

def mat():
    return bpy.data.materials.get(MATERIAL_NAME)

def check(value,label):
    if not value: raise AssertionError(label)
    checks.append(label)
    print("PASS:",label,flush=True)

def geometry():
    o=obj()
    if o.mode=="EDIT":
        bm=bmesh.from_edit_mesh(o.data)
        return [tuple(v.co) for v in bm.verts]
    return [tuple(v.co) for v in o.data.vertices]

def face_materials():
    o=obj()
    faces=bmesh.from_edit_mesh(o.data).faces if o.mode=="EDIT" else o.data.polygons
    return [f.material_index for f in faces]

def call(path,*args,**kwargs):
    area=next(a for a in bpy.context.window.screen.areas if a.type=="VIEW_3D")
    region=next(r for r in area.regions if r.type=="WINDOW")
    with bpy.context.temp_override(area=area,region=region):
        namespace,name=path.split(".")
        return getattr(getattr(bpy.ops,namespace),name)(*args,**kwargs)

def setup():
    global baseline
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh=bpy.data.meshes.new("ModelerMesh")
    mesh.from_pydata([(-1,-1,.1),(1,-1,0),(1,1,0),(-1,1,0)],[],[(0,1,2),(0,2,3)])
    o=bpy.data.objects.new("UndoWindow",mesh)
    bpy.context.scene.collection.objects.link(o)
    o.select_set(True)
    bpy.context.view_layer.objects.active=o
    uv=mesh.uv_layers.new(name="ModelerUV")
    coords=((0,0),(1,0),(1,1),(0,1))
    for i,loop in enumerate(mesh.loops): uv.data[i].uv=coords[loop.vertex_index]
    mesh.materials.append(bpy.data.materials.new("UserMaterial"))
    baseline=geometry()
    call("ed.undo_push",message="Modeler's existing mesh")
    check(mat() is None,"UI baseline: no managed material")

def assign():
    check(call("parallax_cubemap.assign_material","INVOKE_DEFAULT",True)=={"FINISHED"},"UI Assign completes")

def undo_assign():
    check(call("ed.undo")=={"FINISHED"},"Ctrl+Z assignment completes")
    check(obj().active_material.name=="UserMaterial" and geometry()==baseline,
          "Ctrl+Z restores original material and preserves modeller geometry")

def redo_assign():
    check(call("ed.redo")=={"FINISHED"},"Ctrl+Shift+Z assignment completes")
    check(obj().active_material.name==MATERIAL_NAME and not debug_enabled(mat()),
          "Redo restores exactly Debug_Parallax in room mode")

def toggle():
    check(call("parallax_cubemap.toggle_debug","INVOKE_DEFAULT",True)=={"FINISHED"},"UI Toggle completes")

def undo_toggle():
    check(call("ed.undo")=={"FINISHED"},"Ctrl+Z toggle completes")
    check(not debug_enabled(mat()),"Ctrl+Z restores room texture")

def redo_toggle():
    check(call("ed.redo")=={"FINISHED"},"Ctrl+Shift+Z toggle completes")
    check(debug_enabled(mat()),"Redo restores debug texture")

def repeat():
    assign()
    check(debug_enabled(mat()) and len([m for m in bpy.data.materials if m.name.startswith(MATERIAL_NAME)])==1,
          "Repeated assignment preserves debug mode without .001")

def enter_edit():
    global baseline
    call("object.mode_set",mode="EDIT")
    bm=bmesh.from_edit_mesh(obj().data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts[1].co.z=.25
    for f in bm.faces:
        f.material_index=0
        f.select_set(False)
    bm.faces[1].select_set(True)
    bmesh.update_edit_mesh(obj().data)
    baseline=geometry()
    call("ed.undo_push",message="Modeler's unsaved edit")

def edit_undo_toggle():
    check(call("ed.undo")=={"FINISHED"},"Edit Mode Ctrl+Z toggle completes")
    print("EDIT_UNDO_STATE",obj().mode,geometry()==baseline,debug_enabled(mat()),face_materials(),flush=True)
    bpy.context.window_manager.print_undo_steps()
    check(obj().mode=="EDIT" and geometry()==baseline and debug_enabled(mat()),
          "Edit Mode undo restores toggle without losing mesh edits or mode")

def edit_redo_toggle():
    call("ed.redo")
    check(obj().mode=="OBJECT" and geometry()==baseline and not debug_enabled(mat()),
          "Redo restores room in Object Mode without losing mesh edits")

def edit_undo_assign():
    call("ed.undo")
    check(obj().mode=="EDIT" and geometry()==baseline and face_materials()==[0,0],
          "Edit Mode undo restores selected face assignment and preserves modelling work")

def edit_redo_assign():
    call("ed.redo")
    check(obj().mode=="OBJECT" and geometry()==baseline and face_materials()==[0,1],
          "Edit Mode redo changes only selected face")

steps=[setup,assign,undo_assign,redo_assign,toggle,undo_toggle,redo_toggle,repeat,
       enter_edit,toggle,edit_undo_toggle,edit_redo_toggle,enter_edit,assign,edit_undo_assign,edit_redo_assign]

def fresh_edit_setup():
    global baseline
    call("object.mode_set",mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    if mat(): bpy.data.materials.remove(mat())
    setup()
    call("object.mode_set",mode="EDIT")
    bm=bmesh.from_edit_mesh(obj().data)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.verts[2].co.z=.33
    for f in bm.faces: f.select_set(False)
    bm.faces[1].select_set(True)
    bmesh.update_edit_mesh(obj().data)
    baseline=geometry()
    call("ed.undo_push",message="Fresh modeler's edit before material creation")

def check_fresh_assign():
    check(obj().mode=="OBJECT" and geometry()==baseline and face_materials()==[0,1],
          "First Edit Mode creation finishes in Object Mode with only selected face assigned")

def undo_fresh_assign():
    call("ed.undo")
    check(obj().mode=="EDIT" and geometry()==baseline and face_materials()==[0,0]
          and mat() is None,"First creation Ctrl+Z removes the new material and restores Edit Mode edits")

def redo_fresh_assign():
    call("ed.redo")
    check(obj().mode=="OBJECT" and geometry()==baseline and face_materials()==[0,1]
          and mat().name==MATERIAL_NAME,"First creation redo restores exact material without duplicates")

steps.extend([fresh_edit_setup,assign,check_fresh_assign,undo_fresh_assign,redo_fresh_assign])

def restore_after_edit():
    global baseline
    call("object.mode_set", mode="EDIT")
    bm=bmesh.from_edit_mesh(obj().data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts[0].co.z=.91
    for face in bm.faces: face.select_set(True)
    bmesh.update_edit_mesh(obj().data)
    baseline=geometry()
    call("ed.undo_push",message="Later modelling before material restore")
    check(call("parallax_cubemap.restore_materials","INVOKE_DEFAULT",True)=={"FINISHED"},
          "Restore materials completes independently after later modelling")
    check(obj().mode=="OBJECT" and geometry()==baseline and face_materials()==[0,0]
          and addon.backup.KEY not in obj().data and mat() not in list(obj().data.materials),
          "Restore returns originals, removes the Debug slot and consumes its backup")

def undo_restore():
    call("ed.undo")
    check(obj().mode=="EDIT" and geometry()==baseline and face_materials()==[0,1]
          and addon.backup.KEY in obj().data and mat() in list(obj().data.materials),
          "Ctrl+Z restore brings back the Debug slot, persistent backup and Edit Mode without losing edits")

def redo_restore():
    call("ed.redo")
    check(obj().mode=="OBJECT" and geometry()==baseline and face_materials()==[0,0]
          and addon.backup.KEY not in obj().data and mat() not in list(obj().data.materials),
          "Redo restore returns original materials and removes only the restored backup")

def restore_again_after_undo():
    call("ed.undo")
    check(call("parallax_cubemap.restore_materials","INVOKE_DEFAULT",True)=={"FINISHED"}
          and geometry()==baseline and face_materials()==[0,0],
          "Persistent backup remains usable after Undo without stale RNA references")

steps.extend([restore_after_edit,undo_restore,redo_restore,restore_again_after_undo])

def cycle_assign_room():
    check(call("parallax_cubemap.assign_material","INVOKE_DEFAULT",True)=={"FINISHED"}
          and not debug_enabled(mat()), "Reassign after restore starts in room mode")

def cycle_debug():
    check(call("parallax_cubemap.toggle_debug","INVOKE_DEFAULT",True)=={"FINISHED"}
          and debug_enabled(mat()), "Reported cycle switches to Debug")

def cycle_restore():
    check(call("parallax_cubemap.restore_materials","INVOKE_DEFAULT",True)=={"FINISHED"}
          and face_materials()==[0,0] and mat() not in list(obj().data.materials),
          "Reported cycle restores original materials and removes Debug slot")

def cycle_undo_reassign():
    call("ed.undo")
    check(face_materials()==[0,0] and geometry()==baseline
          and mat() not in list(obj().data.materials) and debug_enabled(mat()),
          "Undo fresh reassign restores old bindings and previous shader state")

def cycle_redo_reassign():
    call("ed.redo")
    check(face_materials()==[1,1] and geometry()==baseline
          and not debug_enabled(mat()) and addon.backup.KEY in obj().data,
          "Redo fresh reassign restores room and persistent backup without duplicates")

steps.extend([cycle_assign_room,cycle_debug,cycle_restore,cycle_assign_room,
              cycle_undo_reassign,cycle_redo_reassign])

def tick():
    global stage
    try:
        if stage<len(steps):
            print("STEP",stage,steps[stage].__name__,flush=True)
            steps[stage]()
            stage+=1
            return .35
        (OUT/"undo_verification.json").write_text(json.dumps({"success":True,"checks":checks,
            "blender":bpy.app.version_string},ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception:
        (OUT/"undo_verification.json").write_text(json.dumps({"success":False,"stage":stage,
            "error":traceback.format_exc(),"checks":checks},ensure_ascii=False,indent=2),encoding="utf-8")
        traceback.print_exc()
    bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=1.5)
