"""MPV 归档清单 fntv-manifest.json 的格式、生成、历史哈希，以及跑完整打包流程的端到端测试"""

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dependency_layout import load_layout
from src.manifest import (KnownHashes, Manifest, ManifestError, ManifestHistory, build_manifest,
                          history_from_archives, load_history)


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
            managed_dirs=["scripts/uosc", "scripts/smart_skip"],
        )

        self.assertEqual(manifest.archive_version, "fntv-mpv-v20261114_235959")
        self.assertEqual(manifest.components, {"uosc": "5.13.0", "smart_skip": "local"})
        self.assertEqual(manifest.provides, {"smart-skip.origin-from-play-url": 1})
        self.assertEqual(manifest.managed_dirs, ("scripts/uosc", "scripts/smart_skip"))
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

    def test_file_without_a_role_is_rejected(self):
        write_portable_config(self.portable, {"mpv.conf": b"", "notes.txt": b""})

        with self.assertRaisesRegex(ManifestError, "notes.txt"):
            build_manifest(self.portable, "fntv-mpv-v20261114_235959", {})

    def test_written_bytes_parse_back_to_the_same_manifest(self):
        write_portable_config(self.portable, {"mpv.conf": b"abc", "scripts/uosc/main.lua": b""})
        manifest = build_manifest(self.portable, ARCHIVE_VERSION, {"uosc": "5.13.0"},
                                  managed_dirs=["scripts/uosc"])

        data = manifest.to_bytes()

        self.assertEqual(Manifest.parse(data, "清单"), manifest)
        self.assertTrue(data.endswith(b"}\n"))
        self.assertNotIn(b"\r", data)
        self.assertEqual(list(json.loads(data)), ["formatVersion", "archiveVersion", "components",
                                                   "provides", "managedDirs", "files", "obsolete"])
        self.assertEqual(list(json.loads(data)["files"][0]), ["path", "sha256", "role", "knownHashes"])


def manifest_json(archive_version="fntv-mpv-v20261114_235959", files=(), obsolete=(),
                  **fields) -> bytes:
    """一份结构完整的清单，fields 覆盖或增加顶层字段"""
    data = {"formatVersion": 1, "archiveVersion": archive_version,
            "components": {"uosc": "5.13.0"}, "provides": {"smart-skip.origin-from-play-url": 1},
            "managedDirs": [], "files": list(files), "obsolete": list(obsolete)}
    data.update(fields)
    return json.dumps(data).encode()


def previous_manifest(files=(), obsolete=()) -> Manifest:
    return Manifest.parse(manifest_json(files=files, obsolete=obsolete), "上一版清单")


class TestParseManifest(unittest.TestCase):
    """清单的结构由 Manifest.parse 一处校验，一次报出全部结构错误"""

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

CLIENT_LAYOUT = load_layout(
    json.loads((Path(__file__).parent.parent / "package_cfg.json").read_text(encoding="utf-8"))["dependencies"],
    Path(__file__).parent.parent / "custom_config",
)


class TestShippedMpvConf(unittest.TestCase):
    """仓库里的 mpv.conf 分层：设置都搬进 fntv/defaults.conf，薄 mpv.conf 只引用它"""

    BASE_CONFIG_DIR = Path(__file__).parent.parent / "custom_config" / "base"

    @staticmethod
    def effective_lines(path):
        lines = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                lines.append(line)
        return lines

    def test_defaults_carry_the_original_settings(self):
        # 原 mpv.conf（44d2c9b）里的全部设置，顺序不变
        self.assertEqual(self.effective_lines(self.BASE_CONFIG_DIR / "fntv" / "defaults.conf"), [
            "[fntv-defaults]",
            "border=no",
            "cache-secs=120",
            "vo=gpu-next",
            "hwdec=auto-copy",
            "geometry=1280x720",
            "save-position-on-quit=yes",
            "gpu-shader-cache-dir=~~/.cache",
            "osd-level=1",
            "osd-duration=2000",
            "osd-font-size=36",
            "osd-bar=no",
            "log-file=~~/mpv.log",
        ])

    def test_thin_mpv_conf_only_pulls_in_defaults(self):
        self.assertEqual(self.effective_lines(self.BASE_CONFIG_DIR / "mpv.conf"), [
            'include="~~/fntv/defaults.conf"',
            "profile=fntv-defaults",
        ])


SHA256_DEF = "cb8379ac2098aa165029e3938a51da0bcecfc008fd6795f401178647f96c5b34"  # "def"
SHA256_GHI = "50ae61e841fac4e8f9e40baf2ad36ec868922ea48368c18f9535e47db56dd7fb"  # "ghi"


class TestHistory(unittest.TestCase):
    """历史哈希：从历史归档算出，并入清单的 knownHashes 和 obsolete"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def zip_of(self, name, entries):
        path = self.tmp / name
        with zipfile.ZipFile(path, "w") as z:
            for arcname, data in entries.items():
                z.writestr(arcname, data)
        return path

    def test_history_collects_every_hash_per_portable_config_path(self):
        old = self.zip_of("old.zip", {
            "mpv.exe": b"MZ",
            "portable_config/mpv.conf": b"abc",
            "portable_config\\scripts\\old.lua": b"abc",  # 旧 zip 可能用反斜杠
        })
        new = self.zip_of("new.zip", {
            "portable_config/mpv.conf": b"def",
            "portable_config/scripts/old.lua": b"abc",
        })

        history = history_from_archives([("fntv-mpv-v1", old), ("fntv-mpv-v2", new)])

        self.assertEqual(history, ManifestHistory(("fntv-mpv-v1", "fntv-mpv-v2"), {
            "mpv.conf": tuple(sorted([SHA256_ABC, SHA256_DEF])),
            "scripts/old.lua": (SHA256_ABC,),
        }))

    def test_the_committed_history_file_is_written_back_byte_for_byte(self):
        committed = PROJECT_ROOT / "manifest-history.json"

        self.assertEqual(load_history(committed).to_bytes(), committed.read_bytes())

    def test_a_malformed_history_file_is_rejected(self):
        path = self.tmp / "history.json"
        for data in ['{"archives": []}', '{"archives": [], "files": {"mpv.conf": "abc"}}', "not json"]:
            with self.subTest(data=data):
                path.write_text(data, encoding="utf-8")
                with self.assertRaisesRegex(ManifestError, "history.json"):
                    load_history(path)

    def test_known_hashes_merge_history_and_removed_managed_paths_become_obsolete(self):
        portable = self.tmp / "portable_config"
        write_portable_config(portable, {"mpv.conf": b"ghi", "scripts/uosc/main.lua": b"abc"})
        history = ManifestHistory(("fntv-mpv-v1",), {
            "mpv.conf": (SHA256_ABC,),
            "scripts/uosc/main.lua": (SHA256_ABC, SHA256_DEF),
            "scripts/removed.lua": (SHA256_DEF,),
            "script-opts/removed.conf": (SHA256_DEF,),
        })
        previous = previous_manifest(
            files=[{"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
                    "knownHashes": [SHA256_ABC, SHA256_DEF]}],
            obsolete=[{"path": "scripts/gone-long-ago.lua", "knownHashes": [SHA256_GHI]}])

        manifest = build_manifest(portable, ARCHIVE_VERSION, {},
                                  known=KnownHashes.merge(history, previous))

        files = {f.path: f for f in manifest.files}
        self.assertEqual(files["mpv.conf"].known_hashes,
                         tuple(sorted([SHA256_ABC, SHA256_DEF, SHA256_GHI])))
        self.assertEqual(files["scripts/uosc/main.lua"].known_hashes,
                         tuple(sorted([SHA256_ABC, SHA256_DEF])))
        # 只有 managed 路径进 obsolete；删掉的 config 文件客户端一律保留
        self.assertEqual([(o.path, o.known_hashes) for o in manifest.obsolete], [
            ("scripts/gone-long-ago.lua", (SHA256_GHI,)),
            ("scripts/removed.lua", (SHA256_DEF,)),
        ])

    def test_committed_history_covers_the_published_archives(self):
        history = load_history(PROJECT_ROOT / "manifest-history.json")

        self.assertEqual(list(history.archives), [
            "fntv-mpv-v20260826_013404",
            "fntv-mpv-v20261108_203006",
            "fntv-mpv-v20261108_233327",
            "fntv-mpv-v20261110_224319",
            "fntv-mpv-v20261114_223600",
        ])
        self.assertIn("scripts/uosc/main.lua", history.files)
        for path, hashes in history.files.items():
            self.assertEqual(list(hashes), sorted(set(hashes)), path)
            for h in hashes:
                self.assertRegex(h, "^[0-9a-f]{64}$")


PROJECT_ROOT = Path(__file__).parent.parent


class TestPackagingProducesManifest(unittest.TestCase):
    """端到端：用本地假插件跑打包流程，产出的 zip 带清单并通过契约测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        pkgs = self.tmp / "pkgs"
        write_portable_config(pkgs / "uosc", {
            "scripts/uosc/main.lua": b"-- uosc",
            "fonts/uosc_icons.otf": b"font",
        })
        write_portable_config(pkgs / "uosc_danmaku", {"main.lua": b"-- danmaku"})
        write_portable_config(pkgs / "thumbfast", {"thumbfast.lua": b"-- thumbfast"})
        write_portable_config(pkgs / "mpv", {"mpv.exe": b"MZ", "doc/manual.pdf": b"pdf"})
        write_portable_config(self.tmp / "custom", {
            "uosc_danmaku/danmaku-history.json": b'{"show_danmaku": true}',
            "uosc/script-opts/uosc.conf": b"",
            "base/mpv.conf": THIN_MPV_CONF,
            "base/fntv/defaults.conf": b"[fntv-defaults]\nvo=gpu-next\n",
        })
        self.dependencies = {
            "mpv": {
                "name": "mpv", "version": "20261108", "local_path": str(pkgs / "mpv"),
                "install_to": ".", "entry": "mpv.exe", "exclude_files": ["doc/**"],
            },
            "uosc": {
                "name": "uosc", "version": "5.13.0", "local_path": str(pkgs / "uosc"),
                "entry": "portable_config/scripts/uosc/main.lua",
                "managed_dir": "portable_config/scripts/uosc",
                "custom_install_rules": [
                    {"from": "scripts", "to": "portable_config/scripts", "filter": ["**/*"]},
                    {"from": "fonts", "to": "portable_config/fonts", "filter": ["**/*"]},
                ],
            },
            "uosc_danmaku": {
                "name": "uosc_danmaku", "version": "v2.1.0",
                "local_path": str(pkgs / "uosc_danmaku"),
                "install_to": "portable_config/scripts/uosc_danmaku",
                "entry": "portable_config/scripts/uosc_danmaku/main.lua",
                "managed_dir": "portable_config/scripts/uosc_danmaku",
            },
            "smart_skip": {
                "name": "smart_skip", "version": "local",
                "local_path": str(PROJECT_ROOT / "local_packages" / "smart_skip"),
                "install_to": "portable_config/scripts/smart_skip",
                "entry": "portable_config/scripts/smart_skip/main.lua",
                "managed_dir": "portable_config/scripts/smart_skip",
            },
            "thumbfast": {
                "name": "thumbfast", "version": "local", "local_path": str(pkgs / "thumbfast"),
                "entry": "portable_config/scripts/thumbfast.lua",
                "custom_install_rules": [
                    {"from": "", "to": "portable_config/scripts", "filter": ["thumbfast.lua"]},
                ],
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_empty_history(self) -> Path:
        path = self.tmp / "empty-history.json"
        path.write_text('{"archives": [], "files": {}}', encoding="utf-8")
        return path

    def write_package_config(self) -> Path:
        config_path = self.tmp / "package_cfg.json"
        config_path.write_text(json.dumps({
            "name": json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))["name"],
            "version": "1.0.0",
            "config": {
                "output_dir": str(self.tmp / "out"),
                "temp_dir": str(self.tmp / "temp"),
                "custom_config_dir": str(self.tmp / "custom"),
            },
            "dependencies": self.dependencies,
        }), encoding="utf-8")
        return config_path

    def run_packaging(self, session=None, **run_kwargs):
        from src.main import MPVConfigManager

        run_kwargs.setdefault("history_path", str(self.write_empty_history()))
        manager = MPVConfigManager(str(self.write_package_config()), "ERROR", session=session)
        result = manager.run(package_timestamp="20261114_235959", **run_kwargs)
        return result, self.tmp / "out" / "mpv-package-20261114_235959.zip"

    def test_build_result_points_at_what_was_built(self):
        result, zip_path = self.run_packaging()

        package = result.package
        self.assertEqual(package.timestamp, "20261114_235959")
        self.assertEqual(package.archive_version, "fntv-mpv-v20261114_235959")
        self.assertEqual(package.path, zip_path.resolve())
        self.assertEqual(package.manifest_asset_path, (zip_path.parent / "fntv-manifest.json").resolve())
        self.assertEqual(result.output_dir, (self.tmp / "out").resolve())
        self.assertTrue((result.project_dir / "portable_config").is_dir())
        self.assertEqual(result.processed_dependencies, (
            ("mpv", "20261108"), ("uosc", "5.13.0"), ("uosc_danmaku", "v2.1.0"),
            ("smart_skip", "local"), ("thumbfast", "local"),
        ))
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
            names = set(z.namelist())
        self.assertEqual(manifest["components"], {
            "mpv": "20261108", "uosc": "5.13.0", "uosc_danmaku": "v2.1.0",
            "smart_skip": "local", "thumbfast": "local",
        })
        self.assertEqual(manifest["managedDirs"],
                         ["scripts/uosc", "scripts/uosc_danmaku", "scripts/smart_skip"])
        self.assertIn("mpv.exe", names)
        self.assertNotIn("doc/manual.pdf", names)
        self.assertIn("portable_config/mpv.conf", names)
        self.assertIn("portable_config/fntv/defaults.conf", names)

    def test_disabled_dependency_is_left_out_and_its_managed_files_become_obsolete(self):
        self.dependencies["uosc_danmaku"]["enabled"] = False
        history = self.tmp / "history.json"
        history.write_text(json.dumps({"archives": ["fntv-mpv-v1"], "files": {
            "scripts/uosc_danmaku/main.lua": [SHA256_ABC],
            "danmaku-history.json": [SHA256_DEF],
        }}), encoding="utf-8")

        result, zip_path = self.run_packaging(history_path=str(history))

        self.assertIsNotNone(result)
        self.assertNotIn(("uosc_danmaku", "v2.1.0"), result.processed_dependencies)
        self.assertEqual(result.disabled_dependencies, (("uosc_danmaku", "v2.1.0"),))
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
            names = set(z.namelist())
        self.assertNotIn("uosc_danmaku", manifest["components"])
        self.assertNotIn("scripts/uosc_danmaku", manifest["managedDirs"])
        self.assertNotIn("portable_config/scripts/uosc_danmaku/main.lua", names)
        self.assertNotIn("portable_config/danmaku-history.json", names)
        obsolete = [entry["path"] for entry in manifest["obsolete"]]
        self.assertIn("scripts/uosc_danmaku/main.lua", obsolete)

    def test_known_hashes_of_the_latest_release_manifest_are_kept(self):
        from src.previous_manifest import PreviousRelease
        from tests.test_download_manager import LATEST_TAG, FakeGithub

        github = FakeGithub({"fntv-manifest.json": manifest_json(LATEST_TAG, files=[
            {"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
             "knownHashes": [SHA256_DEF, SHA256_GHI]}])})

        result, zip_path = self.run_packaging(session=github,
                                              previous=PreviousRelease("JayYa/fntv-mpv-config"))

        self.assertIsNotNone(result)
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
        mpv_conf = next(f for f in manifest["files"] if f["path"] == "mpv.conf")
        self.assertTrue({SHA256_DEF, SHA256_GHI} <= set(mpv_conf["knownHashes"]))

    def test_leftovers_from_an_earlier_build_stay_out_of_the_archive(self):
        project_name = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))["name"]
        stale = self.tmp / "out" / project_name / "portable_config" / "scripts" / "uosc" / "removed.lua"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"-- removed upstream")

        result, zip_path = self.run_packaging()

        self.assertIsNotNone(result)
        self.assertFalse(stale.exists())
        with zipfile.ZipFile(zip_path) as z:
            self.assertNotIn("portable_config/scripts/uosc/removed.lua", z.namelist())

    def test_command_line_writes_the_build_result(self):
        from unittest import mock
        from src.main import main

        result_file = self.tmp / "ci" / "build-result.json"
        argv = ["run.py", "--config", str(self.write_package_config()), "--log-level", "ERROR",
                "--package-timestamp", "20261114_235959", "--result-file", str(result_file),
                "--manifest-history", str(self.write_empty_history())]
        with mock.patch("sys.argv", argv), mock.patch("sys.stdout"):
            main()

        data = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(data["archiveVersion"], "fntv-mpv-v20261114_235959")
        self.assertTrue(Path(data["packagePath"]).is_file())
        notes = Path(data["releaseNotesPath"]).read_text(encoding="utf-8")
        self.assertIn("- 🔧 smart_skip (local)", notes)
        self.assertIn("└── portable_config/ # 便携式配置目录", notes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
