# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the actual ZIP into an isolated local extensions repository."""
import bpy,addon_utils,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.project_paths import REPORTS,PROFILES,package_path,prepare_verification
prepare_verification()
repo_dir=PROFILES/"installation"/"repository"
repo_dir.mkdir(parents=True,exist_ok=True)
repo=bpy.context.preferences.extensions.repos.new(name="Parallax isolated test",module="parallax_test")
repo.custom_directory=str(repo_dir)
repo.use_custom_directory=True
repo.use_remote_url=False
repo.enabled=True
module="bl_ext."+repo.module+".parallax_cubemap"
assert bpy.ops.extensions.package_install_files(filepath=str(package_path()),repo=repo.module,enable_on_install=True)=={"FINISHED"}
addon=sys.modules[module]
assert addon.PCM_OT_assign.is_registered and addon.PCM_OT_restore.is_registered
bpy.ops.mesh.primitive_plane_add()
obj=bpy.context.object
original=bpy.data.materials.new("Original")
obj.data.materials.append(original)
for i in range(5):
    assert bpy.ops.parallax_cubemap.assign_material()=={"FINISHED"}
    assert not addon.debug_enabled(addon.canonical_material())
    assert bpy.ops.parallax_cubemap.toggle_debug()=={"FINISHED"}
    assert bpy.ops.parallax_cubemap.restore_materials()=={"FINISHED"}
    assert obj.active_material==original and addon.canonical_material() not in list(obj.data.materials)
addon_utils.disable(module,default_set=True)
assert not addon.PCM_OT_assign.is_registered
addon_utils.enable(module,default_set=True)
assert sys.modules[module].PCM_OT_assign.is_registered
assert bpy.ops.parallax_cubemap.assign_material()=={"FINISHED"}
assert bpy.ops.parallax_cubemap.restore_materials()=={"FINISHED"}
(REPORTS/"installation.json").write_text(json.dumps({"success":True,"cycles":5,"disable_enable":True,
    "blender":bpy.app.version_string,"version":"2.0.0"},indent=2),encoding="utf-8")
print("INSTALLED_ZIP_PASSED",module,flush=True)
