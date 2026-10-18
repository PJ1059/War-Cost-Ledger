-- Prepared consumption observer; not embedded or installed. No game reads/writes.
-- The caller supplies local-player usage and this player's stable fuel inventory.
-- A missing or inconsistent reading breaks that channel's baseline.
local TORCHER = '4FB0F8C02F55C82B'
local STIMS = 0xC8256789
local FUEL_PRICE, STIM_PRICE = 30, 2500 -- workbook EQ-054 / EQ-360, cents
local MAX_EXACT = 9007199254740991
local CONTEXT = {'world', 'mission', 'player', 'peer', 'avatar', 'life'}

local function integer(n, maximum)
    return type(n) == 'number' and n >= 0 and n <= maximum and n % 1 == 0
end
local function identity(value)
    return (type(value) == 'string' and value ~= '') or integer(value, MAX_EXACT)
end
local function same_context(a, b)
    if not a then return false end
    for _, key in ipairs(CONTEXT) do if a[key] ~= b[key] then return false end end
    return true
end

return function()
    local context, fuel, stims
    local api = {torcher_resource = TORCHER, stims_stat = STIMS,
        fuel_price_cents = FUEL_PRICE, stim_price_cents = STIM_PRICE}

    function api:reset()
        context, fuel, stims = nil, nil, nil
    end

    function api:observe(sample)
        local result = {fuel_units = 0, stim_units = 0, fuel_cents = 0,
            stim_cents = 0, total_cents = 0, fuel_status = 'missing', stim_status = 'missing'}
        if type(sample) ~= 'table' then
            self:reset()
            return result
        end
        for _, key in ipairs(CONTEXT) do
            if not identity(sample[key]) then
                self:reset()
                result.fuel_status, result.stim_status = 'identity', 'identity'
                return result
            end
        end
        if not same_context(context, sample) then
            fuel, stims, context = nil, nil, {}
            for _, key in ipairs(CONTEXT) do context[key] = sample[key] end
        end

        local reading = sample.fuel
        if type(reading) ~= 'table' then
            fuel = nil
        elseif reading.resource ~= TORCHER then
            fuel, result.fuel_status = nil, 'unsupported'
        elseif not identity(reading.entity) then
            fuel, result.fuel_status = nil, 'identity'
        else
            local ammo = reading.state
            if type(ammo) ~= 'table' then
                fuel = nil
            elseif not integer(ammo.capacity, 4294967295) or ammo.capacity == 0
                or not integer(ammo.spares, 4294967295)
                or not integer(ammo.rounds, math.min(ammo.capacity, 2147483647))
                or (ammo.from ~= 'copy' and ammo.from ~= 'type') then
                fuel, result.fuel_status = nil, 'invalid'
            else
                -- Chambered is a projectile/pattern field, never +1 fuel.
                local stock = ammo.spares * ammo.capacity + ammo.rounds
                if stock > math.floor(MAX_EXACT / FUEL_PRICE) then
                    fuel, result.fuel_status = nil, 'invalid'
                else
                    if fuel and (fuel.entity ~= reading.entity or fuel.capacity ~= ammo.capacity
                        or fuel.from ~= ammo.from) then fuel = nil end
                    if ammo.working ~= ammo.rounds then
                        fuel, result.fuel_status = nil, 'invalid'
                    else
                        if fuel then
                            result.fuel_units = math.max(0, fuel.stock - stock)
                            result.fuel_status = stock < fuel.stock and 'consumed'
                                or (stock > fuel.stock and 'refilled' or 'unchanged')
                        else
                            result.fuel_status = 'baseline'
                        end
                        fuel = {entity = reading.entity, capacity = ammo.capacity,
                            from = ammo.from, stock = stock}
                    end
                end
            end
        end

        local usage = sample.stims
        if type(usage) ~= 'table' then
            stims = nil
        elseif usage.player ~= sample.player then
            stims, result.stim_status = nil, 'identity'
        else
            local totals = type(usage.stats) == 'table' and usage.stats.totals
            local current = type(totals) == 'table' and totals[STIMS]
            if current == nil then
                stims = nil
            elseif not integer(current, 2147483647) then
                stims, result.stim_status = nil, 'invalid'
            else
                if stims == nil then
                    result.stim_status = 'baseline'
                elseif current < stims then
                    result.stim_status = 'reset'
                else
                    result.stim_units = current - stims
                    result.stim_status = current > stims and 'consumed' or 'unchanged'
                end
                stims = current
            end
        end
        result.fuel_cents = result.fuel_units * FUEL_PRICE
        result.stim_cents = result.stim_units * STIM_PRICE
        result.total_cents = result.fuel_cents + result.stim_cents
        return result
    end
    return api
end
