import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from src.download_manager import Asset, DownloadError, DownloadManager, select_asset
from src.package_config import GithubRelease

MPV = GithubRelease(owner="shinchiro", repo="mpv-winbuild-cmake", version="20261108",
                    filename_pattern="mpv-x86_64-{version}", format="7z")
UOSC = GithubRelease(owner="tomasklaen", repo="uosc", version="5.13.0",
                     filename_pattern="uosc", format="zip")
API = "https://api.github.com/repos/"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, body=b""):
        self.status_code = status_code
        self._json = json_data
        self._body = body

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        if isinstance(self._body, Exception):
            yield b"partial"
            raise self._body
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]


class FakeGithub:
    """假的 requests.Session：API 返回给定的资产列表，下载返回给定的内容"""

    def __init__(self, files, api_status=200, served=None):
        self.files = files
        self.api_status = api_status
        self.served = served or {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.startswith(API):
            if self.api_status != 200:
                return FakeResponse(self.api_status)
            tag = url.rsplit("/", 1)[1]
            return FakeResponse(json_data={"assets": [
                {"name": name, "size": len(body),
                 "browser_download_url": f"https://github.com/o/r/releases/download/{tag}/{name}"}
                for name, body in self.files.items()]})
        name = url.rsplit("/", 1)[1]
        return FakeResponse(body=self.served.get(name, self.files[name]))

    def downloads(self):
        return [url for url, _ in self.calls if not url.startswith(API)]


def assets(*names):
    return [Asset(name, f"https://github.com/o/r/releases/download/t/{name}", 1) for name in names]


class TestSelectAsset(unittest.TestCase):
    def test_exact_name_wins_over_other_matches(self):
        chosen = select_asset(UOSC, assets("uosc.conf", "uosc-src.zip", "uosc.zip"))

        self.assertEqual(chosen.name, "uosc.zip")

    def test_the_single_prefix_match_is_chosen(self):
        chosen = select_asset(MPV, assets("mpv-x86_64-20261108-git-55d3feb45c.7z",
                                          "mpv-x86_64-v3-20261108-git-55d3feb45c.7z",
                                          "mpv-dev-x86_64-20261108-git-55d3feb45c.7z"))

        self.assertEqual(chosen.name, "mpv-x86_64-20261108-git-55d3feb45c.7z")

    def test_several_prefix_matches_fail(self):
        with self.assertRaisesRegex(DownloadError, "2 个资产"):
            select_asset(MPV, assets("mpv-x86_64-20261108-a.7z", "mpv-x86_64-20261108-b.7z"))

    def test_no_match_fails_and_names_the_assets(self):
        with self.assertRaisesRegex(DownloadError, "ffmpeg-x86_64.7z"):
            select_asset(MPV, assets("ffmpeg-x86_64.7z", "mpv-x86_64-20261108.zip"))


class TestDownloadManager(unittest.TestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dest, ignore_errors=True)

    def download(self, github, release, **kwargs):
        return DownloadManager(session=github, **kwargs).download("dep", release, self.dest)

    def test_the_chosen_asset_is_downloaded(self):
        github = FakeGithub({"uosc.conf": b"conf", "uosc.zip": b"zip"})

        path = self.download(github, UOSC)

        self.assertEqual(path, self.dest / "uosc.zip")
        self.assertEqual(path.read_bytes(), b"zip")

    def test_no_matching_asset_downloads_nothing(self):
        github = FakeGithub({"ffmpeg-x86_64.7z": b"ff"})

        with self.assertRaises(DownloadError):
            self.download(github, MPV)
        self.assertEqual(github.downloads(), [])

    def test_rate_limit_is_reported_instead_of_guessing_a_name(self):
        github = FakeGithub({}, api_status=403)

        with self.assertRaisesRegex(DownloadError, "限流"):
            self.download(github, MPV)
        self.assertEqual(github.downloads(), [])

    def test_missing_release_is_reported(self):
        with self.assertRaisesRegex(DownloadError, "20261108"):
            self.download(FakeGithub({}, api_status=404), MPV)

    def test_a_file_of_the_asset_size_is_not_downloaded_again(self):
        (self.dest / "uosc.zip").write_bytes(b"zip")
        github = FakeGithub({"uosc.zip": b"zip"})

        self.download(github, UOSC)

        self.assertEqual(github.downloads(), [])

    def test_a_file_of_another_size_is_downloaded_again(self):
        (self.dest / "uosc.zip").write_bytes(b"truncated-old")
        github = FakeGithub({"uosc.zip": b"zip"})

        path = self.download(github, UOSC)

        self.assertEqual(path.read_bytes(), b"zip")
        self.assertEqual(len(github.downloads()), 1)

    def test_a_short_download_fails_and_leaves_no_file(self):
        github = FakeGithub({"uosc.zip": b"zip-full"}, served={"uosc.zip": b"zip"})

        with self.assertRaisesRegex(DownloadError, "字节"):
            self.download(github, UOSC)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_a_dropped_connection_fails_and_leaves_no_file(self):
        github = FakeGithub({"uosc.zip": b"zip"},
                            served={"uosc.zip": requests.ConnectionError("connection reset")})

        with self.assertRaisesRegex(DownloadError, "connection reset"):
            self.download(github, UOSC)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_proxy_applies_to_the_download_but_not_the_api(self):
        github = FakeGithub({"uosc.zip": b"zip"})

        self.download(github, UOSC, proxy_url="https://proxy.example/", enable_proxy=True)

        api_url, download_url = (url for url, _ in github.calls)
        self.assertTrue(api_url.startswith(API))
        self.assertEqual(download_url,
                         "https://proxy.example/https://github.com/o/r/releases/download/5.13.0/uosc.zip")

    def test_api_uses_the_token_when_set(self):
        github = FakeGithub({"uosc.zip": b"zip"})

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t0ken"}):
            self.download(github, UOSC)

        self.assertEqual(github.calls[0][1]["headers"]["Authorization"], "Bearer t0ken")

    def test_api_is_anonymous_without_a_token(self):
        github = FakeGithub({"uosc.zip": b"zip"})
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}

        with mock.patch.dict(os.environ, env, clear=True):
            self.download(github, UOSC)

        self.assertNotIn("Authorization", github.calls[0][1]["headers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
