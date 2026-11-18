import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.manifest import HistoryFile, ManifestHistory
from src.package_archive import ContractTestFailed, KnownHashes, build_package_archive, is_package_archive_name
from tests.test_manifest import (
    CLIENT_LAYOUT,
    SHA256_ABC,
    SHA256_DEF,
    SHA256_GHI,
    VALID_PORTABLE_CONFIG,
    previous_manifest,
    write_portable_config,
)

PROJECT_ROOT = Path(__file__).parent.parent


class TestBuildPackageArchive(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.project = self.tmp / "out" / "fntv-mpv-config"
        write_portable_config(self.project / "portable_config", VALID_PORTABLE_CONFIG)
        (self.project / "mpv.exe").write_bytes(b"MZ")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, known=None, timestamp="20261114_235959"):
        return build_package_archive(self.project, {"uosc": "5.13.0"}, known or KnownHashes(),
                                     CLIENT_LAYOUT, timestamp=timestamp)

    def test_names_everything_after_the_timestamp(self):
        package = self.build()

        out = (self.tmp / "out").resolve()
        self.assertEqual(package.timestamp, "20261114_235959")
        self.assertEqual(package.archive_version, "fntv-mpv-v20261114_235959")
        self.assertEqual(package.path, out / "mpv-package-20261114_235959.zip")
        self.assertEqual(package.manifest_asset_path, out / "fntv-manifest.json")
        with zipfile.ZipFile(package.path) as z:
            in_zip = z.read("fntv-manifest.json")
            self.assertIn("mpv.exe", z.namelist())
        self.assertEqual(package.manifest_asset_path.read_bytes(), in_zip)
        self.assertEqual(json.loads(in_zip)["archiveVersion"], "fntv-mpv-v20261114_235959")

    def test_known_hashes_reach_the_manifest(self):
        known = KnownHashes.merge(
            ManifestHistory(("fntv-mpv-v1",), {
                "scripts/uosc/main.lua": HistoryFile("managed", (SHA256_ABC,)),
                "scripts/removed.lua": HistoryFile("managed", (SHA256_DEF,)),
            }),
            previous_manifest(obsolete=[{"path": "scripts/older.lua", "knownHashes": [SHA256_GHI]}]),
        )

        package = self.build(known)

        manifest = json.loads(package.manifest_asset_path.read_text(encoding="utf-8"))
        files = {f["path"]: f for f in manifest["files"]}
        self.assertIn(SHA256_ABC, files["scripts/uosc/main.lua"]["knownHashes"])
        self.assertEqual(manifest["obsolete"], [
            {"path": "scripts/older.lua", "knownHashes": [SHA256_GHI]},
            {"path": "scripts/removed.lua", "knownHashes": [SHA256_DEF]},
        ])

    def test_contract_failure_is_raised_with_every_error(self):
        (self.project / "portable_config" / "scripts" / "smart_skip" / "main.lua").unlink()

        with self.assertRaises(ContractTestFailed) as caught:
            self.build()

        self.assertTrue(any("scripts/smart_skip/main.lua" in e for e in caught.exception.errors),
                        caught.exception.errors)

    def test_default_timestamp_uses_beijing_time(self):
        utc = datetime(2026, 11, 14, 17, 8, 7, tzinfo=timezone.utc)
        with mock.patch("src.package_archive.datetime") as fake_datetime:
            fake_datetime.now.side_effect = lambda tz: utc.astimezone(tz)
            package = self.build(timestamp=None)

        self.assertEqual(package.timestamp, "20261115_010807")
        self.assertEqual(package.path.name, "mpv-package-20261115_010807.zip")

    def test_malformed_timestamp_is_rejected_before_writing(self):
        for bad in ["2026-11-10", "20261110_2243", "20261110_224319\n", "../x"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.build(timestamp=bad)
        self.assertEqual(sorted(p.name for p in (self.tmp / "out").iterdir()), ["fntv-mpv-config"])

    def test_recognizes_its_own_archive_names(self):
        self.assertTrue(is_package_archive_name("mpv-package-20261114_235959.zip"))
        for other in ["mpv-package-latest.zip", "mpv-package-20261114_235959.7z",
                      "fntv-manifest.json", "my-mpv-package-20261114_235959.zip"]:
            with self.subTest(other=other):
                self.assertFalse(is_package_archive_name(other))


if __name__ == "__main__":
    unittest.main(verbosity=2)
