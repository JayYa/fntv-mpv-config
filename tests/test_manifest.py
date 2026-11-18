import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.manifest import (
    HistoryFile,
    KnownHashes,
    Manifest,
    ManifestError,
    ManifestHistory,
    build_manifest,
    load_history,
)
from src.package_config import load_package_config

PROJECT_ROOT = Path(__file__).parent.parent


# sha256 的已知值（独立来源：FIPS 180-2 附录 B.1 的 "abc"，以及空串）
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def write_portable_config(root: Path, files: dict):
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


class TestBuildManifest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.portable = self.tmp / "portable_config"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lists_every_file_with_role_and_hash(self):
        write_portable_config(self.portable, {
            "mpv.conf": b"abc",
            "input.conf": b"",
            "script-opts/uosc.conf": b"abc",
            "danmaku-history.json": b"abc",
            "scripts/uosc/main.lua": b"abc",
            "scripts/thumbfast.lua": b"abc",
            "fonts/uosc_icons.otf": b"abc",
            "shaders/Anime4K_Clamp_Highlights.glsl": b"abc",
        })

        manifest = build_manifest(
            self.portable,
            archive_version="fntv-mpv-v20261114_235959",
            components={"uosc": "5.13.0", "smart_skip": "local"},
            layout=CLIENT_LAYOUT,
        )

        self.assertEqual(manifest.archive_version, "fntv-mpv-v20261114_235959")
        self.assertEqual(manifest.components, {"uosc": "5.13.0", "smart_skip": "local"})
        self.assertEqual(manifest.provides, {"smart-skip.origin-from-play-url": 1})
        self.assertEqual(manifest.managed_dirs, ("scripts/uosc", "scripts/uosc_danmaku", "scripts/smart_skip"))
        self.assertEqual(manifest.obsolete, ())

        files = {f.path: f for f in manifest.files}
        self.assertEqual(
            {path: f.role for path, f in files.items()},
            {
                "mpv.conf": "config",
                "input.conf": "config",
                "script-opts/uosc.conf": "config",
                "danmaku-history.json": "seed",
                "scripts/uosc/main.lua": "managed",
                "scripts/thumbfast.lua": "managed",
                "fonts/uosc_icons.otf": "managed",
                "shaders/Anime4K_Clamp_Highlights.glsl": "managed",
            },
        )
        self.assertEqual(files["input.conf"].sha256, SHA256_EMPTY)
        self.assertEqual(files["mpv.conf"].sha256, SHA256_ABC)
        self.assertEqual(files["mpv.conf"].known_hashes, (SHA256_ABC,))

    def test_written_bytes_parse_back_to_the_same_manifest(self):
        write_portable_config(self.portable, {"mpv.conf": b"abc", "scripts/uosc/main.lua": b""})
        manifest = build_manifest(self.portable, ARCHIVE_VERSION, {"uosc": "5.13.0"}, CLIENT_LAYOUT)

        data = manifest.to_bytes()

        self.assertEqual(Manifest.parse(data, "清单"), manifest)
        self.assertTrue(data.endswith(b"}\n"))
        self.assertNotIn(b"\r", data)
        self.assertEqual(list(json.loads(data)), ["formatVersion", "archiveVersion", "components",
                                                   "provides", "managedDirs", "files", "obsolete"])
        self.assertEqual(list(json.loads(data)["files"][0]), ["path", "sha256", "role", "knownHashes"])


def manifest_json(archive_version="fntv-mpv-v20261114_235959", files=(), obsolete=(),
                  **fields) -> bytes:
    data = {"formatVersion": 1, "archiveVersion": archive_version,
            "components": {"uosc": "5.13.0"}, "provides": {"smart-skip.origin-from-play-url": 1},
            "managedDirs": [], "files": list(files), "obsolete": list(obsolete)}
    data.update(fields)
    return json.dumps(data).encode()


def previous_manifest(files=(), obsolete=()) -> Manifest:
    return Manifest.parse(manifest_json(files=files, obsolete=obsolete), "上一版清单")


class TestParseManifest(unittest.TestCase):
    def assertRejected(self, data: bytes, *fragments):
        with self.assertRaises(ManifestError) as caught:
            Manifest.parse(data, "清单")
        for fragment in fragments:
            self.assertTrue(any(fragment in e for e in caught.exception.errors),
                            f"期望有包含 {fragment!r} 的错误，实际: {caught.exception.errors}")
        self.assertTrue(all(e.startswith("清单") for e in caught.exception.errors))

    def test_a_complete_manifest_parses(self):
        manifest = Manifest.parse(manifest_json(
            files=[{"path": "mpv.conf", "sha256": SHA256_ABC, "role": "config",
                    "knownHashes": [SHA256_ABC, SHA256_EMPTY]}],
            obsolete=[{"path": "scripts/old.lua", "knownHashes": [SHA256_EMPTY]}]), "清单")

        self.assertEqual(manifest.files[0].known_hashes, (SHA256_ABC, SHA256_EMPTY))
        self.assertEqual(manifest.obsolete[0].path, "scripts/old.lua")

    def test_not_json_or_not_an_object(self):
        self.assertRejected(b"not json", "不是合法的 JSON")
        self.assertRejected(b"\xff", "不是合法的 JSON")
        self.assertRejected(b"[]", "JSON 对象")

    def test_every_structural_error_is_reported_at_once(self):
        self.assertRejected(json.dumps({"archiveVersion": "x"}).encode(),
                            "formatVersion", "components", "provides", "managedDirs",
                            "缺少 files 列表", "obsolete 应为数组")

    def test_file_entries_need_every_field(self):
        self.assertRejected(manifest_json(files=[
            {"path": "mpv.conf", "role": "config", "knownHashes": []},
            {"path": "input.conf", "sha256": SHA256_ABC, "role": "user", "knownHashes": [SHA256_ABC]},
            {"path": "fonts/a.otf", "sha256": SHA256_ABC, "role": "managed", "knownHashes": []},
            {"sha256": SHA256_ABC},
        ]), "mpv.conf 缺少 sha256", "input.conf 的 role 不合法", "fonts/a.otf 的 knownHashes",
            "files[3]")

    def test_paths_are_listed_once(self):
        entry = {"path": "mpv.conf", "sha256": SHA256_ABC, "role": "config", "knownHashes": [SHA256_ABC]}
        gone = {"path": "scripts/old.lua", "knownHashes": []}

        self.assertRejected(manifest_json(files=[entry, entry]), "files 里 mpv.conf 重复")
        self.assertRejected(manifest_json(obsolete=[gone, gone]), "obsolete 里 scripts/old.lua 重复")
        self.assertRejected(manifest_json(files=[entry], obsolete=[{"path": "mpv.conf", "knownHashes": []}]),
                            "同时出现在 files 和 obsolete 里")
        broken = {"path": "mpv.conf", "role": "config", "knownHashes": []}
        self.assertRejected(manifest_json(files=[broken], obsolete=[{"path": "mpv.conf", "knownHashes": []}]),
                            "mpv.conf 缺少 sha256", "同时出现在 files 和 obsolete 里")

    def test_format_version_and_components_are_checked(self):
        self.assertRejected(manifest_json(formatVersion=2), "formatVersion 应为 1")
        self.assertRejected(manifest_json(components={}), "components")


THIN_MPV_CONF = (
    b"# comment\r\n"
    b"\r\n"
    b'include="~~/fntv/defaults.conf"\r\n'
    b"profile=fntv-defaults\r\n"
    b"# user settings below\r\n"
)

VALID_PORTABLE_CONFIG = {
    "mpv.conf": THIN_MPV_CONF,
    "fntv/defaults.conf": b"# defaults\n[fntv-defaults]\nvo=gpu-next\n",
    "input.conf": b"",
    "script-opts/uosc.conf": b"",
    "danmaku-history.json": b'{"show_danmaku": true}',
    "scripts/uosc/main.lua": b"-- uosc",
    "scripts/uosc_danmaku/main.lua": b"-- danmaku",
    "scripts/smart_skip/main.lua": b"-- smart skip",
    "scripts/thumbfast.lua": b"-- thumbfast",
}

ARCHIVE_VERSION = "fntv-mpv-v20261114_235959"

CLIENT_LAYOUT = load_package_config(Path(__file__).parent.parent / "package_cfg.json").archive_layout


SHA256_DEF = "cb8379ac2098aa165029e3938a51da0bcecfc008fd6795f401178647f96c5b34"  # "def"
SHA256_GHI = "50ae61e841fac4e8f9e40baf2ad36ec868922ea48368c18f9535e47db56dd7fb"  # "ghi"


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_malformed_history_file_is_rejected(self):
        path = self.tmp / "history.json"
        for data in ['{"archives": []}',
                     '{"archives": [], "files": {"mpv.conf": "abc"}}',
                     '{"archives": [], "files": {"mpv.conf": {"hashes": []}}}',
                     '{"archives": [], "files": {"mpv.conf": {"role": "user", "hashes": []}}}',
                     '{"archives": [], "files": {"mpv.conf": {"role": "config"}}}',
                     "not json"]:
            with self.subTest(data=data):
                path.write_text(data, encoding="utf-8")
                with self.assertRaisesRegex(ManifestError, "history.json"):
                    load_history(path)

    def build(self, history=None, previous=None):
        portable = self.tmp / "portable_config"
        write_portable_config(portable, {"mpv.conf": b"ghi", "scripts/uosc/main.lua": b"abc"})
        return build_manifest(portable, ARCHIVE_VERSION, {}, CLIENT_LAYOUT,
                              known=KnownHashes.merge(history, previous))

    def obsolete_paths(self, manifest):
        return [o.path for o in manifest.obsolete]

    def test_known_hashes_of_history_and_previous_manifest_reach_the_files(self):
        history = ManifestHistory(("fntv-mpv-v1",), {
            "mpv.conf": HistoryFile("config", (SHA256_ABC,)),
            "scripts/uosc/main.lua": HistoryFile("managed", (SHA256_ABC, SHA256_DEF)),
        })
        previous = previous_manifest(files=[{"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
                                             "knownHashes": [SHA256_ABC, SHA256_DEF]}])

        files = {f.path: f for f in self.build(history, previous).files}

        self.assertEqual(files["mpv.conf"].known_hashes,
                         tuple(sorted([SHA256_ABC, SHA256_DEF, SHA256_GHI])))
        self.assertEqual(files["scripts/uosc/main.lua"].known_hashes,
                         tuple(sorted([SHA256_ABC, SHA256_DEF])))

    def test_removed_managed_files_become_obsolete_with_their_hashes(self):
        history = ManifestHistory(("fntv-mpv-v1",), {"scripts/removed.lua": HistoryFile("managed", (SHA256_DEF,))})
        previous = previous_manifest(obsolete=[{"path": "scripts/gone-long-ago.lua", "knownHashes": [SHA256_GHI]}])

        manifest = self.build(history, previous)

        self.assertEqual([(o.path, o.known_hashes) for o in manifest.obsolete], [
            ("scripts/gone-long-ago.lua", (SHA256_GHI,)),
            ("scripts/removed.lua", (SHA256_DEF,)),
        ])

    def test_removed_config_and_seed_files_are_kept_by_the_client(self):
        history = ManifestHistory(("fntv-mpv-v1",), {
            "script-opts/removed.conf": HistoryFile("config", (SHA256_DEF,)),
            "removed-history.json": HistoryFile("seed", (SHA256_DEF,)),
        })

        self.assertEqual(self.obsolete_paths(self.build(history)), [])

    def test_the_previous_manifest_role_wins_over_the_history_role(self):
        history = ManifestHistory(("fntv-mpv-v1",), {"became-managed.conf": HistoryFile("config", (SHA256_ABC,))})
        previous = previous_manifest(files=[{"path": "became-managed.conf", "sha256": SHA256_DEF,
                                             "role": "managed", "knownHashes": [SHA256_DEF]}])

        self.assertEqual(self.obsolete_paths(self.build(history, previous)), ["became-managed.conf"])

    def test_committed_history_is_well_formed(self):
        history = load_history(PROJECT_ROOT / "manifest-history.json")

        self.assertTrue(history.archives)
        self.assertEqual(list(history.archives), sorted(set(history.archives)))
        for path, entry in history.files.items():
            self.assertEqual(list(entry.hashes), sorted(set(entry.hashes)), path)
            for h in entry.hashes:
                self.assertRegex(h, "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
