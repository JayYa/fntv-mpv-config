import unittest

from check_comments import find_comments

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


if __name__ == "__main__":
    unittest.main()
