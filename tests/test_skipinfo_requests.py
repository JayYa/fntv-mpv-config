import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime

SMART_SKIP_DIR = Path(__file__).parent.parent / "local_packages" / "smart_skip"

PLAY_URL = "http://127.0.0.1:1999/v/api/v1/playvideo/abc123?token=xyz"

MPV_STUBS = """
local dir = ...
package.path = dir .. '/?.lua;' .. package.path
calls = { requests = {}, subprocess = {} }
package.preload['mp'] = function() return {
    get_script_name = function() return 'smart_skip' end,
    command_native = function() return '/mpv/script-opts' end,
    command_native_async = function(cmd, cb)
        table.insert(calls.subprocess, { cmd = cmd, cb = cb })
    end,
} end
package.preload['mp.utils'] = function() return {
    parse_json = function(s)
        if s == 'not json' then return nil, 'unexpected token' end
        return { body = s }
    end,
    format_json = function(t) return 'encoded-json' end,
} end
package.preload['mp.msg'] = function() return {
    error = function() end,
    info = function() end,
} end
"""

HTTP_ASYNC_STUB = """
package.preload['./http_async'] = function() return {
    request = function(opts, cb)
        table.insert(calls.requests, { opts = opts, cb = cb })
    end,
} end
"""


class SmartSkipLuaTestCase(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MPV_STUBS, SMART_SKIP_DIR.as_posix())
        self.calls = self.lua.eval("calls")

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def to_py(self, value):
        if value is None or not hasattr(value, "items"):
            return value
        items = dict(value.items())
        if items and all(isinstance(k, int) for k in items) and set(items) == set(range(1, len(items) + 1)):
            return [self.to_py(items[i]) for i in range(1, len(items) + 1)]
        return {k: self.to_py(v) for k, v in items.items()}


class TestSkipinfoApi(SmartSkipLuaTestCase):
    def setUp(self):
        super().setUp()
        self.lua.execute(HTTP_ASYNC_STUB)
        self.api = self.lua.require("api")

    def only_request(self):
        requests = self.to_py(self.calls.requests) or []
        self.assertEqual(len(requests), 1)
        return requests[0]

    def assertNoRequest(self):
        self.assertFalse(self.to_py(self.calls.requests))

    def test_saving_lens_posts_intro_and_outro_length_to_play_url_origin(self):
        def callback(resp, err):
            pass

        self.assertTrue(self.api.set_skip_time(PLAY_URL, 90, 120, callback))
        request = self.only_request()
        self.assertEqual(request["opts"], {
            "url": "http://127.0.0.1:1999/api/v1/skipinfo?token=xyz",
            "method": "POST",
            "data": {"guid": "abc123", "skipStart": 90, "skipEnd": 120},
            "json": True,
        })
        self.assertIs(request["cb"], callback)

    def test_reading_lens_gets_skipinfo_of_play_id_from_play_url_origin(self):
        def callback(resp, err):
            pass

        self.assertTrue(self.api.get_skip_time(PLAY_URL, callback))
        request = self.only_request()
        self.assertEqual(request["opts"], {
            "url": "http://127.0.0.1:1999/api/v1/skipinfo/abc123?token=xyz",
            "method": "GET",
            "json": True,
        })
        self.assertIs(request["cb"], callback)

    def test_negative_length_is_not_saved(self):
        for intro, outro in ((-1, 120), (90, -1)):
            with self.subTest(intro=intro, outro=outro):
                self.assertFalse(self.api.set_skip_time(PLAY_URL, intro, outro))
        self.assertNoRequest()

    def test_unusable_play_url_sends_no_request(self):
        cases = {
            "空地址": "",
            "没有 playvideo id": "http://127.0.0.1:1999/v/api/v1/other?token=xyz",
            "没有查询参数": "http://127.0.0.1:1999/v/api/v1/playvideo/abc123",
            "没有 origin": "/v/api/v1/playvideo/abc123?token=xyz",
        }
        for problem, url in cases.items():
            with self.subTest(problem):
                self.assertFalse(self.api.set_skip_time(url, 90, 120))
                self.assertIsNone(self.api.get_skip_time(url))
        self.assertNoRequest()


class TestHttpAsyncRequest(SmartSkipLuaTestCase):
    def setUp(self):
        super().setUp()
        self.http_async = self.lua.require("http_async")
        self.results = []

    def request(self, opts):
        self.http_async.request(self.table(opts), lambda value, err: self.results.append((self.to_py(value), err)))
        subprocess = self.to_py(self.calls.subprocess)
        self.assertEqual(len(subprocess), 1)
        return subprocess[0]

    def finish(self, subprocess, success, result=None, err=None):
        subprocess["cb"](success, self.table(result) if result is not None else None, err)
        self.assertEqual(len(self.results), 1)
        return self.results[0]

    def test_successful_response_is_decoded_as_json(self):
        subprocess = self.request({"url": "http://host/x", "method": "GET"})
        result = self.finish(subprocess, True, {"status": 0, "stdout": '{"code":0}'})
        self.assertEqual(result, ({"body": '{"code":0}'}, None))

    def test_undecodable_response_reports_decode_error(self):
        subprocess = self.request({"url": "http://host/x", "method": "GET"})
        result = self.finish(subprocess, True, {"status": 0, "stdout": "not json"})
        self.assertEqual(result, (None, "json decode failed: unexpected token"))

    def test_curl_failure_reports_exit_status_and_stderr(self):
        subprocess = self.request({"url": "http://host/x", "method": "GET"})
        result = self.finish(subprocess, True, {"status": 6, "stderr": "could not resolve"})
        self.assertEqual(result, (None, "curl exit=6 stderr=could not resolve"))

    def test_subprocess_failure_reports_error(self):
        subprocess = self.request({"url": "http://host/x", "method": "GET"})
        result = self.finish(subprocess, False, err="killed")
        self.assertEqual(result, (None, "subprocess failed: killed"))

    def test_table_body_is_sent_as_json(self):
        subprocess = self.request({"url": "http://host/x", "method": "POST", "data": {"a": 1}, "json": True})
        self.assertEqual(subprocess["cmd"]["args"], [
            "curl", "-sS", "--show-error", "-X", "POST", "http://host/x",
            "-H", "Content-Type: application/json", "--data", "encoded-json",
        ])


if __name__ == "__main__":
    unittest.main()
