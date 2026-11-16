"""
下载与解压管理器的单元测试
"""
import unittest
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest import mock

from src.download_manager import DownloadManager
from src.extract_manager import ExtractManager


class TestDownloadManager(unittest.TestCase):
    """下载管理器测试"""

    def setUp(self):
        self.manager = DownloadManager()

    def _fake_release_response(self):
        response = mock.Mock()
        response.json.return_value = {"assets": [{"name": "mpv-x86_64-20261108-git-55d3feb45c.7z"}]}
        return response

    def test_github_api_uses_token_when_set(self):
        """设置 GITHUB_TOKEN 时 API 请求带认证头（CI 上避免匿名限流）"""
        env = {"GITHUB_TOKEN": "t0ken"}
        with mock.patch.dict(os.environ, env), \
                mock.patch("src.download_manager.requests.get", return_value=self._fake_release_response()) as get:
            name = self.manager._get_github_asset_filename(
                "shinchiro", "mpv-winbuild-cmake", "20261108", "mpv-x86_64-{version}", "7z")

        self.assertEqual(name, "mpv-x86_64-20261108-git-55d3feb45c.7z")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer t0ken")

    def test_github_api_anonymous_without_token(self):
        """没有 token 时仍可匿名请求（本地构建）"""
        with mock.patch.dict(os.environ, {}), \
                mock.patch("src.download_manager.requests.get", return_value=self._fake_release_response()) as get:
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GH_TOKEN", None)
            self.manager._get_github_asset_filename(
                "shinchiro", "mpv-winbuild-cmake", "20261108", "mpv-x86_64-{version}", "7z")

        self.assertNotIn("Authorization", get.call_args.kwargs["headers"])


class TestExtractManager(unittest.TestCase):
    """解压管理器测试"""

    def setUp(self):
        """设置测试环境"""
        self.manager = ExtractManager()

    def test_get_format(self):
        """测试格式识别"""
        self.assertEqual(self.manager._get_format(Path("test.zip")), "zip")
        self.assertEqual(self.manager._get_format(Path("test.7z")), "7z")
        self.assertEqual(self.manager._get_format(Path("test.tar.gz")), "gz")


if __name__ == '__main__':
    unittest.main()
