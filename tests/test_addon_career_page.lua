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
    ui_settings={auto_ui_probe=false,career_ship_sync=false},probe_enabled=false}
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
local addon=dofile(addon_path)
local state=addon.state
local function ticks(n)for _=1,n do frame(.1)end end
local function career_writes()
    local n=0;for _,key in ipairs(writes)do if key=='career_kd' then n=n+1 end end;return n
end
m:alpha(0)
ticks(12)
assert(career_writes()==0 and state.history_kills==351849 and state.history_deaths==4633)
m:alpha(1)
ticks(11)
assert(career_writes()==0 and addon.career_sync_status().status=='reading_page')
ticks(11)
assert(career_writes()==1 and saved.career_kd.source=='personal_career_visible_page')
assert(saved.career_kd.kills==351849 and saved.career_kd.deaths==4633)
assert(saved.career_kd.anchor_mod_kills==449 and saved.career_kd.anchor_mod_deaths==2)
assert(saved.combat_history.medals.fragrant and state.history_kills==351849)
local function sync_logs()
    local n=0;for _,message in ipairs(logs)do if message:find('生涯同步成功',1,true) then n=n+1 end end
    return n
end
local log_count=sync_logs();ticks(30)
assert(career_writes()==1 and sync_logs()==log_count,'same open page must not save/log repeatedly')
assert(state.career_sync.reader.reads_peak<=64 and state.career_sync.reader.bytes_peak<=8192)
m:alpha(0)
local before_sync=addon.career_sync_status().reads;ticks(11)
assert(addon.career_sync_status().reads==before_sync+1
    and state.career_sync.reader.reads==9 and state.history_kills==351849,
    'hidden-page KD sync performs exactly one bounded nine-read visibility check')
assert(addon.career_sync_status().status=='waiting_page')
-- Battle makes no Career read at all; MOD history grows from a new baseline.
mission=true;ticks(1)
stats.totals[K],stats.totals[D]=10,1
before_sync=addon.career_sync_status().reads;ticks(30)
assert(addon.career_sync_status().reads==before_sync
    and state.history_kills==351859 and state.history_deaths==4634)
mission=false;ticks(1)
-- The real displayed post-mission total becomes the new anchor, once.
m:patch(f.fixture.list+0x110+f.M.source.value+272+16,b.encode(351859,'u32'))
m:patch(f.fixture.list+0x110+8*0x1910+f.M.source.value+272+16,b.encode(4634,'u32'))
m:alpha(1);ticks(22)
assert(career_writes()==2 and saved.career_kd.anchor_mod_kills==459
    and saved.career_kd.anchor_mod_deaths==3)
assert(state.history_kills==351859 and state.history_deaths==4634,'no double-count on reanchor')
addon.ui_settings:set('career_page_sync',false)
before_sync=addon.career_sync_status().reads;ticks(20)
assert(addon.career_sync_status().reads==before_sync and addon.career_sync_status().status=='disabled',
    'disabling KD sync leaves the independent Career archive observer available')
assert(state.history_kills==351859 and career_writes()==2)
addon.ui_settings:set('career_page_sync',true)
m:alpha(0);ticks(11)
available=false;local before=#m.reads;ticks(15)
assert(#m.reads==before and state.history_kills==351859)
assert(m.writes==0)
print('PASS built visible-Career path: hidden/Ship/mission gates, stable true351849/4633, exact reanchor, no duplicate IO saves, close/disable/gap retention, preserved medals; no game access.')
