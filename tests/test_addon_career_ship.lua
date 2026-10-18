-- Built addon -> real native reader + saved Career bytes -> store and HUD totals.
-- Only process/frame boundaries and the local-peer fixture are simulated.
local addon_path,runtime,reader_test,reader_source,fixture_path=assert(arg[1]),assert(arg[2]),
    assert(arg[3]),assert(arg[4]),assert(arg[5])
local original_arg=arg
HD2_CAREER_FIXTURE_ONLY=true
arg={reader_source,runtime,fixture_path}
local f=dofile(reader_test)
arg=original_arg;HD2_CAREER_FIXTURE_ONLY=nil
local runtime_loader=table.remove(package.loaders,1)
table.insert(package.loaders,2,runtime_loader)
local m=f.memory()
local b,N=f.b,require('hd2runtime/domains/event_natives')
local K,D,S,H=N.stats.keys.dealt_kills,N.stats.keys.received_deaths,
    N.stats.keys.projectiles_fired,N.stats.keys.projectiles_hit
local function clone(v)
    if type(v)~='table' then return v end
    local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out
end
local saved={combat_history={kills=449,deaths=2,medals={fragrant=true}},
    career_kd={version=1,kills=351849,deaths=4633,anchor_mod_kills=449,anchor_mod_deaths=2},
    ui_settings={auto_ui_probe=false,career_page_sync=false},probe_enabled=false}
local frame,logs,writes,saves=nil,{}, {},0
local store={get=function(_,k,v)return clone(saved[k]==nil and v or saved[k])end,
    set=function(_,k,v)writes[#writes+1]=k;saved[k]=clone(v)end,
    save=function()saves=saves+1 end}
local mod={store=function()return store end,log=function(_,v)logs[#logs+1]=v end,
    bind=function()end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return {
    mod=function()return mod end,ui={overlay=function()return {
        draw=function()end,show=function()end,hide=function()end}end}}end
local available,mission=true,false
local player={['local']=true,entity=42,peer=f.peer}
local stats={totals={[K]=0,[D]=0,[S]=0,[H]=0},sources={}}
m.world.view.slot=function()return{}end
m.world.view.pointer,m.world.view.u32,m.world.view.fill=nil,nil,nil
package.loaded['hd2runtime/runtime/event_world']=nil
package.preload['hd2runtime/runtime/event_world']=function()return {
    open=function()return available and m.world end,
    game_state=function()return {state=mission and 4 or 3,mission=mission,host=true}end,
    players=function()return {player}end,
    stat_breakdown=function()return stats end,
    health_header=function()return nil end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return {
    prove=function()return false end,clock=function()return 0 end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{}end
os.clock=function()return 0 end
-- Unrelated hit installation is already stopped; this fixture has no writable
-- process API and never supplies native game addresses for invocation.
HD2WarCostLedgerHitInstallationV2={stopped=true}
local C=dofile(assert(arg[6], 'native counter reader source'))
local counter=0x302000000
local function add(at,raw)m.records[#m.records+1]={at,raw}end
add(f.fixture.game+C.source.counters,f.ptr(counter))
add(counter+C.source.kills,b.encode(351885,'u32'))
add(counter+C.source.deaths,b.encode(4633,'u32'))
for _,pin in ipairs(C.pins)do add(f.fixture.game+pin.rva,b.unhex(pin.hex))end
for index,name in ipairs(C.names)do
    local at=0x303000000+index*128
    add(f.fixture.game+C.source.names+name.slot*8,f.ptr(at))
    add(at,name.text..'\0'..string.rep('x',63-#name.text))
end
m:alpha(0)
local addon=dofile(addon_path)
local state=addon.state
local function ticks(n)for _=1,n do frame(.1)end end
local function career_writes()
    local n=0;for _,key in ipairs(writes)do if key=='career_kd' then n=n+1 end end;return n
end
ticks(49)
assert(career_writes()==0,'five-second initialization wait')
ticks(22)
local first=addon.career_ship_sync_status()
assert(first.status=='synced' and first.reads==2,tostring(first.status))
assert(career_writes()==1 and saved.career_kd.source=='personal_career_native_counters')
assert(saved.career_kd.kills==351885 and saved.career_kd.deaths==4633)
assert(state.history_kills==351885 and state.history_deaths==4633)
assert(saved.career_kd.anchor_mod_kills==449 and saved.combat_history.medals.fragrant)
local n=#m.reads;ticks(400)
assert(#m.reads==n and career_writes()==1,'same Ship stops automatic/native counter reads and reanchors')
assert(first.reader.reads_peak<=32 and first.reader.bytes_peak<=512)
mission=true;ticks(1)
stats.totals[K],stats.totals[D]=10,1
n=#m.reads;ticks(30)
assert(#m.reads==n and state.history_kills==351895 and state.history_deaths==4634,'battle uses anchor+deltas with zero Career reads')
mission=false;ticks(72)
assert(addon.career_ship_sync_status().status=='waiting_settlement')
assert(career_writes()==1 and state.history_kills==351895,'stale native total cannot erase mission result')
m:patch(counter+C.source.kills,b.encode(351895,'u32'))
m:patch(counter+C.source.deaths,b.encode(4634,'u32'))
ticks(22)
assert(addon.career_ship_sync_status().status=='synced' and career_writes()==2)
assert(saved.career_kd.anchor_mod_kills==459 and saved.career_kd.anchor_mod_deaths==3)
assert(state.history_kills==351895 and state.history_deaths==4634,'true reanchor avoids double counting')
n=#m.reads;ticks(300);assert(#m.reads==n and career_writes()==2)
addon.ui_settings:set('career_ship_sync',false);n=#m.reads;ticks(15)
assert(#m.reads==n and addon.career_ship_sync_status().status=='disabled')
assert(m.writes==0)
print('PASS built Ship Career path: hidden cold fixture, actual counter reader,5s/two samples,reanchor,stop after sync,zero battle IO,delayed native settlement,settings off; native install/process boundaries mocked.')
