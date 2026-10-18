-- Actual built addon and shared consumable fixture; only Game/IO boundaries mocked.
local fixture_path = assert(arg[2]):gsub('test_consumable_reader.lua$', 'test_addon_consumables.lua')
local file = assert(io.open(fixture_path, 'rb'))
local source = file:read('*a'):gsub('\r\n', '\n'); file:close()
local start = assert(source:find('local module=dofile(addon); local state=module.state', 1, true))
local extra = [[
local STIMS, P11 = 0xC8256789, 'D6B1FB05B9109353'
local STIM_PRICE = 250000 -- User-confirmed 2500 MC per standard stim; P11 retains its own price.
local stats_reads, stats_fail, local_missing, health_fail = 0, false, false, false
local reverse_players = false
local original_factory = package.preload['hd2runtime/runtime/event_world']
package.preload['hd2runtime/runtime/event_world'] = function()
    local api = original_factory()
    local original_health = api.entity_state
    api.stat_breakdown = function(world, player_entity, requested, block)
        assert(player_entity == m.player.entity, 'must read local player, not slot 0 or avatar')
        local count = 0
        for _, key in ipairs(requested) do if key == STIMS then count = count + 1 end end
        assert(count == 1, 'STIMS must share the existing stat request exactly once')
        stats_reads = stats_reads + 1
        if stats_fail then return nil end
        return stats
    end
    api.players = function()
        local other = {['local'] = false, entity = 99, peer = '0123456789ABCDEF'}
        if local_missing then return {other} end
        if reverse_players then return {other, m.player} end
        return {m.player, other}
    end
    api.entity_state = function(...)
        if health_fail then return nil end
        return original_health(...)
    end
    return api
end
stats.totals[STIMS] = 0
local module = dofile(addon); local state = module.state
local checks = 0
local p11_cost = 0
local function tick(stim_units, reads)
    local cents = stim_units * STIM_PRICE + p11_cost
    local before = stats_reads
    frame(0.1); checks = checks + 1
    assert(state.total_cents == cents, checks .. ': ' .. tostring(state.total_cents) .. ' expected ' .. cents)
    assert(stats_reads - before == (reads or 1), 'extra or missing stat snapshot ' .. checks)
end
local function used(n) stats.totals[STIMS] = n end
tick(0); assert(state.stims_used == 0 and state.stim_units == 0)
used(1); tick(1)
assert(state.stim_units == 1 and state.stim_cents == STIM_PRICE and state.stims_used == 1)
assert(#state.entries == 1 and state.entries[1].event == 'stim_used')
assert(state.entries[1].price_id == 'EQ-360' and state.entries[1].unit_cents == STIM_PRICE)
used(3); tick(3); tick(3)
bindings['war_cost_ledger.toggle_hud'].on_press(); used(4); tick(4)
assert(state.stim_units == 4 and state.entries[1].quantity == 4)
-- Health, held weapon, SHOTS and avatar availability are independent of standard stims.
m:put(m.held_slots, f.u32(0)); health_fail = true; stats.totals[SHOTS] = nil
used(5); tick(5); assert(not state.stats_ready and state.stim_units == 5)
stats.totals[SHOTS] = 0; health_fail = false; alive = false
m.player.avatar = nil; used(6); tick(6)
m.player.avatar = m.avatar; alive = true; stats.totals[DEATHS] = 1
used(7); tick(7); assert(state.deaths == 1 and state.stim_units == 7)
-- Local identification follows peer flag after slot reorder, not the first player.
reverse_players = true; used(8); tick(8)
stats.sources[P11] = {[SHOTS] = 0, [KILLS] = 0}; tick(8)
assert(state.stim_units == 8 and #state.entries == 1)
-- A P11 shot is charged once as projectile ammunition, not a standard-stim use.
fired(2, P11); p11_cost = 5000; tick(8)
assert(state.stim_units == 8 and state.entries[2].price_id == 'EQ-073')
assert(state.entries[2].quantity == 2 and state.entries[2].amount_cents == 5000)
used(9); tick(9)
-- Invalid or failed native snapshots create a gap, never an inferred debit.
stats_fail = true; used(15); tick(9)
stats_fail = false; tick(9); used(16); tick(10)
used(-1); tick(10); used(20); tick(10); used(21); tick(11)
used(0); tick(11); used(1); tick(12)
available = false; used(10); tick(12, 0)
available = true; tick(12); used(11); tick(13)
local_missing = true; used(20); tick(13, 0)
local_missing = false; tick(13); used(21); tick(14)
-- Explicit local player generation/peer changes do not carry old account growth.
m.player.entity = 20; used(30); tick(14); used(31); tick(15)
m.player.peer = '0123456789ABCDE0'; used(40); tick(15); used(41); tick(16)
assert(#state.entries == 2 and state.entries[1].quantity == 16)
assert(state.stim_units == 16 and state.stim_cents == 16 * STIM_PRICE)
-- The last available mission statistic is charged before end_mission persists.
mission = false; used(42); tick(17)
assert(saved.last_mission.total_cents == 17 * STIM_PRICE + p11_cost)
assert(saved.last_mission.stim_units == 17 and saved.last_mission.stim_cents == 17 * STIM_PRICE)
assert(saved.last_mission.entries[1].quantity == 17 and #saved.last_mission.entries == 2)
-- New mission starts a new baseline and merged row; no previous bill leakage.
mission = true; used(5); p11_cost = 0; tick(0)
assert(state.stims_used == 5 and state.stim_units == 0 and #state.entries == 0)
used(6); tick(1)
assert(#state.entries == 1 and state.entries[1].quantity == 1 and m.writes == 0)
print('PASS: ' .. checks .. ' actual built stim checks: one shared snapshot, 2500 MC/use, independent ammo/health/HUD, no duplicate charges, lifecycle gaps, final mission flush.')
]]
assert(loadstring(source:sub(1, start - 1) .. extra, '@' .. fixture_path .. '#stim-integration'))()
