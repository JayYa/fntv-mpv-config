import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime

SMART_SKIP_DIR = Path(__file__).parent.parent / "local_packages" / "smart_skip"

PLAY_URL = "http://127.0.0.1:1999/v/api/v1/playvideo/abc123?token=xyz"
EPISODE = 1440
CHAPTER_OPTS = {
    "min_skip_duration": 10, "max_skip_duration": 150,
    "max_scan_window": 600, "max_scan_percent": 15,
}


class SkipSessionTestCase(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(
            "package.path = ... .. '/?.lua;' .. package.path",
            SMART_SKIP_DIR.as_posix(),
        )
        self.skip_session = self.lua.require("skip_session")
        self.mode = self.lua.require("skip_window").MODE
        self.media = {"duration": EPISODE, "chapters": [], "mode": self.mode.MANUAL, "chapter_opts": CHAPTER_OPTS}
        self.fetches = []
        self.saves = []
        self.errors = []
        self.deps = self.lua.table_from({
            "skipinfo": self.lua.table_from({
                "fetch": lambda url, cb: self.fetches.append((url, cb)),
                "save": lambda url, lens, cb: self.saves.append((url, self.to_py(lens), cb)),
            }),
            "facts": lambda: self.lua.table_from(self.media, recursive=True),
            "log": self.lua.table_from({
                "info": lambda message: None,
                "error": self.errors.append,
            }),
        })

    def to_py(self, value):
        if value is None or not hasattr(value, "items"):
            return value
        items = dict(value.items())
        if items and all(isinstance(k, int) for k in items) and set(items) == set(range(1, len(items) + 1)):
            return [self.to_py(items[i]) for i in range(1, len(items) + 1)]
        return {k: self.to_py(v) for k, v in items.items()}

    def open(self, path=PLAY_URL):
        return self.skip_session.open(path, self.deps)

    def server_answers(self, lens=None, err=None):
        _, cb = self.fetches[-1]
        cb(self.lua.table_from(lens) if lens is not None else None, err)

    def call(self, session, method, *args):
        return session[method](session, *args)

    def tick(self, session, pos):
        return self.call(session, "tick", pos)

    def lens(self, session):
        return self.to_py(self.call(session, "lens"))


class TestServerLengths(SkipSessionTestCase):
    def test_opening_a_file_reads_its_lengths_from_the_server(self):
        self.open()
        self.assertEqual([url for url, _ in self.fetches], [PLAY_URL])

    def test_server_lengths_become_skip_windows(self):
        session = self.open()
        self.server_answers({"intro": 90, "outro": 120})
        self.assertEqual(self.tick(session, 30), ("intro", 90))

    def test_failed_server_read_is_logged_and_leaves_no_window(self):
        session = self.open()
        self.server_answers(err="服务器返回错误码 404")
        self.assertEqual(self.errors, ["获取服务器片头/片尾时长失败: 服务器返回错误码 404"])
        self.assertIsNone(self.tick(session, 30))

    def test_server_answer_after_close_is_ignored(self):
        session = self.open()
        self.call(session, "close")
        self.server_answers({"intro": 90, "outro": 120})
        self.assertEqual(self.lens(session), {"intro": 0, "outro": 0})

    def test_server_answer_after_a_user_edit_is_ignored(self):
        session = self.open()
        self.call(session, "edit", "intro", 60)
        self.server_answers({"intro": 90, "outro": 120})
        self.assertEqual(self.lens(session), {"intro": 60, "outro": 0})


class TestAutoSkip(SkipSessionTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.open()
        self.server_answers({"intro": 90, "outro": 120})

    def test_position_inside_the_outro_window_skips_to_its_end(self):
        self.assertEqual(self.tick(self.session, 1330), ("outro", EPISODE))

    def test_position_outside_every_window_does_not_skip(self):
        self.assertIsNone(self.tick(self.session, 600))

    def test_each_segment_is_skipped_once_per_file(self):
        self.tick(self.session, 30)
        self.assertIsNone(self.tick(self.session, 30))

    def test_editing_a_skipped_segment_does_not_skip_it_again(self):
        self.tick(self.session, 30)
        self.call(self.session, "edit", "intro", 100)
        self.assertIsNone(self.tick(self.session, 95))


class TestMediaChanges(SkipSessionTestCase):
    def test_windows_wait_for_a_known_duration(self):
        self.media["duration"] = 0
        session = self.open()
        self.server_answers({"intro": 90, "outro": 120})
        self.assertIsNone(self.tick(session, 30))
        self.media["duration"] = EPISODE
        self.call(session, "media_changed")
        self.assertEqual(self.tick(session, 30), ("intro", 90))

    def test_detect_mode_change_takes_effect_on_media_change(self):
        session = self.open()
        self.server_answers({"intro": 90, "outro": 120})
        self.media["mode"] = self.mode.CHAPTER
        self.call(session, "media_changed")
        self.assertIsNone(self.tick(session, 30))


class TestUserEdits(SkipSessionTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.open()

    def test_accepted_edit_is_saved_to_the_server(self):
        self.assertIs(self.call(self.session, "edit", "intro", 60), True)
        self.assertEqual([(url, lens) for url, lens, _ in self.saves], [(PLAY_URL, {"intro": 60, "outro": 0})])

    def test_accepted_edit_moves_the_skip_window(self):
        self.call(self.session, "edit", "intro", 60)
        self.assertEqual(self.tick(self.session, 30), ("intro", 60))

    def test_marking_the_current_position_sets_the_length(self):
        self.call(self.session, "edit_at", "outro", 1340.4)
        self.assertEqual(self.lens(self.session), {"intro": 0, "outro": 99})

    def test_rejected_edit_says_why_and_is_not_saved(self):
        self.assertEqual(self.call(self.session, "edit", "outro", 721), (False, "片尾时长不能超过视频一半"))
        self.assertEqual(self.saves, [])

    def test_clearing_saves_zero_lengths(self):
        self.call(self.session, "edit", "intro", 60)
        self.call(self.session, "clear")
        self.assertEqual(self.saves[-1][1], {"intro": 0, "outro": 0})

    def test_failed_save_is_logged_and_the_edit_still_applies(self):
        self.call(self.session, "edit", "intro", 60)
        self.saves[-1][2](False, "服务器返回错误码 500")
        self.assertEqual(self.errors, ["保存片头/片尾时长失败: 服务器返回错误码 500"])
        self.assertEqual(self.lens(self.session), {"intro": 60, "outro": 0})


if __name__ == "__main__":
    unittest.main()
