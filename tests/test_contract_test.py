"""契约测试：经 contract_test 和根目录的 check_archive.py 对安装包做的一致性检查"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contract_test import contract_test
from src.manifest import KnownHashes, ManifestHistory, build_manifest
from tests.test_manifest import (ARCHIVE_VERSION, CLIENT_LAYOUT, PROJECT_ROOT, SHA256_ABC, SHA256_DEF,
                                 SHA256_EMPTY, SHA256_GHI, THIN_MPV_CONF, VALID_PORTABLE_CONFIG,
                                 previous_manifest, write_portable_config)


class ArchiveFixture(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_zip(self, portable_files=None, edit_manifest=None, extra_zip_files=None,
                 include_manifest=True, include_mpv=True, known=None):
        """按 portable_files 生成清单，可选地改清单或往 zip 里多塞文件，返回 zip 路径"""
        portable_files = VALID_PORTABLE_CONFIG if portable_files is None else portable_files
        root = self.tmp / "build"
        shutil.rmtree(root, ignore_errors=True)
        write_portable_config(root / "portable_config", portable_files)
        manifest = json.loads(build_manifest(root / "portable_config", ARCHIVE_VERSION, {"uosc": "5.13.0"},
                                             known=known,
                                             managed_dirs=CLIENT_LAYOUT.manifest_managed_dirs).to_bytes())
        if edit_manifest:
            edit_manifest(manifest)
        if include_manifest:
            (root / "fntv-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        write_portable_config(root, extra_zip_files or {})
        if include_mpv:
            (root / "mpv.exe").write_bytes(b"MZ")
        zip_path = self.tmp / "mpv-package-20261114_235959.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in root.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(root).as_posix())
        return zip_path

    def assertFailsWith(self, zip_path, fragment, known=None, **kwargs):
        errors = contract_test(zip_path, known or KnownHashes(), CLIENT_LAYOUT, **kwargs)
        self.assertTrue(
            any(fragment in e for e in errors),
            f"期望有包含 {fragment!r} 的错误，实际: {errors}",
        )


class TestContractTest(ArchiveFixture):

    def test_consistent_archive_passes(self):
        zip_path = self.make_zip()

        self.assertEqual(contract_test(zip_path, KnownHashes(), CLIENT_LAYOUT, archive_version=ARCHIVE_VERSION), [])

    def test_manifest_asset_must_exist_and_equal_the_one_in_the_zip(self):
        zip_path = self.make_zip()
        asset = self.tmp / "fntv-manifest.json"
        with zipfile.ZipFile(zip_path) as z:
            asset.write_bytes(z.read("fntv-manifest.json"))
        self.assertEqual(contract_test(zip_path, KnownHashes(), CLIENT_LAYOUT, manifest_asset=asset), [])

        asset.write_bytes(asset.read_bytes() + b"\n")
        self.assertFailsWith(zip_path, "不同", manifest_asset=asset)
        self.assertFailsWith(zip_path, "不存在", manifest_asset=self.tmp / "nowhere.json")

    def test_missing_manifest_fails(self):
        self.assertFailsWith(self.make_zip(include_manifest=False), "fntv-manifest.json")

    def test_a_malformed_manifest_reports_its_structural_errors(self):
        def duplicate(m):
            m["files"].append(dict(m["files"][0]))

        zip_path = self.make_zip(edit_manifest=duplicate)
        errors = contract_test(zip_path, KnownHashes(), CLIENT_LAYOUT, archive_version="fntv-mpv-v20990101_000000",
                               manifest_asset=self.tmp / "nowhere.json")

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("重复", errors[0])

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

    def test_wrong_hash_fails(self):
        def corrupt(m):
            entry = next(f for f in m["files"] if f["path"] == "input.conf")
            entry["sha256"] = SHA256_ABC
            entry["knownHashes"].append(SHA256_ABC)

        self.assertFailsWith(self.make_zip(edit_manifest=corrupt), "input.conf")

    def test_role_must_follow_the_role_rules(self):
        def wrong_role(m):
            next(f for f in m["files"] if f["path"] == "danmaku-history.json")["role"] = "managed"

        self.assertFailsWith(self.make_zip(edit_manifest=wrong_role), "danmaku-history.json")

    def test_client_entry_scripts_must_exist(self):
        files = dict(VALID_PORTABLE_CONFIG)
        del files["scripts/smart_skip/main.lua"]

        self.assertFailsWith(self.make_zip(portable_files=files), "scripts/smart_skip/main.lua")

    def test_mpv_must_sit_at_the_archive_root(self):
        self.assertFailsWith(self.make_zip(include_mpv=False), "mpv.exe")

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

    def test_defaults_conf_is_managed_and_required(self):
        zip_path = self.make_zip()
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
        roles = {f["path"]: f["role"] for f in manifest["files"]}
        self.assertEqual(roles["fntv/defaults.conf"], "managed")

        files = dict(VALID_PORTABLE_CONFIG)
        del files["fntv/defaults.conf"]
        self.assertFailsWith(self.make_zip(portable_files=files), "fntv/defaults.conf")

    def assertMpvConfRejected(self, mpv_conf, defaults=None):
        files = dict(VALID_PORTABLE_CONFIG, **{"mpv.conf": mpv_conf})
        if defaults is not None:
            files["fntv/defaults.conf"] = defaults
        errors = contract_test(self.make_zip(portable_files=files), KnownHashes(), CLIENT_LAYOUT)
        self.assertTrue(errors, f"应拒绝: {mpv_conf!r} / {defaults!r}")

    def test_mpv_conf_layering_is_checked(self):
        # 首个有效行不是 include
        self.assertMpvConfRejected(
            b'vo=gpu\ninclude="~~/fntv/defaults.conf"\nprofile=fntv-defaults\n')
        # include 路径没有 ~~/ 前缀（会按进程当前目录解析）
        self.assertMpvConfRejected(b'include="fntv/defaults.conf"\nprofile=fntv-defaults\n')
        # include 写在 profile 段里
        self.assertMpvConfRejected(
            b'[x]\ninclude="~~/fntv/defaults.conf"\nprofile=fntv-defaults\n')
        # 没有紧跟 profile=fntv-defaults：默认值会排在用户设置之后
        self.assertMpvConfRejected(b'include="~~/fntv/defaults.conf"\nvo=gpu\n')
        # defaults.conf 的选项没放进 [fntv-defaults] 段
        self.assertMpvConfRejected(THIN_MPV_CONF, defaults=b"vo=gpu-next\n[fntv-defaults]\n")


class TestKnownHashesKept(ArchiveFixture):
    """已知哈希只增不减"""

    def test_contract_fails_when_a_history_hash_is_dropped(self):
        known = KnownHashes.merge(ManifestHistory(("fntv-mpv-v1",), {
            "input.conf": (SHA256_ABC,),
            "scripts/removed.lua": (SHA256_DEF,),
        }))

        def drop_file_hash(m):
            next(f for f in m["files"] if f["path"] == "input.conf")["knownHashes"].remove(SHA256_ABC)

        def drop_obsolete_hash(m):
            m["obsolete"] = []

        intact = self.make_zip(known=known)
        self.assertEqual(contract_test(intact, known, CLIENT_LAYOUT), [])

        errors = contract_test(self.make_zip(known=known, edit_manifest=drop_file_hash), known, CLIENT_LAYOUT)
        self.assertTrue(any("input.conf" in e and SHA256_ABC in e for e in errors), errors)

        errors = contract_test(self.make_zip(known=known, edit_manifest=drop_obsolete_hash), known,
                               CLIENT_LAYOUT)
        self.assertTrue(any("scripts/removed.lua" in e for e in errors), errors)

    def test_contract_checks_previous_manifest_hashes_too(self):
        previous = previous_manifest(files=[{"path": "input.conf", "sha256": SHA256_GHI, "role": "config",
                                             "knownHashes": [SHA256_GHI]}])

        self.assertFailsWith(self.make_zip(), SHA256_GHI, known=KnownHashes.merge(previous_manifest=previous))


class TestCheckArchiveCommandLine(ArchiveFixture):
    """根目录的 check_archive.py"""

    def run_script(self, zip_path, *args):
        empty_history = self.tmp / "empty-history.json"
        empty_history.write_text('{"archives": [], "files": {}}', encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "check_archive.py"), str(zip_path),
             "--history", str(empty_history), *args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_exit_code_reflects_result(self):
        good = self.make_zip()
        passed = self.run_script(good, "--archive-version", ARCHIVE_VERSION)
        failed = self.run_script(good, "--archive-version", "fntv-mpv-v20990101_000000")

        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("archiveVersion", failed.stdout + failed.stderr)

    def test_reports_an_unreadable_previous_manifest(self):
        previous = self.tmp / "previous.json"
        previous.write_text('{"archiveVersion": "x"}', encoding="utf-8")

        result = self.run_script(self.make_zip(), "--previous-manifest", str(previous))

        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少 files 列表", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_checks_the_release_manifest_asset(self):
        zip_path = self.make_zip()
        asset = self.tmp / "asset" / "fntv-manifest.json"
        asset.parent.mkdir()
        with zipfile.ZipFile(zip_path) as z:
            asset.write_bytes(z.read("fntv-manifest.json"))

        same = self.run_script(zip_path, "--manifest-asset", str(asset))
        missing = self.run_script(zip_path, "--manifest-asset", str(self.tmp / "nowhere" / "fntv-manifest.json"))
        asset.write_text("{}", encoding="utf-8")
        different = self.run_script(zip_path, "--manifest-asset", str(asset))

        self.assertEqual(same.returncode, 0, same.stdout + same.stderr)
        self.assertNotEqual(missing.returncode, 0)
        self.assertNotEqual(different.returncode, 0)
        self.assertIn("fntv-manifest.json", different.stdout)

    def test_reads_entries_from_the_given_config(self):
        config = self.tmp / "package_cfg.json"
        config.write_text(json.dumps({
            "name": "x",
            "config": {"output_dir": "out", "temp_dir": "temp", "custom_config_dir": "none"},
            "dependencies": {"extra": {
                "name": "extra", "version": "1", "url": "https://github.com/x/extra/releases",
                "filename_pattern": "extra", "format": "zip", "install_to": ".", "entry": "extra.exe",
            }},
        }), encoding="utf-8")

        result = self.run_script(self.make_zip(), "--config", str(config))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("extra.exe", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
