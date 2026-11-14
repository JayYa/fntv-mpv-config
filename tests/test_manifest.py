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

from manifest import ManifestError, build_manifest, check_archive, history_from_archives, load_history


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
        empty_history = self.tmp / "empty-history.json"
        empty_history.write_text('{"archives": [], "files": {}}', encoding="utf-8")
        common = [sys.executable, script, str(good), "--history", str(empty_history)]
        passed = subprocess.run(
            common + ["--archive-version", ARCHIVE_VERSION],
            capture_output=True, text=True, encoding="utf-8",
        )
        failed = subprocess.run(
            common + ["--archive-version", "fntv-mpv-v20990101_000000"],
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

        self.assertEqual(history["archives"], ["fntv-mpv-v1", "fntv-mpv-v2"])
        self.assertEqual(history["files"], {
            "mpv.conf": sorted([SHA256_ABC, SHA256_DEF]),
            "scripts/old.lua": [SHA256_ABC],
        })

    def test_known_hashes_merge_history_and_removed_managed_paths_become_obsolete(self):
        portable = self.tmp / "portable_config"
        write_portable_config(portable, {"mpv.conf": b"ghi", "scripts/uosc/main.lua": b"abc"})
        history = {"archives": ["fntv-mpv-v1"], "files": {
            "mpv.conf": [SHA256_ABC],
            "scripts/uosc/main.lua": [SHA256_ABC, SHA256_DEF],
            "scripts/removed.lua": [SHA256_DEF],
            "script-opts/removed.conf": [SHA256_DEF],
        }}
        previous = {"files": [
            {"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
             "knownHashes": [SHA256_ABC, SHA256_DEF]},
        ], "obsolete": [{"path": "scripts/gone-long-ago.lua", "knownHashes": [SHA256_GHI]}]}

        manifest = build_manifest(portable, ARCHIVE_VERSION, {}, history=history,
                                  previous_manifest=previous)

        files = {f["path"]: f for f in manifest["files"]}
        self.assertEqual(files["mpv.conf"]["knownHashes"],
                         sorted([SHA256_ABC, SHA256_DEF, SHA256_GHI]))
        self.assertEqual(files["scripts/uosc/main.lua"]["knownHashes"],
                         sorted([SHA256_ABC, SHA256_DEF]))
        # 只有 managed 路径进 obsolete；删掉的 config 文件客户端一律保留
        self.assertEqual(manifest["obsolete"], [
            {"path": "scripts/gone-long-ago.lua", "knownHashes": [SHA256_GHI]},
            {"path": "scripts/removed.lua", "knownHashes": [SHA256_DEF]},
        ])

    def test_contract_fails_when_a_history_hash_is_dropped(self):
        checker = TestCheckArchive()
        checker.tmp = self.tmp
        history = {"archives": ["fntv-mpv-v1"], "files": {
            "input.conf": [SHA256_ABC],
            "scripts/removed.lua": [SHA256_DEF],
        }}

        def build_with_history(m):
            m.update(build_manifest(self.tmp / "build" / "portable_config", ARCHIVE_VERSION,
                                    {"uosc": "5.13.0"}, history=history))

        def drop_file_hash(m):
            build_with_history(m)
            entry = next(f for f in m["files"] if f["path"] == "input.conf")
            entry["knownHashes"].remove(SHA256_ABC)

        def drop_obsolete_hash(m):
            build_with_history(m)
            m["obsolete"] = []

        intact = checker.make_zip(edit_manifest=build_with_history)
        self.assertEqual(check_archive(intact, history=history), [])

        errors = check_archive(checker.make_zip(edit_manifest=drop_file_hash), history=history)
        self.assertTrue(any("input.conf" in e and SHA256_ABC in e for e in errors), errors)

        errors = check_archive(checker.make_zip(edit_manifest=drop_obsolete_hash), history=history)
        self.assertTrue(any("scripts/removed.lua" in e for e in errors), errors)

    def test_contract_checks_previous_manifest_hashes_too(self):
        checker = TestCheckArchive()
        checker.tmp = self.tmp
        previous = {"files": [{"path": "input.conf", "sha256": SHA256_GHI, "role": "config",
                               "knownHashes": [SHA256_GHI]}], "obsolete": []}

        errors = check_archive(checker.make_zip(), previous_manifest=previous)

        self.assertTrue(any("input.conf" in e and SHA256_GHI in e for e in errors), errors)

    def test_committed_history_covers_the_published_archives(self):
        history = load_history(PROJECT_ROOT / "manifest-history.json")

        self.assertEqual(history["archives"], [
            "fntv-mpv-v20260826_013404",
            "fntv-mpv-v20261108_203006",
            "fntv-mpv-v20261108_233327",
            "fntv-mpv-v20261110_224319",
            "fntv-mpv-v20261114_223600",
        ])
        self.assertIn("scripts/uosc/main.lua", history["files"])
        for path, hashes in history["files"].items():
            self.assertEqual(hashes, sorted(set(hashes)), path)
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

    def run_packaging(self, **run_kwargs):
        from src.main import MPVConfigManager

        if "history_path" not in run_kwargs:
            empty = self.tmp / "empty-history.json"
            empty.write_text('{"archives": [], "files": {}}', encoding="utf-8")
            run_kwargs["history_path"] = str(empty)

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
        ok = manager.run(package_timestamp="20261114_235959", **run_kwargs)
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

    def test_packaging_merges_history_and_previous_manifest(self):
        history_path = self.tmp / "history.json"
        history_path.write_text(json.dumps({"archives": ["fntv-mpv-v1"], "files": {
            "scripts/uosc/main.lua": [SHA256_ABC],
            "scripts/removed.lua": [SHA256_DEF],
        }}), encoding="utf-8")
        previous_path = self.tmp / "previous.json"
        previous_path.write_text(json.dumps({"files": [], "obsolete": [
            {"path": "scripts/older.lua", "knownHashes": [SHA256_GHI]},
        ]}), encoding="utf-8")

        ok, zip_path = self.run_packaging(history_path=str(history_path),
                                          previous_manifest_path=str(previous_path))

        self.assertTrue(ok)
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read("fntv-manifest.json"))
        files = {f["path"]: f for f in manifest["files"]}
        self.assertIn(SHA256_ABC, files["scripts/uosc/main.lua"]["knownHashes"])
        self.assertEqual(manifest["obsolete"], [
            {"path": "scripts/older.lua", "knownHashes": [SHA256_GHI]},
            {"path": "scripts/removed.lua", "knownHashes": [SHA256_DEF]},
        ])

    def test_packaging_fails_when_contract_fails(self):
        del self.dependencies["smart_skip"]

        ok, _ = self.run_packaging()

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
