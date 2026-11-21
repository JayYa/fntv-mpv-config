--[[
MIT License

Copyright (c) 2025 Tag mig hånden

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

GitHub: https://github.com/QiaoKes/fntv-mpv-config
]]

local http_async = require('./http_async')

local skipinfo = {}

local function nonneg(v)
    v = tonumber(v)
    if not v or v < 0 then return 0 end
    return v
end

local function lens_from(data)
    if type(data) ~= "table" then return { intro = 0, outro = 0 } end
    return { intro = nonneg(data.skipStart), outro = nonneg(data.skipEnd) }
end

local function target(play_url)
    if not play_url or play_url == "" then
        return nil, "播放地址不能为空"
    end

    local id = play_url:match("/playvideo/([^%?]+)")
    local query = play_url:match("%?(.*)")
    if not query or not id then
        return nil, "无法解析播放地址的查询参数:" .. tostring(play_url)
    end

    local origin = play_url:match("^(https?://[^/%?#]+)")
    if not origin then
        return nil, "无法解析播放地址的主机和端口:" .. tostring(play_url)
    end

    return { origin = origin, id = id, query = query }
end

local function unwrap(resp, err)
    if err then return nil, err end
    if not resp then return nil, "服务器没有响应" end
    if resp.code ~= 0 then return nil, "服务器返回错误码 " .. tostring(resp.code) end
    return resp
end

function skipinfo.fetch(play_url, callback)
    local t, reason = target(play_url)
    if not t then return callback(nil, reason) end

    http_async.request({
        url = t.origin .. "/api/v1/skipinfo/" .. t.id .. "?" .. t.query,
        method = "GET",
        json = true
    }, function(resp, err)
        local ok, reason = unwrap(resp, err)
        if not ok then return callback(nil, reason) end
        callback(lens_from(ok.data), nil)
    end)
end

function skipinfo.save(play_url, lens, callback)
    if lens.intro < 0 or lens.outro < 0 then
        return callback(false, "无效的片头/片尾时长,片头:" .. lens.intro .. " 片尾:" .. lens.outro)
    end

    local t, reason = target(play_url)
    if not t then return callback(false, reason) end

    http_async.request({
        url = t.origin .. "/api/v1/skipinfo?" .. t.query,
        method = "POST",
        data = {
            guid = t.id,
            skipStart = lens.intro,
            skipEnd = lens.outro
        },
        json = true
    }, function(resp, err)
        local ok, reason = unwrap(resp, err)
        if not ok then return callback(false, reason) end
        callback(true, nil)
    end)
end

return skipinfo
