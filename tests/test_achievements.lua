-- Run the built addon, replacing only Runtime's read-only boundaries.
local addon_path = assert(arg[1])
local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for k, v in pairs(value) do out[k] = copy(v) end; return out
end
local SHOTS, KILLS, MELEE, DEATHS = 1448579290, 3566519756, 0xC7680A1B, 2641135157
local FIRE = '27BB558C893383CC'
local data = {fire_history = {kills = 499}, combat_history = {kills = 20, deaths = 4, medals = {}}}
data.career_kd = {version=1,kills=20,deaths=4,anchor_mod_kills=20,anchor_mod_deaths=4}
local mission, available, state_readable, is_local = false, true, true, true
local avatar, lifecycle = 101, 3
local world = {game = 1, view = {slot = function() return {} end}}
local health = {health = 80, max_health = 100, life = 0, descriptor = {entity = avatar, owned = true}}
local stats = {totals = {[SHOTS] = 999, [KILLS] = 10, [MELEE] = 3, [DEATHS] = 2},
    sources = {[FIRE] = {[KILLS] = 5}}}
local frame, draw, binding, state
local reads, health_reads, player_reads, sets, saves = 0, 0, 0, 0, 0
local sets_by_key = {}
local store, mod, overlay = {}, {}, {}
function store:get(key, fallback) return copy(data[key] == nil and fallback or data[key]) end
function store:set(key, value)
    sets = sets + 1; sets_by_key[key] = (sets_by_key[key] or 0) + 1; data[key] = copy(value)
end
function store:save() saves = saves + 1 end
function mod:store() return store end
function mod:log() end
function mod:on_frame(fn) frame = fn end
function mod:bind(id, opts) if id == 'war_cost_ledger.toggle_hud' then binding = opts end end
function overlay:draw(fn) draw = fn end
function overlay:show() end
function overlay:hide() end
package.preload['mods/skyeshade/hd2runtime'] = function()
    return {mod = function() return mod end, ui = {overlay = function(opts)
        assert(opts.visible == false); return overlay
    end}}
end
package.preload['hd2runtime/domains/metadata'] = function() return {version = '0.30.3'} end
package.preload['hd2runtime/domains/event_natives'] = function()
    return {stats = {keys = {projectiles_fired = SHOTS, dealt_kills = KILLS, received_deaths = DEATHS,
        projectiles_hit = 2306495825}}}
end
package.preload['hd2runtime/runtime/event_world'] = function()
    return {
        open = function() return available and world or nil end,
        game_state = function() return state_readable and {mission = mission, host = false} or nil end,
        players = function(_, with_avatars)
            player_reads = player_reads + 1
            assert(with_avatars == mission, 'avatar resolution only belongs to mission observations')
            return {{['local'] = is_local, entity = 42, avatar = avatar, lifecycle = lifecycle},
                    {['local'] = false, entity = 999, avatar = 666, lifecycle = 3}}
        end,
        stat_breakdown = function(_, entity, keys)
            reads = reads + 1
            assert(entity == 42 and #keys == 6 and keys[3] == MELEE and keys[4] == DEATHS
                and keys[5] == 2306495825 and keys[6] == 0xC8256789)
            return stats
        end,
        entity_state = function(_, entity)
            health_reads = health_reads + 1
            assert(entity == avatar and entity ~= 666, 'never read teammate or all-enemy health')
            return health
        end,
    }
end
package.preload['hd2runtime/runtime/beacon_redirect'] = function()
    return {prove = function() return false end, clock = function() return 0 end}
end
package.preload['hd2runtime/runtime/stratagem_loadout'] = function() return {} end
local function load()
    rawset(_G, 'HD2WarCostLedgerV1', nil)
    state = dofile(addon_path).state
end
local function tick() frame(0.1) end
local function render(w, h)
    local texts, rects = {}, {}
    local d = {width = w or 1920, height = h or 1080}
    d.scale = math.min(d.width / 1920, d.height / 1080)
    function d:rect(x, y, width, height)
        rects[#rects + 1] = {x = x, y = y, w = width, h = height}
    end
    function d:text(value, x, y, opts)
        texts[#texts + 1] = {text = tostring(value), x = x, y = y, size = opts.size}
    end
    draw(d)
    return texts, rects
end
local function text_contains(fragment)
    -- KD is cached presentation data; native creation is tested against HUD+.
    local stats=rawget(_G,'HD2WarCostLedgerV1').battle_hud:snapshot({map_open=false}).stats
    local kd=stats.kd=='∞' and 'INF' or stats.kd
    local history=stats.history_kd=='∞' and 'INF' or stats.history_kd
    return ('KD '..kd..' | H '..history):find(fragment,1,true)~=nil
end
local function heal(amount)
    health.health = 0; tick()
    health.health = amount; tick()
end
load(); tick()
assert(health_reads == 0 and state.restored_health == 0, 'ship must not sample health')
mission = true; tick()
assert(state.ribbons.melee == 3 and state.ribbons.ignite == 5 and state.ribbons.firepower == 0)
assert(state.kills == 10 and state.deaths == 2 and state.restored_health == 0 and state.health_ready)
assert(state.history_kills == 20 and state.history_deaths == 4 and state.fire_history == 499,
    'late baseline must not retroactively add native totals to history')
assert(not state.medals.fragrant)
stats.totals[SHOTS], stats.totals[KILLS], stats.totals[MELEE], stats.sources[FIRE][KILLS] = 1000, 11, 4, 6
tick()
assert(state.ribbons.firepower == 1 and state.ribbons.melee == 4 and state.ribbons.ignite == 6)
assert(state.fire_history == 500 and state.medals.fragrant and state.history_kills == 21)
assert(state.mission_medals.fragrant, 'crossing the career threshold is a medal earned in THIS mission')
assert(text_contains('KD 5.50 | H 5.25'))
for _ = 1, 10 do tick() end
assert(state.ribbons.melee == 4 and state.fire_history == 500, 'steady polls never duplicate awards')
stats.totals[MELEE] = -1; stats.totals[DEATHS] = 1.5; stats.totals[SHOTS] = 1999; tick()
assert(state.ribbons.melee == 4 and state.deaths == 2 and state.shots == 1999,
    'bad optional counters must not stop the existing shot/bill reader')
stats.totals[MELEE] = 0; stats.totals[DEATHS] = 2; tick()
stats.totals[MELEE] = 1; stats.totals[SHOTS] = 2000; tick()
assert(state.ribbons.melee == 5 and state.ribbons.firepower == 2, 'native reset keeps observed segments')
print('PASS: melee/fire/1000-shot ribbons, steady polls, exact thresholds, native counter reset, optional failures, local multiplayer ownership and recorded KD baseline.')

health.health = 100; tick(); assert(state.restored_health == 20)
for _ = 1, 9 do heal(100) end
heal(79)
assert(state.life_restored_health == 999 and not state.medals.democracy_undying)
health.health = 80; tick()
assert(state.life_restored_health == 1000 and state.medals.democracy_undying)
assert(state.mission_medals.democracy_undying)
stats.totals[DEATHS] = 3; health.life = 2; health.health = 0; tick()
assert(state.life_restored_health == 0 and state.restored_health == 1000 and not state.health_ready)
assert(state.medals.democracy_undying and state.deaths == 3 and state.history_deaths == 5)
avatar = 102; health = {health = 100, max_health = 100, life = 0, descriptor = {entity = avatar, owned = true}}
tick(); assert(state.restored_health == 1000, 'reinforcement full health is not healing')
health.health = 80; tick(); health.health = 100; tick()
assert(state.life_restored_health == 20 and state.restored_health == 1020)
local before = state.restored_health
health = nil; tick()
health = {health = 100, max_health = 100, life = 0, descriptor = {entity = avatar, owned = true}}
tick(); assert(state.restored_health == before, 'an unreadable gap requires a fresh baseline')
health.health = 70; tick(); health.health = 100; tick(); assert(state.restored_health == before + 30)
before = state.restored_health
health.descriptor.owned = false; health.health = 80; tick()
health.descriptor.owned = true; health.health = 100; tick()
assert(state.restored_health == before, 'unowned descriptors cannot contribute a healing delta')
health.max_health = 200; health.health = 150; tick()
assert(state.restored_health == before, 'a changed health scale must establish a new baseline')
health.health = 160; health.life = 1; tick()
assert(state.restored_health == before + 10, 'Runtime life=1 is still alive')
lifecycle = 2; tick()
assert(state.life_restored_health == 0, 'native waiting-for-reinforcement lifecycle ends the life')
lifecycle = 3; health.health = 200; tick()
assert(state.restored_health == before + 10)
before = state.restored_health
health.health = 100; tick(); available = false; tick(); health.health = 200; available = true; tick()
assert(state.restored_health == before, 'missing world must break healing continuity')
health.health = 100; tick(); state_readable = false; tick(); health.health = 200; state_readable = true; tick()
assert(state.restored_health == before, 'unknown game state must break healing continuity')
health.health = 100; tick(); is_local = false; local local_reads = health_reads; tick()
assert(health_reads == local_reads, 'no local player means no health reads')
health.health = 200; is_local = true; tick(); assert(state.restored_health == before)
local good_stats = stats; stats = nil
health.health = 180; tick(); health.health = 190; tick()
assert(state.restored_health == before + 10 and not state.stats_ready,
    'health awards remain independent of a missing cumulative-stat table')
stats = good_stats
for _, invalid in ipairs({-1, 0.5, math.huge, 0/0, 201}) do
    health.health = invalid; tick()
    assert(not state.health_ready)
end
health.health = 200; tick()
assert(state.restored_health == before + 10, 'invalid samples never inflate healing')
health.descriptor.entity = 666; tick(); health.descriptor.entity = avatar; tick()
assert(state.restored_health == before + 10)
print('PASS: one-life 999/1000 healing, death and reinforcement boundaries, retained earned medal, unreadable/ownership/scale/invalid gaps, Runtime alive states and independent local health sampling.')

health.max_health = 100; health.health = 100; health.life = 0; tick()
local remaining = 4999 - state.restored_health
while remaining > 0 do
    local amount = math.min(100, remaining); heal(amount); remaining = remaining - amount
end
assert(state.restored_health == 4999 and not state.medals.freedom_in_veins)
heal(1)
assert(state.restored_health == 5000 and state.medals.freedom_in_veins)
assert(state.mission_medals.freedom_in_veins)
for _, size in ipairs({{1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}, {3440, 1440}}) do
    local texts, rects = render(size[1], size[2])
    assert(#rects == 0 and #texts == 0, 'native combat HUD has no detached 2D panel')
    local area = 0
    for _, rect in ipairs(rects) do
        assert(rect.x >= size[1] * 0.77 and rect.x + rect.w <= size[1])
        assert(rect.y >= 0 and rect.y + rect.h <= size[2] * 0.12)
        area = area + rect.w * rect.h
    end
    assert(area / (size[1] * size[2]) < 0.015, 'all earned backgrounds together stay below 1.5% of screen')
    for _, item in ipairs(texts) do assert(item.size <= 22 * math.min(size[1] / 1920, size[2] / 1080)) end
end
assert(not text_contains('ME') and not text_contains('H1'), 'letter placeholders must not be drawn')
binding.on_press(); assert(#render() == 0)
heal(10); assert(state.restored_health == 5010, 'F8 only hides badges; earning continues')
binding.on_press()
local before_reads, before_health, before_players, before_sets = reads, health_reads, player_reads, sets
local before_keys = copy(sets_by_key)
for _ = 1, 600 do
    stats.totals[SHOTS] = stats.totals[SHOTS] + 1
    frame(1/60)
end
assert(reads - before_reads == 100 and health_reads - before_health == 100 and player_reads - before_players == 100)
assert(sets - before_sets <= 14, 'persistent tables stay batched to two checkpoints per 10s')
for key, count in pairs(sets_by_key) do
    assert(count - (before_keys[key] or 0) <= 2, key .. ' must not copy on every observation')
end
before_reads, before_health = reads, health_reads
frame(5)
assert(reads == before_reads + 1 and health_reads == before_health + 1, 'no catch-up scan burst after a stall')
stats.totals[KILLS] = stats.totals[KILLS] + 2; mission = false; tick()
assert(data.last_mission.restored_health == 5010 and data.last_mission.medals.democracy_undying
    and data.last_mission.medals.freedom_in_veins and data.last_mission.medals.fragrant)
assert(data.last_mission.ribbons.firepower == 2 and data.last_mission.ribbons.melee == 5)
assert(data.combat_history.kills == 23 and data.combat_history.deaths == 5 and saves == 1)
assert(data.combat_history.medals.democracy_undying and data.combat_history.medals.freedom_in_veins)
print('PASS: mission 4999/5000 healing, numeric panel and removed letter placeholders at five resolutions, F8 earning, 100/600-frame shared-reader budget, no catch-up burst and final-tail storage.')

stats = {totals = {[SHOTS] = 0, [KILLS] = 0, [MELEE] = 0, [DEATHS] = 0}, sources = {}}
mission = true; tick()
assert(state.restored_health == 0 and state.life_restored_health == 0 and state.ribbons.melee == 0
    and state.ribbons.ignite == 0 and state.ribbons.firepower == 0)
assert(not state.medals.democracy_undying and not state.medals.freedom_in_veins and state.medals.fragrant)
assert(next(state.mission_medals) == nil, 'old lifetime unlocks must not appear as newly earned mission medals')
assert(text_contains('KD 0/0 | H 4.60'))
stats.totals[KILLS] = 1; tick(); assert(text_contains('KD 1/0 | H 4.80'))
stats.totals[DEATHS] = 1; tick(); assert(text_contains('KD 1.00 | H 4.00'))
mission = false; tick()
local recorded_kills, recorded_deaths = data.combat_history.kills, data.combat_history.deaths
stats = {totals = {[SHOTS] = 99, [KILLS] = 100, [MELEE] = 20, [DEATHS] = 10}, sources = {}}
mission = true; load(); tick()
assert(state.history_kills == recorded_kills and state.history_deaths == recorded_deaths,
    'reload does not backfill recorded history from already-existing match totals')
assert(state.medals.fragrant and state.restored_health == 0)
assert(next(state.mission_medals) == nil, 'reload must not recreate a historical medal popup')
print('PASS: new-mission clearing, permanent recorded unlock flags, zero-death KD and saved history after reload without retrospective inflation.')
