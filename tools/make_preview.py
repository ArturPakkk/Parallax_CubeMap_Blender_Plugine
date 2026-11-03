# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a portable demo using only one interior quad and the user's EXR."""
import sys
from pathlib import Path
import math
import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import demo_path
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
import parallax_cubemap as addon
from parallax_cubemap.shader import material_node
addon.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 900
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX"
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.35,0.43,0.55,1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.45
scene.render.film_transparent = False

def solid(name, color, metallic=0, roughness=.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color,1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return m

def box(name, location, dimensions, material, bevel=.03):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.object
    o.name = name
    o.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    if bevel:
        m = o.modifiers.new("Soft edges", "BEVEL")
        m.width, m.segments = bevel, 3
        o.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return o

plaster=solid("Warm concrete",(.32,.30,.27),roughness=.82)
frame=solid("Anodized graphite",(.028,.034,.038),metallic=.7,roughness=.23)
floor=solid("Studio ground",(.10,.125,.145),roughness=.7)
# A frame cut from separate blocks; no room mesh behind the opening.
box("Facade left",(-2.38,.13,1.85),(.86,.35,4.2),plaster)
box("Facade right",(2.38,.13,1.85),(.86,.35,4.2),plaster)
box("Facade lintel",(0,.13,3.65),(3.90,.35,.6),plaster)
box("Facade base",(0,.13,.05),(3.90,.35,.6),plaster)
box("Window frame L",(-1.86,-.05,1.85),(.12,.25,3.1),frame,.016)
box("Window frame R",(1.86,-.05,1.85),(.12,.25,3.1),frame,.016)
box("Window frame top",(0,-.05,3.36),(3.8,.25,.12),frame,.016)
box("Window sill",(0,-.10,.34),(3.9,.48,.14),frame,.018)
box("Ground",(0,1,-.32),(200,200,.1),floor,0)
mesh = bpy.data.meshes.new("ONE QUAD - no interior geometry")
mesh.from_pydata([(-1.8,0,.4),(1.8,0,.4),(1.8,0,3.3),(-1.8,0,3.3)],[],[(0,1,2,3)])
window = bpy.data.objects.new("WINDOW • orbit to see parallax",mesh)
scene.collection.objects.link(window)
for o in bpy.context.selected_objects:
    o.select_set(False)
window.select_set(True)
bpy.context.view_layer.objects.active = window
# The artist-authored rectangular island fits within the 0-1 tile.
uv=mesh.uv_layers.new(name="Window_UV")
height=2.9/3.6
for loop,coords in zip(uv.data,((0,0),(1,0),(1,height),(0,height))):
    loop.uv=coords
uv.active_render=True
bpy.ops.parallax_cubemap.assign_material()
mat=window.active_material

bpy.ops.object.light_add(type="AREA",location=(-3.5,-4,6.5))
lamp=bpy.context.object
lamp.name="Soft exterior light"
lamp.data.energy=1500
lamp.data.shape="DISK"
lamp.data.size=5
lamp.rotation_euler=(Vector((0,0,1.5))-lamp.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add()
camera=bpy.context.object
camera.name="Orbit preview • frames 1 / 40 / 80"
scene.camera=camera
camera.data.lens=48
camera.data.clip_end=300
target=Vector((0,0,1.65))
for frame_number,position in ((1,(-3.6,-7.8,3.1)),(40,(0,-8.2,2.3)),(80,(3.6,-7.8,3.1))):
    camera.location=position
    camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
    camera.keyframe_insert("location",frame=frame_number)
    camera.keyframe_insert("rotation_euler",frame=frame_number)
scene.frame_start=1
scene.frame_end=80
for number,label in ((1,"Left view"),(40,"Front view"),(80,"Right view")):
    scene.timeline_markers.new(label,frame=number)
scene.frame_set(80)
for o in bpy.context.selected_objects:
    o.select_set(False)
window.select_set(True)
bpy.context.view_layer.objects.active=window
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=="VIEW_3D":
            area.spaces.active.shading.type="MATERIAL"
            area.spaces.active.region_3d.view_perspective="CAMERA"
            area.spaces.active.show_region_ui=True
            area.spaces.active.overlay.show_overlays=False
        elif area.type=="PROPERTIES":
            area.spaces.active.context="MATERIAL"
readme=bpy.data.texts.new("START HERE • Parallax_CubeMap")
readme.write("""DEBUG_PARALLAX / ROOM + DEBUG
Selected WINDOW has one quad and an existing rectangular Window_UV island.
The material reads UV directly. No unwrap, normalization, repeat or UV changes.
Rotate or mirror UV to rotate or mirror the room.
A partial rectangular island shows only that region of the full UV room.
N > Parallax: Assign Material, Debug Texture, Restore Materials.
The EXR is packed; rendering works without the addon.
Camera views: frames 1 / 40 / 80.
""")
scene.render.filepath=str(OUT/"room.png")
bpy.ops.wm.save_as_mainfile(filepath=str(demo_path("Parallax_CubeMap_Demo.blend")))
bpy.ops.render.render(write_still=True)
# Same camera, second atlas. The saved blend remains in default room mode.
bpy.ops.parallax_cubemap.toggle_debug()
scene.render.filepath=str(OUT/"debug.png")
bpy.ops.render.render(write_still=True)
bpy.ops.parallax_cubemap.toggle_debug()
print("DEMO_READY",OUT,flush=True)
