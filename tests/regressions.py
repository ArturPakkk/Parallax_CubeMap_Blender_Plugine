# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused Blender regressions for the 1.3.1 report and 2.0 safety fixes."""
import bpy,bmesh,sys,json,unittest,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import parallax_cubemap as addon
from parallax_cubemap import backup,mesh
from tools.project_paths import REPORTS,prepare_verification
prepare_verification()
addon.register()

def select(*objects):
    if bpy.context.mode!="OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]

def fixture(name="Window",empty=False):
    vertices,faces=[],[]
    for n in range(3):
        i=len(vertices)
        vertices.extend(((n*3,0,0),(n*3+2,0,0),(n*3+2,2,0),(n*3,2,0)))
        faces.append(tuple(range(i,i+4)))
    data=bpy.data.meshes.new(name)
    data.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new(name,data)
    bpy.context.scene.collection.objects.link(obj)
    data.uv_layers.new(name="UserUV")
    data.uv_layers["UserUV"].uv.foreach_set("vector",[c for _ in faces for p in ((0,0),(1,0),(1,1),(0,1)) for c in p])
    if not empty:
        data.materials.append(bpy.data.materials.new("Original"))
    select(obj)
    return obj

def effective(obj):
    return [obj.material_slots[p.material_index].material if p.material_index<len(obj.material_slots) else None
            for p in obj.data.polygons]

def edit_one(obj):
    select(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bm=bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces: f.select_set(False)
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(obj.data)

def cancelled(operator):
    try: return operator()=={"CANCELLED"}
    except RuntimeError: return True

class RegressionTests(unittest.TestCase):
    def tearDown(self):
        if bpy.context.mode!="OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

    def test_debug_restore_reassign_defaults_to_room(self):
        for empty in (False,True):
            obj=fixture(empty=empty)
            original=effective(obj)
            uv=[tuple(v.vector) for v in obj.data.uv_layers["UserUV"].uv]
            for _ in range(30):
                self.assertEqual(bpy.ops.parallax_cubemap.assign_material(),{"FINISHED"})
                self.assertFalse(addon.debug_enabled(addon.canonical_material()))
                self.assertEqual(bpy.ops.parallax_cubemap.toggle_debug(),{"FINISHED"})
                self.assertTrue(addon.debug_enabled(addon.canonical_material()))
                self.assertEqual(bpy.ops.parallax_cubemap.restore_materials(),{"FINISHED"})
                self.assertEqual(effective(obj),original)
                self.assertNotIn(addon.canonical_material(),list(obj.data.materials))
                self.assertNotIn(backup.KEY,obj.data)
            self.assertEqual(uv,[tuple(v.vector) for v in obj.data.uv_layers["UserUV"].uv])
            self.assertEqual(len([m for m in bpy.data.materials if m.name.startswith(addon.MATERIAL_NAME)]),1)
            bpy.data.objects.remove(obj,do_unlink=True)

    def test_selected_faces_do_not_change_blank_unselected_faces(self):
        obj=fixture(empty=True)
        edit_one(obj)
        self.assertEqual(bpy.ops.parallax_cubemap.assign_material(),{"FINISHED"})
        self.assertEqual(effective(obj),[addon.canonical_material(),None,None])
        self.assertIsNone(obj.data.materials[0])
        self.assertEqual(bpy.ops.parallax_cubemap.restore_materials(),{"FINISHED"})
        self.assertEqual(effective(obj),[None,None,None])

    def test_hidden_faces_keep_their_blank_binding(self):
        obj=fixture(empty=True)
        obj.data.polygons[1].hide=True
        bpy.ops.parallax_cubemap.assign_material()
        self.assertEqual(effective(obj),[addon.canonical_material(),None,addon.canonical_material()])

    def test_invalid_untouched_slot_is_padded(self):
        obj=fixture(empty=True)
        obj.data.polygons[1].material_index=3
        edit_one(obj)
        bpy.ops.parallax_cubemap.assign_material()
        self.assertEqual(effective(obj),[addon.canonical_material(),None,None])
        self.assertEqual(obj.data.polygons[1].material_index,3)

    def test_second_window_keeps_shared_debug_mode(self):
        first=fixture("First")
        bpy.ops.parallax_cubemap.assign_material()
        bpy.ops.parallax_cubemap.toggle_debug()
        second=fixture("Second")
        bpy.ops.parallax_cubemap.assign_material()
        self.assertTrue(addon.debug_enabled(addon.canonical_material()))
        bpy.ops.parallax_cubemap.restore_materials()
        select(first)
        self.assertTrue(addon.debug_enabled(addon.canonical_material()))
        bpy.ops.parallax_cubemap.restore_materials()
        select(second)
        bpy.ops.parallax_cubemap.assign_material()
        self.assertFalse(addon.debug_enabled(addon.canonical_material()))

    def test_toggle_is_disabled_after_restore(self):
        obj=fixture()
        bpy.ops.parallax_cubemap.assign_material()
        bpy.ops.parallax_cubemap.toggle_debug()
        bpy.ops.parallax_cubemap.restore_materials()
        self.assertTrue(cancelled(bpy.ops.parallax_cubemap.toggle_debug))
        class Layout:
            enabled=True
            def __init__(self): self.calls=[]
            def operator(self,*args,**kw): self.calls.append((args[0],self.enabled,kw))
            def row(self): return self
        class Panel: layout=Layout()
        addon.PCM_PT_panel.draw(Panel(),bpy.context)
        toggle=Panel.layout.calls[1]
        self.assertFalse(toggle[1])
        self.assertFalse(toggle[2]["depress"])
        self.assertTrue(Panel.layout.calls[0][1])

    def test_padding_rollback_keeps_empty_slots_empty(self):
        a,b=fixture("A",True),fixture("B",True)
        select(a,b)
        bpy.ops.object.mode_set(mode="EDIT")
        for obj in (a,b):
            bm=bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            for f in bm.faces: f.select_set(False)
            bm.faces[0].select_set(True)
            bmesh.update_edit_mesh(obj.data)
        old=mesh.set_faces
        calls=0
        def failing(stage,indices):
            nonlocal calls
            calls+=1
            if calls==2: raise RuntimeError("Injected padding failure")
            return old(stage,indices)
        mesh.set_faces=failing
        try: self.assertTrue(cancelled(bpy.ops.parallax_cubemap.assign_material))
        finally: mesh.set_faces=old
        for obj in (a,b):
            self.assertEqual(len(obj.data.materials),0)
            self.assertEqual(len(obj.material_slots),0)
            self.assertNotIn(backup.KEY,obj.data)
            self.assertEqual(effective(obj),[None,None,None])

    def test_legacy_material_owner_is_reused(self):
        obj=fixture()
        bpy.ops.parallax_cubemap.assign_material()
        material=addon.canonical_material()
        owner=material["px_owner"]
        material["px_owner"]="artinspector.px_cubemap_windows"
        try:
            bpy.ops.parallax_cubemap.toggle_debug()
            bpy.ops.parallax_cubemap.restore_materials()
            bpy.ops.parallax_cubemap.assign_material()
            self.assertEqual(addon.canonical_material(),material)
            self.assertFalse(addon.debug_enabled(material))
        finally: material["px_owner"]=owner

    def test_images_use_requested_names(self):
        fixture()
        bpy.ops.parallax_cubemap.assign_material()
        images={n.image.name for role in ("ROOM","DEBUG")
                for n in addon.material_node(addon.canonical_material(),role).node_tree.nodes if n.type=="TEX_IMAGE"}
        self.assertEqual(images,{"T_Parallax_02","Parallax_Debug"})

suite=unittest.defaultTestLoader.loadTestsFromTestCase(RegressionTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
(REPORTS/"regressions.json").write_text(json.dumps({"success":result.wasSuccessful(),"tests":result.testsRun,
    "failures":len(result.failures),"errors":len(result.errors),"blender":bpy.app.version_string},indent=2),encoding="utf-8")
if not result.wasSuccessful(): raise SystemExit(1)
