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

local OSD_ALIGN_BOTTOM_LEFT = "{\\an1}"

mutils.SCRIPT   = mp.get_script_name()
local conf_dir  = mp.command_native({ "expand-path", "~~/script-opts" })
local conf_path = conf_dir .. "/" .. mutils.SCRIPT .. ".conf"

function mutils.dur() return mp.get_property_number('duration', 0) or 0 end

function mutils.timepos() return mp.get_property_number('time-pos', 0) or 0 end

function mutils.show_message(text, duration)
    duration = duration or 3
    local ass = mp.get_property_osd("osd-ass-cc/0")
    local styled_text = ass .. OSD_ALIGN_BOTTOM_LEFT .. text
    mp.osd_message(styled_text, duration)
end

function mutils.get_chapter_list()
    local chapters = mp.get_property_native('chapter-list')
    if not chapters then return nil end
    return chapters
end

function mutils.skip_if_in(curr_pos, a, b, why)
    if curr_pos >= a and curr_pos <= b then
        mutils.show_message(why, 2)
        mp.set_property_number('time-pos', b)
        return true
    end
    return false
end

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

function mutils.parse_number(v)
    if type(v) ~= 'string' then return nil end
    local trimmed = v:match('^%s*(.-)%s*$')
    if trimmed == '' then return nil end
    return tonumber(trimmed)
end

function mutils.parse_integer(v)
    local n = mutils.parse_number(v)
    if not n or n ~= math.floor(n) then return nil end
    return n
end

return mutils
