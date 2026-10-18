-- Exercise the actual built debit sites through the existing native-boundary
-- fixtures. No total-difference inference is used by production notifications.
local addon,runtime_root,integration_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(integration_fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local module=dofile(path);state=module.state
local charges=assert(module.charge_notifications)
local now=0
local function tick() now=now+.1;clock=clock+100000;frame(.1) end
local function rows()
    local found={}
    for _,row in ipairs(charges:snapshot(now,true).items) do found[row.key]=row end
    return found
end
local function total_notices()
    local total=0
    for _,row in ipairs(charges:snapshot(now,true).items) do total=total+row.amount_cents end
    return total
end
local function call(id,entity)
    beacons[entity]={entity=entity,type=id,activated=false};tick()
    beacons[entity].activated=true;tick()
end
local STIMS=0xC8256789
stats.totals[STIMS]=25
stats.totals[SHOTS]=100
stats.sources['968211C0033DCE64']={[SHOTS]=100,[KILLS]=0}
tick()
assert(state.total_cents==0 and total_notices()==0,'initial native counters are baseline, never replayed')
stats.totals[STIMS]=26;tick()
local stim=assert(rows()['stim:EQ-360'])
assert(stim.name:find('治疗') and stim.amount_cents==250000)
stats.totals[SHOTS]=110;stats.sources['968211C0033DCE64'][SHOTS]=110;tick()
assert(total_notices()==250350 and state.total_cents==250350)
local ammo_count=0
for key,item in pairs(rows()) do
    if key:sub(1,5)=='ammo:' then assert(item.amount_cents==350 and item.name:find('弹药'));ammo_count=ammo_count+1 end
end
assert(ammo_count==1)
stats.totals[SHOTS]=120;stats.sources['968211C0033DCE64'][SHOTS]=120;tick()
assert(total_notices()==250700)
call(1238358532,1001)
assert(total_notices()==state.total_cents and state.total_cents==5950700)
local call_count=0
for key,item in pairs(rows()) do if key:sub(1,5)=='call:' then assert(item.amount_cents==5700000);call_count=call_count+1 end end
assert(call_count==1)
call(3108516875,2001)
barrages={{entity=3001,payload='0xEF66B417EDC3B1D6',fired=0}};tick()
assert(state.total_cents==5950700,'unfired barrage has no notice or fee')
barrages[1].fired=3;tick()
assert(state.total_cents==12250700 and total_notices()==state.total_cents)
local shell_count=0
for key,item in pairs(rows()) do if key:sub(1,6)=='shell:' then assert(item.name:find('炮弹'));shell_count=shell_count+1 end end
assert(shell_count==1)
local amount=total_notices();tick();tick();assert(total_notices()==amount,'unchanged observations do not duplicate notices')
-- A native counter gap is not backcharged or replayed as a notification.
stats.totals[STIMS]=nil;tick();stats.totals[STIMS]=40;tick()
assert(total_notices()==amount and state.total_cents==amount)
-- Changing historical account/display data is not a debit source.
state.history_kills=999999;state.history_deaths=1;tick()
assert(total_notices()==amount)
-- Preview uses separate factory models and cannot fabricate a real debit.
module.game_hud:start_preview(4,now)
assert(total_notices()==amount)
for i=1,25 do tick() end
assert(total_notices()==0 and state.total_cents==amount,'expired notices leave the bill unchanged')
stats.totals[STIMS]=41;tick()
assert(total_notices()==250000,'only the new debit enters the next batch')
active=false;tick()
assert(total_notices()==0 and saved.last_mission.total_cents==amount+250000)
active=true;stats.totals[STIMS]=0;tick()
assert(total_notices()==0 and state.total_cents==0,'mission transition clears presentation independently')
print('PASS: built addon directly emits confirmed stim, ammunition, stratagem, orbital-shell fees; no baseline replay, duplicate polling, gap catch-up, history-derived fee, preview mutation or mission leakage.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@charge-notification-integration'))()
