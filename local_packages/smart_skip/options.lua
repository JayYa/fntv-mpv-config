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

local skip_window = require('./skip_window')

-- 检测模式（定义在 skip_window）
local DETECT_MODE = skip_window.MODE

-- 用户配置：从 script-opts/smart_skip.conf 读取，菜单修改后整份写回。
-- 每个文件的片头/片尾时长不在这里，见 main.lua 的文件状态。
local opts = {
    -- 基础设置
    enabled = false,
    detect_mode = DETECT_MODE.AUTO, -- auto, chapter, manual

    -- 章节检测参数
    min_skip_duration = 10,  -- 最短片头/片尾长度s
    max_skip_duration = 150, -- 最长片头/片尾长度s
    max_scan_window = 600,   -- 最大扫描窗口（10分钟）
    max_scan_percent = 15,   -- 视频长度百分比

    -- 快捷键快速跳过时长
    manual_skip_duration = 90,
}

return {
    opts = opts,
    DETECT_MODE = DETECT_MODE,
}
