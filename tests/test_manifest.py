"""MPV 归档清单 fntv-manifest.json 的生成和契约测试"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from manifest import ManifestError, build_manifest, check_archive


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
        )

        self.assertEqual(manifest["formatVersion"], 1)
        self.assertEqual(manifest["archiveVersion"], "fntv-mpv-v20261114_235959")
        self.assertEqual(manifest["components"], {"uosc": "5.13.0", "smart_skip": "local"})
        self.assertEqual(manifest["provides"], {"smart-skip.origin-from-play-url": 1})
        for d in ("scripts/uosc", "scripts/uosc_danmaku", "scripts/smart_skip"):
            self.assertIn(d, manifest["managedDirs"])
        self.assertEqual(manifest["obsolete"], [])

        files = {f["path"]: f for f in manifest["files"]}
        self.assertEqual(
            {path: f["role"] for path, f in files.items()},
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
        self.assertEqual(files["input.conf"]["sha256"], SHA256_EMPTY)
        self.assertEqual(files["mpv.conf"]["sha256"], SHA256_ABC)
        self.assertEqual(files["mpv.conf"]["knownHashes"], [SHA256_ABC])

    def test_file_without_a_role_is_rejected(self):
        write_portable_config(self.portable, {"mpv.conf": b"", "notes.txt": b""})

        with self.assertRaisesRegex(ManifestError, "notes.txt"):
            build_manifest(self.portable, "fntv-mpv-v20261114_235959", {})


VALID_PORTABLE_CONFIG = {
    "mpv.conf": b"vo=gpu-next\n",
    "input.conf": b"",
    "script-opts/uosc.conf": b"",
    "danmaku-history.json": b'{"show_danmaku": true}',
    "scripts/uosc/main.lua": b"-- uosc",
    "scripts/uosc_danmaku/main.lua": b"-- danmaku",
    "scripts/smart_skip/main.lua": b"-- smart skip",
    "scripts/thumbfast.lua": b"-- thumbfast",
}

ARCHIVE_VERSION = "fntv-mpv-v20261114_235959"


class TestCheckArchive(unittest.TestCase):
    """契约测试：对打包产出的 zip 检查清单"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_zip(self, portable_files=None, edit_manifest=None, extra_zip_files=None,
                 include_manifest=True):
        """按 portable_files 生成清单，可选地改清单或往 zip 里多塞文件，返回 zip 路径"""
        portable_files = VALID_PORTABLE_CONFIG if portable_files is None else portable_files
        root = self.tmp / "build"
        shutil.rmtree(root, ignore_errors=True)
        write_portable_config(root / "portable_config", portable_files)
        manifest = build_manifest(root / "portable_config", ARCHIVE_VERSION, {"uosc": "5.13.0"})
        if edit_manifest:
            edit_manifest(manifest)
        if include_manifest:
            (root / "fntv-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        write_portable_config(root, extra_zip_files or {})
        (root / "mpv.exe").write_bytes(b"MZ")
        zip_path = self.tmp / "mpv-package-20261114_235959.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in root.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(root).as_posix())
        return zip_path

    def assertFailsWith(self, zip_path, fragment, **kwargs):
        errors = check_archive(zip_path, **kwargs)
        self.assertTrue(
            any(fragment in e for e in errors),
            f"期望有包含 {fragment!r} 的错误，实际: {errors}",
        )

    def test_command_line_exit_code_reflects_result(self):
        script = str(PROJECT_ROOT / "check_archive.py")
        good = self.make_zip()
        passed = subprocess.run(
            [sys.executable, script, str(good), "--archive-version", ARCHIVE_VERSION],
            capture_output=True, text=True, encoding="utf-8",
        )
        failed = subprocess.run(
            [sys.executable, script, str(good), "--archive-version", "fntv-mpv-v20990101_000000"],
            capture_output=True, text=True, encoding="utf-8",
        )

        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("archiveVersion", failed.stdout + failed.stderr)

    def test_consistent_archive_passes(self):
        zip_path = self.make_zip()

        self.assertEqual(check_archive(zip_path, archive_version=ARCHIVE_VERSION), [])

    def test_missing_manifest_fails(self):
        self.assertFailsWith(self.make_zip(include_manifest=False), "fntv-manifest.json")

    def test_archive_version_must_equal_tag(self):
        self.assertFailsWith(
            self.make_zip(), "archiveVersion",
            archive_version="fntv-mpv-v20990101_000000",
        )

    def test_file_in_zip_but_not_in_manifest_fails(self):
        zip_path = self.make_zip(extra_zip_files={"portable_config/scripts/extra.lua": b"--"})

        self.assertFailsWith(zip_path, "scripts/extra.lua")

    def test_manifest_entry_missing_from_zip_fails(self):
        def add_ghost(m):
            m["files"].append({"path": "scripts/ghost.lua", "sha256": SHA256_EMPTY,
                               "role": "managed", "knownHashes": [SHA256_EMPTY]})

        self.assertFailsWith(self.make_zip(edit_manifest=add_ghost), "scripts/ghost.lua")

    def test_duplicate_manifest_entry_fails(self):
        def duplicate(m):
            m["files"].append(dict(m["files"][0]))

        self.assertFailsWith(self.make_zip(edit_manifest=duplicate), "重复")

    def test_wrong_hash_fails(self):
        def corrupt(m):
            next(f for f in m["files"] if f["path"] == "input.conf")["sha256"] = SHA256_ABC

        self.assertFailsWith(self.make_zip(edit_manifest=corrupt), "input.conf")

    def test_invalid_or_wrong_role_fails(self):
        def bad_role(m):
            next(f for f in m["files"] if f["path"] == "input.conf")["role"] = "user"

        def wrong_role(m):
            next(f for f in m["files"] if f["path"] == "danmaku-history.json")["role"] = "managed"

        self.assertFailsWith(self.make_zip(edit_manifest=bad_role), "input.conf")
        self.assertFailsWith(self.make_zip(edit_manifest=wrong_role), "danmaku-history.json")

    def test_client_entry_scripts_must_exist(self):
        files = dict(VALID_PORTABLE_CONFIG)
        del files["scripts/smart_skip/main.lua"]

        self.assertFailsWith(self.make_zip(portable_files=files), "scripts/smart_skip/main.lua")

    def test_provides_keys_must_be_complete(self):
        def drop_provides(m):
            m["provides"] = {}

        self.assertFailsWith(
            self.make_zip(edit_manifest=drop_provides), "smart-skip.origin-from-play-url"
        )

    def test_managed_dirs_must_be_complete(self):
        def drop_dir(m):
            m["managedDirs"].remove("scripts/uosc_danmaku")

        self.assertFailsWith(self.make_zip(edit_manifest=drop_dir), "scripts/uosc_danmaku")


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
        write_portable_config(self.tmp / "custom", {
            "uosc_danmaku/danmaku-history.json": b'{"show_danmaku": true}',
            "uosc/script-opts/uosc.conf": b"",
        })
        self.dependencies = {
            "uosc": {
                "name": "uosc", "version": "5.13.0", "local_path": str(pkgs / "uosc"),
                "custom_install_rules": [
                    {"from": "scripts", "to": "portable_config/scripts", "filter": ["**/*"]},
                    {"from": "fonts", "to": "portable_config/fonts", "filter": ["**/*"]},
                ],
            },
            "uosc_danmaku": {
                "name": "uosc_danmaku", "version": "v2.1.0",
                "local_path": str(pkgs / "uosc_danmaku"),
            },
            "smart_skip": {
                "name": "smart_skip", "version": "local",
                "local_path": str(PROJECT_ROOT / "local_packages" / "smart_skip"),
            },
            "thumbfast": {
                "name": "thumbfast", "version": "local", "local_path": str(pkgs / "thumbfast"),
                "custom_install_rules": [
                    {"from": "", "to": "portable_config/scripts", "filter": ["thumbfast.lua"]},
                ],
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_packaging(self):
        from src.main import MPVConfigManager

        config_path = self.tmp / "package_cfg.json"
        config_path.write_text(json.dumps({
            "name": "fntv-mpv-config",
            "version": "1.0.0",
            "config": {
                "output_dir": str(self.tmp / "out"),
                "temp_dir": str(self.tmp / "temp"),
                "custom_config_dir": str(self.tmp / "custom"),
            },
            "dependencies": self.dependencies,
        }), encoding="utf-8")
        manager = MPVConfigManager(str(config_path), "ERROR")
        ok = manager.run(package_timestamp="20261114_235959")
        return ok, self.tmp / "out" / "mpv-package-20261114_235959.zip"

    def test_package_contains_manifest_matching_its_tag(self):
        ok, zip_path = self.run_packaging()

        self.assertTrue(ok)
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
        self.assertEqual(manifest["archiveVersion"], "fntv-mpv-v20261114_235959")
        self.assertEqual(manifest["components"], {
            "uosc": "5.13.0", "uosc_danmaku": "v2.1.0",
            "smart_skip": "local", "thumbfast": "local",
        })
        self.assertEqual(check_archive(zip_path, archive_version="fntv-mpv-v20261114_235959"), [])

    def test_packaging_fails_when_contract_fails(self):
        del self.dependencies["smart_skip"]

        ok, _ = self.run_packaging()

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
