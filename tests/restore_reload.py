import bpy,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, prepare_verification
prepare_verification()
OUT = REPORTS
import parallax_cubemap as addon
from parallax_cubemap import backup
obj=bpy.data.objects["PortableRestore"]
assert backup.KEY in obj.data
addon.register()
assert bpy.ops.parallax_cubemap.restore_materials()=={"FINISHED"}
assert [obj.material_slots[p.material_index].material.name for p in obj.data.polygons]==["PortableRestoreMaterial0","PortableRestoreMaterial1"]
assert abs(obj.data.vertices[0].co.z-.654)<1e-5 and backup.KEY not in obj.data
p=OUT/"restore_verification.json"
data=json.loads(p.read_text(encoding="utf-8"))
data["checks"].append("Fresh process reopens a blend saved with addon disabled and restores retained materials without losing edits")
data["save_reopen"]=True
p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
print("RESTORE_REOPEN_PASSED",flush=True)
