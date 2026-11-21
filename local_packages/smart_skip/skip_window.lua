local M = {}

M.MODE = {
    CHAPTER = 1,
    MANUAL = 2,
    AUTO = 3,
}

local function nonneg(v)
    v = tonumber(v)
    if not v or v < 0 then return 0 end
    return v
end

function M.from_server(data)
    if type(data) ~= "table" then return { intro = 0, outro = 0 } end
    return { intro = nonneg(data.skipStart), outro = nonneg(data.skipEnd) }
end

local function outro_ok(outro, d) return outro <= d / 2 end
local function fits(intro, outro, d) return intro + outro <= d end

local function drop_invalid_segments(lens, d)
    local outro = nonneg(lens.outro)
    if not outro_ok(outro, d) then outro = 0 end
    local intro = nonneg(lens.intro)
    if not fits(intro, outro, d) then intro = 0 end
    return intro, outro
end

local function manual_windows(lens, d)
    local intro_len, outro_len = drop_invalid_segments(lens, d)
    local intro = intro_len > 0 and { 0, intro_len } or nil
    local outro = outro_len > 0 and { d - outro_len, d } or nil
    return intro, outro
end

function M.edit(lens, duration, kind, len)
    local d = tonumber(duration) or 0
    if d <= 0 then return nil, "视频时长未知" end
    len = tonumber(len)
    if not len or len < 0 then return nil, "必须 ≥ 0" end
    local intro, outro = drop_invalid_segments(lens, d)
    local new = { intro = intro, outro = outro }
    new[kind] = len
    if not outro_ok(new.outro, d) then return nil, "片尾时长不能超过视频一半" end
    if not fits(new.intro, new.outro, d) then return nil, "片头与片尾不能重叠" end
    return new, nil
end

function M.edit_at(lens, duration, kind, pos)
    local d = tonumber(duration) or 0
    local len = kind == "outro" and math.floor(d - pos) or math.floor(pos)
    return M.edit(lens, d, kind, len)
end

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

local function intro_after_cold_open(candidates)
    return candidates[2] or candidates[1]
end

local function outro_before_post_credits(candidates)
    return candidates[#candidates - 1] or candidates[#candidates]
end

local function chapter_windows(chapters, d, o)
    if not chapters or #chapters == 0 then return nil, nil end
    local scan = math.min(o.max_scan_window, (o.max_scan_percent / 100) * d)
    local intros = sections_in(chapters, 0, scan, o.min_skip_duration, o.max_skip_duration)
    local outros = sections_in(chapters, d - scan, d, o.min_skip_duration, o.max_skip_duration)
    return intro_after_cold_open(intros), outro_before_post_credits(outros)
end

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
    return { intro = c_intro or m_intro, outro = c_outro or m_outro }
end

return M
