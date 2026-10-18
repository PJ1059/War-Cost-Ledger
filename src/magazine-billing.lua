-- One inventory authority per supported held weapon. No native reads or writes.
-- Fuel excludes the chamber; clip-fed cartridges include one loaded chamber.
local MAX = 9007199254740991
local KEYS = {'world', 'mission', 'player', 'peer', 'avatar', 'life'}
local function count(n, cap)
    return type(n) == 'number' and n >= 0 and n <= cap and n % 1 == 0
end
local function id(n) return type(n) == 'string' and n ~= '' or count(n, MAX) end
return function(prices)
    local previous, context, unsettled_since
    local api = {}
    function api:reset() previous, context, unsettled_since = nil, nil, nil end
    function api:observe(sample)
        local out = {units = 0, cents = 0, ready = false, status = 'missing'}
        if type(sample) ~= 'table' then self:reset(); return out end
        for _, key in ipairs(KEYS) do
            if not id(sample[key]) then self:reset(); out.status = 'identity'; return out end
        end
        local same = context ~= nil
        for _, key in ipairs(KEYS) do if not context or context[key] ~= sample[key] then same = false end end
        if not same then
            self:reset(); context = {}
            for _, key in ipairs(KEYS) do context[key] = sample[key] end
        end
        local reading, now = sample.reading, sample.time
        local price = type(reading) == 'table' and prices[reading.resource]
        if not price or not id(reading.entity) or not count(now, MAX) then
            previous, unsettled_since = nil, nil; return out
        end
        local a = reading.state
        if reading.reserve_mode=='backpack_fuel' then
            if type(a)~='table' or a.from~='backpack' or not count(a.remaining,10000) or not id(a.pack_entity)then
                previous,unsettled_since=nil,nil;out.status='invalid';return out
            end
            if previous and(previous.entity~=reading.entity or previous.resource~=reading.resource
                or previous.mode~='backpack_fuel' or previous.pack_entity~=a.pack_entity)then previous=nil end
            out.ready,out.price=true,price
            out.status=previous and(a.remaining<previous.stock and 'consumed'
                or a.remaining>previous.stock and 'refilled' or 'unchanged')or 'baseline'
            if previous then out.units=math.max(0,previous.stock-a.remaining)end
            out.cents=out.units*price.unit_cents
            previous={entity=reading.entity,resource=reading.resource,mode='backpack_fuel',
                pack_entity=a.pack_entity,stock=a.remaining}
            unsettled_since=nil;return out
        end
        if reading.reserve_mode=='heatsink' then
            if type(a)~='table' or a.from~='heat' or not count(a.spares,10000)then
                previous,unsettled_since=nil,nil;out.status='invalid';return out
            end
            if previous and(previous.entity~=reading.entity or previous.resource~=reading.resource
                or previous.mode~='heatsink')then previous=nil end
            out.ready,out.price=true,price
            out.status=previous and(a.spares<previous.stock and 'consumed'
                or a.spares>previous.stock and 'refilled' or 'unchanged')or 'baseline'
            if previous then out.units=math.max(0,previous.stock-a.spares)end
            out.cents=out.units*price.unit_cents
            previous={entity=reading.entity,resource=reading.resource,mode='heatsink',stock=a.spares}
            unsettled_since=nil;return out
        end
        if type(a) ~= 'table' or not count(a.capacity, 4294967295) or a.capacity == 0
            or not count(a.spares, 4294967295) or not count(a.rounds, math.min(a.capacity, 2147483647))
            or not count(a.working, math.min(a.capacity, 2147483647))
            or (a.from ~= 'copy' and a.from ~= 'type')
            or (reading.reserve_mode ~= 'magazine' and reading.reserve_mode ~= 'fuel') then
            previous, unsettled_since = nil, nil; out.status = 'invalid'; return out
        end
        local chamber = 0
        if reading.reserve_mode == 'magazine' then
            if not count(a.chambered, 4294967295) or not count(a.chamber_empty, 1) then
                previous, unsettled_since = nil, nil; out.status = 'invalid'; return out
            end
            if a.chambered ~= 0 and a.chamber_empty == 0 then chamber = 1 end
        end
        local stock = a.spares * a.capacity + a.rounds + chamber
        if not count(stock, math.floor(MAX / math.max(1, price.unit_cents))) then
            previous, unsettled_since = nil, nil; out.status = 'invalid'; return out
        end
        if previous and (previous.entity ~= reading.entity or previous.resource ~= reading.resource
            or previous.capacity ~= a.capacity or previous.from ~= a.from
            or previous.mode ~= reading.reserve_mode) then previous, unsettled_since = nil, nil end
        -- Do not bill a reserve-first reload while the fresh magazine is still empty,
        -- nor a working/network mismatch. Keep this exact instance's baseline briefly.
        local pending = a.working ~= a.rounds or (previous and a.spares < previous.spares
            and (a.rounds == 0 or (a.rounds == previous.rounds and a.rounds < a.capacity)))
        -- A magazine filling before its reserve decrement must not become a refill baseline.
        pending = pending or (previous and a.spares == previous.spares
            and a.rounds > previous.rounds and stock > previous.stock)
        if pending then
            unsettled_since = unsettled_since or now
            if now < unsettled_since or now - unsettled_since > 2000 then previous = nil end
            out.status = 'unsettled'; return out
        end
        out.ready, out.price = true, price
        out.status = previous and (stock < previous.stock and 'consumed'
            or stock > previous.stock and 'refilled' or 'unchanged') or 'baseline'
        if previous then out.units = math.max(0, previous.stock - stock) end
        out.cents = out.units * price.unit_cents
        previous = {entity = reading.entity, resource = reading.resource, capacity = a.capacity,
            from = a.from, mode = reading.reserve_mode, stock = stock, spares = a.spares, rounds = a.rounds}
        unsettled_since = nil
        return out
    end
    return api
end
