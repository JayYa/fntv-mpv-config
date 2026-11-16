"""安装包构建：已知哈希、契约测试入口、打包与命名"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.package_archive import KnownHashes

SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
SHA256_DEF = "cb8379ac2098aa165029e3938a51da0bcecfc008fd6795f401178647f96c5b34"
SHA256_GHI = "50ae61e841fac4e8f9e40baf2ad36ec868922ea48368c18f9535e47db56dd7fb"

PROJECT_ROOT = Path(__file__).parent.parent


class TestKnownHashes(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_json(self, name, data) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_merges_history_with_previous_manifest(self):
        history = self.write_json("history.json", {"archives": ["v1"], "files": {
            "mpv.conf": [SHA256_ABC],
        }})
        previous = self.write_json("previous.json", {
            "files": [{"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
                       "knownHashes": [SHA256_GHI]}],
            "obsolete": [{"path": "scripts/old.lua", "knownHashes": [SHA256_ABC]}],
        })

        known = KnownHashes.load(history, previous)

        self.assertEqual(known.of("mpv.conf"), {SHA256_ABC, SHA256_DEF, SHA256_GHI})
        self.assertEqual(known.of("scripts/old.lua"), {SHA256_ABC})
        self.assertEqual(known.previously_obsolete, {"scripts/old.lua"})

    def test_defaults_to_the_committed_history(self):
        known = KnownHashes.load()

        committed = json.loads((PROJECT_ROOT / "manifest-history.json").read_text(encoding="utf-8"))
        self.assertEqual(known.of("scripts/uosc/main.lua"),
                         set(committed["files"]["scripts/uosc/main.lua"]))
        self.assertEqual(known.previously_obsolete, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
