"""构建结果：结果 JSON、Release 说明和 --result-file 参数"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from release import BuildResult, render_release_notes, write_build_result

GITHUB_ENV = {
    "GITHUB_SHA": "abc123",
    "GITHUB_REF_NAME": "release",
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "JayYa/fntv-mpv-config",
}

EXPECTED_TREE = """\
fntv-mpv-config/
├── mpv.exe # MPV播放器主程序
└── portable_config/ # 便携式配置目录
    ├── fonts/ # 字体文件目录
    │   └── uosc_icons.OTF # 字体文件
    ├── Input.conf # 快捷键配置
    ├── notes.txt
    └── scripts/ # 插件脚本目录
        └── uosc/ # uosc插件"""


class ReleaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        project = self.tmp / "out" / "fntv-mpv-config"
        files = [
            "mpv.exe",
            "portable_config/Input.conf",
            "portable_config/notes.txt",
            "portable_config/fonts/uosc_icons.OTF",
            # 第 4 层不再展开
            "portable_config/scripts/uosc/main.lua",
        ]
        for rel in files:
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        package = self.tmp / "out" / "mpv-package-20261115_010807.zip"
        package.write_bytes(b"zip")
        asset = self.tmp / "out" / "fntv-manifest.json"
        asset.write_text("{}", encoding="utf-8")
        self.result = BuildResult(
            output_dir=self.tmp / "out",
            project_dir=project,
            dependencies=[("mpv", "20261108"), ("smart_skip", "")],
            timestamp="20261115_010807",
            archive_version="fntv-mpv-v20261115_010807",
            package_path=package,
            manifest_asset_path=asset,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRenderReleaseNotes(ReleaseTestCase):

    def test_notes_on_github_actions(self):
        notes = render_release_notes(self.result, GITHUB_ENV)

        self.assertEqual(notes, f"""\
🎬 FNTV MPV - 自动构建包

📅 构建时间: 20261115_010807
🔧 构建分支: release
📝 提交ID: abc123

## 📦 本次构建包含
### 🎥 核心组件
- MPV播放器主程序
- 便携式配置文件结构
- 预配置的快捷键和播放设置

### 🔧 启用的插件/组件
- 🔧 mpv (20261108)
- 🔧 smart_skip

## 🚀 快速开始
1. 下载 `mpv-package-20261115_010807.zip` 文件
2. 解压到任意目录
3. 双击运行 `mpv.exe` 即可使用
4. 所有配置都是便携式的，无需安装

## 📁 目录结构
```
{EXPECTED_TREE}
```

## ⚙️ 配置管理
- 🎮 快捷键: `portable_config/input.conf`
- 🎨 UI设置: `portable_config/script-opts/uosc.conf`
- 💬 弹幕设置: `portable_config/script-opts/uosc_danmaku.conf`

## 🔗 相关链接
- 📖 [使用文档](https://github.com/JayYa/fntv-mpv-config/blob/abc123/README.md)
- 🐛 [问题反馈](https://github.com/JayYa/fntv-mpv-config/issues)
- 🔄 [配置更新](https://github.com/JayYa/fntv-mpv-config/releases)
""")

    def test_notes_outside_ci_omit_commit_branch_and_links(self):
        notes = render_release_notes(self.result, {})

        self.assertIn("📅 构建时间: 20261115_010807\n\n## 📦", notes)
        self.assertNotIn("构建分支", notes)
        self.assertNotIn("提交ID", notes)
        self.assertNotIn("相关链接", notes)
        self.assertTrue(notes.endswith("uosc_danmaku.conf`\n"), notes[-80:])

    def test_links_without_commit_skip_the_docs_link(self):
        env = dict(GITHUB_ENV)
        del env["GITHUB_SHA"]

        notes = render_release_notes(self.result, env)

        self.assertIn("问题反馈", notes)
        self.assertNotIn("使用文档", notes)


class TestWriteBuildResult(ReleaseTestCase):

    def test_writes_json_and_notes_side_by_side(self):
        path = write_build_result(self.result, self.tmp / "ci" / "build-result.json", GITHUB_ENV)

        data = json.loads(path.read_text(encoding="utf-8"))
        notes = self.tmp / "ci" / "release-notes.md"
        self.assertEqual(data, {
            "archiveVersion": "fntv-mpv-v20261115_010807",
            "timestamp": "20261115_010807",
            "outputDir": str(self.result.output_dir),
            "packagePath": str(self.result.package_path),
            "manifestAssetPath": str(self.result.manifest_asset_path),
            "releaseNotesPath": str(notes.resolve()),
        })
        self.assertEqual(notes.read_text(encoding="utf-8"),
                         render_release_notes(self.result, GITHUB_ENV))

    def test_rejects_a_build_without_package(self):
        unpacked = BuildResult(output_dir=self.result.output_dir, project_dir=self.result.project_dir)

        with self.assertRaises(ValueError):
            write_build_result(unpacked, self.tmp / "build-result.json", {})
        self.assertFalse((self.tmp / "build-result.json").exists())


class TestResultFileCli(unittest.TestCase):
    """--result-file 需要打包，解析参数时就拒绝矛盾组合"""

    def parse(self, argv):
        from src.main import create_cli_parser, parse_args
        return parse_args(create_cli_parser(), argv)

    def test_result_file_parsed(self):
        self.assertEqual(self.parse(["--result-file", "r.json"]).result_file, "r.json")
        self.assertIsNone(self.parse([]).result_file)

    def test_result_file_without_package_exits(self):
        for skip in ["--skip-package", "--skip-install"]:
            with self.subTest(skip=skip):
                with mock.patch("sys.stderr", new_callable=io.StringIO):
                    with self.assertRaises(SystemExit):
                        self.parse(["--result-file", "r.json", skip])


if __name__ == "__main__":
    unittest.main(verbosity=2)
