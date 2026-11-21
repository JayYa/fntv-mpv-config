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

local mp          = require('mp')
local msg         = require('mp.msg')
local utils       = require('mp.utils')
local mutils      = require('./mutils')

local options_mod = require('./options')
local opts        = options_mod.opts
local DETECT_MODE = options_mod.DETECT_MODE
local SCRIPT      = mp.get_script_name()

local session     = nil

local function mode_name(m)
    if m == DETECT_MODE.CHAPTER then return '章节模式' end
    if m == DETECT_MODE.MANUAL then return '手动模式' end
    if m == DETECT_MODE.AUTO then return '自动模式' end
    return tostring(m)
end

local function bool_sign(b) return b and '✔' or 'X' end

local function length_control(kind, title)
    return {
        type  = 'number',
        title = title,
        hint  = '输入整数（秒）后回车',
        parse = mutils.parse_integer,
        get   = function() return session.lens()[kind] end,
        apply = function(n) return session.edit(kind, n) end,
        after = function(n)
            msg.info(title .. ' => ' .. n .. ' 秒')
        end,
    }
end

local function open_uosc_menu(items, title, footnote, menu_type)
    local props = {
        type            = menu_type or 'menu_skip',
        title           = title or '跳过片头片尾设置',
        items           = items,
        footnote        = footnote or '提示：回车提交；Esc 返回',
        search_style    = 'on_demand',
        search_debounce = 0,
    }
    mp.commandv('script-message-to', 'uosc', 'open-menu', utils.format_json(props))
end

local function open_input(control_id, title, placeholder)
    local props = {
        type              = 'menu_input_' .. control_id,
        title             = title or '请输入整数（秒）',
        items             = {
            { title = '输入后按 Enter 提交', align = 'center', italic = true, selectable = false, keep_open = true },
        },
        search_style      = 'palette',
        search_debounce   = 'submit',
        on_search         = { 'script-message-to', SCRIPT, 'menu:input', control_id },
        search_suggestion = placeholder or '',
        footnote          = '仅允许非负整数（单位：秒）',
    }
    mp.commandv('script-message-to', 'uosc', 'open-menu', utils.format_json(props))
end

local Controls = {
    enabled = {
        type  = 'toggle',
        title = '总开关',
        parse = mutils.parse_integer,
        get   = function() return opts.enabled end,
        set   = function(v)
            opts.enabled = not not v
            mutils.save_options(opts)
        end,
        after = function(n)
            msg.info('跳过功能：' .. bool_sign(opts.enabled))
        end,
    },

    detect_mode = {
        type    = 'radio',
        title   = '模式选择',
        options = {
            { id = DETECT_MODE.AUTO, name = '自动模式', hint = '优先章节，无则使用手动模式' },
            { id = DETECT_MODE.CHAPTER, name = '章节模式', hint = '通过章节自动识别' },
            { id = DETECT_MODE.MANUAL, name = '手动模式', hint = '手动指定片头片尾长度' },
        },
        parse   = mutils.parse_integer,
        get     = function() return opts.detect_mode end,
        set     = function(id)
            opts.detect_mode = tonumber(id) or opts.detect_mode
            mutils.save_options(opts)
            session.refresh()
        end,
        after   = function(n)
            msg.info('检测模式 => ' .. mode_name(opts.detect_mode))
        end,
    },

    intro = length_control('intro', '片头时长（秒）'),

    outro = length_control('outro', '片尾时长（秒）'),

    skipdur = {
        type     = 'number',
        title    = '快捷跳过时长（秒）',
        hint     = '输入整数（秒）后回车',
        parse    = mutils.parse_integer,
        get      = function() return opts.manual_skip_duration or 0 end,
        apply    = function(n)
            if n < 0 then return false, '必须 ≥ 0' end
            opts.manual_skip_duration = n
            mutils.save_options(opts)
            return true
        end,
        after    = function(n)
            msg.info('快捷跳过时长 => ' .. n .. ' 秒')
        end,
    },
}

local function build_items()
    local items = {}

    table.insert(items, {
        title      = string.format('跳过功能：%s', bool_sign(opts.enabled)),
        bold       = true,
        italic     = true,
        keep_open  = true,
        selectable = false,
    })

    table.insert(items, {
        title      = opts.enabled and '关闭' or '开启',
        hint       = Controls.enabled.title,
        value      = { 'script-message-to', SCRIPT, 'menu:action', 'toggle', 'enabled' },
        keep_open  = true,
        selectable = true,
    })

    table.insert(items, { title = '— 模式选择 —', keep_open = true, selectable = false })
    local dm = Controls.detect_mode
    for _, opt in ipairs(dm.options) do
        table.insert(items, {
            title      = ((dm.get() == opt.id) and '● ' or '○ ') .. opt.name,
            hint       = opt.hint,
            value      = { 'script-message-to', SCRIPT, 'menu:action', 'set', 'detect_mode', tostring(opt.id) },
            keep_open  = true,
            selectable = true,
        })
    end

    table.insert(items,
        { title = '— 快捷键快速跳过时长（秒） —', keep_open = true, selectable = false, hint = '默认快捷键: Backspace' })

    table.insert(items, {
        title      = string.format('跳过时长：%d', Controls.skipdur.get()),
        hint       = Controls.skipdur.hint,
        value      = { 'script-message-to', SCRIPT, 'menu:action', 'open_input', 'skipdur' },
        keep_open  = true,
        selectable = true,
    })

    table.insert(items, { title = '— 手动设置片头片尾时间 —', keep_open = true, selectable = false })

    table.insert(items, {
        title      = string.format('设置片头: %d s', Controls.intro.get()),
        hint       = '将片头结束时间设置为当前播放位置',
        value      = { 'script-message-to', SCRIPT, 'menu:action', 'set_skip_time', 'intro' },
        keep_open  = true,
        selectable = true,
    })

    table.insert(items, {
        title      = string.format('设置片尾: %d s', Controls.outro.get()),
        hint       = '将片尾开始时间设置为当前播放位置',
        value      = { 'script-message-to', SCRIPT, 'menu:action', 'set_skip_time', 'outro' },
        keep_open  = true,
        selectable = true,
    })

    table.insert(items, {
        title      = string.format('清空片头片尾设置'),
        hint       = '',
        value      = { 'script-message-to', SCRIPT, 'menu:action', 'clean_skip_time', 'all' },
        keep_open  = true,
        selectable = true,
    })

    return items
end

local function open_main_menu()
    open_uosc_menu(build_items(), '跳过片头片尾设置', '提示：回车提交；Esc 返回', 'menu_skip')
end

local function on_action(op, id, value)
    if not op then return end

    if op == 'toggle' and id == 'enabled' then
        local c = Controls.enabled
        c.set(not c.get())
        if c.after then c.after(c.get()) end
        return open_main_menu()
    end

    if op == 'open_input' and id then
        local c = Controls[id]; if not c then return end
        return open_input(id, c.title, tostring(c.get()))
    end

    if op == 'set' and id == 'detect_mode' and value then
        local c = Controls.detect_mode
        c.set(tonumber(value))
        if c.after then c.after() end
        return open_main_menu()
    end

    if op == 'set_skip_time' and (id == 'intro' or id == 'outro') then
        local ok, reason = session.edit_at(id, mutils.timepos())
        if ok then
            Controls[id].after(session.lens()[id])
        else
            mutils.show_message('⚠️ ' .. Controls[id].title .. '：' .. reason, 3)
        end
        return open_main_menu()
    end

    if op == 'clean_skip_time' then
        session.clear()
        return open_main_menu()
    end

end

local function on_input(id, value)
    local c = Controls[id]; if not c then return end

    local n
    if c.parse then
        n = c.parse(value)
    end

    if not n then
        return open_input(id, c.title .. '（无效输入）', '')
    end

    local ok, reason = c.apply(n)
    if not ok then
        return open_input(id, c.title .. '(' .. (reason or '非法') .. ')', '')
    end

    if c.after then c.after(n) end
    return open_main_menu()
end

local M = {}

function M.init(s)
    session = s

    mp.register_script_message('menu:action', on_action)
    mp.register_script_message('menu:input', on_input)

    mp.commandv('script-message-to', 'uosc', 'set-button', 'skip_cfg_btn', utils.format_json({
        icon    = 'settings',
        tooltip = '跳过片头片尾设置',
        command = 'script-message open-skip-menu',
    }))

    mp.register_script_message('open-skip-menu', open_main_menu)
end

return M
