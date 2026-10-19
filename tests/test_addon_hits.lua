-- Built addon -> native-stat boundary -> real ledger/notification/HUD models.
local path,runtime=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua')) end
end)
local N=require('hd2runtime/domains/event_natives')
local S,K,H=N.stats.keys.projectiles_fired,N.stats.keys.dealt_kills,N.stats.keys.projectiles_hit
local frame,bindings,saved=nil,{},{}
local mission,reads=true,0
local native={totals={[S]=0,[K]=0,[H]=0},sources={}}
local store={get=function(_,k,v) return saved[k] or v end,set=function(_,k,v) saved[k]=v end,save=function() end}
local mod={store=function() return store end,log=function() end,
    bind=function(_,id,v) bindings[id]=v end,on_frame=function(_,fn) frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function() return {mod=function() return mod end,
    ui={overlay=function() return {draw=function() end,show=function() end,hide=function() end} end}} end
package.preload['hd2runtime/runtime/event_world']=function() return {
    open=function() return {game=1,view={slot=function() return {} end}} end,
    game_state=function() return {mission=mission} end,
    entity_state=function() return nil, 'fixture has no avatar Health record' end,
    players=function() return {{['local']=true,entity=42}} end,
    stat_breakdown=function(_,_,wanted)
        local found=false;for _,key in ipairs(wanted) do if key==H then found=true end end
        assert(found,'actual stat read must request HITS');reads=reads+1;return native
    end} end
package.preload['hd2runtime/runtime/beacon_redirect']=function() return {prove=function() return false end,clock=function() return 0 end,beacons=function() return {} end} end
package.preload['hd2runtime/runtime/stratagem_loadout']=function() return {prove=function() return false end,id_of=function() return nil end} end
local addon=dofile(path);local state=addon.state
local bullet,incendiary,stoker,spray='A6A735ACCB4A327F','C12A34F375BD5A87','8A307BD1811A5FE9','4FB0F8C02F55C82B'
local function set(total,values)
    native.totals[H],native.sources=total,{}
    for id,n in pairs(values) do native.sources[id]={[S]=0,[K]=0,[H]=n} end
    local before=reads;frame(.1)
    assert(reads==before+1,'HITS must share one native stat read for this observation tick')
end
set(8,{[bullet]=5,[incendiary]=1,[spray]=2})
assert(state.hits==6 and state.ribbons.hit_total==6 and state.hit_stats_ready)
set(13,{[bullet]=7,[incendiary]=2,[stoker]=1,[spray]=3})
assert(state.hits==10 and state.total_cents==0 and state.fire_kills==0)
local view=addon.game_hud.notifications:snapshot(1,true,true)
local found
for _,item in ipairs(view.ribbons) do if item.id=='H01' then found=item end end
assert(found and found.count==10,'native HUD model must collect one total-hit ribbon')
for _,item in ipairs(view.items) do assert(item.id~='H01','total ribbon must not pretend to be a classified instant icon') end
bindings['war_cost_ledger.toggle_hud'].on_press()
set(14,{[bullet]=8,[incendiary]=2,[stoker]=1,[spray]=3})
assert(state.hits==11,'F8 hidden must continue native hit accounting')
frame(.1);assert(state.hits==11)
native.totals[H]=nil;frame(.1);assert(state.hits==11 and not state.hit_stats_ready)
set(15,{[bullet]=9,[incendiary]=2,[stoker]=1,[spray]=3});assert(state.hits==12)
mission=false;frame(.1);mission=true
set(0,{});assert(state.hits==0 and state.ribbons.hit_total==0)
print('Built hit integration: native requested key, known sources, spray exclusion, one collected ribbon, hidden recording, gap recovery and mission reset passed.')
