local skip_window = require('./skip_window')

local M = {}

local Session = {}
Session.__index = Session

local SEGMENTS = { 'intro', 'outro' }

function Session:_recompute()
    local facts = self.deps.facts()
    self.windows = skip_window.windows({
        duration = facts.duration,
        lens = self.current_lens,
        mode = facts.mode,
        chapters = facts.chapters or {},
        chapter_opts = facts.chapter_opts,
    })
end

function Session:_on_server_lens(lens, err)
    if self.closed or self.edited then return end
    if not lens then
        self.deps.log.error("获取服务器片头/片尾时长失败: " .. tostring(err))
        return
    end
    self.current_lens = lens
    self:_recompute()
    self.deps.log.info(string.format("服务器片头/片尾时长: 片头 %s 秒, 片尾 %s 秒", lens.intro, lens.outro))
end

function Session:_adopt(lens, reason)
    if not lens then return false, reason end
    self.current_lens = lens
    self.edited = true
    self:_recompute()
    local log = self.deps.log
    self.deps.skipinfo.save(self.path, lens, function(ok, err)
        if not ok then
            log.error("保存片头/片尾时长失败: " .. tostring(err))
        end
    end)
    return true
end

function Session:lens()
    return self.current_lens
end

function Session:edit(kind, len)
    return self:_adopt(skip_window.edit(self.current_lens, self.deps.facts().duration, kind, len))
end

function Session:edit_at(kind, pos)
    return self:_adopt(skip_window.edit_at(self.current_lens, self.deps.facts().duration, kind, pos))
end

function Session:clear()
    return self:_adopt({ intro = 0, outro = 0 })
end

function Session:media_changed()
    self:_recompute()
end

function Session:tick(pos)
    for _, kind in ipairs(SEGMENTS) do
        local w = self.windows[kind]
        if w and not self.skipped[kind] and pos >= w[1] and pos <= w[2] then
            self.skipped[kind] = true
            return kind, w[2]
        end
    end
end

function Session:close()
    self.closed = true
end

function M.open(path, deps)
    local session = setmetatable({
        path = path,
        deps = deps,
        current_lens = { intro = 0, outro = 0 },
        edited = false,
        closed = false,
        windows = {},
        skipped = {},
    }, Session)
    session:_recompute()
    deps.skipinfo.fetch(path, function(lens, err) session:_on_server_lens(lens, err) end)
    return session
end

return M
