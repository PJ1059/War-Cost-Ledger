-- Actual built addon uses native fixture for held heat reserve plus real generated prices.
local addon,fixture,runtime=assert(arg[1]),assert(arg[2]),assert(arg[3])
local path=fixture:gsub('test_consumable_reader.lua$','test_addon_consumables.lua')
local file=assert(io.open(path,'rb'));local source=file:read('*a'):gsub('\r\n','\n');file:close()
local at=assert(source:find('local module=dofile(addon); local state=module.state',1,true))
local prefix=source:sub(1,at-1):gsub("local SOURCE='A6A735ACCB4A327F'","local SOURCE='8645F167B3C813A2'")
local extra=[[
local b=require('hd2runtime/core/bytes')
local heat,heat_states,heat_descs,heat_desc=0x430000000,0x431000000,0x432000000,0x433000000
m:put(m.game+0x3326D48,f.ptr(heat));m:put(heat+20,f.u32(1));m:hash(heat,40,m.entity,0)
m:put(heat+64,f.ptr(heat_descs));m:put(heat_descs,f.ptr(heat_desc))
m:put(heat_desc,b.unhex(SOURCE):reverse()..f.u32(m.entity)..f.u32(29)..f.u32(40)..f.u32(1))
m:put(heat+88,f.ptr(heat_states))
local reader_path=fixture_path:gsub('tests/test_consumable_reader.lua$','src/consumable-reader.lua')
local code_file=assert(io.open(reader_path,'rb'));local reader_code=code_file:read('*a');code_file:close()
for rva,hex in reader_code:gmatch("{rva=(%d+),hex='([%x]+)'}")do m:put(m.game+tonumber(rva),b.unhex(hex))end
local function reserve(n,temperature)m:put(heat_states,f.u32(n)..b.encode(temperature or 0,'f32')..f.u32(0))end
reserve(3,0)
local module=dofile(addon);local state=module.state
local checks=0
local function tick(cents)
    frame(.1);checks=checks+1
    assert(state.total_cents==cents,checks..': '..state.total_cents..' expected '..cents
        ..' / '..tostring(state.consumption_status)..' / '..tostring(state.consumable_reader.reason))
end
tick(0)
assert(state.inventory_managed['EQ-044-HEATSINK'] and not state.inventory_managed['EQ-044'])
fired(10);reserve(3,75);tick(10)
assert(state.entries[1].name:find('武器维护折旧费',1,true))
reserve(3,0);tick(10) -- natural cooling does not buy a heatsink
reserve(2,0);tick(7510)
assert(state.entries[2].price_id=='EQ-044-HEATSINK' and state.entries[2].quantity==1)
assert(state.entries[2].name:find('散热片',1,true))
reserve(3,0);tick(7510);reserve(2,0);tick(15010) -- refill is free, next replacement is charged
fired(20);tick(15020) -- maintenance never disabled by the separate reserve authority
mission=false;tick(15020)
assert(saved.last_mission.total_cents==15020 and #saved.last_mission.entries==2)
-- A backpack weapon is billed on each mother shot, including shots after refill.
local AC='A8CFFB316F0B5C5F'
m=f.memory(false,AC)
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0},sources={}}
mission=true;tick(0);fired(1,AC);tick(12000)
-- Inventory replenishment itself adds no cost; following shot still does.
ammo(100,8);tick(12000);fired(2,AC);tick(24000)
mission=false;tick(24000)
assert(saved.last_mission.entries[1].price_id=='EQ-087' and saved.last_mission.entries[1].quantity==2)
-- Current B/FLAM-80 fuel lives in the matching worn backpack Deposit.
local ED=require('hd2runtime/domains/player_equipment');local I,P=ED.inventory,ED.deposit
local FUEL,PACK='78A8185F63A70795','43EB1C3C1A1860E0'
m=f.memory(false,FUEL)
local inv,ids,who,rows=0x440000000,0x441000000,0x442000000,0x443000000
local dep,descs,desc,states=0x450000000,0x451000000,0x452000000,0x453000000
m:put(m.game+I.global,f.ptr(inv));m:hash(inv,I.hash,m.avatar,2)
m:put(inv+I.descriptors,f.ptr(ids));m:put(ids+16,f.ptr(who))
m:put(who,string.rep('\0',8)..f.u32(m.avatar)..f.u32(29)..f.u32(40)..f.u32(1))
m:put(inv+I.records,f.ptr(rows));m:put(rows+2*I.stride+I.slots.backpack,f.u32(88))
m:put(dep+P.descriptors,f.ptr(descs));m:put(descs+24,f.ptr(desc))
m:put(desc,b.unhex(PACK):reverse()..f.u32(88)..f.u32(29)..f.u32(40)..f.u32(1))
m:put(m.game+P.global,f.ptr(dep));m:hash(dep,P.hash,88,3);m:put(dep+P.live,f.ptr(states))
for rva,hex in reader_code:gmatch("{rva=(%d+),hex='([%x]+)'}")do m:put(m.game+tonumber(rva),b.unhex(hex))end
local function fuel(n)m:put(states+3*P.liveStride+P.amount,f.u32(n))end
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0},sources={}}
mission=true;fuel(500);tick(0);assert(state.inventory_managed['EQ-113'])
fuel(490);tick(300);assert(state.fuel_units==10 and state.fuel_cents==300)
fuel(500);tick(300);fuel(498);tick(360)
mission=false;tick(360)
assert(saved.last_mission.fuel_units==12 and saved.last_mission.entries[1].price_id=='EQ-113')
assert(m.writes==0 and state.consumable_reader.operations_peak<=64)
print('PASS: '..checks..' actual built maintenance/heatsink separate fees, free cooling/refill, reused reserve cost, AC-8 mother rounds after refill and saved entries')
]]
assert(loadstring(prefix..extra,'@billing-052-built-integration'))()
