import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.build import BuildFailed, BuildScope, build
from src.package_config import load_package_config
from tests.test_manifest import (SHA256_ABC, SHA256_DEF, SHA256_GHI, THIN_MPV_CONF, manifest_json,
                                 write_portable_config)

PROJECT_ROOT = Path(__file__).parent.parent


class BuildTestCase(unittest.TestCase):
    """用本地假插件搭一份打包配置，跑真实的构建流程"""

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
                "config_roles": {"danmaku-history.json": "seed"},
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
            "base_config_roles": {"fntv/defaults.conf": "managed"},
            "dependencies": self.dependencies,
        }), encoding="utf-8")
        return config_path

    def build(self, **kwargs):
        kwargs.setdefault("history_path", self.write_empty_history())
        config = load_package_config(self.write_package_config())
        return build(config, package_timestamp="20261114_235959", **kwargs)

    @property
    def zip_path(self) -> Path:
        return self.tmp / "out" / "mpv-package-20261114_235959.zip"


class TestPackaging(BuildTestCase):

    def test_build_result_points_at_what_was_built(self):
        result = self.build()

        package = result.package
        self.assertEqual(package.timestamp, "20261114_235959")
        self.assertEqual(package.archive_version, "fntv-mpv-v20261114_235959")
        self.assertEqual(package.path, self.zip_path.resolve())
        self.assertEqual(package.manifest_asset_path, (self.zip_path.parent / "fntv-manifest.json").resolve())
        self.assertEqual(result.output_dir, (self.tmp / "out").resolve())
        self.assertTrue((result.project_dir / "portable_config").is_dir())
        self.assertEqual(result.processed_dependencies, (
            ("mpv", "20261108"), ("uosc", "5.13.0"), ("uosc_danmaku", "v2.1.0"),
            ("smart_skip", "local"), ("thumbfast", "local"),
        ))
        with zipfile.ZipFile(self.zip_path) as z:
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
            "scripts/uosc_danmaku/main.lua": {"role": "managed", "hashes": [SHA256_ABC]},
            "danmaku-history.json": {"role": "seed", "hashes": [SHA256_DEF]},
        }}), encoding="utf-8")

        result = self.build(history_path=history)

        self.assertNotIn(("uosc_danmaku", "v2.1.0"), result.processed_dependencies)
        self.assertEqual(result.disabled_dependencies, (("uosc_danmaku", "v2.1.0"),))
        with zipfile.ZipFile(self.zip_path) as z:
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

        self.build(session=github, previous=PreviousRelease("JayYa/fntv-mpv-config"))

        with zipfile.ZipFile(self.zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
        mpv_conf = next(f for f in manifest["files"] if f["path"] == "mpv.conf")
        self.assertTrue({SHA256_DEF, SHA256_GHI} <= set(mpv_conf["knownHashes"]))

    def test_leftovers_from_an_earlier_build_stay_out_of_the_archive(self):
        project_name = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))["name"]
        stale = self.tmp / "out" / project_name / "portable_config" / "scripts" / "uosc" / "removed.lua"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"-- removed upstream")

        self.build()

        self.assertFalse(stale.exists())
        with zipfile.ZipFile(self.zip_path) as z:
            self.assertNotIn("portable_config/scripts/uosc/removed.lua", z.namelist())


class TestBuildFails(BuildTestCase):

    def assert_fails(self, *expected_reasons, **kwargs):
        with self.assertRaises(BuildFailed) as caught:
            self.build(**kwargs)
        for reason in expected_reasons:
            self.assertTrue(any(reason in error for error in caught.exception.errors),
                            f"{reason!r} 不在 {caught.exception.errors}")
        return caught.exception

    def test_a_subset_of_dependencies_cannot_be_packaged(self):
        self.assert_fails("完整打包", dependencies=["uosc"])

        self.assertFalse((self.tmp / "out").exists())

    def test_unknown_and_disabled_dependency_names_are_all_reported(self):
        self.dependencies["thumbfast"]["enabled"] = False

        self.assert_fails("没有这些依赖项: nope", "这些依赖项已停用: thumbfast",
                          scope=BuildScope.INSTALL, dependencies=["thumbfast", "nope", "uosc"])

    def test_a_dependency_that_cannot_be_fetched_is_named_and_the_temp_dir_is_kept(self):
        broken = self.tmp / "pkgs" / "thumbfast.zip"
        broken.write_bytes(b"not a zip")
        self.dependencies["thumbfast"]["local_path"] = str(broken)
        leftover = self.tmp / "temp" / "mpv" / "mpv.zip"
        leftover.parent.mkdir(parents=True)
        leftover.write_bytes(b"cached")

        failure = self.assert_fails("处理依赖项 thumbfast 失败")

        self.assertIsNotNone(failure.__cause__)
        self.assertTrue(leftover.exists())

    def test_every_contract_test_error_is_reported(self):
        self.dependencies["uosc"]["entry"] = "portable_config/scripts/uosc/missing.lua"
        self.dependencies["thumbfast"]["entry"] = "portable_config/scripts/missing.lua"

        self.assert_fails("portable_config/scripts/uosc/missing.lua",
                          "portable_config/scripts/missing.lua")


class TestTempDir(BuildTestCase):

    def setUp(self):
        super().setUp()
        self.leftover = self.tmp / "temp" / "mpv" / "mpv.zip"
        self.leftover.parent.mkdir(parents=True)
        self.leftover.write_bytes(b"cached")

    def test_a_successful_build_removes_the_temp_dir(self):
        self.build(scope=BuildScope.FETCH)

        self.assertFalse((self.tmp / "temp").exists())

    def test_keep_temp_leaves_the_temp_dir(self):
        self.build(scope=BuildScope.FETCH, keep_temp=True)

        self.assertTrue(self.leftover.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
