# SPDX-License-Identifier: GPL-3.0-or-later
"""Build an installable Blender 4.5+ extension ZIP from audited source."""
import argparse
import hashlib
import json
import tomllib
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ADDON=ROOT/"parallax_cubemap"
FILES=("__init__.py","shader.py","mesh.py","backup.py","translations.py","blender_manifest.toml",
       "assets/T_Parallax_02.exr","assets/Parallax_Debug.exr")
DOCS=("README_RU.md","README_EN.md","LICENSE","ASSET_NOTICE.txt","THIRD_PARTY_NOTICES.md","docs/LICENSING.md")
def build(output=None):
    version=tomllib.loads((ADDON/"blender_manifest.toml").read_text(encoding="utf-8"))["version"]
    target=Path(output) if output else ROOT/"dist"
    target.mkdir(parents=True,exist_ok=True)
    archive=target/f"Parallax_CubeMap_{version}.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for base,names in ((ADDON,FILES),(ROOT,DOCS)):
            for name in names:
                data=(base/name).read_bytes()
                item=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
                item.compress_type=zipfile.ZIP_DEFLATED
                item.external_attr=0o644 << 16
                z.writestr(item,data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(FILES+DOCS)
        for base,names in ((ADDON,FILES),(ROOT,DOCS)):
            for name in names: assert z.read(name)==(base/name).read_bytes()
    archive.with_suffix(".sha256").write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n",encoding="utf-8")
    return archive
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output")
    print(build(p.parse_args().output))
