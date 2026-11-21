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

local msg = require('mp.msg')
local mutils = require('./mutils')
local http_async = require('./http_async')

local api = {}

local function skipinfo_target(play_url)
    if not play_url or play_url == "" then
        msg.error("播放地址不能为空")
        return nil
    end

    local id, query = mutils.extract_id_and_query(play_url)
    if not query or not id then
        msg.error("无法解析播放地址的查询参数:" .. tostring(play_url))
        return nil
    end

    local origin = mutils.extract_origin(play_url)
    if not origin then
        msg.error("无法解析播放地址的主机和端口:" .. tostring(play_url))
        return nil
    end

    return origin, id, query
end

function api.set_skip_time(play_url, intro, outro, callback)
    if intro < 0 or outro < 0 then
        msg.error("无效的片头/片尾时长,片头:" .. intro .. " 片尾:" .. outro)
        return false
    end

    local origin, id, query = skipinfo_target(play_url)
    if not origin then return false end

    http_async.request({
        url = origin .. "/api/v1/skipinfo?" .. query,
        method = "POST",
        data = {
            guid = id,
            skipStart = intro,
            skipEnd = outro
        },
        json = true
    }, callback)

    return true
end

function api.get_skip_time(play_url, callback)
    local origin, id, query = skipinfo_target(play_url)
    if not origin then return nil end

    http_async.request({
        url = origin .. "/api/v1/skipinfo/" .. id .. "?" .. query,
        method = "GET",
        json = true
    }, callback)

    return true
end

return api