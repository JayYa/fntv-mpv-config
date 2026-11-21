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

local mp = require('mp')
local msg = require('mp.msg')
local opt = require('mp.options')
local mutils = require('./mutils')
local skipinfo = require('./skipinfo')
local options = require('./options')
local skip_session = require('./skip_session')
local menu = require('./menu')
local opts = options.opts

local LABELS = { intro = "⏭️ 正在跳过片头...", outro = "⏭️ 正在跳过片尾..." }
local NO_FILE = "没有正在播放的文件"

local current = nil

local function media_facts()
    return {
        duration = mutils.dur(),
        chapters = mutils.get_chapter_list(),
        mode = opts.detect_mode,
        chapter_opts = opts,
    }
end

local deps = { skipinfo = skipinfo, facts = media_facts, log = msg }

local function on_file_loaded()
    if current then current:close() end
    current = skip_session.open(mp.get_property('path'), deps)
end

local function on_end_file()
    if current then current:close() end
    current = nil
end

local function on_time_pos(_, pos)
    if not pos or not current or not opts.enabled then return end
    local kind, target = current:tick(pos)
    if not kind then return end
    mutils.show_message(LABELS[kind], 2)
    mp.set_property_number('time-pos', target)
    msg.info(string.format("跳过%s 到 %s 秒, mode=%s", kind, tostring(target), tostring(opts.detect_mode)))
end

local function on_media_changed()
    if current then current:media_changed() end
end

local function manual_skip_forward()
    local duration = tonumber(opts.manual_skip_duration) or 0
    if duration <= 0 then
        msg.warn('manual_skip_duration 未设置或小于等于 0，跳过快捷键已忽略')
        return
    end

    mp.commandv('seek', tostring(duration), 'relative', 'exact')
    mutils.show_message(string.format('⏩ 快速跳过 %d 秒', duration), 2)
end

local session = {
    lens = function()
        return current and current:lens() or { intro = 0, outro = 0 }
    end,
    edit = function(kind, len)
        if not current then return false, NO_FILE end
        return current:edit(kind, len)
    end,
    edit_at = function(kind, pos)
        if not current then return false, NO_FILE end
        return current:edit_at(kind, pos)
    end,
    clear = function()
        if not current then return false, NO_FILE end
        return current:clear()
    end,
    refresh = on_media_changed,
}

local function init()
    opt.read_options(opts, mp.get_script_name())

    mp.register_event("file-loaded", on_file_loaded)
    mp.register_event("end-file", on_end_file)
    mp.observe_property("time-pos", "number", on_time_pos)
    mp.observe_property("duration", "number", on_media_changed)
    mp.observe_property("chapter-list", "native", on_media_changed)

    mp.add_key_binding(nil, 'manual-skip', manual_skip_forward)
    mp.register_script_message('manual-skip', manual_skip_forward)

    menu.init(session)
end

init()
