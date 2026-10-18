-- Offline integration prototype. Not embedded in addon.lua or installed in the game.
-- Adapters must supply local, verified direct contacts. This module detects nothing.
local KEYS = {'total', 'ricochet', 'blocked', 'penetration', 'full_penetration',
    'through', 'part_destroyed', 'weakpoint', 'melee'}
local RESULTS = {ricochet = true, blocked = true, penetration = true, full_penetration = true}
local EXCLUDED = {spray = true, burning = true, ground_fire = true, explosion_area = true}
local function count(n) return type(n) == 'number' and n > 0 and n < math.huge and n % 1 == 0 end
local function clock(n) return type(n) == 'number' and n >= 0 and n < math.huge end

return function()
    local api = {cumulative = {}, recent = {}, idle_seconds = 2, last_hit = nil, revision = 0}
    local function clear(values) for _, key in ipairs(KEYS) do values[key] = 0 end end
    clear(api.cumulative); clear(api.recent)
    function api:reset()
        clear(self.cumulative); clear(self.recent)
        self.last_hit = nil; self.revision = self.revision + 1
    end
    function api:collect(now)
        if clock(now) and self.last_hit and now - self.last_hit >= self.idle_seconds then
            clear(self.recent); self.last_hit = nil; self.revision = self.revision + 1
        end
    end
    function api:accept(contact, now)
        if not clock(now) or type(contact) ~= 'table' or contact.verified ~= true
            or contact.local_player ~= true or contact.direct ~= true
            or (contact.attack ~= 'projectile' and contact.attack ~= 'melee')
            or EXCLUDED[contact.mode] or not count(contact.count or 1) then return false end
        -- A snapshot must not attach an unproven classification to a known total.
        if contact.result ~= nil and not RESULTS[contact.result] then return false end
        if self.last_hit and now < self.last_hit then return false end
        self:collect(now)
        local n = contact.count or 1
        local function add(key)
            self.cumulative[key] = self.cumulative[key] + n
            self.recent[key] = self.recent[key] + n
        end
        add('total')
        if contact.result then add(contact.result) end
        -- These dimensions can overlap the result; total grows only once.
        for _, key in ipairs({'ricochet', 'through', 'part_destroyed', 'weakpoint'}) do
            if contact[key] == true and contact.result ~= key then add(key) end
        end
        if contact.attack == 'melee' then add('melee') end
        self.last_hit = now; self.revision = self.revision + 1
        return true
    end
    function api:visible(now, map_open, hud_enabled)
        self:collect(now)
        if hud_enabled == false then return nil end
        if map_open == true then return self.cumulative end
        if self.last_hit then return self.recent end
        return nil
    end
    return api
end
