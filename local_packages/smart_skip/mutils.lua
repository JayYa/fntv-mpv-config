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

local mp        = require('mp')
local utils     = require('mp.utils')
local msg       = require('mp.msg')

local mutils    = {}

mutils.SCRIPT   = mp.get_script_name()
-- 用 mpv 提供的方式拿配置文件路径
local conf_dir  = mp.command_native({ "expand-path", "~~/script-opts" })
local conf_path = conf_dir .. "/" .. mutils.SCRIPT .. ".conf"

function mutils.to_json(tbl)
    -- utils.format_json 成功时返回 1 个值；失败时返回 (nil, "error")
    local s, err = utils.format_json(tbl)
    if not s then return nil, err end
    return s
end

function mutils.dur() return mp.get_property_number('duration', 0) or 0 end

function mutils.timepos() return mp.get_property_number('time-pos', 0) or 0 end

-- 在OSD上显示消息
function mutils.show_message(text, duration)
    duration = duration or 3 -- 默认显示3秒
    -- 设置OSD样式和对齐方式
    local ass = mp.get_property_osd("osd-ass-cc/0")
    -- {\\an1} 表示左下角对齐，{\\an2} 表示底部居中对齐
    local styled_text = ass .. "{\\an1}" .. text
    mp.osd_message(styled_text, duration)
end

-- 获取章节列表
function mutils.get_chapter_list()
    local chapters = mp.get_property_native('chapter-list')
    if not chapters then return nil end
    return chapters
end

-- 跳过一次：如果当前位置在 [a,b] 内，立即 seek 到 b
function mutils.skip_if_in(curr_pos, a, b, why)
    if curr_pos >= a and curr_pos <= b then
        mutils.show_message(why, 2)
        mp.set_property_number('time-pos', b)
        return true
    end
    return false
end

-- 提取 path 中的 id 以及原始 query string
function mutils.extract_id_and_query(url)
    -- 提取 id （playvideo/后到 ? 前）
    local id = url:match("/playvideo/([^%?]+)")
    -- 提取 query string （? 后的部分）
    local query = url:match("%?(.*)")

    return id, query
end

-- 提取 path 的 origin（scheme://host:port），skipinfo 请求发往同一个 Proxy
function mutils.extract_origin(url)
    return url:match("^(https?://[^/%?#]+)")
end

-- 目录不存在时创建；Windows 没有 mkdir -p，改走 cmd 的 mkdir（会自动建中间目录）
local function ensure_dir(dir)
    if utils.file_info(dir) then return end
    local args
    if package.config:sub(1, 1) == "\\" then
        args = { "cmd", "/d", "/c", "mkdir", (dir:gsub("/", "\\")) }
    else
        args = { "mkdir", "-p", dir }
    end
    mp.command_native({ name = "subprocess", args = args, playback_only = false })
end

-- 持久化用户配置（整份写回 script-opts/<脚本名>.conf）
function mutils.save_options(opts)
    ensure_dir(utils.split_path(conf_path))

    local f, err = io.open(conf_path, "w+")
    if not f then
        msg.error("无法写入配置: " .. tostring(err))
        return
    end

    for k, v in pairs(opts) do
        local val
        if type(v) == "boolean" then
            val = v and "yes" or "no"
        else
            val = tostring(v)
        end
        f:write(string.format("%s=%s\n", k, val))
    end

    f:close()
    msg.info("配置已保存到 " .. conf_path)
end

-- 解析为数字
function mutils.parse_number(v)
    if type(v) ~= 'string' then return nil end
    local trimmed = v:match('^%s*(.-)%s*$')
    if trimmed == '' then return nil end
    return tonumber(trimmed)
end

-- 解析整数
function mutils.parse_integer(v)
    local n = mutils.parse_number(v)
    if not n or n ~= math.floor(n) then return nil end
    return n
end

return mutils
