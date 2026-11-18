import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.package_archive import PackageArchive
from src.release import FILE_ATTRIBUTE_HIDDEN, BuildResult, Dependency, render_release_notes, write_build_result

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
    ├── script-opts/ # 插件配置目录
    │   ├── uosc_danmaku.conf # 弹幕插件配置
    │   └── uosc.conf # uosc插件配置
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
            "portable_config/script-opts/uosc.conf",
            "portable_config/script-opts/uosc_danmaku.conf",
            "portable_config/scripts/uosc/main.lua",
        ]
        for rel in files:
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        if sys.platform == "win32":
            import ctypes
            hidden = project / "portable_config" / "desktop.ini"
            hidden.write_bytes(b"x")
            ctypes.windll.kernel32.SetFileAttributesW(str(hidden), FILE_ATTRIBUTE_HIDDEN)
        package = self.tmp / "out" / "mpv-package-20261115_010807.zip"
        package.write_bytes(b"zip")
        asset = self.tmp / "out" / "fntv-manifest.json"
        asset.write_text("{}", encoding="utf-8")
        self.result = BuildResult(
            output_dir=self.tmp / "out",
            project_dir=project,
            processed_dependencies=(Dependency("mpv", "20261108"), Dependency("smart_skip", "")),
            package=PackageArchive(
                path=package,
                manifest_asset_path=asset,
                archive_version="fntv-mpv-v20261115_010807",
                timestamp="20261115_010807",
            ),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRenderReleaseNotes(ReleaseTestCase):

    def test_notes_name_the_disabled_dependencies(self):
        result = replace(self.result, disabled_dependencies=(Dependency("uosc_danmaku", "v2.1.0"),))

        notes = render_release_notes(result, GITHUB_ENV)

        self.assertIn("- 🔧 smart_skip\n\n已停用：uosc_danmaku\n", notes)
        self.assertNotIn("已停用", render_release_notes(self.result, GITHUB_ENV))

    def test_notes_on_github_actions_name_the_commit_and_link_its_docs(self):
        notes = render_release_notes(self.result, GITHUB_ENV)

        self.assertIn("📅 构建时间: 20261115_010807\n🔧 构建分支: release\n📝 提交ID: abc123\n", notes)
        self.assertIn("(https://github.com/JayYa/fntv-mpv-config/blob/abc123/README.md)", notes)
        self.assertIn("(https://github.com/JayYa/fntv-mpv-config/issues)", notes)

    def test_notes_list_dependencies_with_their_versions(self):
        notes = render_release_notes(self.result, GITHUB_ENV)

        self.assertIn("\n- 🔧 mpv (20261108)\n- 🔧 smart_skip\n", notes)

    def test_notes_name_the_package_and_show_its_visible_tree(self):
        notes = render_release_notes(self.result, GITHUB_ENV)

        self.assertIn("`mpv-package-20261115_010807.zip`", notes)
        self.assertIn(f"```\n{EXPECTED_TREE}\n```", notes)

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
            "releaseTitle": "FNTV MPV v20261115_010807",
            "artifactName": "fntv-mpv-config-20261115_010807",
            "outputDir": str(self.result.output_dir),
            "packagePath": str(self.result.package.path),
            "manifestAssetPath": str(self.result.package.manifest_asset_path),
            "releaseNotesPath": str(notes.resolve()),
        })
        self.assertEqual(notes.read_text(encoding="utf-8"),
                         render_release_notes(self.result, GITHUB_ENV))

    def test_rejects_a_build_without_package(self):
        unpacked = BuildResult(output_dir=self.result.output_dir, project_dir=self.result.project_dir)

        with self.assertRaises(ValueError):
            write_build_result(unpacked, self.tmp / "build-result.json", {})
        self.assertFalse((self.tmp / "build-result.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
