-- Actual built entry. Only its inline native probe is replaced by a stub;
-- fixture world/store/overlay boundaries are declared and never access Game.
local addon_path,runtime=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local JSON=require('hd2runtime/runtime/mod_store')
local f=assert(io.open(addon_path,'rb'));local built=f:read('*a'):gsub('\r\n','\n');f:close()
local version=assert(built:match("local VERSION = '([^']+)'"),'requires actual versioned built entry')
local source_sha=built:match('local PLUGIN_FRAME_PROBE_SOURCE_SHA = "([%x]+)"')
    or built:match("local PLUGIN_FRAME_PROBE_SOURCE_SHA = '([%x]+)'")
assert(source_sha and#source_sha==64)
local start=assert(built:find('-- Explicit, one-shot timing diagnostic.',1,true))
local finish=assert(built:find('\n            end)()\n            plugin_frame_probe=module.new()',start,true))
local patched=built:sub(1,start-1).."return assert(rawget(_G,'HD2OwnedPluginFrameProbeStub'))"..built:sub(finish)
local function clone(v)if type(v)~='table'then return v end;local o={};for k,x in pairs(v)do o[k]=clone(x)end;return o end
local c,frame
local stub={new=function()
    c.news=c.news+1
    local p={d={phase='idle',counter=0,payload_ready=false,engine_dispatch_proven=false},stops=0}
    function p:start(w,g)
        assert(w==c.world and g.mission==false and(g.state==2 or g.state==3))
        c.starts=c.starts+1;self.started=c.clock;self.d.phase='running';self.d.reason='WINDOW_RUNNING'
        return self:status()
    end
    function p:stop(reason)
        c.stop_reasons[#c.stop_reasons+1]=reason;self.stops=self.stops+1
        self.d.phase='stopped';self.d.reason=reason;self.d.counter=3
        local pending=c.mode=='cleanup'and self.stops<3
        self.d.cleanup_required=pending;self.d.restored=not pending
        return self:status()
    end
    function p:tick(w,g)
        assert(w==c.world and g.state==2);c.ticks=c.ticks+1
        if c.clock-self.started>=2-1e-9 then return self:stop('WINDOW_ENDED')end
        return self:status()
    end
    function p:status()return clone(self.d)end
    c.probe=p;return p
end}
rawset(_G,'HD2OwnedPluginFrameProbeStub',stub)
local mod={store=function()return c.main_store end,log=function(_,s)c.logs[#c.logs+1]=s end,
    bind=function()end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return{mod=function()return mod end,
    ui={overlay=function()return{draw=function()end,show=function()end,hide=function()end}end}}end
package.preload['hd2runtime/runtime/event_world']=function()return{
    open=function()return c.available and c.world end,
    game_state=function()return{state=2,mission=false,host=true}end,players=function()return{}end,
    entity_state=function()return nil end,stat_breakdown=function()return{totals={},sources={}}end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return{prove=function()return false end,clock=function()return 0 end,beacons=function()return{}end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{prove=function()return false end,id_of=function()return nil end}end
JSON.open=function(owner)
    assert(owner=='mods/hd2_costs/war_cost_ledger/plugin_frame_probe','unexpected independent diagnostic owner')
    c.opens=c.opens+1
    return{get=function(_,k,v)assert(k=='last');return clone(c.last or v)end,
        set=function(_,k,v)assert(k=='last');c.independent_sets=c.independent_sets+1;c.last=clone(v)end,
        save=function()c.independent_saves=c.independent_saves+1;JSON.decode(JSON.encode(c.last));return true end}
end
os.clock=function()return c and c.clock or 0 end
local function load_case(mode,last)
    c={mode=mode,clock=0,available=true,news=0,starts=0,ticks=0,stop_reasons={},logs={},opens=0,
        independent_sets=0,independent_saves=0,last=clone(last),main_writes={},saved={
            ui_settings={auto_ui_probe=false,career_page_sync=false},probe_enabled=false,
            native_hit_auto_install=false,last_mission={sequence=91,mission=false,sentinel='keep-account'}}}
    c.last_mission_json=JSON.encode(c.saved.last_mission)
    c.main_store={get=function(_,k,v)return clone(c.saved[k]==nil and v or c.saved[k])end,
        set=function(_,k,v)c.main_writes[#c.main_writes+1]=k;c.saved[k]=clone(v)end,save=function()return true end}
    c.world={game=0x10000000,exe=0x140000000,runtime={mode='live',
        read=function()return nil end,query=function()return nil end,module=function()return nil end,
        address=function(v)return v end},view={slot=function()return{}end,pointer=function()return nil end,u32=function()return nil end}}
    rawset(_G,'HD2WarCostLedgerV1',nil)
    c.addon=assert(loadstring(patched,'@actual-built-addon-probe-fixture'))()
    assert(c.addon.version==version)
    return c
end
local function ticks(n)for _=1,n do c.clock=c.clock+.1;frame(.1)end end
local function isolated()
    local s=JSON.encode(c.addon.state)
    assert(not s:find(source_sha,1,true)and not s:find('"plugin_frame_probe"',1,true))
    assert(JSON.encode(c.saved.last_mission)==c.last_mission_json)
    for _,k in ipairs(c.main_writes)do assert(k~='plugin_frame_probe'and k~='plugin_frame_result'and k~='last')end
end
local passed={};local function test(name,fn)fn();passed[#passed+1]=name end
test('running then deadline saves only the independent summary',function()
    load_case('expiry');ticks(1)
    assert(c.starts==1 and c.addon.plugin_frame_probe_status().phase=='running'and c.independent_saves==0)
    ticks(20)
    assert(c.last and c.last.phase=='stopped'and c.last.reason=='WINDOW_ENDED'and c.last.restored)
    assert(c.last.source_sha==source_sha and c.independent_sets==1 and c.independent_saves==1)
    isolated();local n=c.ticks;ticks(4);assert(c.ticks==n and c.independent_saves==1)
end)
test('world loss stops the active probe and preserves main state',function()
    load_case('loss');ticks(1);c.available=false;ticks(1)
    assert(c.stop_reasons[1]=='WORLD_UNAVAILABLE'and c.last and c.last.restored)
    assert(c.independent_saves==1);isolated()
end)
test('pending cleanup retries explicitly and is not cached before success',function()
    load_case('cleanup');ticks(21)
    local pending=c.addon.plugin_frame_probe_status()
    assert(pending.cleanup_required and pending.source_sha==nil and c.last==nil and c.independent_saves==0)
    ticks(1);assert(c.stop_reasons[2]=='CLEANUP_RETRY'and c.last==nil and c.independent_saves==0)
    ticks(1);assert(c.stop_reasons[3]=='CLEANUP_RETRY'and c.last.restored and not c.last.cleanup_required)
    assert(c.last.source_sha==source_sha and c.independent_saves==1);isolated()
end)
test('same-source completed cache skips creation and startup',function()
    local saved=clone(c.last)
    load_case('cached',saved);ticks(4)
    assert(c.opens==1 and c.news==0 and c.starts==0 and c.independent_sets==0 and c.independent_saves==0)
    assert(c.addon.plugin_frame_probe_status().source_sha==source_sha);isolated()
end)
print('PASS actual built'..version..' plugin frame integration: '..#passed..' focused cases; independent summary, cleanup cache gate and same-source skip; no Game/native prototype access.')
return JSON.encode({status='PASS',count=#passed,cases=passed,version=version,source_sha=source_sha,
    actual_built_entry=true,inline_probe_stub=true,game_accessed=false,installed=false})
