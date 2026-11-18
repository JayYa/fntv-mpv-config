import shutil
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

from src.dependency_source import DependencySource, FetchError, remove_temp_dir
from src.package_config import GithubRelease, LocalArchive, LocalDir

UOSC = GithubRelease(owner="tomasklaen", repo="uosc", version="5.13.0",
                     filename_pattern="uosc", format="zip")


def write_zip(path: Path, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


def download_uosc(main_lua: str):
    def download(name, release, dest_dir):
        archive = dest_dir / "uosc.zip"
        write_zip(archive, {"scripts/uosc/main.lua": main_lua, "fonts/a.otf": ""})
        return archive
    return download


class TestDependencySource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.temp_dir = self.tmp / "temp"
        self.downloader = mock.Mock()
        self.source = DependencySource(self.temp_dir, downloader=self.downloader)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_local_folder_is_the_content_dir(self):
        plugin = self.tmp / "local_packages" / "plugin"
        plugin.mkdir(parents=True)
        (plugin / "main.lua").write_text("-- plugin")

        content = self.source.fetch("plugin", LocalDir(plugin))

        self.assertEqual(content, plugin)
        self.assertFalse(self.temp_dir.exists())

    def test_local_archive_loses_its_single_root_folder(self):
        write_zip(self.tmp / "plugin.zip", {"plugin-1.0/main.lua": "-- plugin"})

        content = self.source.fetch("plugin", LocalArchive(self.tmp / "plugin.zip"))

        self.assertEqual((content / "main.lua").read_text(), "-- plugin")
        self.assertTrue(content.is_relative_to(self.temp_dir / "plugin"))

    def test_missing_local_path_fails(self):
        with self.assertRaises(FetchError):
            self.source.fetch("plugin", LocalDir(self.tmp / "nowhere"))

    def test_download_is_unpacked_and_older_downloads_are_dropped(self):
        old = self.temp_dir / "uosc" / "uosc-old.zip"
        write_zip(old, {"old.lua": ""})
        self.downloader.download.side_effect = download_uosc("-- uosc")

        content = self.source.fetch("uosc", UOSC)

        self.assertTrue((content / "scripts" / "uosc" / "main.lua").is_file())
        self.assertFalse(old.exists())

    def test_offline_uses_the_cached_download(self):
        self.downloader.download.side_effect = download_uosc("-- cached")
        self.source.fetch("uosc", UOSC)
        self.downloader.reset_mock()
        offline = DependencySource(self.temp_dir, offline=True, downloader=self.downloader)

        content = offline.fetch("uosc", UOSC)

        self.assertEqual((content / "scripts" / "uosc" / "main.lua").read_text(), "-- cached")
        self.downloader.download.assert_not_called()

    def test_offline_fails_when_the_cached_download_is_another_version(self):
        self.downloader.download.side_effect = download_uosc("-- 5.12")
        self.source.fetch("uosc", replace(UOSC, version="5.12.0"))
        offline = DependencySource(self.temp_dir, offline=True, downloader=self.downloader)

        with self.assertRaises(FetchError) as caught:
            offline.fetch("uosc", UOSC)
        self.assertIn("5.12.0", str(caught.exception))
        self.assertIn("5.13.0", str(caught.exception))

    def test_offline_without_cache_fails(self):
        offline = DependencySource(self.temp_dir, offline=True, downloader=self.downloader)

        with self.assertRaises(FetchError):
            offline.fetch("uosc", UOSC)
        self.downloader.download.assert_not_called()

    def test_offline_fails_on_an_archive_left_without_its_source_record(self):
        write_zip(self.temp_dir / "uosc" / "uosc.zip", {"scripts/uosc/main.lua": "-- unknown"})
        offline = DependencySource(self.temp_dir, offline=True, downloader=self.downloader)

        with self.assertRaises(FetchError):
            offline.fetch("uosc", UOSC)

    def test_offline_fails_when_the_cached_archive_was_replaced(self):
        self.downloader.download.side_effect = download_uosc("-- cached")
        self.source.fetch("uosc", UOSC)
        write_zip(self.temp_dir / "uosc" / "uosc.zip", {"scripts/uosc/main.lua": "-- replaced by hand"})
        offline = DependencySource(self.temp_dir, offline=True, downloader=self.downloader)

        with self.assertRaises(FetchError):
            offline.fetch("uosc", UOSC)

    def test_clean_removes_the_temp_dir(self):
        write_zip(self.temp_dir / "uosc" / "uosc.zip", {"a": ""})

        remove_temp_dir(self.temp_dir)

        self.assertFalse(self.temp_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
