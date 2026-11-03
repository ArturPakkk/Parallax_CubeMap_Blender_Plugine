# SPDX-License-Identifier: GPL-3.0-or-later
"""Render and operator regressions for direct, signed UV mapping in Blender."""
import json
import sys
from pathlib import Path
import numpy as np
import bpy
import bmesh
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, prepare_verification, render_path
prepare_verification()
OUT = REPORTS
OUT.mkdir(parents=True, exist_ok=True)
import parallax_cubemap as addon
from parallax_cubemap.shader import create_material, material_node
from parallax_cubemap.mesh import prepare_selection, commit_selection, release_selection
addon.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.engine="BLENDER_EEVEE_NEXT"
scene.render.resolution_x=96
scene.render.resolution_y=96
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.image_settings.color_mode="RGBA"
scene.view_settings.view_transform="Standard"
scene.view_settings.look="None"
scene.world.color=(0,0,0)
results=[]
def check(value,name):
    assert value,name
    results.append(name)
    print("PASS:",name,flush=True)
def select(obj):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
def plane(name="Window",triangles=False):
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],[],
                    [(0,1,2),(0,2,3)] if triangles else [(0,1,2,3)])
    obj=bpy.data.objects.new(name,mesh)
    scene.collection.objects.link(obj)
    select(obj)
    return obj
base=((0,0),(1,0),(1,1),(0,1))
def set_uv(obj,transform=lambda u,v:(u,v),name="Artist_UV"):
    layer=obj.data.uv_layers.get(name) or obj.data.uv_layers.new(name=name)
    for poly in obj.data.polygons:
        for index in poly.loop_indices:
            u,v=base[obj.data.loops[index].vertex_index]
            layer.data[index].uv=transform(u,v)
    obj.data.uv_layers.active=layer
    obj.data.update()
    bpy.context.view_layer.update()
    return layer
def snapshot(obj):
    return {uv.name:[tuple(d.uv) for d in uv.data] for uv in obj.data.uv_layers}
def assign(mat):
    stages=prepare_selection(bpy.context)
    try:
        return commit_selection(stages,mat)
    finally:
        release_selection(stages)
def camera_at(location):
    camera.location=location
    camera.rotation_euler=(-camera.location).to_track_quat("-Z","Y").to_euler()
    bpy.context.view_layer.update()
bpy.ops.object.camera_add(location=(0,0,4))
camera=bpy.context.object
camera.data.lens=70
scene.camera=camera
obj=plane(triangles=True)
uv=set_uv(obj)
original=snapshot(obj)
im=bpy.data.images.new("DiagnosticAtlas",width=192,height=192,alpha=True,float_buffer=True)
pixels=np.zeros((192,192,4),dtype=np.float32)
for (col,row),color in {
    (1,1):(.25,.25,.25,1), (0,1):(1,0,0,1), (2,1):(0,1,0,1),
    (1,0):(0,0,1,1), (1,2):(1,1,0,1),
}.items():
    pixels[row*64:(row+1)*64,col*64:(col+1)*64]=color
im.pixels.foreach_set(pixels.ravel())
im.update()
mat=create_material(im,"Diagnostic Parallax")
assign(mat)
check(snapshot(obj)==original,"Assignment preserves all original UV values and layer names")
check(len(obj.modifiers)==0,"No geometry modifier or cached UV attributes added")
n=material_node(mat)
check(len(n.inputs)==0,"Material group exposes no settings")
# Isolate the computed interior from fixed exposure and reflective glass.
em=mat.node_tree.nodes.new("ShaderNodeEmission")
mat.node_tree.links.new(n.outputs["Interior Color"],em.inputs["Color"])
out=next(n for n in mat.node_tree.nodes if n.type=="OUTPUT_MATERIAL")
mat.node_tree.links.new(em.outputs[0],out.inputs["Surface"])
def render(name):
    path=render_path("UV", "uv_test_"+name+".png")
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    image=bpy.data.images.load(str(path),check_existing=False)
    a=np.array(image.pixels[:]).reshape(96,96,4)
    c=a[46:50,46:50,:3]
    c=np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4).mean(axis=(0,1))
    bpy.data.images.remove(image)
    return c
cases=[
    ("base_left",lambda u,v:(u,v),(4,0,3),(1,0,0)),
    ("base_right",lambda u,v:(u,v),(-4,0,3),(0,1,0)),
    ("base_floor",lambda u,v:(u,v),(0,4,3),(0,0,1)),
    ("base_ceiling",lambda u,v:(u,v),(0,-4,3),(1,1,0)),
    ("mirror_u",lambda u,v:(1-u,v),(4,0,3),(0,1,0)),
    ("mirror_v",lambda u,v:(u,1-v),(0,4,3),(1,1,0)),
    ("upside_down",lambda u,v:(1-u,1-v),(4,0,3),(0,1,0)),
    ("upside_down_ceiling",lambda u,v:(1-u,1-v),(0,4,3),(1,1,0)),
    ("rotate_90",lambda u,v:(1-v,u),(4,0,3),(0,0,1)),
    ("rotate_90_right",lambda u,v:(1-v,u),(0,4,3),(0,1,0)),
]
for name,transform,position,expected in cases:
    set_uv(obj,transform)
    camera_at(position)
    actual=render(name)
    check(np.max(abs(actual-expected))<.04,
          "EEVEE live UV "+name+" -> "+str(actual.tolist()))
# Verify both signs with Cycles' separate normal-map implementation.
scene.render.engine="CYCLES"
scene.cycles.samples=8
scene.cycles.device="CPU"
for name,transform,position,expected in (cases[4],cases[5],cases[8]):
    set_uv(obj,transform)
    camera_at(position)
    actual=render("cycles_"+name)
    check(np.max(abs(actual-expected))<.04,"Cycles live UV "+name+" -> "+str(actual.tolist()))
scene.render.engine="BLENDER_EEVEE_NEXT"
# Direct crop, translation and scale: never fit the island back to 0..1.
for y in range(64):
    for x in range(64):
        pixels[64+y,64+x]=((x+.5)/64,(y+.5)/64,0,1)
im.pixels.foreach_set(pixels.ravel())
im.update()
camera.data.type="ORTHO"
camera.data.ortho_scale=1.5
camera_at((0,0,4))
set_uv(obj,lambda u,v:(.1+.3*u,.3+.5*v))
actual=render("partial_tile_crop")
check(np.max(abs(actual-(.25,.55,0)))<.02,
      "Partial rectangular island samples exact UV coordinates, without normalization")
before=snapshot(obj)
assign(mat)
check(snapshot(obj)==before,"Rectangular partial-tile UV is not stretched, moved or repacked")
set_uv(obj,lambda u,v:(.55+.3*u,.1+.4*v))
actual=render("moved_crop")
check(np.max(abs(actual-(.7,.3,0)))<.02,"Moving UV changes sampled room region immediately")
# Second active UV map chosen without touching the original one.
set_uv(obj,lambda u,v:(.15+.3*u,.5+.4*v),name="Another_Artist_Map").active_render=True
before=snapshot(obj)
assign(mat)
actual=render("active_map")
check(np.max(abs(actual-(.3,.7,0)))<.02 and snapshot(obj)==before,
      "Assignment uses existing render UV map and preserves other maps")
# Actual button, reuse and all-selection preflight.
check(bpy.ops.parallax_cubemap.assign_material()=={"FINISHED"},"Single button assigns bundled EXR material")
real=obj.active_material
check(real.name=="Debug_Parallax","Material is named exactly Debug_Parallax")
count=len(bpy.data.materials)
slots=len(obj.data.materials)
check(bpy.ops.parallax_cubemap.assign_material()=={"FINISHED"} and obj.active_material==real
      and len(bpy.data.materials)==count and len(obj.data.materials)==slots,
      "Repeated assignment reuses Debug_Parallax without .001 duplicates")
check(all(t.image.packed_file for t in material_node(real).node_tree.nodes if t.type=="TEX_IMAGE"),
      "Bundled EXR is packed into the material's scene")
bad=plane("BadUV")
set_uv(bad,lambda u,v:(u+1,v))
obj.select_set(True)
before=(snapshot(obj),snapshot(bad),len(obj.data.materials),len(bad.data.materials))
try:
    stages=prepare_selection(bpy.context)
    release_selection(stages)
    raise AssertionError("Out-of-tile UV should fail")
except ValueError:
    pass
check(before==(snapshot(obj),snapshot(bad),len(obj.data.materials),len(bad.data.materials)),
      "UV outside 0-1 rejects the whole selection without changes")
select(bad)
# Existing material also must not repeat after later UV edits out of range.
bad.data.materials.append(mat)
camera_at((0,0,4))
obj.hide_render=True
actual=render("outside_no_repeat")
obj.hide_render=False
check(max(actual)<.01,"Out-of-tile UV does not repeat the room after later edits")
bpy.data.objects.remove(bad,do_unlink=True)
missing=plane("MissingUV")
try:
    stages=prepare_selection(bpy.context)
    release_selection(stages)
    raise AssertionError("Missing UV should fail")
except ValueError:
    pass
check(len(missing.data.uv_layers)==0 and len(missing.data.materials)==0,
      "Missing UV is rejected instead of generating a new map")
bpy.data.objects.remove(missing,do_unlink=True)
select(obj)
other=bpy.data.materials.new("Facade")
obj.data.materials.append(other)
for p in obj.data.polygons:
    p.material_index=len(obj.data.materials)-1
before=snapshot(obj)
bpy.ops.object.mode_set(mode="EDIT")
bm=bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()
for f in bm.faces:
    f.select_set(False)
bm.faces[1].select_set(True)
bmesh.update_edit_mesh(obj.data)
check(bpy.ops.parallax_cubemap.assign_material()=={"FINISHED"},"Button works in Edit Mode")
bpy.ops.object.mode_set(mode="OBJECT")
check(obj.data.materials[obj.data.polygons[0].material_index]==other
      and obj.data.materials[obj.data.polygons[1].material_index]==real
      and snapshot(obj)==before,"Unselected face material and all UVs stay unchanged")
# Inspect the actual panel draw calls instead of only counting classes.
class Layout:
    def __init__(self): self.calls=[]
    def operator(self,*args,**kw): self.calls.append((args,kw))
    def row(self): return self
layout=Layout()
class Panel:
    pass
panel=Panel()
panel.layout=layout
addon.PCM_PT_panel.draw(panel,bpy.context)
check(len(layout.calls)==3 and layout.calls[0][1]["text"]=="Assign Material"
      and layout.calls[1][0][0]=="parallax_cubemap.toggle_debug",
      "Panel has assignment, debug toggle and restore only")
addon.unregister()
addon.register()
check(not hasattr(bpy.types.Scene,"px_windows"),"No scene settings or old properties registered")
(OUT/"verification.json").write_text(json.dumps({"blender":bpy.app.version_string,
    "version":"2.0.0","count":len(results),"checks":results},ensure_ascii=False,indent=2),encoding="utf-8")
print("ALL CHECKS PASSED:",len(results),flush=True)
