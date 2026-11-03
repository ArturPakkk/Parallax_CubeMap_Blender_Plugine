# SPDX-License-Identifier: GPL-3.0-or-later
import ast,hashlib,re,sys,tomllib,unittest,zipfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from package import build,FILES,DOCS
class PackageTests(unittest.TestCase):
    def test_manifest_supports_45(self):
        m=tomllib.loads((ROOT/"parallax_cubemap/blender_manifest.toml").read_text(encoding="utf-8"))
        self.assertEqual(m["id"],"parallax_cubemap")
        self.assertEqual(m["name"],"Parallax_CubeMap")
        self.assertEqual(m["blender_version_min"],"4.5.0")
        self.assertNotIn("permissions",m)
    def test_readmes_have_five_sentences(self):
        for name in ("README_RU.md","README_EN.md"):
            text=(ROOT/name).read_text(encoding="utf-8").strip()
            sentences=re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я«])",text)
            self.assertEqual(len(sentences),5,name)
    def test_shipped_texture_hashes(self):
        for name,digest in {
            "T_Parallax_02.exr":"e5765a2e3f15b9d8590518aba6b8033b19a5fb9879532334884338d24bcd01db",
            "Parallax_Debug.exr":"5ff33f1ce47ad650462d0b31ee129c789c590a9fd91db574698895fe7ca44c5c"}.items():
            self.assertEqual(hashlib.sha256((ROOT/"parallax_cubemap/assets"/name).read_bytes()).hexdigest(),digest)
    def test_runtime_imports_are_local_and_allowlisted(self):
        allowed={"bpy","bmesh","math","pathlib","dataclasses","uuid"}
        for path in (ROOT/"parallax_cubemap").glob("*.py"):
            tree=ast.parse(path.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n,ast.Import): self.assertTrue(all(a.name in allowed for a in n.names),str(path))
                if isinstance(n,ast.ImportFrom) and n.level==0: self.assertIn(n.module,allowed | {"bpy.types"})
                if isinstance(n,ast.Call) and isinstance(n.func,ast.Name): self.assertNotIn(n.func.id,{"exec","eval","compile","open","__import__"})
    def test_archive_is_exact_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            p=build(temp)
            before=p.read_bytes()
            self.assertEqual(before,build(temp).read_bytes())
            with zipfile.ZipFile(p) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(set(z.namelist()),set(FILES+DOCS))
                for n in z.namelist():
                    self.assertNotIn("..",Path(n).parts)
                    self.assertFalse(n.startswith(("/",".git","GARBAGE")))
                    source=(ROOT/"parallax_cubemap"/n) if n in FILES else ROOT/n
                    self.assertEqual(z.read(n),source.read_bytes())
if __name__=="__main__": unittest.main()
