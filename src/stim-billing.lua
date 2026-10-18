-- Standard stim usage from the local player's native cumulative mission stat.
-- The caller shares its existing stat_breakdown result; no native reads here.
-- Health gains, carried stock, animations and projectile counts are not inputs.
local STIMS, MAX_COUNT = 0xC8256789, 2147483647
local MAX_EXACT = 9007199254740991
local IDENTITY = {'world', 'mission', 'player', 'peer'}

local function integer(value, maximum)
    return type(value) == 'number' and value >= 0 and value <= maximum and value % 1 == 0
end
local function world_identity(value)
    return (type(value) == 'string' and value ~= '') or integer(value, MAX_EXACT)
end
local function peer_identity(value)
    if type(value) ~= 'string' or #value ~= 16 or not value:match('^%x+$')
        or value == '0000000000000000' then return nil end
    return value:upper()
end

return function(price)
    assert(type(price) == 'table' and (price.key == nil or price.key == STIMS), 'invalid stim key')
    assert(integer(price.unit_cents, math.floor(MAX_EXACT / MAX_COUNT)), 'invalid stim price')
    local unit_cents = price.unit_cents
    local previous, identity
    local api = {key = STIMS, unit_cents = unit_cents}

    function api:reset()
        previous, identity = nil, nil
    end

    function api:observe(sample)
        local result = {units = 0, cents = 0, ready = false, status = 'missing'}
        if type(sample) ~= 'table' then self:reset(); return result end
        local peer = peer_identity(sample.peer)
        if not world_identity(sample.world) or not integer(sample.mission, MAX_EXACT)
            or not integer(sample.player, 4294967295) or sample.player == 0 or not peer then
            self:reset(); result.status = 'identity'; return result
        end
        local current_identity = {world = sample.world, mission = sample.mission,
            player = sample.player, peer = peer}
        local same = identity ~= nil
        for _, field in ipairs(IDENTITY) do
            if not identity or identity[field] ~= current_identity[field] then same = false; break end
        end
        if not same then previous = nil end
        identity = current_identity
        local totals = type(sample.stats) == 'table' and sample.stats.totals
        local current
        if type(totals) == 'table' then current = totals[STIMS] end
        if current == nil then previous = nil; return result end
        if not integer(current, MAX_COUNT) then
            previous = nil; result.status = 'invalid'; return result
        end
        result.ready, result.current = true, current
        if previous == nil then result.status = 'baseline'
        elseif current < previous then result.status = 'reset'
        else
            result.units = current - previous
            result.cents = result.units * unit_cents
            result.status = result.units > 0 and 'consumed' or 'unchanged'
        end
        previous = current
        return result
    end
    return api
end
