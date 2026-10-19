-- Actual built addon: one Ship export-name inventory, no calls or native install.
local addon_path,runtime,folder=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local mod_store=require('hd2runtime/runtime/mod_store')
mod_store.set_folder(folder)
local opens,original_open=0,mod_store.open
mod_store.open=function(owner)opens=opens+1;return original_open(owner)end
local calls,frame,logs,saved=0,nil,{}, {ui_settings={auto_ui_probe=false},probe_enabled=false}
local function fail()calls=calls+1;error('engine member or metamethod called')end
local hostile={__index=fail,__tostring=fail,__pairs=fail,__call=fail}
local engine=setmetatable({},hostile)
for _,name in ipairs({'PhysicsWorld','Actor','World','Unit','ScriptWorld','Application'})do
    rawset(engine,name,setmetatable({z=fail,a=true},hostile))
end
_G.stingray=engine
local function clone(v)
    if type(v)~='table'then return v end
    local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out
end
local inventory_writes=0
local store={get=function(_,k,v)return clone(saved[k]==nil and v or saved[k])end,
    set=function(_,k,v)
        if k=='engine_api_inventory_v1'then inventory_writes=inventory_writes+1 end
        saved[k]=clone(v)
    end,save=function()end}
local mod={store=function()return store end,log=function(_,s)logs[#logs+1]=s end,
    bind=function()end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return {mod=function()return mod end,
    ui={overlay=function()return {draw=function()end,show=function()end,hide=function()end}end}}end
local mission,state,available=false,3,true
local world={game=0x10000000,view={slot=function()return{}end},runtime={mode='live'}}
package.preload['hd2runtime/runtime/event_world']=function()return {
    open=function()return available and world end,
    game_state=function()return {mission=mission,state=state,host=true}end,
    players=function()return {}end,entity_state=function()return nil end,
    stat_breakdown=function()return {totals={},sources={}}end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return {prove=function()return false end,clock=function()return 0 end,beacons=function()return {} end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{prove=function()return false end,id_of=function()return nil end}end
os.clock=function()return 0 end
local function load()
    rawset(_G,'HD2WarCostLedgerV1',nil)
    return dofile(addon_path)
end
local module=load()
local function ticks(n)for _=1,n do frame(.1)end end
ticks(59)
assert(inventory_writes==0 and not rawget(_G,'HD2WarCostLedgerHitInstallationV2'))
local hit=module.native_hit_status()
assert(hit.status=='CODE_COPY_WORLD_UNAVAILABLE' and not hit.ready)
assert(hit.copy.phase=='failed' and not hit.copy.installed
    and hit.copy.allocation_calls==0 and hit.copy.reads==0,
    'missing native boundaries must stop the observation copy before reads or allocation')
mission,state=true,4;ticks(80)
assert(inventory_writes==0 and calls==0)
mission,state=false,3;ticks(62)
local inventory=assert(saved.engine_api_inventory_v1)
local expected_sha=inventory.source_sha
assert(inventory_writes==1 and inventory.complete and inventory.total_entries==18)
assert(inventory.total_scanned==18 and inventory.modules==nil and calls==0)
assert(opens==1 and inventory.summary_version==1 and inventory.dump_saved)
local dump=original_open('mods/hd2_costs/war_cost_ledger/engine_exports')
assert(dump:describe().saved==1 and inventory.dump_file==dump:describe().file)
local file=assert(io.open(folder..'/'..inventory.dump_file,'rb'))
local full_json=file:read('*a');file:close()
local full=mod_store.decode(full_json).inventory
assert(#full.modules==7 and full.total_entries==18 and full.source_sha==expected_sha)
local summary_json=mod_store.encode(inventory)
assert(not summary_json:find('"modules"',1,true) and not summary_json:find('"entries"',1,true))
assert(mod_store.decode(summary_json).dump_saved)
assert(mod_store.decode(mod_store.encode(module.state)).engine_api_inventory.dump_saved)
assert(not rawget(_G,'HD2WarCostLedgerHitInstallationV2') and module.state.hit_classification_ready==false)
ticks(1000)
assert(inventory_writes==1 and calls==0 and opens==1 and dump:describe().saved==1)
module=load();ticks(100)
assert(inventory_writes==1 and module.engine_inventory_status().source_sha==inventory.source_sha and opens==1)
-- A different build/source marker does not suppress this diagnostic.
saved.engine_api_inventory_v1.source_sha='older-reader'
module=load();ticks(62)
assert(inventory_writes==2 and saved.engine_api_inventory_v1.source_sha==expected_sha)
assert(opens==2 and dump:describe().saved==2)
_G.stingray=nil
saved.engine_api_inventory_v1=nil
module=load();ticks(62)
assert(inventory_writes==3 and opens==2 and not saved.engine_api_inventory_v1.dump_saved)
assert(saved.engine_api_inventory_v1.reason=='UNSUPPORTED_ROOT' and saved.engine_api_inventory_v1.modules==nil)
-- A bad diagnostic clock remains an explicit partial result, not a frame error.
_G.stingray=engine
world.runtime.precise_time=function()error('clock unavailable')end
saved.engine_api_inventory_v1=nil
module=load();ticks(62)
assert(inventory_writes==4 and opens==3 and saved.engine_api_inventory_v1.reason=='CLOCK_INVALID')
assert(saved.engine_api_inventory_v1.dump_elapsed_ms==nil and calls==0)
assert(mod_store.decode(mod_store.encode(module.state)).engine_api_inventory.reason=='CLOCK_INVALID')
_G.stingray=nil
print('PASS built engine-export diagnostic: stable Ship only, separate full JSON saved once, compact account/state summary, nil root opens no dump; no members/metamethods or old native install; task/reset/cache/source-version gates.')
