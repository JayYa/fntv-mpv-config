"""依赖来源：每种依赖都经 fetch 变成内容目录"""
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.dependency_source import DependencySource, FetchError

NETWORK_DEP = {"url": "https://github.com/tomasklaen/uosc/releases", "version": "5.13.0",
               "filename_pattern": "uosc", "format": "zip"}


def write_zip(path: Path, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


class TestDependencySource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.temp_dir = self.tmp / "temp"
        self.downloader = mock.Mock()
        self.source = DependencySource(self.temp_dir, self.tmp, downloader=self.downloader)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_local_folder_is_the_content_dir(self):
        plugin = self.tmp / "local_packages" / "plugin"
        plugin.mkdir(parents=True)
        (plugin / "main.lua").write_text("-- plugin")

        content = self.source.fetch("plugin", {"local_path": "./local_packages/plugin"})

        self.assertEqual(content, plugin)
        self.assertFalse(self.temp_dir.exists())

    def test_local_archive_loses_its_single_root_folder(self):
        write_zip(self.tmp / "plugin.zip", {"plugin-1.0/main.lua": "-- plugin"})

        content = self.source.fetch("plugin", {"local_path": "plugin.zip"})

        self.assertEqual((content / "main.lua").read_text(), "-- plugin")
        self.assertTrue(content.is_relative_to(self.temp_dir / "plugin"))

    def test_missing_local_path_fails(self):
        with self.assertRaises(FetchError):
            self.source.fetch("plugin", {"local_path": "nowhere"})

    def test_download_is_unpacked_and_older_downloads_are_dropped(self):
        old = self.temp_dir / "uosc" / "uosc-old.zip"
        write_zip(old, {"old.lua": ""})

        def download(name, config, dest_dir):
            archive = dest_dir / "uosc.zip"
            write_zip(archive, {"scripts/uosc/main.lua": "-- uosc", "fonts/a.otf": ""})
            return archive
        self.downloader.download.side_effect = download

        content = self.source.fetch("uosc", NETWORK_DEP)

        self.assertTrue((content / "scripts" / "uosc" / "main.lua").is_file())
        self.assertFalse(old.exists())

    def test_offline_uses_the_cached_download(self):
        write_zip(self.temp_dir / "uosc" / "uosc.zip",
                  {"scripts/uosc/main.lua": "-- cached", "fonts/a.otf": ""})
        offline = DependencySource(self.temp_dir, self.tmp, offline=True, downloader=self.downloader)

        content = offline.fetch("uosc", NETWORK_DEP)

        self.assertEqual((content / "scripts" / "uosc" / "main.lua").read_text(), "-- cached")
        self.downloader.download.assert_not_called()

    def test_offline_without_cache_fails(self):
        offline = DependencySource(self.temp_dir, self.tmp, offline=True, downloader=self.downloader)

        with self.assertRaises(FetchError):
            offline.fetch("uosc", NETWORK_DEP)
        self.downloader.download.assert_not_called()

    def test_offline_needs_a_format_to_find_the_cache(self):
        offline = DependencySource(self.temp_dir, self.tmp, offline=True, downloader=self.downloader)

        with self.assertRaisesRegex(FetchError, "format"):
            offline.fetch("uosc", {**NETWORK_DEP, "format": ""})

    def test_clean_removes_the_temp_dir(self):
        write_zip(self.temp_dir / "uosc" / "uosc.zip", {"a": ""})

        self.source.clean()

        self.assertFalse(self.temp_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
