-- Actual built addon + actual Runtime memory reader. Only native process IO is a fixture.
local addon, fixture_path, runtime_root = assert(arg[1]), assert(arg[2]), assert(arg[3])
local old_arg=arg
HD2_CONSUMABLE_FIXTURE_ONLY=true
arg={fixture_path:gsub('tests/test_consumable_reader.lua$', 'src/consumable-reader.lua'),runtime_root}
local f=dofile(fixture_path)
arg=old_arg; HD2_CONSUMABLE_FIXTURE_ONLY=nil
-- Keep the real Runtime loader for data/read functions, but permit the explicit
-- mocked frame/player API below to replace the boundary to the running game.
local runtime_loader=table.remove(package.loaders,1)
table.insert(package.loaders,2,runtime_loader)
local SHOTS,KILLS,DEATHS=f.N.stats.keys.projectiles_fired,f.N.stats.keys.dealt_kills,f.N.stats.keys.received_deaths
local SOURCE='A6A735ACCB4A327F'
local m=f.memory(false,SOURCE)
local frame, draw, bindings, saved=nil,nil,{},{}
local available,mission,alive=true,true,true
local stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0},sources={}}
local function clone(v) if type(v)~='table' then return v end; local r={};for k,x in pairs(v) do r[k]=clone(x) end;return r end
local store,mod,overlay={},{},{}
function store:get(k,v) return clone(saved[k]==nil and v or saved[k]) end
function store:set(k,v) saved[k]=clone(v) end
function store:save() end
function mod:store() return store end
function mod:log() end
function mod:bind(id,v) bindings[id]=v;return {} end
function mod:on_frame(fn) frame=fn end
function overlay:draw(fn) draw=fn end
function overlay:show() end
function overlay:hide() end
package.preload['mods/skyeshade/hd2runtime']=function() return {mod=function() return mod end,ui={overlay=function() return overlay end}} end
package.loaded['hd2runtime/runtime/event_world']=nil
package.preload['hd2runtime/runtime/event_world']=function()
    return setmetatable({open=function() return available and m.world end,
        game_state=function() return {mission=mission,host=true} end,
        players=function() return {m.player,{['local']=false,entity=99,peer='ally'}} end,
        entity_state=function(_,avatar) return {life=alive and 0 or 2,health=alive and 100 or 0,max_health=100,
            descriptor={entity=avatar,owned=true}} end,
        stat_breakdown=function() return stats end,
        health_header=function() return nil end}, {__index=f.world_api})
end
package.preload['hd2runtime/runtime/beacon_redirect']=function() return {prove=function() return false end,clock=function() return 100000 end,beacons=function()return {}end} end
package.preload['hd2runtime/runtime/stratagem_loadout']=function() return {prove=function() return false end,id_of=function()return nil end} end
local function ammo(rounds,spares,empty,working)
    m:put(m.records+f.D.turretWeapon.magazine.stride,f.u32(working or rounds)..f.u32(0)..f.u32(1)..f.u32(0))
    m:put(m.entries+f.D.ammo.entryStride,f.u32(spares)..f.u32(rounds)..string.char(empty or 0,0,0,0))
end
local function fired(n,resource)
    resource=resource or SOURCE
    stats.totals[SHOTS]=n; stats.sources[resource]={[SHOTS]=n,[KILLS]=0}
end
ammo(100,3)
-- Fee semantics use a deterministic clock. The reader's separate suite tests
-- real pre-read soft-budget exits; LuaJIT compilation timing is not a fee input.
os.clock=function() return 0 end
local module=dofile(addon); local state=module.state
local checks=0
local function tick(cents)
    frame(0.1); checks=checks+1
    assert(state.total_cents==cents,checks..': '..state.total_cents..' expected '..cents)
end
tick(0); assert(state.inventory_managed['EQ-082'],tostring(state.consumption_status)..' / '..tostring(state.consumable_reader.reason))
ammo(80,3); fired(20);tick(700)
assert(state.shots==20 and state.entries[1].inventory_units==20)
ammo(100,2);tick(3500) -- 80 discarded, zero new SHOTS
tick(3500);tick(3500) -- no duplicate polling charge
ammo(0,2,1); fired(121);tick(7035) -- 101 cartridges inc chamber consumed
ammo(99,1);tick(7035) -- dry reload costs nothing
ammo(100,3);tick(7035) -- refill costs nothing
bindings['war_cost_ledger.toggle_hud'].on_press()
ammo(95,3); fired(126);tick(7210) -- hidden HUD still records
assert(state.shots==126 and #state.entries==1)
-- Reserve-first reload does not prematurely bill one whole extra magazine.
ammo(0,2,1,95);tick(7210)
ammo(100,2);tick(10535)
-- Switching away invalidates inventory; source stats cannot double bill it.
local held=m.regions[m.held_slots]; m:put(m.held_slots,f.u32(0));fired(130);tick(10535)
m:put(m.held_slots,held);ammo(80,2);tick(10535) -- newly seen stock is a baseline
ammo(70,2);fired(140);tick(10885)
available=false;tick(10885)
available=true;ammo(20,2);fired(190);tick(10885)
ammo(10,2);fired(200);tick(11235)
alive=false;ammo(0,0,1);tick(11235)
alive=true;ammo(100,3);tick(11235)
ammo(99,3);fired(201);tick(11270)
assert(state.equipment_ammo_cents==11270 and state.kills==0)
mission=false;tick(11270)
assert(saved.last_mission.total_cents==11270)
-- A fresh mission of Torcher fire has no native SHOTS but still pays for fuel.
m=f.memory(false,f.TORCHER); ammo(100,3)
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0},sources={}}
mission=true;tick(0);assert(state.inventory_managed['EQ-054'],tostring(state.consumption_status)..' / '..tostring(state.consumable_reader.reason))
ammo(92,3); stats.totals[KILLS]=9; stats.sources[f.TORCHER]={[SHOTS]=0,[KILLS]=9};tick(240)
assert(state.shots==0 and state.kills==9 and state.fire_kills==9)
ammo(100,2);tick(3000) -- remaining 92 fuel discarded on refill
assert(state.fuel_units==100 and state.fuel_cents==3000 and #state.entries==1)
assert(state.entries[1].price_id=='EQ-054' and state.entries[1].name:find('燃料'))
ammo(100,4);tick(3000)
mission=false;tick(3000)
assert(saved.last_mission.fuel_units==100 and m.writes==0)
assert(state.consumable_reader.operations_peak<=48 and state.consumable_reader.read_peak<=4096)
print('PASS: '..checks..' built addon billing checks using actual Runtime memory fields; discarded clips, fuel, no double charges, refill, reload, hidden HUD, lifecycle/gaps, preserved SHOTS/FIRE and compact saved bills.')
