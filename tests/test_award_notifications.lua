local create = dofile(assert(arg[1]))
local icons = {
    {id = 'R01', key = 'air', name = '防空', kind = 'ribbon', colour = '#8BBAD6'},
    {id = 'R02', key = 'heavy', name = '反重', kind = 'ribbon'},
    {id = 'M01', key = 'harvester', name = '民主收割机', kind = 'medal'},
    {id = 'M02', key = 'expert', name = '防空专家', kind = 'medal'},
}
local function find(items, id)
    for _, item in ipairs(items) do if item.id == id then return item end end
end
local function unique(view)
    local seen = {}
    for _, group in ipairs({view.items, view.ribbons, view.medals}) do
        for _, item in ipairs(group) do assert(not seen[item.id], 'one type appears only once'); seen[item.id] = true end
    end
end
local state = {sequence = 4, ribbons = {air = 12, heavy = 0}, mission_medals = {harvester = true}}
local notices = create(state, icons)
local first = notices:snapshot(20, true, true)
assert(#first.items == 0 and #first.ribbons == 1 and first.ribbons[1].count == 12)
assert(#first.medals == 1 and first.deadline == nil, 'first observation must not replay old awards')
assert(notices:snapshot(20.5, true, true) == first, 'idle frames retain the exact snapshot')
state.ribbons.air = 13
local one = notices:snapshot(21, true, true)
assert(#one.items == 1 and one.items[1].count == 1 and one.items[1].total == 13 and one.deadline == 23)
assert(#one.ribbons == 0 and #one.medals == 1)
unique(one)
state.ribbons.air, state.ribbons.heavy, state.mission_medals.expert = 15, 2, true
local mixed = notices:snapshot(22, true, true)
assert(#mixed.items == 3 and find(mixed.items, 'R01').count == 3 and find(mixed.items, 'R02').count == 2)
assert(find(mixed.items, 'M02').count == 1 and mixed.deadline == 24)
unique(mixed)
assert(notices:snapshot(23.99, true, true) == mixed, 'same totals never postpone the shared deadline')
local collected = notices:snapshot(24, true, false)
assert(#collected.items == 0 and #collected.medals == 2 and #collected.ribbons == 0 and collected.deadline == nil)
local mapped = notices:snapshot(24, true, true)
assert(#mapped.ribbons == 2 and find(mapped.ribbons, 'R01').count == 15)
assert(find(mapped.ribbons, 'R02').count == 2 and #mapped.medals == 2)
unique(mapped)

state.ribbons.air = 16
local late = notices:snapshot(30, true, false)
assert(#late.items == 1 and late.items[1].count == 1 and late.deadline == 32, 'new batch contains only new growth')
assert(#notices:snapshot(1000, true, true).items == 0, 'a long frame must finish the batch immediately')
state.ribbons.air, state.ribbons.heavy = nil, 0
state.mission_medals.expert = false
local missing = notices:snapshot(1001, true, true)
assert(find(missing.ribbons, 'R01').count == 16 and find(missing.ribbons, 'R02').count == 2)
assert(#missing.items == 0 and #missing.medals == 2)
state.ribbons.air, state.ribbons.heavy, state.mission_medals.expert = 16, 2, true
assert(notices:snapshot(1002, true, true) == missing, 'backward/absent read recovery cannot duplicate awards')
for _, value in ipairs({-1, 1.5, math.huge, 0/0}) do
    state.ribbons.air = value
    assert(notices:snapshot(1003, true, true) == missing, 'invalid counts must not replace verified totals')
end
state.ribbons.air = 17
local hidden = notices:snapshot(1004, false, true)
assert(#hidden.items == 0 and #hidden.medals == 0 and #hidden.ribbons == 0 and hidden.deadline == 1006)
assert(#notices:snapshot(1005, true, false).items == 1, 'hiding must not suppress observation')
notices:snapshot(1006, false, false)
assert(find(notices:snapshot(1007, true, true).ribbons, 'R01').count == 17, 'hidden timeout still collects totals')

state.sequence, state.ribbons, state.mission_medals = 5, {air = 0, heavy = 0}, {}
local reset = notices:snapshot(1010, true, true)
assert(#reset.items == 0 and #reset.ribbons == 0 and #reset.medals == 0 and reset.deadline == nil)
state.ribbons.air, state.mission_medals.expert = 2, true
local new_mission = notices:snapshot(1011, true, true)
assert(#new_mission.items == 2 and find(new_mission.items, 'R01').count == 2)
assert(new_mission.deadline == 1013, 'an award may trigger again in a new mission')
state.sequence, state.ribbons, state.mission_medals = 6, {heavy = 3}, {harvester = true}
local advanced = notices:snapshot(1012, true, true)
assert(#advanced.items == 2 and find(advanced.items, 'R02').count == 3)
assert(find(advanced.items, 'M01') and not find(advanced.items, 'M02'), 'new sequence drops stale recent items')
assert(advanced.deadline == 1014, 'growth arriving with a new sequence starts from its zero baseline')

local unavailable = {sequence = 1}
local reader = create(unavailable, icons)
assert(#reader:snapshot(0, true, true).items == 0)
unavailable.ribbons, unavailable.mission_medals = {air = 8}, {expert = true}
local baseline = reader:snapshot(1, true, true)
assert(#baseline.items == 0 and find(baseline.ribbons, 'R01').count == 8 and #baseline.medals == 1)
unavailable.ribbons.air = 9
assert(reader:snapshot(2, true, true).items[1].count == 1, 'first valid read establishes a baseline')
unavailable.sequence = nil
assert(reader:snapshot(2.5, true, true).items[1].count == 1, 'missing sequence must not reset a known mission')
local deadline = reader.deadline
assert(reader:snapshot(1.5, true, true).deadline == deadline, 'a stale caller cannot rewind the clock')
assert(#reader:snapshot(4, true, true).items == 0)
assert(not pcall(function() reader:update(math.huge) end))
assert(not pcall(function() reader:update(0/0) end))

-- A sequence starts before native stats are ready. A late join's first raw
-- cumulative values must be silently established in that ready frame.
state.sequence, state.ribbons, state.mission_medals = 7, {air = 0}, {}
notices:snapshot(1200, true, true)
state.ribbons.air, state.mission_medals.harvester = 20, true
notices:baseline(1201)
local ready = notices:snapshot(1201, true, true)
assert(#ready.items == 0 and ready.deadline == nil and find(ready.ribbons, 'R01').count == 20)
assert(find(ready.medals, 'M01') and state.mission_medals.harvester == true and state.ribbons.air == 20,
    'baseline must retain earned medals and never modify the ledger')
state.ribbons.air, state.ribbons.heavy = 21, 5
local after_ready = notices:snapshot(1202, true, true)
assert(#after_ready.items == 1 and find(after_ready.items, 'R01').count == 1)
assert(find(after_ready.ribbons, 'R02').count == 5,
    'a source missing at baseline waits for its own first valid read without replay')
state.ribbons.heavy = 6
assert(find(notices:snapshot(1203, true, true).items, 'R02').count == 1)
-- Even if an adapter observes first stats immediately before the baseline call,
-- the stale burst is removed while all verified totals remain collected.
notices:baseline(1203)
local quiet = notices:snapshot(1203, true, true)
assert(#quiet.items == 0 and quiet.deadline == nil and #quiet.medals == 1)
assert(find(quiet.ribbons, 'R01').count == 21 and find(quiet.ribbons, 'R02').count == 6)
notices:baseline(1201)
state.ribbons.air = 22
assert(notices:snapshot(1202, true, true).deadline == 1205,
    'baseline and subsequent calls cannot reset the monotonic clock')
state.sequence, state.ribbons, state.mission_medals = 8, {air = 50}, {expert = true}
notices:baseline(1210)
local direct_ready = notices:snapshot(1210, true, true)
assert(#direct_ready.items == 0 and find(direct_ready.ribbons, 'R01').count == 50 and #direct_ready.medals == 1,
    'baseline may be the first observation of a new sequence')
assert(not pcall(function() notices:baseline(math.huge) end))

-- Retained snapshots prevent allocations at render frequency. With GC paused,
-- unchanged 10,000-frame updates must keep memory and table identity stable.
local retained = reader:snapshot(10, true, true)
collectgarbage('collect'); collectgarbage('stop')
local memory = collectgarbage('count')
for index = 1, 10000 do assert(reader:snapshot(10 + index / 1000, true, true) == retained) end
local growth = collectgarbage('count') - memory
collectgarbage('restart')
assert(growth < 16, 'unchanged frames allocate no snapshots: ' .. tostring(growth) .. ' KiB')
print('PASS: initial and late-join ready baselines, mixed same-frame growth, unique types, shared 2s collection, idle cache, late batch, long frame, hidden recording, invalid/backward reads, mission reset and 10000-frame allocation check.')

local repeats={sequence=20,ribbons={},mission_medals={harvester=true}}
local repeated=create(repeats,icons)
assert(#repeated:snapshot(0,true,true).items==0)
repeats.mission_medals.harvester=2
local twice=repeated:snapshot(.1,true,true)
assert(find(twice.items,'M01').count==1 and find(twice.items,'M01').total==2)
repeats.mission_medals.harvester=4
assert(find(repeated:snapshot(.2,true,true).items,'M01').count==3)
local folded=repeated:snapshot(3,true,true)
assert(find(folded.medals,'M01').count==4 and #folded.items==0)
repeats.mission_medals.harvester=true
assert(repeated:snapshot(3.1,true,true)==folded,'bool fallback cannot lower the numeric high water')
repeats.mission_medals.harvester=5
local again=repeated:snapshot(3.2,true,true)
assert(find(again.items,'M01').count==1 and find(again.items,'M01').total==5)
print('PASS: bool-to-count notifications, same-batch repeated acquisitions, fold totals and no rollback replay.')
