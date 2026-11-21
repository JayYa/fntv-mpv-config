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
local utils = require('mp.utils')
local mutils = require('./mutils')
local api = require('./api')
local options = require('./options')
local skip_window = require('./skip_window')
local menu = require('./menu')
local opts = options.opts

local LABELS = { intro = "⏭️ 正在跳过片头...", outro = "⏭️ 正在跳过片尾..." }

local current = nil

local function recompute(state)
    state.windows = skip_window.windows({
        duration = mutils.dur(),
        lens = state.lens,
        mode = opts.detect_mode,
        chapters = mutils.get_chapter_list() or {},
        chapter_opts = opts,
    })
end

local function on_file_loaded()
    local state = {
        path = mp.get_property('path'),
        lens = { intro = 0, outro = 0 },
        edited = false,
        windows = {},
        auto_skipped_this_file = {},
    }
    current = state
    recompute(state)

    api.get_skip_time(state.path, function(resp, err)
        if current ~= state or state.edited then return end
        if err or not resp or resp.code ~= 0 then
            msg.error("获取服务器片头/片尾时长失败: " .. tostring(err or (resp and resp.code)))
            return
        end
        state.lens = skip_window.from_server(resp.data)
        recompute(state)
        msg.info(string.format("服务器片头/片尾时长: 片头 %s 秒, 片尾 %s 秒", state.lens.intro, state.lens.outro))
    end)
end

local function on_end_file()
    current = nil
end

local function on_time_pos(_, pos)
    local state = current
    if not pos or not state or not opts.enabled then return end
    for _, kind in ipairs({ 'intro', 'outro' }) do
        local w = state.windows[kind]
        if w and not state.auto_skipped_this_file[kind] then
            state.auto_skipped_this_file[kind] = mutils.skip_if_in(pos, w[1], w[2], LABELS[kind])
            if state.auto_skipped_this_file[kind] then
                msg.info(string.format("跳过%s, mode=%s args:%s", kind, tostring(opts.detect_mode), utils.to_string(w)))
            end
        end
    end
end

local function on_media_changed()
    if current then recompute(current) end
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

local function adopt_user_lens(lens, reason)
    if not lens then return false, reason end
    if not current then return false, "没有正在播放的文件" end
    current.lens = lens
    current.edited = true
    recompute(current)
    api.set_skip_time(current.path, lens.intro, lens.outro, function(resp, err)
        if err or not resp or resp.code ~= 0 then
            msg.error("保存片头/片尾时长失败: " .. tostring(err or (resp and resp.code)))
        end
    end)
    return true
end

local function current_lens()
    return current and current.lens or { intro = 0, outro = 0 }
end

local session = {
    lens = current_lens,
    edit = function(kind, len)
        return adopt_user_lens(skip_window.edit(current_lens(), mutils.dur(), kind, len))
    end,
    edit_at = function(kind, pos)
        return adopt_user_lens(skip_window.edit_at(current_lens(), mutils.dur(), kind, pos))
    end,
    clear = function()
        return adopt_user_lens({ intro = 0, outro = 0 })
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
