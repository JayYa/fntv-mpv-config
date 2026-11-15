-- 跳过窗口：一个文件里要自动跳过的片头区间与片尾区间（见 GLOSSARY.md）
--
-- 纯 Lua，不依赖 mp，便于测试。状态只用两个时长表示，与服务器 skipinfo 一致：
--   lens = { intro = 片头时长, outro = 片尾时长 }，单位秒，0 表示没有
-- 片尾时长从视频末尾倒数；绝对区间只在知道 duration 时由 windows() 算出。

local M = {}

M.MODE = {
    CHAPTER = 1, -- 只看章节
    MANUAL = 2,  -- 只看片头/片尾时长
    AUTO = 3,    -- 每段先看章节，没有再看时长
}

local function nonneg(v)
    v = tonumber(v)
    if not v or v < 0 then return 0 end
    return v
end

-- 服务器 skipinfo 的 data（skipStart = 片头时长，skipEnd = 片尾时长）转成 lens
function M.from_server(data)
    if type(data) ~= "table" then return { intro = 0, outro = 0 } end
    return { intro = nonneg(data.skipStart), outro = nonneg(data.skipEnd) }
end

-- 合法性规则（服务器数据与用户编辑共用）：
--   0 <= 片尾时长 <= duration / 2，0 <= 片头时长，片头 + 片尾 <= duration
-- 返回去掉不合规段之后的时长（不合规的段视为 0）
local function outro_ok(outro, d) return outro <= d / 2 end
local function fits(intro, outro, d) return intro + outro <= d end

local function usable_lens(lens, d)
    local outro = nonneg(lens.outro)
    if not outro_ok(outro, d) then outro = 0 end
    local intro = nonneg(lens.intro)
    if not fits(intro, outro, d) then intro = 0 end
    return intro, outro
end

local function manual_windows(lens, d)
    local intro_len, outro_len = usable_lens(lens, d)
    local intro = intro_len > 0 and { 0, intro_len } or nil
    local outro = outro_len > 0 and { d - outro_len, d } or nil
    return intro, outro
end

-- 用户把某一段（kind = "intro" | "outro"）的时长改成 len
-- 合规时返回新的 lens；否则返回 nil 和原因
function M.edit(lens, duration, kind, len)
    local d = tonumber(duration) or 0
    if d <= 0 then return nil, "视频时长未知" end
    if len < 0 then return nil, "必须 ≥ 0" end
    local new = { intro = nonneg(lens.intro), outro = nonneg(lens.outro) }
    new[kind] = len
    if not outro_ok(new.outro, d) then return nil, "片尾时长不能超过视频一半" end
    if not fits(new.intro, new.outro, d) then return nil, "片头与片尾不能重叠" end
    return new, nil
end

-- 用户在播放位置 pos 处标记：片头到此结束 / 片尾从此开始；按整秒换算成时长后同 edit
function M.edit_at(lens, duration, kind, pos)
    local d = tonumber(duration) or 0
    local len = kind == "outro" and math.floor(d - pos) or math.floor(pos)
    return M.edit(lens, d, kind, len)
end

-- 在 [from, to] 内开始、长度在 [min_len, max_len] 之间的章节区间
local function sections_in(chapters, from, to, min_len, max_len)
    local found = {}
    for i = 1, #chapters - 1 do
        local a, b = chapters[i].time, chapters[i + 1].time
        if a >= from and a <= to and b - a >= min_len and b - a <= max_len then
            found[#found + 1] = { a, b }
        end
    end
    return found
end

local function chapter_windows(chapters, d, o)
    if not chapters or #chapters == 0 then return nil, nil end
    local scan = math.min(o.max_scan_window, (o.max_scan_percent / 100) * d)
    local intros = sections_in(chapters, 0, scan, o.min_skip_duration, o.max_skip_duration)
    local outros = sections_in(chapters, d - scan, d, o.min_skip_duration, o.max_skip_duration)
    -- 多个候选时，片头取第二个（第一个可能是冷开场），片尾取倒数第二个（最后一个可能是彩蛋）
    return intros[2] or intros[1], outros[#outros - 1] or outros[#outros]
end

-- 算出跳过窗口
-- input = { duration, lens, mode, chapters, chapter_opts }
-- 返回 { intro = {a, b} | nil, outro = {a, b} | nil }
function M.windows(input)
    local d = tonumber(input.duration) or 0
    if d <= 0 then return {} end
    local mode = input.mode
    local c_intro, c_outro, m_intro, m_outro
    if mode ~= M.MODE.MANUAL then
        c_intro, c_outro = chapter_windows(input.chapters, d, input.chapter_opts)
    end
    if mode ~= M.MODE.CHAPTER then
        m_intro, m_outro = manual_windows(input.lens, d)
    end
    -- 自动模式（以及未知模式）每段各自先取章节，没有再取时长
    return { intro = c_intro or m_intro, outro = c_outro or m_outro }
end

return M
