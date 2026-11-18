import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.download_manager import DownloadManager
from src.previous_manifest import PreviousManifestError, PreviousManifestFile, PreviousRelease, load_known_hashes
from tests.test_download_manager import API, LATEST_TAG, FakeGithub
from tests.test_manifest import SHA256_ABC, SHA256_DEF, SHA256_GHI, manifest_json

PROJECT_ROOT = Path(__file__).parent.parent
REPO = "JayYa/fntv-mpv-config"


def manifest_bytes(archive_version=LATEST_TAG, files=(), obsolete=()):
    return manifest_json(archive_version, files=files, obsolete=obsolete)


class TestLoadKnownHashes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.history = self.write("history.json", b'{"archives": [], "files": {}}')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def from_release(self, github):
        return load_known_hashes(self.history, PreviousRelease(REPO), DownloadManager(session=github))

    def test_the_latest_release_manifest_is_merged_into_the_known_hashes(self):
        github = FakeGithub({"mpv-package-20261115_010807.zip": b"zip",
                             "fntv-manifest.json": manifest_bytes(files=[
                                 {"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
                                  "knownHashes": [SHA256_DEF, SHA256_GHI]}])})

        known = self.from_release(github)

        self.assertEqual(known.of("mpv.conf"), {SHA256_DEF, SHA256_GHI})
        self.assertEqual(github.calls[0][0], f"{API}{REPO}/releases/latest")

    def test_a_latest_release_without_a_manifest_fails(self):
        github = FakeGithub({"mpv-package-20261115_010807.zip": b"zip"})

        with self.assertRaisesRegex(PreviousManifestError, "没有 fntv-manifest.json"):
            self.from_release(github)

    def test_a_release_manifest_of_another_archive_version_fails(self):
        github = FakeGithub({"fntv-manifest.json": manifest_bytes("fntv-mpv-v20261101_000000")})

        with self.assertRaisesRegex(PreviousManifestError, "fntv-mpv-v20261101_000000"):
            self.from_release(github)

    def test_a_release_manifest_without_files_fails(self):
        github = FakeGithub({"fntv-manifest.json": json.dumps({"archiveVersion": LATEST_TAG}).encode()})

        with self.assertRaisesRegex(PreviousManifestError, "files"):
            self.from_release(github)

    def test_a_manifest_file_is_merged_with_the_history(self):
        history = self.write("history.json", json.dumps(
            {"archives": ["v1"], "files": {"mpv.conf": {"role": "config", "hashes": [SHA256_ABC]}}}).encode())
        previous = self.write("previous.json", manifest_bytes(
            files=[{"path": "mpv.conf", "sha256": SHA256_DEF, "role": "config",
                    "knownHashes": [SHA256_DEF, SHA256_GHI]}],
            obsolete=[{"path": "scripts/old.lua", "knownHashes": [SHA256_ABC]}]))

        known = load_known_hashes(history, PreviousManifestFile(previous))

        self.assertEqual(known.of("mpv.conf"), {SHA256_ABC, SHA256_DEF, SHA256_GHI})
        self.assertEqual(known.of("scripts/old.lua"), {SHA256_ABC})
        self.assertEqual(known.previously_obsolete, {"scripts/old.lua"})

    def test_a_manifest_file_without_files_fails(self):
        previous = self.write("previous.json", b'{"archiveVersion": "x"}')

        with self.assertRaisesRegex(PreviousManifestError, "files"):
            load_known_hashes(self.history, PreviousManifestFile(previous))

    def test_a_manifest_entry_without_a_hash_fails_as_a_previous_manifest_error(self):
        previous = self.write("previous.json", manifest_bytes(
            files=[{"path": "mpv.conf", "role": "config", "knownHashes": [SHA256_DEF]}]))

        with self.assertRaisesRegex(PreviousManifestError, "mpv.conf 缺少 sha256"):
            load_known_hashes(self.history, PreviousManifestFile(previous))

    def test_a_manifest_file_that_is_not_json_fails(self):
        previous = self.write("previous.json", b"not json")

        with self.assertRaisesRegex(PreviousManifestError, "读取上一版清单失败"):
            load_known_hashes(self.history, PreviousManifestFile(previous))

    def test_without_arguments_only_the_committed_history_is_used(self):
        known = load_known_hashes()

        committed = json.loads((PROJECT_ROOT / "manifest-history.json").read_text(encoding="utf-8"))
        self.assertEqual(known.of("scripts/uosc/main.lua"),
                         set(committed["files"]["scripts/uosc/main.lua"]["hashes"]))
        self.assertEqual(known.previously_obsolete, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
