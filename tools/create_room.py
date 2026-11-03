# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the original 3x3 room atlas from authored Blender primitives.
No external images, HDRIs, models or fonts are loaded.
Run: blender -b --factory-startup --python tools/create_room.py
"""
from pathlib import Path
import bpy,math,numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/"GARBAGE"/"RoomGenerator"
WORK.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.engine="CYCLES"
scene.cycles.device="CPU"
scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.render.resolution_x=684
scene.render.resolution_y=684
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="OPEN_EXR"
scene.render.image_settings.color_mode="RGBA"
scene.render.image_settings.color_depth="16"
scene.render.image_settings.exr_codec="ZIP"
scene.render.film_transparent=True
scene.view_settings.view_transform="Standard"
scene.world.use_nodes=True
scene.world.node_tree.nodes["Background"].inputs[0].default_value=(.8,.88,1,1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value=.35
def mat(name,color,metal=0,rough=.55):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value=(*color,1)
    p.inputs["Metallic"].default_value=metal
    p.inputs["Roughness"].default_value=rough
    return m
ivory=mat("Original warm plaster",(.62,.59,.52),rough=.82)
sage=mat("Original sage accent",(.19,.31,.27),rough=.8)
oak=mat("Original warm oak",(.24,.115,.048),rough=.5)
dark=mat("Original graphite",(.025,.034,.039),metal=.25,rough=.32)
fabric=mat("Original rust fabric",(.34,.095,.048),rough=.9)
green=mat("Original foliage",(.09,.22,.10),rough=.8)
cream=mat("Original ceramic",(.72,.67,.54),rough=.4)
gold=mat("Original brushed brass",(.34,.24,.095),metal=.75,rough=.3)
# Procedural floor uses no bitmap.
floor=mat("Original procedural oak floor",(.3,.15,.07))
n=floor.node_tree.nodes;l=floor.node_tree.links
tex=n.new("ShaderNodeTexNoise");tex.inputs["Scale"].default_value=9;tex.inputs["Detail"].default_value=2
coord=n.new("ShaderNodeTexCoord")
mapping=n.new("ShaderNodeVectorMath");mapping.operation="MULTIPLY";mapping.inputs[1].default_value=(4,.3,2)
l.new(coord.outputs["Generated"],mapping.inputs[0]);l.new(mapping.outputs[0],tex.inputs["Vector"])
ramp=n.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color=(.075,.032,.012,1)
ramp.color_ramp.elements[1].color=(.32,.17,.07,1)
l.new(tex.outputs["Fac"],ramp.inputs[0]);l.new(ramp.outputs[0],n.get("Principled BSDF").inputs["Base Color"])
def box(name,pos,size,material,group,bevel=.018):
    bpy.ops.mesh.primitive_cube_add(size=1,location=pos)
    o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(material);o["room_group"]=group
    if bevel:
        b=o.modifiers.new("Original soft edges","BEVEL");b.width=bevel;b.segments=3
        o.modifiers.new("Original normals","WEIGHTED_NORMAL")
    return o
# Room: x=-2..2, y=0..4, z=0..3.
walls={}
walls["back"]=box("Back plaster",(0,4.06,1.5),(4.12,.12,3.12),ivory,"walls",0)
walls["left"]=box("Sage left wall",(-2.06,2,1.5),(.12,4.12,3.12),sage,"walls",0)
walls["right"]=box("Right plaster",(2.06,2,1.5),(.12,4.12,3.12),ivory,"walls",0)
walls["floor"]=box("Oak floor",(0,2,-.06),(4.12,4.12,.12),floor,"walls",0)
walls["top"]=box("Warm ceiling",(0,2,3.06),(4.12,4.12,.12),ivory,"walls",0)
# Furniture layer 1: desk, monitor and desk lamp.
box("Desk top",(-.3,1.8,.94),(1.85,.76,.09),oak,"desk")
for x in (-1.1,.5):
    box("Desk leg",(x,1.8,.46),(.055,.59,.92),dark,"desk",.006)
box("Desk drawer",(-.94,1.85,.70),(.36,.58,.36),oak,"desk")
for z in (.62,.74):
    box("Drawer brass grip",(-.94,1.55,z),(.13,.025,.018),gold,"desk",.003)
screen=mat("Original dark monitor",(.018,.055,.066),rough=.27)
screen.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value=(.025,.09,.11,1)
screen.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value=.4
box("Monitor",(-.25,1.95,1.28),(.72,.065,.43),dark,"desk")
box("Monitor display",(-.25,1.912,1.28),(.67,.008,.38),screen,"desk",.006)
box("Monitor stem",(-.25,1.96,1.02),(.045,.07,.18),dark,"desk",.005)
box("Monitor base",(-.25,1.91,.995),(.31,.18,.024),dark,"desk",.005)
box("Desk notebook",(.35,1.65,1.0),(.29,.19,.025),cream,"desk",.004)
box("Lamp base",(-1.00,1.90,1.01),(.16,.16,.045),gold,"desk")
box("Lamp stem",(-1.00,1.95,1.25),(.018,.018,.45),gold,"desk",.004)
box("Lamp head",(-.91,1.93,1.48),(.23,.14,.06),cream,"desk")
# Furniture layer 2: asymmetrical open shelving and authored decorative panels.
for x in (1.07,1.78):
    box("Bookcase upright",(x,3.43,1.14),(.045,.36,2.2),oak,"shelf",.008)
for z in (.12,.61,1.10,1.59,2.22):
    box("Bookcase shelf",(1.425,3.43,z),(.755,.38,.045),oak,"shelf",.008)
book_colors=[mat("Original book "+str(i),c) for i,c in enumerate(((.13,.24,.28),(.55,.28,.11),(.62,.57,.43),(.24,.35,.24),(.38,.15,.12)))]
for level,z in enumerate((.15,.64,1.13,1.62)):
    for j in range(6):
        h=.28+((j*7+level*3)%5)*.026
        box("Authored book",(1.12+j*.095,3.38,z+h/2),(.065,.22,h),book_colors[(j+level)%5],"shelf",.004)
box("Wall art frame",(-.72,3.96,1.92),(1.15,.05,.68),oak,"shelf")
box("Wall art linen",(-.72,3.925,1.92),(1.07,.014,.60),cream,"shelf",.003)
box("Abstract sage panel",(-.87,3.914,1.95),(.29,.01,.34),sage,"shelf",.003)
box("Abstract terracotta panel",(-.48,3.912,1.84),(.25,.01,.21),fabric,"shelf",.003)
# Furniture layer 3: lounge seat and low side table.
box("Lounge seat",(-1.0,.88,.42),(.76,.68,.16),fabric,"chair",.065)
back=box("Lounge back",(-1.0,1.17,.78),(.76,.13,.66),fabric,"chair",.055)
back.rotation_euler.x=math.radians(-8)
for x in (-1.29,-.71):
    for y in (.65,1.10):
        box("Lounge leg",(x,y,.17),(.045,.045,.34),oak,"chair",.005)
box("Side table",(.90,.95,.53),(.48,.48,.06),oak,"chair")
for x in (.73,1.07):
    box("Side table support",(x,.95,.25),(.035,.34,.5),gold,"chair",.004)
box("Ceramic planter",(.90,.95,.66),(.18,.18,.22),cream,"chair")
for i in range(7):
    angle=i*math.pi*2/7
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=1,location=(.9+math.cos(angle)*.075,.95+math.sin(angle)*.075,.87+(i%3)*.06))
    o=bpy.context.object;o.name="Original plant leaf";o.scale=(.035,.025,.15);o.rotation_euler=(.35*math.sin(angle),.35*math.cos(angle),angle)
    o.data.materials.append(green);o["room_group"]="chair"
# Broad daylight plus a warm overhead fill.
for pos,energy,size,color in (((-1,-2,3),500,4,(.82,.9,1)),((.7,1.7,2.8),130,2.0,(1,.8,.58))):
    bpy.ops.object.light_add(type="AREA",location=pos)
    lamp=bpy.context.object;lamp.data.energy=energy;lamp.data.shape="DISK";lamp.data.size=size;lamp.data.color=color
    lamp.rotation_euler=(Vector((0,2,1))-lamp.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add()
cam=bpy.context.object;cam.data.type="ORTHO";scene.camera=cam
geometry=[o for o in scene.objects if o.type=="MESH"]
def render_tile(name,position,direction,up,aspect=(1,1),visible="walls",wall=None):
    cam.location=position
    # Track camera -Z forward with Y as up, then handle floor/ceiling explicitly.
    if up==(0,0,1):
        cam.rotation_euler=Vector(direction).to_track_quat("-Z","Y").to_euler()
    else:
        from mathutils import Matrix
        f=Vector(direction).normalized();u=Vector(up).normalized();right=f.cross(u).normalized()
        cam.rotation_euler=Matrix((right,u,-f)).transposed().to_euler()
    cam.data.ortho_scale=4
    scene.render.pixel_aspect_x,scene.render.pixel_aspect_y=aspect
    for o in geometry:
        group=o.get("room_group")
        o.visible_camera=(group==visible and (wall is None or o==walls[wall]))
    scene.render.filepath=str(WORK/(name+".exr"))
    bpy.ops.render.render(write_still=True)
    im=bpy.data.images.load(scene.render.filepath,check_existing=False)
    data=np.asarray(im.pixels[:],dtype=np.float32).reshape((684,684,4))
    bpy.data.images.remove(im)
    print("GENERATED",name,flush=True)
    return data
tiles={}
tiles[(1,1)]=render_tile("back",(0,1,1.5),(0,1,0),(0,0,1),(4,3),wall="back")
tiles[(0,1)]=render_tile("left",(0,2,1.5),(-1,0,0),(0,0,1),(4,3),wall="left")
tiles[(2,1)]=render_tile("right",(0,2,1.5),(1,0,0),(0,0,1),(4,3),wall="right")
tiles[(1,0)]=render_tile("floor",(0,2,2),(0,0,-1),(0,1,0),wall="floor")
tiles[(1,2)]=render_tile("top",(0,2,1),(0,0,1),(0,-1,0),wall="top")
for key,group in (((0,2),"desk"),((2,2),"shelf"),((2,0),"chair")):
    tiles[key]=render_tile(group,(0,-6,1.65),(0,1,-.025),(0,0,1),(4,3),visible=group)
# Assemble a fresh atlas from the original renders; input assets are never read.
canvas=np.zeros((2048,2048,4),dtype=np.float32)
edges=(0,683,1365,2048)
for (col,row),data in tiles.items():
    h,w=edges[row+1]-edges[row],edges[col+1]-edges[col]
    ys=np.linspace(0,683,h).astype(np.int32);xs=np.linspace(0,683,w).astype(np.int32)
    tile=data[ys[:,None],xs[None,:],:].copy()
    tile[:,:,:3]/=2**2.2  # Native shader's fixed exposure restores the baked lighting.
    canvas[edges[row]:edges[row+1],edges[col]:edges[col+1],:]=tile
atlas=bpy.data.images.new("T_Parallax_02",width=2048,height=2048,alpha=True,float_buffer=True)
atlas.alpha_mode="PREMUL"
atlas.pixels.foreach_set(canvas.ravel())
out=ROOT/"parallax_cubemap"/"assets"/"T_Parallax_02.exr"
atlas.save_render(str(out),scene=scene)
for o in geometry: o.visible_camera=True
scene.render.pixel_aspect_x=4;scene.render.pixel_aspect_y=3
bpy.ops.wm.save_as_mainfile(filepath=str(WORK/"Original_Parallax_Room.blend"))
print("ORIGINAL_ROOM_READY",out,flush=True)
