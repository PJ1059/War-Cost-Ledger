local create = dofile(assert(arg[1]))
local A, B = '0123456789ABCDEF', 'FEDCBA9876543210'
local api = create({[A] = {name_zh = '测试步枪'}, [B] = {name_zh = '测试手雷'}})
local function event(kills, sources, unknown)
    return {local_player = true, mission = 9, frame = 100, time = 10,
        kills = kills, total = 30, sources = sources, unattributed = unknown}
end
local original = event(2, {{type = A:lower(), name = 'test rifle', kills = 2}}, 0)
local batch = assert(api:observe(original))
assert(batch.status == 'single_source' and batch.label == '测试步枪' and batch.known_kills == 2)
assert(batch.sources[1].type == A and batch.per_victim == false)
assert(original.sources[1].type == A:lower() and not original.status, 'Runtime snapshot remains unchanged')
batch = assert(api:observe(event(3, {{type = A, kills = 1}, {type = B, kills = 2}}, 0)))
assert(batch.status == 'mixed_sources' and batch.label == '混合来源')
assert(batch.sources[1].type == B and batch.sources[1].kills == 2 and batch.unknown_kills == 0)
assert(not batch.entity_id and not batch.weapon_for_victim, 'no guessed weapon-to-enemy mapping')
batch = assert(api:observe(event(4, {{type = A, kills = 3}}, 1)))
assert(batch.status == 'mixed_sources' and batch.known_kills == 3 and batch.unknown_kills == 1)
batch = assert(api:observe(event(2, nil, nil)))
assert(batch.status == 'unknown_source' and batch.label == '未知来源' and batch.unknown_kills == 2)
assert(batch.label ~= '持续伤害', 'unassigned stats do not prove damage over time')
batch = assert(api:observe(event(1, {{type = 'unsupported', name = 'opaque source', kills = 1}}, 0)))
assert(batch.status == 'unknown_source' and #batch.sources == 0 and batch.unknown_kills == 1)
batch = assert(api:observe(event(3, {{type = A, kills = 1}, {type = A, kills = 2}}, 0)))
assert(batch.status == 'single_source' and #batch.sources == 1 and batch.sources[1].kills == 3)
local last = api.latest
local rejected, why = api:observe(event(1, {{type = A, kills = 2}}, 0))
assert(not rejected and why == 'INCONSISTENT_SOURCE_COUNTS' and api.latest == last)
local foreign = event(1, {{type = A, kills = 1}}, 0); foreign.local_player = false
assert(select(2, api:observe(foreign)) == 'NOT_LOCAL_CREDIT')
assert(select(2, api:observe(event(0, {}, 0))) == 'INVALID_KILL_GROWTH')
assert(select(2, api:observe(event(1.5, {}, 0))) == 'INVALID_KILL_GROWTH')
local invalid = event(1, {{type = A, kills = 1}}, 0); invalid.total = 0
assert(select(2, api:observe(invalid)) == 'INVALID_KILL_TOTAL')
local many = {}; for i = 1, 65 do many[i] = {type = A, kills = 0} end
assert(select(2, api:observe(event(1, many, 1))) == 'INVALID_SOURCE_COUNTS')
api:reset(); assert(not api.latest and api.diagnostics.kills == 0)
local callback, options, event_name, callbacks = nil, nil, nil, 0
local runtime = {on = function(name, handler, opts)
    event_name, callback, options = name, handler, opts
    return {state = 'active'}
end}
local subscription = api:subscribe(runtime, 'mods/test/ledger', function(value)
    callbacks = callbacks + 1; assert(value == api.latest)
end)
assert(subscription.state == 'active' and event_name == 'player_kill_credited')
assert(options.id == 'ledger_source_credit' and options.scope == 'session' and options.owner == 'mods/test/ledger')
callback(original)
assert(callbacks == 1 and api.diagnostics.batches == 1 and api.diagnostics.kills == 2)
callback(foreign); assert(callbacks == 1)
assert(select(2, api:subscribe({})) == 'RUNTIME_EVENTS_UNAVAILABLE')
print('PASS: Runtime source credit batches: single, mixed, unknown, no victim guess, local-only, bounded validation and isolated subscription.')
