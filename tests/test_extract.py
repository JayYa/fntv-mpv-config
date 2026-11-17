import io
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

from src.extract import ExtractError, archive_format, extract_archive


class TestExtractArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_tar(self, name, members):
        path = self.tmp / name
        with tarfile.open(path, "w:gz") as tar:
            for member_name, data in members.items():
                info = tarfile.TarInfo(member_name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def test_formats_are_recognised_by_extension(self):
        self.assertEqual(archive_format(Path("a.zip")), "zip")
        self.assertEqual(archive_format(Path("A.7Z")), "7z")
        self.assertEqual(archive_format(Path("a-1.0.tar.gz")), "tar.gz")
        self.assertEqual(archive_format(Path("a.tar")), "tar")
        self.assertIsNone(archive_format(Path("a.gz")))
        self.assertIsNone(archive_format(Path("main.lua")))

    def test_tar_gz_is_extracted(self):
        archive = self.write_tar("plugin.tar.gz", {"plugin/main.lua": b"-- plugin"})

        extract_archive(archive, self.tmp / "out")

        self.assertEqual((self.tmp / "out" / "plugin" / "main.lua").read_bytes(), b"-- plugin")

    def test_tar_members_outside_the_target_are_refused(self):
        archive = self.write_tar("evil.tar.gz", {"../escaped.txt": b"x"})

        with self.assertRaises(ExtractError):
            extract_archive(archive, self.tmp / "out")
        self.assertFalse((self.tmp / "escaped.txt").exists())

    def test_unknown_extension_fails(self):
        archive = self.tmp / "plugin.lua"
        archive.write_text("--")

        with self.assertRaisesRegex(ExtractError, "不支持"):
            extract_archive(archive, self.tmp / "out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
