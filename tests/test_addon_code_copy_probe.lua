-- Actual built entry: only the new native copy controller is stubbed.
local addon_path,runtime=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua')) end
end)
local JSON=require('hd2runtime/runtime/mod_store')
local f=assert(io.open(addon_path,'rb'));local built=f:read('*a'):gsub('\r\n','\n');f:close()
assert(built:find("local VERSION = '0.4.23'",1,true))
local copy_sha=assert(built:match('local CODE_COPY_PROBE_SOURCE_SHA = "([%x]+)"'))
local old_sha=assert(built:match('local PLUGIN_FRAME_PROBE_SOURCE_SHA = "([%x]+)"'))
local first=assert(built:find('-- Explicit one-shot, two-second code-copy smoke preparation.',1,true))
local last=assert(built:find('\n        end)()\n    end,\n    persist=function',first,true))
local patched=built:sub(1,first-1).."return assert(rawget(_G,'HD2OwnedCodeCopyStub'))"..built:sub(last)
local function clone(v)if type(v)~='table'then return v end;local x={};for k,a in pairs(v)do x[k]=clone(a)end;return x end
local c,frame
rawset(_G,'HD2OwnedCodeCopyStub',{new=function()
    c.news=c.news+1
    local p={d={phase='idle',counter=0}}
    function p:start(_,game)
        assert(game.state==3 and game.mission==false);c.starts=c.starts+1
        self.started=c.clock;self.d.phase='running';self.d.reason='WINDOW_RUNNING';return self:status()
    end
    function p:stop(reason)
        c.stops=c.stops+1
        self.d={phase='stopped',reason=reason,counter=9,
            cleanup_required=c.mode=='cleanup'and c.stops<2,restored=not(c.mode=='cleanup'and c.stops<2)}
        return self:status()
    end
    function p:tick()
        c.ticks=c.ticks+1
        if c.clock-self.started>=2-1e-9 then return self:stop('WINDOW_ENDED')end
        return self:status()
    end
    function p:status()return clone(self.d)end
    return p
end})
local mod={store=function()return c.store end,log=function(_,s)c.logs[#c.logs+1]=s end,
    bind=function()end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return{mod=function()return mod end,
    ui={overlay=function()return{draw=function()end,show=function()end,hide=function()end}end}}end
package.preload['hd2runtime/runtime/event_world']=function()return{
    open=function()return c.available and c.world end,
    game_state=function()return{state=c.state,mission=c.state==4,host=true}end,players=function()return{}end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return{prove=function()return false end,clock=function()return 0 end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{}end
JSON.open=function(owner)
    if owner:sub(-19)=='/plugin_frame_probe'then return{get=function()return{source_sha=old_sha,phase='stopped'}end}end
    assert(owner=='mods/hd2_costs/war_cost_ledger/code_copy_probe')
    return{set=function(_,k,v)assert(k=='last');c.last=clone(v)end,
        save=function()c.saves=c.saves+1;JSON.decode(JSON.encode(c.last));return true end}
end
os.clock=function()return c and c.clock or 0 end
local function fresh(mode)
    c={mode=mode,clock=0,available=true,state=3,news=0,starts=0,ticks=0,stops=0,saves=0,logs={},writes={},
        saved={ui_settings={auto_ui_probe=false,career_page_sync=false,code_copy_test=2},probe_enabled=false,
            last_mission={sentinel='preserve',sequence=12},combat_history={kills=449,deaths=2,medals={}}}}
    c.old_mission=JSON.encode(c.saved.last_mission)
    c.store={get=function(_,k,v)return clone(c.saved[k]==nil and v or c.saved[k])end,
        set=function(_,k,v)c.writes[#c.writes+1]=k;c.saved[k]=clone(v)end,save=function()return true end}
    c.world={game=0x10000000,exe=0x140000000,runtime={mode='live',read=function()return nil end,
        query=function()return nil end,module=function()return nil end,address=function(v)return v end},
        view={slot=function()return{}end,pointer=function()return nil end,u32=function()return nil end}}
    rawset(_G,'HD2WarCostLedgerV1',nil);rawset(_G,'ModOptionsMenu',nil)
    c.addon=assert(loadstring(patched,'@actual-code-copy-addon-fixture'))()
end
local function advance(n)for _=1,n do c.clock=c.clock+.1;frame(.1)end end
local function isolated()
    assert(JSON.encode(c.saved.last_mission)==c.old_mission)
    assert(c.saved.combat_history.kills==449 and c.saved.combat_history.deaths==2)
    for _,k in ipairs(c.writes)do assert(k~='code_copy_probe'and k~='last')end
end
fresh('deadline');advance(8)
assert(c.starts==0 and c.news==0 and c.saves==0,'saved menu action started automatically')
assert(c.addon.ui_settings:set('code_copy_test',2));advance(49)
assert(c.starts==0);advance(2);assert(c.starts==1 and c.saves==0)
advance(22);assert(c.last and c.last.restored and c.last.source_sha==copy_sha and c.saves==1)
isolated();assert(c.addon.ui_settings:set('code_copy_test',2));advance(70)
assert(c.starts==1 and c.saves==1)
fresh('loss');c.addon.ui_settings:set('code_copy_test',2);advance(51)
c.available=false;advance(2);assert(c.last.restored and c.last.reason=='WORLD_UNAVAILABLE');isolated()
fresh('cleanup');c.addon.ui_settings:set('code_copy_test',2);advance(51)
c.addon.cancel_code_copy_probe();assert(c.saves==0 and c.addon.code_copy_probe_status().cleanup_required)
advance(2);assert(c.saves==1 and c.last.restored and c.stops==2);isolated()
print('PASS actual built0.4.23 code-copy entry: explicit menu queue, no startup/repeat, deadline, world loss, cleanup retry, independent JSON summary and preserved combat data.')
