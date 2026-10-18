-- Real built addon, native kill observer, persistence, notification and history.
-- Reuse the existing owned native-memory fixture; no game/account interaction.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind,life=0,credit=0}
    actors[#actors+1]=a;return a
end
local function kill(a)
    a.life,a.credit=2,0x11
    stats.totals[KILLS]=stats.totals[KILLS]+1
end
local function find(items,id)for _,v in ipairs(items)do if v.id==id then return v end end end
tick(3)
assert(state.ribbons.killstreak==0,'mission-start ribbon zero must be observed before the first native stats baseline')
stats.totals[KILLS]=5;tick()
local first_ribbon=find(module.game_hud:native_model(now,true,600).awards.items,'R11')
assert(first_ribbon and first_ribbon.count==1 and first_ribbon.total==1,
    'first five kills must pop R11 instead of silently becoming its baseline')
assert(module.career_award_snapshot().totals.ribbons.killstreak==1)
assert(module.mission_history_snapshot().entries[1].ribbons.killstreak==1)
for wave=1,3 do
    local batch={}
    for n=1,100 do batch[n]=actor('51EEA86BF6997E4E')end
    tick(12)
    for _,a in ipairs(batch)do kill(a)end
    tick(6)
    assert(state.mission_medals.democracy_harvester==wave,'every 100 in the same life awards another acquisition')
    assert(module.career_award_snapshot().totals.medals.democracy_harvester==wave)
    assert(module.mission_history_snapshot().entries[1].medals.democracy_harvester==wave)
    local live=module.game_hud:native_model(now,true,600)
    local notice=find(live.awards.items,'M01')
    assert(notice and notice.total==wave,'each acquisition reaches the actual live popup pipeline')
end
assert(state.life_light_kills==300 and state.ribbons.killstreak==61)
assert(state.mission_medals.democracy_star==1 and state.mission_medals.super_democracy_star==1
    and state.mission_medals.supreme_democracy_star==1)
-- The pair consumes distinct giants; a third cannot reuse either of them.
local first,second,third=actor('9E2E17F2CCCCAFDD'),actor('9E2E17F2CCCCAFDD'),actor('9E2E17F2CCCCAFDD')
tick(6);kill(first);tick(2);kill(second);tick(2)
assert(state.mission_medals.double_giant==1)
kill(third);tick(2);assert(state.mission_medals.double_giant==1)
assert(module.career_award_snapshot().totals.medals.double_giant==1)
-- Native batched kills cannot order before/after a death; do not bridge them.
stats.totals[DEATHS]=1;stats.totals[KILLS]=stats.totals[KILLS]+70;tick()
assert(state.killstreak==0 and state.life_light_kills==0)
assert(state.mission_medals.democracy_star==1,'the death-containing batch must not create a new chain')
-- The next exact native increments form a fresh chain; type coverage is optional.
for _=1,70 do stats.totals[KILLS]=stats.totals[KILLS]+1;tick()end
assert(state.killstreak==70 and state.mission_medals.democracy_star==2)
assert(module.career_award_snapshot().totals.medals.democracy_star==2)
active=false;tick()
assert(saved.last_mission.mission_medals.democracy_harvester==3)
assert(saved.mission_history_v1.entries[1].medals.democracy_harvester==3)
local before=module.career_award_snapshot().totals.medals.democracy_harvester
local before_ribbons=module.career_award_snapshot().totals.ribbons.killstreak
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state;tick(2)
assert(module.career_award_snapshot().totals.medals.democracy_harvester==before,'reload cannot replay or re-import repeated acquisitions')
assert(module.career_award_snapshot().totals.ribbons.killstreak==before_ribbons,'reload cannot re-import the first streak ribbon')
assert(#module.game_hud:native_model(now,true,600).awards.items==0,'reload must not replay old streak or medal notifications')
print('PASS: first five native kills pop R11 with exact cumulative/history counts; built observer to 300 light/three achievements, repeated popups, cumulative/history counts, 750ms giant pair, native 70-kill chain, death-batch exclusion and reload without duplication.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@repeat-achievements-integration'))()
