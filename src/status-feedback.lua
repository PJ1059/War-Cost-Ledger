-- Offline synthetic-input prototype. No game reads, hooks, GUI nodes or installation.
-- The adapter must prove the player, hostile target, full entity generation and an
-- actual effective period. Requests, damage ticks, kills and missing reads prove none.
-- All aliases of one application share cycle_id. 'ended' means that entire family
-- period really ended, not that one gas/fire component or the actor stopped reading.
local KEYS = {'status_fire', 'status_poison'}
local FAMILY = {fire = 'status_fire', burning_heavy = 'status_fire',
    gas = 'status_poison', gas_2 = 'status_poison',
    gas_confusion = 'status_poison', gas_confusion_2 = 'status_poison'}
local MAX_CYCLES = 4096
local function clock(n) return type(n) == 'number' and n >= 0 and n < math.huge end
local function token(value)
    if type(value) == 'number' and value >= 0 and value <= 9007199254740991 and value % 1 == 0 then
        return 'n' .. string.format('%.0f', value) .. ':'
    end
    if type(value) == 'string' and #value > 0 and #value <= 128 then
        return 's' .. #value .. ':' .. value
    end
end

return function()
    local cycles, active = {}, {}
    local api = {cumulative = {}, recent = {}, idle_seconds = 2,
        revision = 0, cycle_count = 0, max_cycles = MAX_CYCLES, capacity_reached = false}
    local last_clock, last_effect
    local function clear(values) for _, key in ipairs(KEYS) do values[key] = 0 end end
    clear(api.cumulative); clear(api.recent)
    function api:reset()
        clear(self.cumulative); clear(self.recent)
        cycles, active, last_clock, last_effect = {}, {}, nil, nil
        self.cycle_count, self.capacity_reached = 0, false
        self.revision = self.revision + 1
    end
    function api:collect(now)
        if not clock(now) or (last_clock and now < last_clock) then return false end
        last_clock = now
        if last_effect and now - last_effect >= self.idle_seconds then
            clear(self.recent); last_effect = nil
            self.revision = self.revision + 1
        end
        return true
    end
    function api:accept(event, now)
        if not clock(now) or (last_clock and now < last_clock) or type(event) ~= 'table'
            or event.verified ~= true or event.local_player ~= true or event.hostile ~= true
            or (event.kind ~= 'effective' and event.kind ~= 'ended')
            or (event.count ~= nil and event.count ~= 1) then return false end
        local family = FAMILY[event.status]
        local target = event.target
        if not family or type(target) ~= 'table' then return false end
        local id, generation, period = token(target.id), token(target.generation), token(event.cycle_id)
        if not id or not generation or not period then return false end
        local owner_key = id .. generation .. family
        local cycle_key = owner_key .. period
        local record = cycles[cycle_key]
        if event.kind == 'ended' then
            -- A verified end never counts and cannot invent a previously unseen period.
            if not record or not record.active or active[owner_key] ~= record then return false end
            self:collect(now)
            record.active, active[owner_key] = false, nil
            self.revision = self.revision + 1
            return true
        end
        -- Retain completed periods until match reset; late replay cannot count again.
        -- A different cycle also needs the previous period's verified end first.
        if record or active[owner_key] then return false end
        if self.cycle_count >= MAX_CYCLES then
            -- Fail closed instead of evicting deduplication evidence and double-counting.
            self.capacity_reached = true
            return false
        end
        self:collect(now)
        record = {active = true}
        cycles[cycle_key], active[owner_key] = record, record
        self.cycle_count = self.cycle_count + 1
        self.cumulative[family] = self.cumulative[family] + 1
        self.recent[family] = self.recent[family] + 1
        last_effect = now
        self.revision = self.revision + 1
        return true
    end
    function api:visible(now, map_open, hud_enabled)
        if not self:collect(now) or hud_enabled == false then return nil end
        if map_open == true then return self.cumulative end
        for _, key in ipairs(KEYS) do if self.recent[key] > 0 then return self.recent end end
        return nil
    end
    return api
end
