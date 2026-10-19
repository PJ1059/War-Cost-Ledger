-- Runs the actual built entry with simulated read-only HD2Runtime interfaces.
-- This fixture owns a ready legacy native host. Runtime-only drawing has its
-- actual-built coverage in test_addon_overlay_068.lua.
rawset(_G,'HD2WarCostLedgerNativeHUDV1',{ready=true})
local addon_path = assert(arg[1], 'built addon path required')
local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for k, v in pairs(value) do out[k] = copy(v) end; return out
end
local data, logs, frame, draw = {}, {}
local current = {game = 1}
local mission, host, player_count, local_player = false, true, 1, true
local readable, proved, ids_proved, available = true, true, true, true
local list = {}
local saves, reads, last_texts = 0, 0, {}
local stat_reads, world_reads, player_reads, store_sets = 0, 0, 0, 0
local sets_by_key = {}
local SHOTS, KILLS = 1448579290, 3566519756
local stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}
local SOURCE_A, SOURCE_B = 'A6A735ACCB4A327F', 'B43235DBD493750C'
current.view = {slot = function() return {} end}
local store = {}
function store:get(key, fallback) if data[key] == nil then return fallback end; return copy(data[key]) end
function store:set(key, value)
    store_sets = store_sets + 1; sets_by_key[key] = (sets_by_key[key] or 0) + 1
    data[key] = copy(value)
end
function store:save() saves = saves + 1; return true end
local mod = {}
function mod:store() return store end
function mod:log(message) logs[#logs + 1] = message end
function mod:on_frame(fn) frame = fn end
local overlay = {}
function overlay:draw(fn) draw = fn end
function overlay:show() end
function overlay:hide() end
function mod:bind() return {state = 'active'} end
package.preload['mods/skyeshade/hd2runtime'] = function()
    return {mod = function() return mod end, ui = {overlay = function() return overlay end}}
end
package.preload['hd2runtime/domains/metadata'] = function() return {version = '0.30.3'} end
package.preload['hd2runtime/runtime/event_world'] = function()
    return {
        open = function() world_reads = world_reads + 1; if available then return current end; return nil, 'unavailable test' end,
        game_state = function() return {mission = mission, host = host} end,
        entity_state = function() return nil, 'fixture has no avatar Health record' end,
        players = function()
            player_reads = player_reads + 1
            local out = {}; for i = 1, player_count do
                out[i] = {['local'] = i == 1 and local_player, entity = i == 1 and 42 or 999}
            end
            return out
        end,
        stat_breakdown = function(_, player_entity, keys)
            stat_reads = stat_reads + 1
            assert(player_entity == 42, 'must only read the local player')
            assert(keys[1] == SHOTS and keys[2] == KILLS)
            return stats
        end,
    }
end
package.preload['hd2runtime/runtime/beacon_redirect'] = function()
    return {
        prove = function() return proved, 'pins changed test' end,
        beacons = function() if readable then return list end; return nil, 'unreadable test' end,
        clock = function() return 123456789 end,
        -- A write, native call or exclusive watch requested here would make the test fail.
    }
end
package.preload['hd2runtime/runtime/stratagem_loadout'] = function()
    return {
        prove = function() return ids_proved, 'ids changed test' end,
        id_of = function(_, kind)
            reads = reads + 1
            if kind == 92 then return 458198946 end
            if kind == 93 then return 14345846 end
            return 999
        end,
    }
end
package.preload['hd2runtime/domains/event_natives'] = function()
    return {stats = {keys = {projectiles_fired = SHOTS, dealt_kills = KILLS,
        received_deaths = 2641135157, projectiles_hit = 0x897A5551}}}
end
local module = dofile(addon_path)
local state = module.state
local d = {scale = 1, width = 1920, height = 1080}
function d:rect(...) end
function d:text(text) last_texts[#last_texts + 1] = tostring(text) end
local function tick() frame(0.1); last_texts = {}; draw(d) end
local function beacon(entity, activated, kind)
    list[entity] = {entity = entity, activated = activated, type = kind or 92}
end
local function total(cents, count)
    assert(state.total_cents == cents, 'unexpected total ' .. state.total_cents)
    assert(#state.entries == count, 'unexpected entry count ' .. #state.entries)
end

tick(); total(0, 0)
mission = true; tick(); total(0, 0)
assert(state.sequence == 1)
-- Arrow input and carrying the ball create no active beacon.
for _ = 1, 5 do tick() end; total(0, 0)
-- Existing active beacon at the first observation must not produce a new charge.
beacon(10, true); tick(); total(0, 0)
list = {}; tick()
-- A thrown ball not yet activated costs nothing; removal before activation also costs nothing.
beacon(11, false); tick(); total(0, 0)
list = {}; tick(); total(0, 0)
-- Activation yields exactly one call. Polling it for 120 more frames never duplicates it.
beacon(12, false); tick(); beacon(12, true); tick(); total(4200000, 1)
for _ = 1, 120 do tick() end; total(4200000, 1)
assert(#last_texts == 0, 'combat must not duplicate the native HUD with a flat overlay')
assert(state.entries[1].name == 'MG-43 机枪')
assert(state.entries[1].transport_cents == 3000000)
assert(state.entries[1].equipment_cents == 1200000)
assert(state.entries[1].prepaid_ammo_cents == 0)
assert(state.entries[1].game_clock_us == 123456789)
assert(data.last_mission.total_cents == 4200000)
-- Other stratagem types must not be mistaken for MG-43.
beacon(13, false, 1); tick(); beacon(13, true, 1); tick(); total(4200000, 1)
-- A second independent call is charged once; the stable native ID is cached.
beacon(14, false); tick(); beacon(14, true); tick(); total(8400000, 2)
assert(reads == 2, 'ID lookup should occur once per stratagem type')
-- Missing proof/read causes no financial event.
beacon(15, false); tick(); proved = false; beacon(15, true); tick(); total(8400000, 2)
proved = true; list = {}; tick()
beacon(16, false); tick(); ids_proved = false; beacon(16, true); tick(); total(8400000, 2)
ids_proved = true; list = {}; tick()
beacon(17, false); tick(); readable = false; beacon(17, true); tick(); total(8400000, 2)
readable = true; list = {}; tick()
-- Multiplayer pauses the remainder of this test mission, including after the peer leaves.
player_count = 2; tick()
assert(state.coverage == 'local_stats_calls_paused')
beacon(18, false); tick(); beacon(18, true); tick(); total(8400000, 2)
player_count = 1; beacon(19, false); tick(); beacon(19, true); tick(); total(8400000, 2)
mission = false; tick()
assert(state.status == 'ended' and data.last_mission.status == 'ended' and saves == 1)
total(8400000, 2)
-- New mission resets totals; no retroactive call on entry.
mission = true; tick(); total(0, 0); assert(state.sequence == 2)
list = {}; tick()
-- Host and local-player identity have to agree before we attribute a cost.
host = false; beacon(20, false); tick(); beacon(20, true); tick(); total(0, 0)
host = true; local_player = false; beacon(21, false); tick(); beacon(21, true); tick(); total(0, 0)
local_player = true; player_count = 0; beacon(22, false); tick(); beacon(22, true); tick(); total(0, 0)
player_count = 1; beacon(23, false); tick(); beacon(23, true); tick(); total(4200000, 1)
-- Module loaded twice does not install another callback, reset totals or duplicate the cost.
local old_frame = frame
assert(dofile(addon_path) == module and frame == old_frame)
tick(); total(4200000, 1)
available = false; tick(); total(4200000, 1)
available = true; mission = false; tick()
assert(data.last_mission.total_cents == 4200000)
print('PASS: real addon code; activation, cancelled/old/other beacons, deduplication, saved details, HUD text, mission reset, native proof/read gates, solo ownership and reload.')

-- New slice: M-105 call-in, source-attributed round billing and native personal match counters.
list = {}; stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}
mission = true; tick(); total(0, 0)
assert(state.shots == 0 and state.kills == 0 and state.m105_billed_shots == 0)
beacon(30, false, 93); tick(); total(0, 0)
beacon(30, true, 93); tick(); total(3840000, 1)
assert(state.call_counts.m105 == 1 and state.call_counts.mg43 == 0)
for _ = 1, 120 do tick() end; total(3840000, 1)
assert(state.entries[1].name == 'M-105 盟友' and state.entries[1].equipment_cents == 840000)
-- A batch of 250 rounds must charge 250 * 35 cents, not one event/frame/trigger.
stats = {totals = {[SHOTS] = 270, [KILLS] = 11},
    sources = {[SOURCE_A] = {[SHOTS] = 250}, ['OTHER_WEAPON'] = {[SHOTS] = 15},
               ['UNKNOWN_SOURCE'] = {[SHOTS] = 5}}}
tick(); total(3848750, 2)
assert(state.shots == 270 and state.kills == 11)
assert(state.m105_billed_shots == 250 and state.ammo_cents == 8750)
assert(state.entries[2].quantity == 250 and state.entries[2].name == 'M-105 盟友弹药')
assert(#last_texts==0, 'native combat presentation must have no flat text duplicate')
for _ = 1, 120 do tick() end; total(3848750, 2)
-- Two source variants in one poll, plus unrelated and unattributed shots: only M-105 sources incur cost.
stats = {totals = {[SHOTS] = 305, [KILLS] = 15},
    sources = {[SOURCE_A] = {[SHOTS] = 255}, [SOURCE_B] = {[SHOTS] = 20},
               ['OTHER_WEAPON'] = {[SHOTS] = 25}, ['UNKNOWN_SOURCE'] = {[SHOTS] = 5}}}
tick(); total(3849625, 2)
assert(state.m105_billed_shots == 275 and state.shots == 305 and state.kills == 15)
assert(state.entries[2].quantity == 275, 'ammo must remain a compact aggregate entry')
-- Kills can grow without a shot (for example a stratagem): no additional ammunition fee.
stats.totals[KILLS] = 35; tick(); total(3849625, 2); assert(state.kills == 35)
-- Temporary unavailable stats retain the last totals and recover the missing delta once.
local valid_stats = stats
stats = nil; tick(); total(3849625, 2); assert(state.shots == 305 and not state.stats_ready)
valid_stats.totals[SHOTS] = 315; valid_stats.sources[SOURCE_B][SHOTS] = 30
stats = valid_stats; tick(); total(3849975, 2)
assert(state.shots == 315 and state.m105_billed_shots == 285 and state.stats_ready)
-- Stats/round costs still work with an unavailable beacon API; the systems must be independent.
proved = false
stats.totals[SHOTS] = 320; stats.sources[SOURCE_B][SHOTS] = 35; tick(); total(3850150, 2)
proved = true
-- A second player never contributes their stats; own ammo still counts, while call-in detection pauses.
player_count = 2; host = false
stats.totals[SHOTS] = 325; stats.totals[KILLS] = 36; stats.sources[SOURCE_B][SHOTS] = 40
tick(); total(3850325, 2)
assert(state.shots == 325 and state.kills == 36 and state.m105_billed_shots == 295)
assert(state.coverage == 'local_stats_calls_paused')
beacon(31, false, 93); tick(); beacon(31, true, 93); tick(); total(3850325, 2)
assert(state.call_counts.m105 == 1)
mission = false; tick()
assert(data.last_mission.shots == 325 and data.last_mission.kills == 36)
assert(data.last_mission.entries[2].quantity == 295)
-- The new mission has a fresh native baseline: pickup ammo can be billed without another procurement.
player_count, host, list = 1, true, {}
stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}
mission = true; tick(); total(0, 0)
assert(state.shots == 0 and state.kills == 0 and state.m105_billed_shots == 0)
stats = {totals = {[SHOTS] = 2, [KILLS] = 1}, sources = {[SOURCE_A] = {[SHOTS] = 2}}}
tick(); total(70, 1); assert(state.call_counts.m105 == 0)
-- A reset native table preserves the observed segment; subsequent new counts add to it once.
stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}; tick(); total(70, 1)
stats = {totals = {[SHOTS] = 3, [KILLS] = 2}, sources = {[SOURCE_A] = {[SHOTS] = 3}}}
tick(); total(175, 1); assert(state.shots == 5 and state.kills == 3 and state.m105_billed_shots == 5)
-- Invalid read cannot turn a fractional/negative count into an invoice.
stats = {totals = {[SHOTS] = -1, [KILLS] = 4}, sources = {[SOURCE_A] = {[SHOTS] = 4}}}
tick(); total(175, 1); assert(not state.stats_ready)
mission = false; tick()
-- Starting observation mid-mission displays native totals but does not retro-bill already-fired ammo.
stats = {totals = {[SHOTS] = 150, [KILLS] = 10}, sources = {[SOURCE_A] = {[SHOTS] = 100}}}
mission = true; tick(); total(0, 0)
assert(state.shots == 150 and state.kills == 10 and state.m105_fired == 100)
stats.totals[SHOTS] = 160; stats.sources[SOURCE_A][SHOTS] = 110; tick(); total(350, 1)
assert(state.shots == 160 and state.m105_billed_shots == 10)
print('PASS: M-105 procurement, 250-round burst pricing, variant source attribution, no pricing of unknown/other sources, ammo aggregation, all-weapon personal shots, stratagem-inclusive kills, read recovery, multiplayer locality, counter reset, pickup and mid-mission baseline.')

-- Source policy: napalm and flame weapons count; HE airstrike, delivery pods, lasers and generic kills don't.
mission = false; tick()
local FLAM, NAPALM, ORBITAL = '39AB99895147A3BF', '27BB558C893383CC', 'A16AB4FF66AE6970'
local LASER, HE, POD = 'D54B9505C0F72873', '2EA01CB1676ACA29', 'E90F771A36FB441E'
stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}
mission = true; tick()
assert(state.fire_kills == 0 and state.ribbons.ignite == 0 and state.fire_history == 0)
stats = {totals = {[SHOTS] = 10, [KILLS] = 28},
    sources = {[FLAM] = {[KILLS] = 3}, [NAPALM] = {[KILLS] = 4}, [ORBITAL] = {[KILLS] = 5},
        [LASER] = {[KILLS] = 4}, [HE] = {[KILLS] = 4}, [POD] = {[KILLS] = 4},
        ['unknown'] = {[KILLS] = 4}}}
tick(); assert(state.fire_kills == 12 and state.ribbons.ignite == 12 and state.fire_history == 12)
for _ = 1, 30 do tick() end
assert(state.fire_kills == 12 and state.fire_history == 12, 'no duplicate counting on steady polls')
stats = nil; tick(); assert(not state.stats_ready and state.fire_kills == 12)
stats = {totals = {[SHOTS] = 10, [KILLS] = 30}, sources = {[FLAM] = {[KILLS] = 5},
    [NAPALM] = {[KILLS] = 4}, [ORBITAL] = {[KILLS] = 5}}}
tick(); assert(state.fire_kills == 14 and state.fire_history == 14, 'temporary read gap is recovered')
-- Death/reset in the same mission preserves prior observed totals, with each variant counted once.
stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}; tick()
stats.totals[KILLS] = 2; stats.sources[FLAM] = {[KILLS] = 2}; tick()
assert(state.fire_kills == 16 and state.fire_history == 16)
mission = false; tick()
assert(data.fire_history.kills == 16 and data.last_mission.ribbons.ignite == 16)
-- New match clears the ribbon; historical totals persist. 500 observed kills unlock 香喷喷.
stats = {totals = {[SHOTS] = 0, [KILLS] = 0}, sources = {}}; mission = true; tick()
assert(state.fire_kills == 0 and state.fire_history == 16 and not state.medals.fragrant)
stats.totals[KILLS] = 483; stats.sources[FLAM] = {[KILLS] = 483}; tick()
assert(state.fire_history == 499 and not state.medals.fragrant)
stats.totals[KILLS] = 484; stats.sources[FLAM][KILLS] = 484; tick()
assert(state.fire_history == 500 and state.medals.fragrant)
mission = false; tick(); assert(data.fire_history.kills == 500)
-- Late/reloaded observation never backfills the history from already-accounted native counters.
stats = {totals = {[SHOTS] = 100, [KILLS] = 50}, sources = {[FLAM] = {[KILLS] = 50}}}
mission = true; tick(); assert(state.fire_kills == 50 and state.fire_history == 500)
stats.totals[KILLS] = 51; stats.sources[FLAM][KILLS] = 51; tick()
assert(state.fire_kills == 51 and state.fire_history == 501)
print('PASS: flame/napalm source accounting, exclusion, missing reads, resets, per-match ribbon, cumulative history and 500 threshold; late baseline is not backfilled.')

-- 600 gameplay frames at 60fps must perform 100 observations, not 600 source scans/store copies.
local before_stats, before_world, before_players, before_sets = stat_reads, world_reads, player_reads, store_sets
local before_keys = copy(sets_by_key)
for _ = 1, 600 do
    stats.totals[SHOTS] = stats.totals[SHOTS] + 1
    frame(1/60)
end
assert(stat_reads - before_stats == 100 and world_reads - before_world == 100 and player_reads - before_players == 100)
assert(store_sets - before_sets <= 14, 'persistent tables must stay batched to two checkpoints per 10s')
for key,count in pairs(sets_by_key) do
    assert(count-(before_keys[key] or 0)<=2, key..' must not copy on every observation')
end
local before_lag = stat_reads
frame(5); assert(stat_reads == before_lag + 1, 'a long frame must not trigger a catch-up burst')
-- Final tail is read and flushed immediately, even if the normal checkpoint is not due.
stats.totals[KILLS] = 52; stats.sources[FLAM][KILLS] = 52; mission = false; tick()
assert(data.last_mission.fire_kills == 52 and data.fire_history.kills == 502)
print('PASS: 60fps observation budget 100/600 frames, one shared stat read, batched storage, no lag catch-up, final tail checkpoint.')

-- Regression: diagnostic time must use actual frame time, not observer carry-over or its initial preset.
package.preload['hd2runtime/runtime/mod_store'] = function() return {} end
local io_open = io.open
local checks = 0
io.open = function(path, ...)
    if path:find('ledger_probe_request.json', 1, true) then checks = checks + 1; return nil end
    return io_open(path, ...)
end
data.probe_enabled = true
rawset(_G, 'HD2WarCostLedgerV1', nil); dofile(addon_path)
for _ = 1, 600 do frame(1/60) end
assert(checks == 10, 'enabled probe must check exactly 10 times in 10 seconds at 60fps')
checks = 0
rawset(_G, 'HD2WarCostLedgerV1', nil); dofile(addon_path)
for _ = 1, 167 do frame(0.06) end
assert(checks == 10, 'observer fractional remainder must not be added twice to probe time')
io.open = io_open
print('PASS: integrated probe cadence at 60fps and irregular frame time, including initial observer preset.')
