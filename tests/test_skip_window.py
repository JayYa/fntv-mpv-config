"""smart_skip 的跳过窗口 module（skip_window.lua）

用 lupa 内嵌的 Lua 5.1 加载，和 mpv 的 LuaJIT 同一套语义；
能在没有 mp 的运行时里加载，本身就证明它不依赖 mpv。
"""

import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime

SMART_SKIP_DIR = Path(__file__).parent.parent / "local_packages" / "smart_skip"

CHAPTER_OPTS = {
    "min_skip_duration": 10, "max_skip_duration": 150,
    "max_scan_window": 600, "max_scan_percent": 15,
}


class SkipWindowTestCase(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(
            "package.path = ... .. '/?.lua;' .. package.path",
            SMART_SKIP_DIR.as_posix(),
        )
        self.sw = self.lua.require("skip_window")

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def to_py(self, value):
        """Lua 表转 Python：数组表转 list，其它转 dict，nil 转 None"""
        if value is None or not hasattr(value, "items"):
            return value
        items = dict(value.items())
        if items and all(isinstance(k, int) for k in items) and set(items) == set(range(1, len(items) + 1)):
            return [self.to_py(items[i]) for i in range(1, len(items) + 1)]
        return {k: self.to_py(v) for k, v in items.items()}

    def windows(self, duration, lens=None, mode="MANUAL", chapters=None):
        result = self.sw.windows(self.table({
            "duration": duration,
            "lens": lens or {"intro": 0, "outro": 0},
            "mode": self.sw.MODE[mode],
            "chapters": chapters or [],
            "chapter_opts": CHAPTER_OPTS,
        }))
        return self.to_py(result) or {}

    def lens_from_server(self, data):
        return self.to_py(self.sw.from_server(self.table(data) if data is not None else None))


class TestManualWindows(SkipWindowTestCase):
    def test_server_lengths_become_intro_and_outro_windows(self):
        lens = self.lens_from_server({"skipStart": 90, "skipEnd": 120})
        self.assertEqual(
            self.windows(1440, lens),
            {"intro": [0, 90], "outro": [1320, 1440]},
        )

    def test_outro_longer_than_half_the_video_is_dropped(self):
        lens = self.lens_from_server({"skipStart": 90, "skipEnd": 800})
        self.assertEqual(self.windows(1440, lens), {"intro": [0, 90]})

    def test_intro_overlapping_the_outro_is_dropped(self):
        self.assertEqual(
            self.windows(600, {"intro": 400, "outro": 250}),
            {"outro": [350, 600]},
        )

    def test_missing_or_broken_server_data_gives_no_window(self):
        for data in (None, {}, {"skipStart": -5, "skipEnd": "abc"}):
            with self.subTest(data=data):
                self.assertEqual(self.windows(1440, self.lens_from_server(data)), {})

    def test_no_window_until_duration_is_known(self):
        lens = self.lens_from_server({"skipStart": 90, "skipEnd": 120})
        self.assertEqual(self.windows(0, lens), {})


# 24 分钟一集：冷开场 0–30，片头 30–120，正片，片尾 1300–1390，彩蛋 1390–结尾
EPISODE = 1440
EPISODE_CHAPTERS = [
    {"title": "冷开场", "time": 0},
    {"title": "OP", "time": 30},
    {"title": "正片", "time": 120},
    {"title": "ED", "time": 1300},
    {"title": "彩蛋", "time": 1390},
]


class TestChapterWindows(SkipWindowTestCase):
    def test_chapter_mode_takes_the_op_and_ed_chapters_and_ignores_lengths(self):
        self.assertEqual(
            self.windows(EPISODE, {"intro": 60, "outro": 60}, mode="CHAPTER", chapters=EPISODE_CHAPTERS),
            {"intro": [30, 120], "outro": [1300, 1390]},
        )

    def test_chapter_mode_without_chapters_has_no_window(self):
        self.assertEqual(self.windows(EPISODE, {"intro": 60, "outro": 60}, mode="CHAPTER"), {})


class TestAutoWindows(SkipWindowTestCase):
    def test_auto_prefers_chapters_for_each_segment(self):
        self.assertEqual(
            self.windows(EPISODE, {"intro": 60, "outro": 60}, mode="AUTO", chapters=EPISODE_CHAPTERS),
            {"intro": [30, 120], "outro": [1300, 1390]},
        )

    def test_auto_fills_a_segment_without_chapter_from_its_length(self):
        only_op = EPISODE_CHAPTERS[:3]  # 片尾没有章节
        self.assertEqual(
            self.windows(EPISODE, {"intro": 60, "outro": 100}, mode="AUTO", chapters=only_op),
            {"intro": [30, 120], "outro": [1340, 1440]},
        )

    def test_removed_silence_mode_behaves_like_auto(self):
        result = self.to_py(self.sw.windows(self.table({
            "duration": EPISODE, "lens": {"intro": 60, "outro": 100}, "mode": 4,
            "chapters": EPISODE_CHAPTERS[:3], "chapter_opts": CHAPTER_OPTS,
        })))
        self.assertEqual(result, {"intro": [30, 120], "outro": [1340, 1440]})



class TestEdits(SkipWindowTestCase):
    NO_DATA = {"intro": 0, "outro": 0}

    def edit(self, lens, duration, kind, value):
        new_lens, reason = self.sw.edit(self.table(lens), duration, kind, value)
        return self.to_py(new_lens), reason

    def edit_at(self, lens, duration, kind, pos):
        new_lens, reason = self.sw.edit_at(self.table(lens), duration, kind, pos)
        return self.to_py(new_lens), reason

    def test_intro_can_be_typed_without_server_data(self):
        self.assertEqual(self.edit(self.NO_DATA, EPISODE, "intro", 90), ({"intro": 90, "outro": 0}, None))

    def test_rejected_edits_say_why(self):
        cases = [
            ({"intro": 0, "outro": 0}, "outro", 721, "片尾时长不能超过视频一半"),
            ({"intro": 0, "outro": 700}, "intro", 741, "片头与片尾不能重叠"),
            ({"intro": 800, "outro": 0}, "outro", 700, "片头与片尾不能重叠"),
            ({"intro": 0, "outro": 0}, "intro", -1, "必须 ≥ 0"),
        ]
        for lens, kind, value, reason in cases:
            with self.subTest(kind=kind, value=value):
                self.assertEqual(self.edit(lens, EPISODE, kind, value), (None, reason))

    def test_edits_need_a_known_duration(self):
        self.assertEqual(self.edit(self.NO_DATA, 0, "intro", 90), (None, "视频时长未知"))

    def test_boundary_edits_are_accepted(self):
        self.assertEqual(self.edit({"intro": 0, "outro": 0}, EPISODE, "outro", 720), ({"intro": 0, "outro": 720}, None))
        self.assertEqual(self.edit({"intro": 0, "outro": 700}, EPISODE, "intro", 740), ({"intro": 740, "outro": 700}, None))

    def test_marking_the_current_position_sets_whole_second_lengths(self):
        self.assertEqual(self.edit_at(self.NO_DATA, EPISODE, "intro", 95.7), ({"intro": 95, "outro": 0}, None))
        # 片尾从 1340.4 秒开始 → 离结尾 99.6 秒，取整为 99
        self.assertEqual(self.edit_at(self.NO_DATA, EPISODE, "outro", 1340.4), ({"intro": 0, "outro": 99}, None))

    def test_marking_the_current_position_is_validated_too(self):
        self.assertEqual(self.edit_at(self.NO_DATA, EPISODE, "outro", 300), (None, "片尾时长不能超过视频一半"))


if __name__ == "__main__":
    unittest.main()
