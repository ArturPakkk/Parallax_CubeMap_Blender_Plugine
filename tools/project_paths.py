from pathlib import Path
import tomllib
ROOT=Path(__file__).resolve().parents[1]
ADDON=ROOT/"parallax_cubemap"
DOCS=ROOT
VERSION=tomllib.loads((ADDON/"blender_manifest.toml").read_text(encoding="utf-8"))["version"]
VERIFICATION=ROOT/"GARBAGE"/"Verification"
REPORTS=VERIFICATION/"Reports"
SCENES=VERIFICATION/"Scenes"
PROFILES=VERIFICATION/"Profiles"
BUILDS=ROOT/"dist"
def prepare_verification():
    for d in (REPORTS,SCENES,PROFILES): d.mkdir(parents=True,exist_ok=True)
def package_path(version=VERSION,legacy=False,build_root=BUILDS):
    return Path(build_root)/f"Parallax_CubeMap_{version}.zip"
def demo_path(filename,**kwargs): return SCENES/filename
def render_path(suite,filename):
    d=VERIFICATION/"Renders"/suite
    d.mkdir(parents=True,exist_ok=True)
    return d/filename
