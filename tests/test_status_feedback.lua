-- Every event below is synthetic. Passing this test proves no native game interface.
local create = dofile(assert(arg[1]))
local tests = 0
local function check(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end
local function event(status, id, period, kind, generation)
    return {verified = true, local_player = true, hostile = true, status = status or 'fire',
        target = {id = id or 'enemy-1', generation = generation or 1},
        cycle_id = period or 'period-1', kind = kind or 'effective'}
end
local function slots(values)
    local n = 0; for _ in pairs(values) do n = n + 1 end; return n
end

check('first effective application counts; requests, ticks, refreshes and kills do not', function()
    local f = create()
    for _, kind in ipairs({'request', 'tick', 'refresh', 'kill'}) do
        assert(not f:accept(event('fire', nil, nil, kind), 0))
    end
    assert(f:accept(event(), 1))
    for _, kind in ipairs({'request', 'tick', 'refresh', 'kill'}) do
        assert(not f:accept(event('fire', nil, nil, kind), 2.9))
    end
    assert(f.cumulative.status_fire == 1 and f.cumulative.status_poison == 0)
    assert(f:visible(3, false, true) == nil, 'rejected activity must not refresh the deadline')
end)
check('rapid duplicate observations keep two stable slots and one period record', function()
    local f = create(); local recent, cumulative = f.recent, f.cumulative
    assert(f:accept(event(), 0))
    for i = 1, 10000 do assert(not f:accept(event(), i / 10000)) end
    assert(f.recent == recent and f.cumulative == cumulative)
    assert(slots(f.recent) == 2 and slots(f.cumulative) == 2 and f.cycle_count == 1)
    assert(f.cumulative.status_fire == 1 and f.recent.status_fire == 1)
end)
check('a real end permits a new period; old replay and repeated end stay rejected', function()
    local f = create(); assert(f:accept(event(), 1))
    assert(not f:accept(event('fire', nil, 'period-2'), 1.1))
    assert(f:accept(event('fire', nil, nil, 'ended'), 1.2))
    assert(not f:accept(event('fire', nil, nil, 'ended'), 1.3))
    assert(not f:accept(event(), 1.3))
    assert(f:accept(event('fire', nil, 'period-2'), 1.4))
    assert(not f:accept(event('fire', nil, 'period-1', 'ended'), 1.5))
    assert(not f:accept(event('fire', nil, 'period-3'), 1.5))
    assert(f.cumulative.status_fire == 2 and f.cycle_count == 2)
end)
check('lost actors, disconnected reads and icon collection never end a period', function()
    local f = create(); assert(f:accept(event(), 1))
    for _, kind in ipairs({'disappeared', 'read_disconnected', 'missing', 'unknown'}) do
        assert(not f:accept(event('fire', nil, nil, kind), 2))
    end
    assert(f:visible(100, false, true) == nil)
    assert(not f:accept(event(), 100))
    assert(not f:accept(event('fire', nil, 'period-2'), 100))
    assert(not f:accept(event('fire', nil, 'unseen-period', 'ended'), 100))
    assert(f.cumulative.status_fire == 1)
end)
check('entity reuse requires generation and cannot end the previous generation', function()
    local f = create(); assert(f:accept(event(), 1))
    assert(not f:accept(event('fire', nil, nil, 'ended', 2), 1.1))
    assert(f:accept(event('fire', nil, nil, 'effective', 2), 1.2))
    assert(not f:accept(event(), 1.3))
    assert(f.cumulative.status_fire == 2 and f.cycle_count == 2)
end)
check('identity tokens keep numeric, string and delimiter-containing identities separate', function()
    local f = create()
    assert(f:accept(event('fire', 1, 1), 0))
    assert(f:accept(event('fire', '1', 1), 0))
    assert(f:accept(event('fire', 's1:a', 'b:c', nil, 'g:1'), 0))
    assert(f:accept(event('fire', 'a', 's3:b:c', nil, '1'), 0))
    assert(f.cumulative.status_fire == 4)
end)
check('fire aliases count a shared effective period once', function()
    local f = create(); assert(f:accept(event('fire'), 1))
    assert(not f:accept(event('burning_heavy'), 1.1))
    assert(f:accept(event('burning_heavy', nil, nil, 'ended'), 1.2))
    assert(f:accept(event('burning_heavy', nil, 'period-2'), 1.3))
    assert(not f:accept(event('fire', nil, 'period-2'), 1.4))
    assert(f.cumulative.status_fire == 2)
end)
check('gas damage and both confusion aliases count one shared gas application', function()
    local f = create(); assert(f:accept(event('gas'), 1))
    for _, status in ipairs({'gas_2', 'gas_confusion', 'gas_confusion_2'}) do
        assert(not f:accept(event(status), 1.1))
    end
    assert(f.cumulative.status_poison == 1)
    assert(f:accept(event('gas_confusion_2', nil, nil, 'ended'), 1.2))
    assert(f:accept(event('gas_2', nil, 'period-2'), 1.3))
    assert(f.cumulative.status_poison == 2)
end)
check('experimental poison and unproved status aliases never become player gas', function()
    local f = create()
    for _, status in ipairs({'poison', 'burning', 'guessed_fire', 'confusion', 'status_fire'}) do
        assert(not f:accept(event(status), 0))
    end
    assert(f.cumulative.status_fire == 0 and f.cumulative.status_poison == 0 and f.cycle_count == 0)
end)
check('area application to eight proven enemies adds eight; an aggregate count is refused', function()
    local f = create()
    for i = 1, 8 do assert(f:accept(event('gas', 'enemy-' .. i, 'area-1'), 1)) end
    for i = 1, 8 do assert(not f:accept(event('gas_2', 'enemy-' .. i, 'area-1'), 1.1)) end
    local aggregate = event('gas', 'enemy-9', 'area-1'); aggregate.count = 8
    assert(not f:accept(aggregate, 1.2))
    assert(f.cumulative.status_poison == 8 and f.recent.status_poison == 8 and f.cycle_count == 8)
end)
check('fire and gas periods on the same enemy remain independent', function()
    local f = create(); assert(f:accept(event('fire'), 1)); assert(f:accept(event('gas'), 1))
    assert(f:accept(event('fire', nil, nil, 'ended'), 1.1))
    assert(f:accept(event('fire', nil, 'period-2'), 1.2))
    assert(not f:accept(event('gas', nil, 'period-2'), 1.2))
    assert(f.cumulative.status_fire == 2 and f.cumulative.status_poison == 1)
end)
check('both types collect together two seconds after the last new success', function()
    local f = create(); assert(f:accept(event('fire'), 0)); assert(f:accept(event('gas'), 1))
    local shown = f:visible(2.5, false, true)
    assert(shown.status_fire == 1 and shown.status_poison == 1)
    assert(not f:accept(event('burning_heavy'), 2.6))
    assert(not f:accept(event('gas', nil, nil, 'refresh'), 2.7))
    assert(f:accept(event('gas', nil, nil, 'ended'), 2.8))
    shown = f:visible(2.999, false, true)
    assert(shown.status_fire == 1 and shown.status_poison == 1)
    assert(f:visible(3, false, true) == nil)
    assert(f.recent.status_fire == 0 and f.recent.status_poison == 0)
    local map = f:visible(3, true, true)
    assert(map.status_fire == 1 and map.status_poison == 1)
    assert(f:accept(event('fire', 'enemy-2'), 3.1))
    assert(f.recent.status_fire == 1 and f.cumulative.status_fire == 2)
    assert(f.recent.status_poison == 0 and f.cumulative.status_poison == 1)
end)
check('map totals, F8 hiding and match reset preserve stable counter tables', function()
    local f = create(); local recent, cumulative = f.recent, f.cumulative
    assert(f:accept(event('fire'), 1)); assert(f:visible(1.1, false, false) == nil)
    assert(f:accept(event('gas'), 1.2))
    assert(f:visible(10, true, true) == cumulative)
    assert(cumulative.status_fire == 1 and cumulative.status_poison == 1)
    assert(f:visible(10, false, true) == nil)
    assert(f:visible(10, true, false) == nil)
    f:reset()
    assert(f.recent == recent and f.cumulative == cumulative and f.cycle_count == 0)
    assert(cumulative.status_fire == 0 and cumulative.status_poison == 0)
    assert(not f:accept(event('fire', nil, nil, 'ended'), 0))
    assert(f:accept(event(), 0), 'a new match starts its own period history')
end)
check('unverified, remote and non-hostile evidence cannot create or end a period', function()
    local f = create(); assert(f:accept(event(), 1))
    for _, field in ipairs({'verified', 'local_player', 'hostile'}) do
        for _, kind in ipairs({'effective', 'ended'}) do
            local sample = event('fire', 'enemy-2', nil, kind); sample[field] = false
            assert(not f:accept(sample, 1.1))
            sample = event('fire', nil, nil, 'ended'); sample[field] = nil
            assert(not f:accept(sample, 1.1))
        end
    end
    assert(not f:accept(event('fire', nil, 'period-2'), 1.2))
    assert(f.cumulative.status_fire == 1)
end)
check('complete identities and period tokens are required; invalid fields are rejected', function()
    local f = create()
    for _, field in ipairs({'id', 'generation'}) do
        local sample = event(); sample.target[field] = nil; assert(not f:accept(sample, 0))
        for _, bad in ipairs({'', -1, 1.5, math.huge, 0/0, true, {}, string.rep('x', 129)}) do
            sample = event(); sample.target[field] = bad; assert(not f:accept(sample, 0))
        end
    end
    for _, bad in ipairs({'', -1, 1.5, math.huge, 0/0, true, {}, string.rep('x', 129)}) do
        local sample = event(); sample.cycle_id = bad; assert(not f:accept(sample, 0))
    end
    local sample = event(); sample.cycle_id = nil; assert(not f:accept(sample, 0))
    sample = event(); sample.target = nil; assert(not f:accept(sample, 0))
    assert(not f:accept(nil, 0) and not f:accept('effective', 0))
    assert(f.cycle_count == 0 and f.cumulative.status_fire == 0)
end)
check('invalid or backwards time cannot count, end or show a period', function()
    local f = create(); assert(f:accept(event(), 2)); f:collect(5)
    for _, bad in ipairs({-1, math.huge, 0/0, 4.9}) do
        assert(not f:accept(event('gas'), bad))
        assert(not f:accept(event('fire', nil, nil, 'ended'), bad))
        assert(not f:collect(bad) and f:visible(bad, true, true) == nil)
    end
    assert(not f:accept(event('fire', nil, 'period-2'), 5))
    assert(f.cumulative.status_fire == 1 and f.cumulative.status_poison == 0)
end)
check('bounded period history retains tombstones and refuses new periods when full', function()
    local f = create()
    for i = 1, f.max_cycles do assert(f:accept(event('fire', i), 0)) end
    assert(f.cycle_count == 4096 and not f.capacity_reached)
    assert(not f:accept(event('fire', 'overflow'), 0) and f.capacity_reached)
    assert(f:accept(event('fire', 1, nil, 'ended'), 0))
    assert(not f:accept(event('fire', 1), 0), 'retired period must not be evicted')
    assert(not f:accept(event('fire', 1, 'period-2'), 0))
    assert(f.cycle_count == f.max_cycles and f.cumulative.status_fire == 4096)
    assert(slots(f.recent) == 2 and slots(f.cumulative) == 2)
    f:reset(); assert(not f.capacity_reached and f:accept(event('fire', 1), 0))
end)
check('retired synthetic status applications cannot become kill ribbons', function()
    local create_hud = dofile(assert(arg[2]))
    local f, enabled = create(), true
    local state = {ribbons = {ignite = 82}, mission_medals = {}}
    local hud = create_hud(state, function() return enabled end)
    for i = 1, 8 do assert(f:accept(event('fire', i), 0)) end
    for i = 1, 12 do assert(f:accept(event('gas', i), 0)) end
    state.ribbons.status_fire, state.ribbons.status_poison = f.cumulative.status_fire, f.cumulative.status_poison
    local map = hud:snapshot({map_open = true, width = 336})
    assert(#map.ribbons == 1 and map.ribbons[1].name == '燃烧击杀' and map.ribbons[1].count == 82)
    assert(hud:snapshot({map_open = false}).ribbons[1] == nil)
    enabled = false; assert(not hud:snapshot({map_open = true}).shown)
    assert(f:accept(event('fire', 'hidden-enemy'), 1))
    state.ribbons.status_fire = f.cumulative.status_fire
    enabled = true; map = hud:snapshot({map_open = true})
    assert(#map.ribbons == 1 and state.ribbons.ignite == 82 and not state.ribbons.poison)
end)
print('Status-feedback prototype: ' .. tests .. ' checks passed; synthetic effective periods only; no native reader or install')
