import unittest

from check_comments import find_comments, lowered_baseline, ratchet_errors

LICENSE_HEADER = "--[[\nMIT License\n\nCopyright (c) 2025\n]]\n"


def lines_of(path, source):
    return [line for line, _text in find_comments(path, source)]


class PythonCommentsTest(unittest.TestCase):
    def test_finds_full_line_and_trailing_comments(self):
        self.assertEqual(lines_of("a.py", "# one\nx = 1  # two\n"), [1, 2])

    def test_hash_inside_a_string_is_not_a_comment(self):
        self.assertEqual(lines_of("a.py", 'x = "# not a comment"\n'), [])

    def test_shebang_on_the_first_line_is_not_a_comment(self):
        self.assertEqual(lines_of("a.py", "#!/usr/bin/env python3\nx = 1\n"), [])


class LuaCommentsTest(unittest.TestCase):
    def test_finds_line_comments_with_their_line_numbers(self):
        self.assertEqual(lines_of("a.lua", "-- one\nlocal x = 1 -- two\n"), [1, 2])

    def test_long_comment_counts_once(self):
        self.assertEqual(lines_of("a.lua", "local x = 1\n--[==[\na\n]]\nb\n]==]\nlocal y = 2 -- after\n"), [2, 7])

    def test_dashes_inside_quoted_strings_are_not_comments(self):
        source = 'local a = { "--data", \'--x\', "say \\"--\\"" }\n'
        self.assertEqual(lines_of("a.lua", source), [])

    def test_dashes_inside_long_strings_are_not_comments(self):
        self.assertEqual(lines_of("a.lua", "local s = [[\n-- text\n]]\n-- real\n"), [4])

    def test_license_header_at_the_top_is_not_a_comment(self):
        self.assertEqual(lines_of("a.lua", LICENSE_HEADER + "local x = 1\n"), [])

    def test_license_text_after_code_is_a_comment(self):
        self.assertEqual(lines_of("a.lua", "local x = 1\n" + LICENSE_HEADER), [2])


class RatchetTest(unittest.TestCase):
    def test_more_comments_than_the_baseline_fail(self):
        errors = ratchet_errors({"a.py": 2}, {"a.py": 1})
        self.assertEqual(len(errors), 1)
        self.assertIn("基线只允许 1 条", errors[0])

    def test_a_file_missing_from_the_baseline_allows_no_comments(self):
        self.assertIn("基线只允许 0 条", ratchet_errors({"new.lua": 1}, {})[0])

    def test_fewer_comments_than_the_baseline_ask_for_an_update(self):
        self.assertIn("--update", ratchet_errors({}, {"a.py": 1})[0])

    def test_matching_the_baseline_passes(self):
        self.assertEqual(ratchet_errors({"a.py": 1}, {"a.py": 1}), [])

    def test_update_lowers_the_baseline_and_drops_clean_files(self):
        self.assertEqual(lowered_baseline({"a.py": 1, "b.py": 0}, {"a.py": 3, "b.py": 2}), {"a.py": 1})

    def test_update_never_raises_the_baseline(self):
        with self.assertRaisesRegex(ValueError, "a.py"):
            lowered_baseline({"a.py": 2}, {"a.py": 1})


if __name__ == "__main__":
    unittest.main()
