# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate Blender's live translation system in an isolated UI process."""
import bpy, sys, json, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.project_paths import REPORTS, PROFILES, prepare_verification
prepare_verification()
OUT = REPORTS
import parallax_cubemap as addon
from parallax_cubemap import translations as loc
addon.register()
bpy.context.preferences.filepaths.temporary_directory=str(PROFILES/"language"/"temp")
bpy.context.preferences.view.use_save_prompt=False
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label)
    print("PASS",label,flush=True)
def error_message():
    bpy.ops.object.select_all(action="DESELECT")
    try:
        bpy.ops.parallax_cubemap.assign_material()
    except RuntimeError as error:
        return str(error)
    raise AssertionError("Expected missing selection")
def test():
    try:
        pref=bpy.context.preferences.view
        pref.use_translate_interface=True
        pref.use_translate_tooltips=True
        pref.language="en_US"
        check(all(loc.tr(en)==en for en in loc.RUSSIAN), "All messages use English in English Blender")
        check("Select window mesh objects" in error_message(), "Actual operator error is English")
        pref.language="ru_RU"
        check(all(loc.tr(en)==ru for en,ru in loc.RUSSIAN.items()), "All messages use Russian after live language change")
        check("Выберите Mesh-объекты" in error_message(), "Actual operator error is Russian")
        for cls in (addon.PCM_OT_assign,addon.PCM_OT_toggle_debug,addon.PCM_OT_restore):
            check(cls.bl_translation_context==loc.CONTEXT
                  and bpy.app.translations.pgettext_tip(cls.bl_description,loc.CONTEXT)==loc.RUSSIAN[cls.bl_description],
                  "Russian tooltip and private translation context: "+cls.bl_idname)
        class Layout:
            enabled=True
            calls=[]
            def operator(self,*args,**kw): self.calls.append(kw)
            def row(self): return self
        class Panel: layout=Layout()
        addon.PCM_PT_panel.draw(Panel(),bpy.context)
        check([bpy.app.translations.pgettext_iface(c["text"],c["text_ctxt"]) for c in Panel.layout.calls]
              ==["Назначить материал","Debug-текстура","Вернуть материалы"],
              "All three panel buttons pass the correct Russian translation context")
        pref.use_translate_interface=False
        check(loc.tr("Restore Materials")=="Restore Materials", "Interface translation preference is respected")
        pref.use_translate_interface=True
        addon.register()
        check(loc.tr("Restore Materials")=="Вернуть материалы", "Repeated registration keeps translations working")
        addon.unregister()
        addon.unregister()
        addon.register()
        check(loc.tr("Assign Material")=="Назначить материал", "Disable/re-enable restores Russian translations")
        pref.language="en_US"
        check(loc.tr("Restore Materials")=="Restore Materials"
              and addon.MATERIAL_NAME=="Debug_Parallax", "Switching back to English leaves material naming unchanged")
        result={"success":True,"version":"2.0.0","blender":bpy.app.version_string,"checks":checks,
                "catalogue_entries":len(loc.RUSSIAN)}
    except Exception:
        result={"success":False,"checks":checks,"error":traceback.format_exc()}
        traceback.print_exc()
    (OUT/"language_verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(test,first_interval=1.5)
