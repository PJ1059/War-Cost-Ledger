-- Independent authority regression against the built addon and its real-memory fixture.
-- Reuse the current integration harness exactly, then supply this extra sequence.
local path = assert(arg[2]):gsub('test_consumable_reader.lua$', 'test_addon_consumables.lua')
local file = assert(io.open(path, 'rb'))
local source = file:read('*a'):gsub('\r\n', '\n'); file:close()
local first = assert(source:find('tick(0); assert(state.inventory_managed', 1, true))
local extra = [[
-- Native stats remain the fee authority while the inventory read is missing.
m.fault=function() return false end
tick(0); assert(not state.inventory_managed['EQ-082'])
ammo(80,3); fired(20); tick(700)
assert(not state.inventory_managed['EQ-082'])
assert(state.entries[1].fired_units==20 and not state.entries[1].inventory_units)
-- The successful baseline frame pays its source-stat growth once, then switches.
m.fault=nil
ammo(70,3); fired(30); tick(1050)
assert(state.inventory_managed['EQ-082'])
assert(state.entries[1].fired_units==30 and not state.entries[1].inventory_units)
ammo(65,3); fired(35); tick(1225)
assert(state.entries[1].fired_units==30 and state.entries[1].inventory_units==5)
-- Missing reads after ownership cause a documented coverage gap; they do not
-- reactivate stats and cannot be retroactively combined with a fresh baseline.
m.fault=function() return false end
ammo(60,3); fired(40); tick(1225)
m.fault=nil; tick(1225)
ammo(55,3); fired(45); tick(1400)
tick(1400)
assert(state.shots==45)
assert(state.entries[1].fired_units==30 and state.entries[1].inventory_units==10)
assert(state.entries[1].quantity==40 and state.entries[1].amount_cents==1400)
assert(state.equipment_ammo_cents==1400 and #state.entries==1 and m.writes==0)
mission=false; tick(1400)
assert(saved.last_mission.entries[1].fired_units==30)
assert(saved.last_mission.entries[1].inventory_units==10)
print('PASS: '..checks..' extra built checks: stats before first inventory baseline, one-way ownership, no double billing or gap back-charge; native shot display and compact summary preserved.')
]]
assert(loadstring(source:sub(1, first - 1) .. extra, '@' .. path .. '#independent-authority-review'))()
