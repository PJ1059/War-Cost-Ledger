local create = dofile(assert(arg[1]))
local tests = 0
local TORCHER, STIMS = '4FB0F8C02F55C82B', 0xC8256789
local function check(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end
local function snapshot(spares, rounds, used, capacity)
    -- Exactly the public Runtime ammo_state / stat_breakdown field shapes.
    return {world = 'world-1', mission = 8, player = 0x10001,
        peer = '0000000200000001', avatar = 0x20001, life = 1,
        fuel = {entity = 0x30001, resource = TORCHER,
            state = {rounds = rounds, working = rounds, chambered = 0,
                chamber_empty = 1, spares = spares, capacity = capacity or 100, from = 'copy'}},
        stims = {player = 0x10001,
            stats = {totals = {[STIMS] = used}, main = {[STIMS] = used}, sources = {}}}}
end
local function amounts(result, fuel, stim)
    assert(result.fuel_units == fuel and result.stim_units == stim)
    assert(result.fuel_cents == fuel * 30 and result.stim_cents == stim * 2500)
    assert(result.total_cents == fuel * 30 + stim * 2500)
end

check('confirmed identities and prices are separate from projectile costs', function()
    local f = create()
    assert(f.torcher_resource == TORCHER and f.stims_stat == 3357894537)
    assert(f.fuel_price_cents == 30 and f.stim_price_cents == 2500)
    amounts(f:observe(snapshot(3, 100, 3)), 0, 0)
    amounts(f:observe(snapshot(3, 92, 4)), 8, 1)
end)
check('Torcher shots zero does not prevent exact fuel depletion billing', function()
    local f = create(); local s = snapshot(3, 100, 0)
    s.shots, s.kills, s.fire_kills = 0, 5, 5; f:observe(s)
    s.fuel.state.rounds, s.fuel.state.working = 92, 92
    s.kills, s.fire_kills = 8, 8
    amounts(f:observe(s), 8, 0)
    assert(s.shots == 0 and s.kills == 8 and s.fire_kills == 8)
end)
check('repeated snapshots and hidden HUD never repeat a charge', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    amounts(f:observe(snapshot(3, 90, 1)), 10, 1)
    local s = snapshot(3, 90, 1); s.hud_enabled, s.map_open = false, true
    for i = 1, 200 do amounts(f:observe(s), 0, 0) end
    s.fuel.state.rounds, s.fuel.state.working = 89, 89
    amounts(f:observe(s), 1, 0)
end)
check('partial magazine discard bills exactly the remaining 92 units', function()
    local f = create(); f:observe(snapshot(3, 92, 0))
    amounts(f:observe(snapshot(2, 100, 0)), 92, 0)
end)
check('empty reload changes magazine state without creating fuel consumption', function()
    local f = create(); f:observe(snapshot(2, 0, 0))
    amounts(f:observe(snapshot(1, 100, 0)), 0, 0)
    amounts(f:observe(snapshot(1, 98, 0)), 2, 0)
end)
check('refill rebases upward and only later depletion is charged', function()
    local f = create(); f:observe(snapshot(1, 100, 0))
    local r = f:observe(snapshot(3, 100, 0)); amounts(r, 0, 0)
    assert(r.fuel_status == 'refilled')
    amounts(f:observe(snapshot(3, 96, 0)), 4, 0)
end)
check('inconsistent reserve-first reload snapshot does not invent 100 spent units', function()
    local f = create(); f:observe(snapshot(3, 92, 0))
    local s = snapshot(2, 92, 0); s.fuel.state.working = 100
    amounts(f:observe(s), 0, 0)
    assert(f:observe(s).fuel_status == 'invalid')
    amounts(f:observe(snapshot(2, 100, 0)), 0, 0)
    amounts(f:observe(snapshot(2, 99, 0)), 1, 0)
end)
check('inconsistent rounds-first reload breaks continuity rather than guessing discard', function()
    for _, rounds in ipairs({92, 0}) do
        local f = create(); f:observe(snapshot(3, rounds, 0))
        local s = snapshot(3, 100, 0); s.fuel.state.working = rounds
        amounts(f:observe(s), 0, 0)
        amounts(f:observe(snapshot(2, 100, 0)), 0, 0)
    end
end)
check('inconsistent refill intermediate drop is not mistaken for spending', function()
    local f = create(); f:observe(snapshot(1, 90, 0))
    local s = snapshot(1, 0, 0); s.fuel.state.working = 90
    amounts(f:observe(s), 0, 0)
    amounts(f:observe(snapshot(3, 100, 0)), 0, 0)
    amounts(f:observe(snapshot(3, 99, 0)), 1, 0)
end)
check('actual modified capacity is respected and capacity changes break the baseline', function()
    local f = create(); f:observe(snapshot(3, 200, 0, 200))
    amounts(f:observe(snapshot(3, 192, 0, 200)), 8, 0)
    amounts(f:observe(snapshot(2, 200, 0, 200)), 192, 0)
    amounts(f:observe(snapshot(2, 80, 0, 100)), 0, 0)
    amounts(f:observe(snapshot(2, 79, 0, 100)), 1, 0)
end)
check('chamber flags and projectile pattern never add or consume a unit of fuel', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    local s = snapshot(3, 100, 0); s.fuel.state.chambered = 0xDEADBEEF
    s.fuel.state.chamber_empty = 0; amounts(f:observe(s), 0, 0)
    s.fuel.state.chambered, s.fuel.state.chamber_empty = 0, 1
    amounts(f:observe(s), 0, 0)
end)
check('weapon instance and copy provenance changes cannot compare different stocks', function()
    for _, change in ipairs({'entity', 'from'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(1, 30, 0)
        if change == 'entity' then s.fuel.entity = 0x30002 else s.fuel.state.from = 'type' end
        amounts(f:observe(s), 0, 0)
        s.fuel.state.rounds, s.fuel.state.working = 29, 29
        amounts(f:observe(s), 1, 0)
    end
end)
check('switching away from Torcher or losing the reading breaks fuel continuity', function()
    for _, mode in ipairs({'other_weapon', 'missing'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(0, 0, 1)
        if mode == 'missing' then s.fuel = nil else s.fuel.resource = 'D6B1FB05B9109353' end
        amounts(f:observe(s), 0, 1)
        amounts(f:observe(snapshot(1, 30, 1)), 0, 0)
    end
end)
check('every world mission player peer avatar and life boundary rebases both counters', function()
    for _, key in ipairs({'world', 'mission', 'player', 'peer', 'avatar', 'life'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(1, 30, 3)
        s[key] = type(s[key]) == 'string' and 'world-2' or s[key] + 1
        s.stims.player = s.player; amounts(f:observe(s), 0, 0)
        s.fuel.state.rounds, s.fuel.state.working = 29, 29
        s.stims.stats.totals[STIMS] = 4; amounts(f:observe(s), 1, 1)
    end
end)
check('missing local identity cannot charge and cannot leave a stale baseline', function()
    for _, key in ipairs({'world', 'mission', 'player', 'peer', 'avatar', 'life'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(1, 30, 3); s[key] = nil
        amounts(f:observe(s), 0, 0)
        amounts(f:observe(snapshot(1, 29, 4)), 0, 0)
    end
end)
check('missing fuel state and capacity do not suppress valid stim deltas', function()
    for _, key in ipairs({'state', 'capacity'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(1, 20, 1)
        if key == 'state' then s.fuel.state = nil else s.fuel.state.capacity = nil end
        amounts(f:observe(s), 0, 1)
        amounts(f:observe(snapshot(1, 19, 2)), 0, 1)
    end
end)
check('invalid memory counts and unmatched working copy clear only fuel baseline', function()
    for _, bad in ipairs({{key = 'rounds', value = -1}, {key = 'rounds', value = 101},
        {key = 'spares', value = 1.5}, {key = 'capacity', value = 0},
        {key = 'capacity', value = math.huge}, {key = 'working', value = 99},
        {key = 'spares', value = 0 / 0}, {key = 'from', value = 'unknown'},
        {key = 'spares', value = 4294967296}}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(3, 100, 1); s.fuel.state[bad.key] = bad.value
        amounts(f:observe(s), 0, 1)
        amounts(f:observe(snapshot(3, 90, 2)), 0, 1)
    end
end)
check('stock exceeding exact currency arithmetic cannot produce a giant guessed charge', function()
    local f = create(); local s = snapshot(4294967295, 2147483647, 0, 4294967295)
    assert(f:observe(s).fuel_status == 'invalid')
    amounts(f:observe(snapshot(1, 100, 0)), 0, 0)
end)
check('new life rebases mission cumulative stims without resetting the native count', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    amounts(f:observe(snapshot(3, 100, 5)), 0, 5)
    local s = snapshot(3, 100, 5); s.life, s.avatar = 2, 0x20002
    amounts(f:observe(s), 0, 0)
    s.stims.stats.totals[STIMS] = 6; amounts(f:observe(s), 0, 1)
end)
check('standard stims charge one then two uses and never backfill the initial three', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    amounts(f:observe(snapshot(3, 100, 1)), 0, 1)
    amounts(f:observe(snapshot(3, 100, 3)), 0, 2)
    f = create(); amounts(f:observe(snapshot(3, 100, 3)), 0, 0)
    amounts(f:observe(snapshot(3, 100, 4)), 0, 1)
end)
check('already computed totals use main plus source exactly once', function()
    local f = create(); local s = snapshot(3, 100, 3)
    s.stims.stats.main[STIMS] = 1
    s.stims.stats.sources[TORCHER] = {[STIMS] = 2}; f:observe(s)
    s.stims.stats.main[STIMS], s.stims.stats.totals[STIMS] = 2, 4
    amounts(f:observe(s), 0, 1)
    amounts(f:observe(s), 0, 0)
end)
check('counter rollback rebases and never refunds or recharges prior uses', function()
    local f = create(); f:observe(snapshot(3, 100, 5))
    local r = f:observe(snapshot(3, 100, 0)); amounts(r, 0, 0)
    assert(r.stim_status == 'reset')
    amounts(f:observe(snapshot(3, 100, 1)), 0, 1)
end)
check('teammate and missing stat owners cannot charge local standard stims', function()
    for _, mode in ipairs({'missing', 'teammate'}) do
        local f = create(); f:observe(snapshot(3, 100, 0))
        local s = snapshot(3, 99, 4)
        if mode == 'missing' then s.stims.player = nil else s.stims.player = 0x10002 end
        amounts(f:observe(s), 1, 0)
        amounts(f:observe(snapshot(3, 98, 4)), 1, 0)
        amounts(f:observe(snapshot(3, 97, 5)), 1, 1)
    end
end)
check('received P11 health gains and stim inventory refill create no standard-use charge', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    local s = snapshot(3, 100, 0)
    s.restored_health, s.stim_inventory, s.received_p11 = 100, 6, true
    s.stims.stats.sources.D6B1FB05B9109353 = {[1448579290] = 1}
    amounts(f:observe(s), 0, 0)
    assert(s.stims.stats.sources.D6B1FB05B9109353[1448579290] == 1)
end)
check('actual local injector consuming for teammate follows proven native usage rather than recipient', function()
    local f = create(); f:observe(snapshot(3, 100, 0))
    local s = snapshot(3, 100, 1); s.recipient = 0x10002
    amounts(f:observe(s), 0, 1)
end)
check('missing invalid and failed stim counts never act as zero or alter fuel billing', function()
    for _, value in ipairs({false, -1, 1.5, math.huge, 0 / 0, 2147483648}) do
        local f = create(); f:observe(snapshot(3, 100, 3))
        local s = snapshot(3, 99, 3); s.stims.stats.totals[STIMS] = value
        amounts(f:observe(s), 1, 0)
        amounts(f:observe(snapshot(3, 98, 5)), 1, 0)
    end
    for _, mode in ipairs({'usage', 'stats', 'key'}) do
        local f = create(); f:observe(snapshot(3, 100, 3))
        local s = snapshot(3, 99, 3)
        if mode == 'usage' then s.stims = nil
        elseif mode == 'stats' then s.stims.stats = nil
        else s.stims.stats.totals[STIMS] = nil end
        amounts(f:observe(s), 1, 0)
        amounts(f:observe(snapshot(3, 98, 5)), 1, 0)
    end
end)
check('caller mutation and explicit reset cannot reuse stale observation tables', function()
    local f = create(); local s = snapshot(3, 100, 0); f:observe(s)
    s.mission = 9; s.fuel.state.rounds, s.fuel.state.working = 90, 90
    s.stims.stats.totals[STIMS] = 1; amounts(f:observe(s), 0, 0)
    f:reset(); amounts(f:observe(snapshot(0, 0, 4)), 0, 0)
    amounts(f:observe(nil), 0, 0)
end)
print('Consumable billing: ' .. tests .. ' checks passed; proven-input fixtures only, no game I/O')
