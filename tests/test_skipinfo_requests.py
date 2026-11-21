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


class TestSkipinfo(SmartSkipLuaTestCase):
    def setUp(self):
        super().setUp()
        self.lua.execute(HTTP_ASYNC_STUB)
        self.skipinfo = self.lua.require("skipinfo")
        self.results = []

    def record(self, *result):
        self.results.append(tuple(self.to_py(value) for value in result))

    def fetch(self, url=PLAY_URL):
        self.skipinfo.fetch(url, self.record)

    def save(self, lens, url=PLAY_URL):
        self.skipinfo.save(url, self.table(lens), self.record)

    def only_request(self):
        requests = self.to_py(self.calls.requests) or []
        self.assertEqual(len(requests), 1)
        return requests[0]

    def respond(self, resp=None, err=None):
        self.only_request()["cb"](self.table(resp) if resp is not None else None, err)

    def only_result(self):
        self.assertEqual(len(self.results), 1)
        return self.results[0]

    def assertNoRequest(self):
        self.assertFalse(self.to_py(self.calls.requests))

    def assertPlayUrlRejected(self, url, message):
        self.fetch(url)
        self.save({"intro": 90, "outro": 120}, url)
        self.assertNoRequest()
        self.assertEqual(self.results, [(None, message), (False, message)])

    def test_saving_intro_and_outro_length_posts_skipinfo_to_play_url_origin(self):
        self.save({"intro": 90, "outro": 120})
        self.assertEqual(self.only_request()["opts"], {
            "url": "http://127.0.0.1:1999/api/v1/skipinfo?token=xyz",
            "method": "POST",
            "data": {"guid": "abc123", "skipStart": 90, "skipEnd": 120},
            "json": True,
        })

    def test_reading_intro_and_outro_length_gets_skipinfo_of_play_id_from_play_url_origin(self):
        self.fetch()
        self.assertEqual(self.only_request()["opts"], {
            "url": "http://127.0.0.1:1999/api/v1/skipinfo/abc123?token=xyz",
            "method": "GET",
            "json": True,
        })

    def test_server_skip_start_and_end_are_read_as_intro_and_outro_length(self):
        self.fetch()
        self.respond({"code": 0, "data": {"skipStart": 90, "skipEnd": 120}})
        self.assertEqual(self.only_result(), ({"intro": 90, "outro": 120}, None))

    def test_missing_or_broken_server_lengths_are_read_as_zero(self):
        for data in (None, {}, {"skipStart": -5, "skipEnd": "abc"}):
            with self.subTest(data=data):
                self.calls.requests = self.lua.table()
                self.results = []
                self.fetch()
                self.respond({"code": 0, "data": data})
                self.assertEqual(self.only_result(), ({"intro": 0, "outro": 0}, None))

    def test_server_error_code_fails_the_read(self):
        self.fetch()
        self.respond({"code": 404})
        self.assertEqual(self.only_result(), (None, "服务器返回错误码 404"))

    def test_request_error_fails_the_read(self):
        self.fetch()
        self.respond(err="curl exit=7 stderr=refused")
        self.assertEqual(self.only_result(), (None, "curl exit=7 stderr=refused"))

    def test_accepted_save_succeeds(self):
        self.save({"intro": 90, "outro": 120})
        self.respond({"code": 0})
        self.assertEqual(self.only_result(), (True, None))

    def test_server_error_code_fails_the_save(self):
        self.save({"intro": 90, "outro": 120})
        self.respond({"code": 500})
        self.assertEqual(self.only_result(), (False, "服务器返回错误码 500"))

    def test_negative_intro_length_is_not_saved(self):
        self.save({"intro": -1, "outro": 120})
        self.assertNoRequest()
        self.assertEqual(self.results, [(False, "无效的片头/片尾时长,片头:-1 片尾:120")])

    def test_negative_outro_length_is_not_saved(self):
        self.save({"intro": 90, "outro": -1})
        self.assertNoRequest()
        self.assertEqual(self.results, [(False, "无效的片头/片尾时长,片头:90 片尾:-1")])

    def test_empty_play_url_is_rejected(self):
        self.assertPlayUrlRejected("", "播放地址不能为空")

    def test_play_url_without_play_id_is_rejected(self):
        url = "http://127.0.0.1:1999/v/api/v1/other?token=xyz"
        self.assertPlayUrlRejected(url, "无法解析播放地址的查询参数:" + url)

    def test_play_url_without_query_is_rejected(self):
        url = "http://127.0.0.1:1999/v/api/v1/playvideo/abc123"
        self.assertPlayUrlRejected(url, "无法解析播放地址的查询参数:" + url)

    def test_play_url_without_origin_is_rejected(self):
        url = "/v/api/v1/playvideo/abc123?token=xyz"
        self.assertPlayUrlRejected(url, "无法解析播放地址的主机和端口:" + url)


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
