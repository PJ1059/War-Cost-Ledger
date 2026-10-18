-- Actual built addon + default collector globals + current-process readonly adapter.
local addon_path,runtime,folder,expected=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local JSON=require('hd2runtime/runtime/mod_store')
JSON.set_folder(folder)
local rt=require('hd2runtime/runtime/windows_readonly')()
local original_module=rt.module
local lua_handle=assert(original_module('lua51.dll'))
local lua_base,host_base=rt.address(lua_handle),rt.address(assert(original_module(nil)))
-- Only module identity role mapping is simulated. Actual read/query/hash remain SDK code.
rt.module=function(name)return name=='game.dll'and lua_handle or original_module(name)end
local expected_addresses=JSON.decode(expected)
local target_names={{'World','set_flow_callback_object'},{'Unit','flow_event'},
    {'Application','flow_callback_context_world'},{'Application','flow_callback_context_unit'},
    {'Application','flow_callback_context_entity'},{'Application','flow_callback_context_level'}}
local calls,metamethod_calls,sentinel_hits=0,0,0
local targets,allowed_gc,allowed_code={},{},{}
local function denied()metamethod_calls=metamethod_calls+1;error('owned engine metamethod invoked')end
local meta={__index=denied,__newindex=denied,__tostring=denied,__pairs=denied,__call=denied}
local engine=setmetatable({},meta)
for _,name in ipairs({'World','Unit','Application'})do rawset(engine,name,setmetatable({},meta))end
for i,target in ipairs(target_names)do
    local fn=assert(rawget(_G,'owned_fn_'..i))
    rawset(rawget(engine,target[1]),target[2],fn);targets[fn]=true
    allowed_gc[tonumber(string.format('%p',fn):sub(3),16)]=true
    allowed_code[expected_addresses[i]]=true
end
rawset(_G,'stingray',engine)
local real_read,real_query,real_hash=rt.read,rt.query,rt.module_hash
local reads,bytes,queries,hashes=0,0,0,0
rt.read=function(at,n)
    assert((n==32 and allowed_gc[at])or(n==16 and allowed_code[at]),'read outside declared owned function ranges')
    reads=reads+1;bytes=bytes+n;return real_read(at,n)
end
rt.query=function(at)
    assert(allowed_gc[at]or allowed_code[at],'query outside declared owned function ranges')
    queries=queries+1;return real_query(at)
end
rt.module_hash=function(handle)assert(handle==lua_handle);hashes=hashes+1;return real_hash(handle)end
local function clone(v)
    if type(v)~='table'then return v end
    local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out
end
local baseline={version=1,kills=351849,deaths=4633,anchor_mod_kills=449,anchor_mod_deaths=2,
    source='personal_career_visible_page',local_peer='0102030405060708',synced_at='owned-preexisting',
    policy='visible_page_plus_observed_deltas'}
local saved={combat_history={kills=449,deaths=2,medals={fragrant=true}},career_kd=clone(baseline),
    ui_settings={auto_ui_probe=false,career_page_sync=false},probe_enabled=false,
    engine_api_inventory_v1={summary_version=1,
        source_sha='9b2ab93446eb730a433a8273064a196213698acdfe5fb16eed152b86663415ea',
        exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
        dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
        dump_saved=true,complete=false,reason='owned-preexisting'}}
local baseline_json=JSON.encode(baseline)
local frame,logs,writes,saves=nil,{}, {},0
local summary_writes,career_writes=0,0
local store={get=function(_,k,default)local value=saved[k];if value==nil then value=default end;return clone(value)end,
    set=function(_,k,value)
        writes[#writes+1]=k;saved[k]=clone(value)
        if k=='engine_cfunction_inventory_v1'then summary_writes=summary_writes+1 end
        if k=='career_kd'then career_writes=career_writes+1 end
    end,save=function()saves=saves+1;return true end}
local mod={store=function()return store end,log=function(_,message)logs[#logs+1]=message end,
    bind=function()end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return {mod=function()return mod end,
    ui={overlay=function()return {draw=function()end,show=function()end,hide=function()end}end}}end
local specs,values,changes={},{},{}
rawset(_G,'ModOptionsMenu',{api=1,version=3,
    register_option=function(id,spec)specs[id]=spec;values[id]=spec.default;return true end,
    get=function(id)return values[id]end,set=function(id,v)values[id]=v end,
    on_change=function(id,fn)changes[id]=fn end})
local available,mission=true,false
local world={exe=host_base,game=lua_base,runtime=rt,view={slot=function()return{}end}}
local native_keys=require('hd2runtime/domains/event_natives').stats.keys
local stat={totals={[native_keys.projectiles_fired]=0,[native_keys.projectiles_hit]=0,
    [native_keys.dealt_kills]=0,[native_keys.received_deaths]=0},sources={}}
package.preload['hd2runtime/runtime/event_world']=function()return {
    open=function()return available and world end,
    game_state=function()return {state=mission and 4 or 3,mission=mission,host=true}end,
    players=function()return {}end,stat_breakdown=function()return stat end,
    health_header=function()return nil end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return {prove=function()return false end,clock=function()return 0 end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{}end
local opens,original_open=0,JSON.open
JSON.open=function(owner)
    assert(owner=='mods/hd2_costs/war_cost_ledger/engine_bindings','unexpected store owner')
    opens=opens+1;return original_open(owner)
end
-- Count calls to the six exact target closure objects. An unrelated owned C
-- sentinel validates this hook without ever invoking a target.
local sentinel=assert(owned_sentinel)
debug.sethook(function(event)
    if event=='call'then
        local info=debug.getinfo(2,'f')
        if info and targets[info.func]then calls=calls+1 end
        if info and info.func==sentinel then sentinel_hits=sentinel_hits+1 end
    end
end,'c')
sentinel();assert(sentinel_hits==1,'C-call detector not supported')
local events=require('hd2runtime/runtime/events')
local passed={}
local function test(name,fn)fn();passed[#passed+1]=name end
local function load()
    rawset(_G,'HD2WarCostLedgerV1',nil)
    return dofile(addon_path)
end
local addon=load();assert(addon.version=='0.4.21')
local function ticks(n)for _=1,n do frame(.1);events.tick(.1)end end
test('Ship8s delay then mission resets without native sampler IO',function()
    ticks(79);assert(summary_writes==0 and reads==0 and hashes==0)
    mission=true;ticks(100);assert(summary_writes==0 and reads==0 and hashes==0)
end)
test('missing world resets the Ship deadline',function()
    mission=false;ticks(40);assert(summary_writes==0)
    available=false;ticks(20);assert(summary_writes==0 and reads==0)
    available=true;ticks(79);assert(summary_writes==0 and hashes==0)
end)
test('actual built default collector saves independent full dump and compact summary',function()
    ticks(4)
    local summary=assert(saved.engine_cfunction_inventory_v1)
    assert(summary_writes==1 and summary.resolved==6 and summary.found==6 and summary.complete,
        'six candidates expected; got '..tostring(summary.reason)..'/'..tostring(summary.resolved))
    assert(summary.ProfileVerified and summary.dump_saved and not summary.contract_ready)
    assert(summary.functions==nil and summary.profile==nil and summary.hash==summary.lua_sha)
    assert(opens==1 and hashes==1 and reads==12 and bytes==288)
    local dump=original_open('mods/hd2_costs/war_cost_ledger/engine_bindings')
    assert(dump:describe().saved==1)
    local file=assert(io.open(folder..'/'..summary.dump_file,'rb'))
    local full=JSON.decode(file:read('*a')).inventory;file:close()
    assert(full.source_sha=='881948948430f7b7a4ad03127e066feb108b6ce4c4d0923d4e3e59b8c9611833')
    assert(#full.functions==6 and full.resolved==6 and full.ProfileVerified)
    for i,row in ipairs(full.functions)do
        assert(row.name==target_names[i][1]..'.'..target_names[i][2])
        assert(row.module=='game'and row.rva==expected_addresses[i]-lua_base and#row.hex==32)
    end
    local encoded=JSON.encode(summary)
    assert(not encoded:find('"functions"',1,true)and not encoded:find('"hex"',1,true))
    local state=JSON.decode(JSON.encode(addon.state))
    assert(state.engine_cfunction_inventory.resolved==6 and state.engine_cfunction_inventory.functions==nil)
end)
test('1000 frames and actual deferred timers never rewrite or rehash',function()
    local dump=original_open('mods/hd2_costs/war_cost_ledger/engine_bindings')
    ticks(1000)
    assert(summary_writes==1 and opens==1 and hashes==1 and reads==12 and dump:describe().saved==1)
    assert(not dump:describe().dirty)
end)
test('cross startup summary cache is historical and performs no sampling IO',function()
    addon=load();ticks(100)
    local status=addon.engine_bindings_status()
    assert(status.status=='historical'and not status.identity_ready and status.resolved==6)
    assert(summary_writes==1 and opens==1 and hashes==1 and reads==12)
end)
test('native install remains off and existing career baseline survives all boundaries',function()
    assert(not rawget(_G,'HD2WarCostLedgerHitInstallationV2'))
    assert(addon.native_hit_status().status=='deferred_protection_denied')
    assert(addon.state.hit_classification_ready==false and career_writes==0)
    assert(JSON.encode(saved.career_kd)==baseline_json and saved.combat_history.medals.fragrant)
    assert(addon.state.history_kills==351849 and addon.state.history_deaths==4633)
    assert(addon.ui_settings.status=='registered'and type(specs['hd2_costs.war_cost_ledger.career_page_sync'].description)=='function')
    assert(calls==0 and metamethod_calls==0)
end)
debug.sethook()
return JSON.encode({status='PASS',cases=passed,count=#passed,version=addon.version,
    schema='engine_cfunction_inventory_v1',owner='mods/hd2_costs/war_cost_ledger/engine_bindings',
    source_sha=saved.engine_cfunction_inventory_v1.source_sha,summary=saved.engine_cfunction_inventory_v1,
    counts={target_callbacks_executed=calls,metamethod_calls=metamethod_calls,sentinel_hook_hits=sentinel_hits,
        readonly_reads=reads,readonly_bytes=bytes,readonly_queries=queries,module_hashes=hashes,
        independent_store_opens=opens,summary_writes=summary_writes,career_baseline_writes=career_writes,
        primary_store_saves=saves},
    fixture='Own LuaState closures and actual readonly current PID; game.dll aliases own loaded lua51.dll; world/state/store/MOM/overlay are declared fixtures',
    game_process_reads=0,engine_calls=0,native_install=false})
