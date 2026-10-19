-- Actual built entry; only host/world boundaries are simulated. No game access.
local addon_path,runtime,fixture_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
local fixture=dofile(fixture_path)
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua')) end
end)
local win=require('hd2runtime/runtime/windows_ffi') -- bind real SDK before substitution
local ffi,real_kernel=win.ffi,win.kernel
win.kernel=setmetatable({GetModuleHandleA=function(name)
    if name=='game.dll' then return ffi.cast('void *',fixture.image.base) end
    return real_kernel.GetModuleHandleA(name)
end},{__index=function(_,name)return real_kernel[name]end})
local bytes=require('hd2runtime/core/bytes')
local keys=require('hd2runtime/domains/event_natives').stats.keys
local S,K,H,D=keys.projectiles_fired,keys.dealt_kills,keys.projectiles_hit,keys.received_deaths
local function clone(v)
    if type(v)~='table' then return v end
    local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out
end
local frame,bindings,logs=nil,{},{}
local saved={ui_settings={auto_ui_probe=false},probe_enabled=false,native_hit_auto_install=true}
local store={get=function(_,k,default)return clone(saved[k]==nil and default or saved[k])end,
    set=function(_,k,v)saved[k]=clone(v)end,save=function()end}
local mod={store=function()return store end,log=function(_,s)logs[#logs+1]=s end,
    bind=function(_,name,definition)bindings[name]=definition end,
    on_frame=function(_,callback)assert(frame==nil,'unexpected extra frame');frame=callback end}
local overlay={shown=false,draw=function()end,
    show=function(self)self.shown=true end,hide=function(self)self.shown=false end}
package.preload['mods/skyeshade/hd2runtime']=function()
    return {mod=function()return mod end,ui={overlay=function()return overlay end}}
end
local mission,stats_available,now=false,false,0
local player={['local']=true,entity=42,peer='FEDCBA9876543210'}
local stats={totals={[S]=0,[K]=0,[H]=99,[D]=0},sources={['A6A735ACCB4A327F']={[S]=0,[K]=0,[H]=99}}}
local reads,refused,proofs,stat_reads=0,0,0,0
local view={slot=function()return{}end} -- pointer=nil keeps unrelated native UI paths unavailable
function view.read(at,size)
    for _,page in ipairs(fixture.readable_pages)do
        if at>=page and size>=0 and at+size<=page+4096 then
            reads=reads+1;return ffi.string(ffi.cast('const void *',at),size)
        end
    end
    refused=refused+1;return nil
end
function view.proves(at,pin)
    proofs=proofs+1
    local raw=view.read(at,#pin/2)
    return raw~=nil and raw==bytes.unhex(pin)
end
local world={game=fixture.image.base,exe=fixture.image.base,runtime={mode='live'},view=view}
package.preload['hd2runtime/runtime/event_world']=function()return {
    open=function()return world end,
    game_state=function()return {state=mission and 4 or 3,mission=mission,host=true}end,
    entity_state=function()return nil end,
    players=function()return {player}end,
    stat_breakdown=function(_,entity,wanted)
        assert(entity==player.entity);stat_reads=stat_reads+1
        local requested={};for _,key in ipairs(wanted)do requested[key]=true end
        assert(requested[S] and requested[K] and requested[H])
        return stats_available and stats or nil
    end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return {prove=function()return false end,clock=function()return 0 end,beacons=function()return{}end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{prove=function()return false end,id_of=function()return nil end}end
local addon=dofile(addon_path)
assert(addon.version==fixture.addon_version and type(frame)=='function')
local state=addon.state
local checks,events={},{}
local function tick(dt)dt=dt or .1;now=now+dt;frame(dt)end
local function check(name,fn)
    fn();checks[#checks+1]=name;print('PASS '..name)
end
local function observe(name)
    events[#events+1]={case=name,sequence=state.sequence,mission=state.mission,
        ribbons=clone(state.ribbons),native=clone(addon.native_hit_status()),visible=overlay.shown}
end
local function item_of(list,id)
    local found
    for _,item in ipairs(list)do if item.id==id then assert(not found,'duplicate HUD item '..id);found=item end end
    return found
end
local function model()return addon.game_hud:native_model(now,overlay.shown)end
check('built on_frame automatically installs seven owned Ship sites',function()
    for _=1,60 do
        tick()
        local installation=rawget(_G,'HD2WarCostLedgerHitInstallationV2')
        if installation and installation.package and installation.package.native_certified then break end
    end
    local installation=assert(rawget(_G,'HD2WarCostLedgerHitInstallationV2'))
    local package=assert(installation.package)
    local evidence=assert(package.lifetime.transaction)
    assert(package.native_certified and package.lifetime.patched and package.lifetime.function_count==19)
    assert(evidence.result==0 and evidence.patched==7 and evidence.rollback_failures==0
        and evidence.resume_failures==0 and evidence.enum_failures==0)
    assert(evidence.enumerated==evidence.thread_count+1)
    for _,site in ipairs(fixture.sites)do
        local raw=view.read(world.game+site.rva,site.replace_bytes)
        assert(raw~=bytes.unhex(site.pin_hex) and raw:byte(1)==0xE8)
        if site.replace_bytes==6 then assert(raw:byte(6)==0x90)end
    end
    observe('ship-installed')
end)
local package=assert(rawget(_G,'HD2WarCostLedgerHitInstallationV2').package)
local publish=ffi.cast(win.fn('uint32_t (*)(void *,void *)'),package.addresses.publish)
local record=ffi.new('uint8_t[96]')
local function u64(at,text)
    ffi.copy(record+at,bytes.unhex(text):reverse(),8)
end
local function event(kind,epoch)
    ffi.fill(record,96)
    local current=assert(addon.native_hit_status().current,'native mission not active')
    u64(8,epoch or current.epoch);u64(16,current.peer)
    ffi.cast('uint32_t *',record+44)[0]=99
    ffi.cast('uint32_t *',record+60)[0]=kind=='ricochet' and 2 or 1
    ffi.cast('float *',record+64)[0]=4;ffi.cast('float *',record+68)[0]=3
    ffi.cast('float *',record+72)[0]=1;ffi.cast('float *',record+76)[0]=25
    ffi.cast('uint32_t *',record+84)[0]=1;ffi.cast('uint32_t *',record+88)[0]=0x1FF
    ffi.cast('float *',record+92)[0]=kind=='blocked' and -1 or kind=='penetration' and .5 or 1
    return tonumber(publish(ffi.cast('void *',package.bridge),record))
end
check('Mission waits for stats baseline before configuring native identity',function()
    mission=true;tick()
    assert(state.mission and not state.stats_ready and state.stats_baseline==nil)
    assert(not addon.native_hit_status().ready and addon.native_hit_status().current==nil)
    stats_available=true;tick()
    local status=addon.native_hit_status()
    assert(state.stats_ready and state.stats_baseline and status.ready and status.current.status=='active')
    assert(status.current.epoch==string.format('%016X',state.sequence) and status.current.accepted==0)
    observe('mission-baseline-ready')
end)
check('native publisher FIFO drain decoder updates all four built ribbon counters',function()
    for _,kind in ipairs({'ricochet','blocked','blocked','penetration','full_penetration'})do assert(event(kind)==1)end
    tick()
    local r=state.ribbons
    assert(r.hit_ricochet==1 and r.hit_blocked==2 and r.hit_penetration==1 and r.hit_full_penetration==1)
    assert(r.hit_total==99,'classified records must not add to independent native HITS')
    local status=addon.native_hit_status()
    assert(status.ready and status.current.accepted==5 and status.current.records==5)
    local hud=model()
    for id,count in pairs({H02=1,H03=2,H04=1,H05=1})do assert(item_of(hud.awards.items,id).count==count)end
    assert(item_of(hud.awards.items,'H01')==nil)
    observe('native-four-classes')
end)
check('same class accumulates into one side HUD item',function()
    assert(event('blocked')==1 and event('blocked')==1);tick()
    assert(state.ribbons.hit_blocked==4 and addon.native_hit_status().current.accepted==7)
    assert(item_of(model().awards.items,'H03').count==4)
    observe('same-class-batch')
end)
check('F8 hides presentation while actual native counting continues',function()
    bindings['war_cost_ledger.toggle_hud'].on_press();assert(not overlay.shown)
    assert(event('ricochet')==1);tick()
    assert(state.ribbons.hit_ricochet==2 and addon.native_hit_status().ready)
    assert(addon.native_hit_status().current.accepted==8)
    local hud=model();assert(not hud.awards.shown and #hud.awards.items==0 and #hud.awards.ribbons==0)
    observe('F8-hidden-still-counts')
    bindings['war_cost_ledger.toggle_hud'].on_press();assert(overlay.shown)
end)
check('two seconds idle folds side batches into collected ribbon totals',function()
    model();tick(2.1)
    assert(bindings['war_cost_ledger.toggle_collection']==nil, 'retired F9 shortcut must not be registered')
    addon.game_hud:configure({ribbon_mode='always'})
    local hud=model();assert(#hud.awards.items==0 and hud.collected)
    for id,count in pairs({H01=99,H02=2,H03=4,H04=1,H05=1})do
        assert(item_of(hud.awards.ribbons,id).count==count)
    end
    observe('idle-folded')
end)
local old_sequence,old_epoch=state.sequence,addon.native_hit_status().current.epoch
check('returning Ship pauses producers and drains final old mission batch',function()
    assert(event('blocked')==1);mission=false;tick()
    local status=addon.native_hit_status()
    assert(not state.mission and not status.ready and status.current==nil)
    assert(status.previous.sequence==old_sequence and status.previous.accepted==9)
    assert(state.ribbons.hit_blocked==5 and saved.last_mission.ribbons.hit_blocked==5)
    assert(not overlay.shown and package.native_certified)
    observe('returned-ship-final-drain')
end)
check('next mission resets counters and rejects stale old epoch events',function()
    stats={totals={[S]=0,[K]=0,[H]=0,[D]=0},sources={}}
    mission=true;tick()
    assert(state.sequence==old_sequence+1 and addon.native_hit_status().ready)
    for _,key in ipairs({'hit_total','hit_ricochet','hit_blocked','hit_penetration','hit_full_penetration'})do
        assert(state.ribbons[key]==0,'previous mission leaked into '..key)
    end
    assert(addon.native_hit_status().current.accepted==0)
    assert(event('blocked',old_epoch)==2);tick()
    assert(state.ribbons.hit_blocked==0 and addon.native_hit_status().current.accepted==0)
    assert(event('full_penetration')==1);tick()
    assert(state.ribbons.hit_full_penetration==1 and state.ribbons.hit_blocked==0)
    assert(addon.native_hit_status().current.accepted==1 and addon.native_hit_status().previous.accepted==9)
    observe('new-mission-isolated')
    mission=false;tick() -- stop owned producers before destroying this Lua state
end)
check('existing certified owned package remains consumable with auto install off',function()
    local attempts=rawget(_G,'HD2WarCostLedgerHitInstallationV2').attempts
    saved.native_hit_auto_install=false
    rawset(_G,'HD2WarCostLedgerV1',nil);frame=nil
    addon=dofile(addon_path);state=addon.state
    tick()
    assert(addon.native_hit_status().status~='deferred_protection_denied')
    assert(rawget(_G,'HD2WarCostLedgerHitInstallationV2').attempts==attempts)
    stats={totals={[S]=0,[K]=0,[H]=0,[D]=0},sources={}}
    mission=true;tick()
    assert(addon.native_hit_status().ready)
    assert(event('blocked')==1);tick()
    assert(state.ribbons.hit_blocked==1 and addon.native_hit_status().current.accepted==1)
    assert(rawget(_G,'HD2WarCostLedgerHitInstallationV2').attempts==attempts)
    observe('certified-reload-auto-off')
    mission=false;tick()
end)
-- Serialization is test evidence only; production modules above were unmodified.
local function json(value)
    if type(value)=='string' then return string.format('%q',value):gsub('\\\n','\\n') end
    if type(value)=='boolean' or type(value)=='number' then return tostring(value)end
    assert(type(value)=='table')
    local entries={}
    if #value>0 then
        for _,v in ipairs(value)do entries[#entries+1]=json(v)end
        return '['..table.concat(entries,',')..']'
    end
    for k,v in pairs(value)do entries[#entries+1]=json(k)..':'..json(v)end
    table.sort(entries);return '{'..table.concat(entries,',')..'}'
end
local evidence={passed=true,checks=#checks,check_names=checks,events=events,
    installed_sites=7,native_entries=19,transaction=clone(package.lifetime.transaction),
    own_image_reads=reads,refused_unrelated_reads=refused,pin_proofs=proofs,stat_reads=stat_reads,
    native_ui_status=addon.native_ui and addon.native_ui.status,
    task_layout_status=addon.task_layout_code_status(),original_calls=0,game_access=false}
print('OWNED_EVIDENCE_JSON '..json(evidence))
win.kernel=real_kernel
