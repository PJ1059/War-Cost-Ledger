-- Presentation of already verified ledger totals. This module reads no game memory.
-- The caller supplies a monotonic clock; hidden presentation still observes totals.
-- Returned snapshots are retained views and must be treated as read-only.
local function count(value)
    return type(value) == 'number' and value >= 0 and value < math.huge and value % 1 == 0
end
local function clock(value)
    return type(value) == 'number' and value >= 0 and value < math.huge
end

return function(state, icons)
    assert(type(state) == 'table' and type(icons) == 'table', 'award notifications need state and icon definitions')
    local records, seen_ids = {}, {}
    for index, icon in ipairs(icons) do
        assert(type(icon) == 'table' and (icon.kind == 'ribbon' or icon.kind == 'medal')
            and type(icon.id) == 'string' and type(icon.key) == 'string' and not seen_ids[icon.id],
            'award definitions need unique IDs and ribbon/medal kinds')
        seen_ids[icon.id] = true
        records[index] = {icon = icon, observed = false, total = 0, active = false, batch = 0}
    end
    local api = {version = 1, idle_seconds = 2, revision = 0, deadline = nil}
    local initialized, sequence, last_now, cached = false, nil, 0, nil
    local cached_revision, cached_visible, cached_map
    local function finish_batch()
        for _, record in ipairs(records) do record.active, record.batch = false, 0 end
        api.deadline = nil
    end
    local function item(record, recent)
        local icon = record.icon
        return {id = icon.id, key = icon.key, name = icon.name, kind = icon.kind,
            colour = icon.colour, side_icon = icon.side_icon == true,
            count = recent and record.batch or record.total, total = record.total}
    end
    local function observe(now, suppress_initial_replay)
        assert(clock(now), 'award notifications need a finite non-negative clock')
        -- A late caller cannot rewind an active batch or extend its lifetime.
        if now < last_now then now = last_now else last_now = now end
        local changed, fresh = false, not initialized
        local current_sequence = count(state.sequence) and state.sequence or nil
        if not initialized then
            initialized, sequence = true, current_sequence
        elseif current_sequence ~= nil and sequence == nil then
            -- Establishing previously unavailable identity is not a new mission.
            sequence = current_sequence
        elseif current_sequence ~= nil and current_sequence ~= sequence then
            sequence = current_sequence
            finish_batch()
            for _, record in ipairs(records) do
                record.observed, record.total = true, 0
            end
            changed = true
        end
        if api.deadline and (suppress_initial_replay or now >= api.deadline) then
            finish_batch(); changed = true
        end
        local grew = false
        for _, record in ipairs(records) do
            local icon = record.icon
            if icon.kind == 'ribbon' then
                local value = type(state.ribbons) == 'table' and state.ribbons[icon.key] or nil
                if count(value) then
                    if not record.observed then
                        -- A late first valid read is only a baseline, never a replay.
                        record.observed, record.total = true, value
                        if value > 0 then changed = true end
                    elseif value > record.total then
                        local delta = value - record.total
                        record.total = value
                        if not fresh and not suppress_initial_replay and icon.side ~= false then
                            record.active, record.batch = true, record.batch + delta
                            grew = true
                        end
                        changed = true
                    end
                    -- Missing, invalid and backward reads retain the last verified
                    -- high-water mark. Recovery cannot manufacture another award.
                elseif suppress_initial_replay and record.total == 0 then
                    -- The first ready statistics frame cannot establish a zero
                    -- baseline for a source that is still unavailable.
                    record.observed = false
                end
            else
                local values = state.mission_medals
                if type(values) == 'table' then
                    local value = values[icon.key]
                    value = value == true and 1 or (count(value) and value or 0)
                    if not record.observed then
                        record.observed, record.total = true, value
                        if value > 0 then changed = true end
                    elseif value > record.total then
                        local delta = value - record.total
                        record.total = value
                        if not fresh and not suppress_initial_replay then
                            record.active, record.batch, grew = true, record.batch + delta, true
                        end
                        changed = true
                    end
                    -- Legacy true means one acquisition. Counts are monotonic
                    -- within a mission, so repeated awards can pop without any
                    -- false/missing/backward frame manufacturing another one.
                elseif suppress_initial_replay and record.total == 0 then record.observed = false end
            end
        end
        if grew then api.deadline = now + api.idle_seconds end
        if changed then api.revision = api.revision + 1 end
        return api.revision
    end
    function api:update(now)
        return observe(now, false)
    end
    -- A fee or another award may extend the same visible two-second batch.
    -- Never revive a folded batch or create a timer without active content.
    function api:extend_deadline(value)
        if self.deadline and clock(value) and value>self.deadline then
            self.deadline=value;self.revision=self.revision+1
        end
        return self.deadline
    end
    -- Call once when the new mission's first valid native statistics arrive,
    -- before presenting that frame. Late-join totals become collected baseline,
    -- not newly earned notifications. Ledger state and its unlocks are untouched.
    function api:baseline(now)
        return observe(now, true)
    end
    function api:snapshot(now, visible, map_open)
        self:update(now)
        visible, map_open = visible == true, map_open == true
        if cached and cached_revision == self.revision and cached_visible == visible and cached_map == map_open then
            return cached
        end
        local view = {version = 1, shown = visible, map_open = map_open, revision = self.revision,
            deadline = self.deadline, items = {}, medals = {}, ribbons = {}, hits = {}}
        if visible then
            for _, record in ipairs(records) do
                -- Map detail includes current total even while that type still
                -- has a recent notification. It never mixes with ribbon rows.
                if record.icon.side_icon and record.total>0 then
                    view.hits[#view.hits+1]=item(record,false)
                end
                if record.active then
                    view.items[#view.items + 1] = item(record, true)
                elseif record.total > 0 then
                    if record.icon.kind == 'medal' then view.medals[#view.medals + 1] = item(record, false)
                    elseif map_open then view.ribbons[#view.ribbons + 1] = item(record, false) end
                end
            end
        end
        cached, cached_revision, cached_visible, cached_map = view, self.revision, visible, map_open
        return view
    end
    return api
end
