-- Reuse the actual built addon/Runtime memory fixture, replacing only Game/IO boundaries.
local path=assert(arg[2]):gsub('test_consumable_reader.lua$','test_addon_consumables.lua')
local file=assert(io.open(path,'rb'));local source=file:read('*a'):gsub('\r\n','\n');file:close()
local at=assert(source:find('local module=dofile(addon); local state=module.state',1,true))
local extra=[[
local D=require('hd2runtime/domains/player_equipment');local I=D.inventory
local b=require('hd2runtime/core/bytes')
local GAS,HE,KNIFE='0416984F4922757B','6B11FC757618C57E','F7B35A9C5AE340B6'
local function heavy_total(ribbons)
    local n=0;for key,value in pairs(ribbons)do
        if(key=='heavy'or key:sub(1,6)=='heavy_')and type(value)=='number'then n=n+value end
    end;return n
end
local manager,records,counts,descriptors,descriptor=0x410000000,0x411000000,0x412000000,0x413000000,0x414000000
local function inventory(kind,n)
    m:put(m.game+I.global,f.ptr(manager));m:hash(manager,I.hash,m.player.avatar,0)
    m:put(manager+I.records,f.ptr(records));m:put(manager+I.counts,f.ptr(counts))
    m:put(manager+I.descriptors,f.ptr(descriptors));m:put(descriptors,f.ptr(descriptor))
    m:put(descriptor,string.rep('\0',8)..f.u32(m.player.avatar)..string.rep('\0',8)..f.u32(1))
    m:put(records+I.slots.held,f.u32(0))
    m:put(records+I.throwable,b.unhex(kind):reverse());m:put(counts,f.u32(n))
end
for _,pin in ipairs(D.pins)do m:put(m.game+pin.rva,b.unhex(pin.hex))end
inventory(GAS,4)
local credit
local original_runtime=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local value=original_runtime()
    value.events={on=function(name,fn,options)
        assert(name=='player_kill_credited' and options.id=='ledger_source_credit' and options.scope=='session')
        credit=fn;return {state='active'}
    end};return value
end
local module=dofile(addon);local state=module.state
local checks,emitted=0,0
local original_emit=module.charge_notifications.emit
function module.charge_notifications:emit(key,name,amount,now)
    emitted=emitted+amount;assert(key:find('grenade:') and name~='')
    return original_emit(self,key,name,amount,now)
end
local function tick(expected)
    local before=state.total_cents;emitted=0;local sequence=state.sequence
    frame(.1);checks=checks+1
    assert(state.total_cents==expected,checks..': '..state.total_cents..' expected '..expected..' / '..state.grenade_status..' / '..state.grenade_reader.reason)
    assert(emitted==(sequence==state.sequence and expected-before or expected))
end
tick(0);assert(state.grenade_status=='baseline')
local original_type=m.regions[m.entity_manager+f.N.wielder.descriptors]
local function hold_gas()
    m:put(records+I.slots.held,f.u32(m.entity))
    m:put(m.entity_manager+f.N.wielder.descriptors,b.unhex(GAS):reverse()
        ..f.u32(m.entity)..f.u32(29)..f.u32(40)..f.u32(1))
end
inventory(GAS,3);hold_gas();tick(0);tick(0) -- holding is not consumption
inventory(GAS,4);m:put(m.entity_manager+f.N.wielder.descriptors,original_type);tick(0) -- cancel is free
inventory(GAS,3);hold_gas();tick(0)
inventory(GAS,3);m:put(m.entity_manager+f.N.wielder.descriptors,original_type);tick(18000) -- actual release
inventory(GAS,3);tick(18000);assert(state.grenade_units==1 and state.grenade_cents==18000)
assert(#state.entries==1 and state.entries[1].event=='throwable_consumed' and state.entries[1].price_id=='EQ-127')
inventory(GAS,1);tick(54000);tick(54000)
inventory(GAS,6);tick(54000);inventory(GAS,5);tick(72000)
bindings['war_cost_ledger.toggle_hud'].on_press();inventory(GAS,4);tick(90000)
assert(state.grenade_units==5 and state.entries[1].quantity==5)
inventory(HE,3);tick(90000);inventory(HE,2);tick(94500)
assert(#state.entries==2 and state.entries[2].price_id=='EQ-116')
inventory(KNIFE,4);tick(94500);inventory(KNIFE,3);tick(94500)
inventory(GAS,3);tick(94500)
available=false;tick(94500);available=true;inventory(GAS,2);tick(94500)
inventory(GAS,1);tick(112500)
alive=false;inventory(GAS,0);tick(112500)
alive=true;inventory(GAS,4);tick(112500);inventory(GAS,3);tick(130500)
-- A complete peer change, even sharing its low bytes, creates a new baseline.
m.player.peer='0123456789ABCDEF';inventory(GAS,2);tick(130500)
inventory(GAS,1);tick(148500)
-- Public source-credit integration is observational only: no duplicate costs/stats/ribbons.
local before_kills,before_heavy=state.kills,heavy_total(state.ribbons)
credit({local_player=true,kills=2,total=2,sources={{type=SOURCE,name='Stalwart',kills=2}},unattributed=0})
local snap=module.kill_source_snapshot()
assert(snap.subscribed and snap.latest.status=='single_source' and snap.latest.per_victim==false)
assert(state.total_cents==148500 and state.kills==before_kills and heavy_total(state.ribbons)==before_heavy)
mission=false;tick(148500)
assert(saved.last_mission.grenade_cents==148500 and saved.last_mission.grenade_units==9)
assert(saved.last_mission.entries[1].quantity==8 and saved.last_mission.entries[2].quantity==1)
mission=true;inventory(GAS,4);tick(0);assert(not module.kill_source_snapshot().latest)
inventory(GAS,3);tick(18000)
assert(state.entries[1].quantity==1 and state.equipment_ammo_cents==18000 and m.writes==0)
assert(state.grenade_reader.operations_peak<=64 and state.grenade_reader.read_peak<=4096)
print('PASS: '..checks..' actual built disposable grenade bills, gas/HE exact prices, existing debit notifications, refill/type/knife/hidden-HUD/life/peer/gap/save/new-mission; source-credit does not duplicate any counts.')
]]
assert(loadstring(source:sub(1,at-1)..extra,'@grenade-built-integration'))()
