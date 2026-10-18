-- Independent boundary review using the real stat/presentation modules and built artwork.
-- No game process, native reads, process writes or synthetic hit-result classifier.
local create_hits=dofile(assert(arg[1]))
local create_battle=dofile(assert(arg[2]))
local create_awards=dofile(assert(arg[3]))
local create_native=dofile(assert(arg[4]))
local art=dofile(assert(arg[5]))
local create_layout=dofile(arg[4]:gsub('native%-hud%-addon%.lua$','hud-layout.lua'))
local K=0x897A5551
local STOKER='8A307BD1811A5FE9'
local STOKER_SPRAY='992B6F65A5BAB53D'
local INCENDIARY='C12A34F375BD5A87'
local TORCHER='4FB0F8C02F55C82B'
local allowed={[STOKER]=true,[INCENDIARY]=true}
local total,failures=0,{}
local function check(name,fn)
    total=total+1
    local ok,why=pcall(fn)
    if not ok then failures[#failures+1]=name..': '..tostring(why) end
end
local function snapshot(native,values)
    local out={totals={[K]=native},sources={}}
    for source,value in pairs(values) do out.sources[source]={[K]=value,[0x0646D0B3]=99999} end
    return out
end
local function equal(value,expected,label)
    assert(value==expected,(label or 'value')..': '..tostring(value)..' ~= '..tostring(expected))
end

check('Stoker main and incendiary projectiles remain separate from both flame branches',function()
    local h=create_hits(allowed,K)
    local n,d,first=h:sample(snapshot(23,{[STOKER]=11,[STOKER_SPRAY]=8,[INCENDIARY]=3,[TORCHER]=1}),7)
    assert(n==14 and d==0 and first and h.ready)
    n,d=h:sample(snapshot(27,{[STOKER]=13,[STOKER_SPRAY]=9,[INCENDIARY]=3,[TORCHER]=2}),7)
    assert(n==16 and d==2)
    n,d=h:sample(snapshot(31,{[STOKER]=13,[STOKER_SPRAY]=11,[INCENDIARY]=3,[TORCHER]=4}),7)
    assert(n==16 and d==0,'Spray-only growth must not add ordinary projectile contacts')
end)
check('new source with unchanged native total does not replay historical attribution',function()
    local h=create_hits(allowed,K)
    equal(h:sample(snapshot(10,{[STOKER]=10}),7),10)
    assert(h:sample(snapshot(10,{[INCENDIARY]=10}),7)==nil)
    assert(h.total==10 and h.added==0 and h.reason=='HIT_SOURCE_REBASE')
    local n,d=h:sample(snapshot(11,{[INCENDIARY]=11}),7)
    assert(n==11 and d==1,'next actual growth must remain countable after source rebase')
end)
check('source sum valid but growth exceeds native growth is a rebase not a count',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(20,{[STOKER]=10}),7)
    assert(h:sample(snapshot(21,{[INCENDIARY]=15}),7)==nil)
    assert(h.total==10 and h.added==0 and not h.ready)
    equal(h:sample(snapshot(22,{[INCENDIARY]=16}),7),11)
end)
check('in-place reused snapshot is compared to copied numerical baselines',function()
    local h=create_hits(allowed,K)
    local s=snapshot(2,{[STOKER]=2})
    h:sample(s,7)
    s.totals[K]=4;s.sources[STOKER][K]=4
    local n,d=h:sample(s,7)
    assert(n==4 and d==2)
    n,d=h:sample(s,7);assert(n==4 and d==0)
end)
check('same user entity across avatar respawn preserves cumulative hit counters',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(8,{[STOKER]=8}),7)
    -- Avatar/death identity does not belong to this player-stat interface.
    local n,d=h:sample(snapshot(10,{[STOKER]=10}),7)
    assert(n==10 and d==2)
    n,d=h:sample(snapshot(10,{[STOKER]=10}),7)
    assert(n==10 and d==0)
end)
check('new user entity establishes baseline without replay or erasing mission count',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(8,{[STOKER]=8}),7)
    local n,d,first=h:sample(snapshot(30,{[INCENDIARY]=30}),8)
    assert(n==8 and d==0 and not first)
    n,d=h:sample(snapshot(31,{[INCENDIARY]=31}),8)
    assert(n==9 and d==1)
end)
check('native cumulative reset rebases observed mission total without side replay',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(8,{[STOKER]=8}),7)
    local n,d=h:sample(snapshot(2,{[STOKER]=2}),7)
    assert(n==8 and d==0)
    n,d=h:sample(snapshot(3,{[STOKER]=3}),7)
    assert(n==9 and d==1)
end)
check('temporarily missing source retains high water and later growth counts once',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(8,{[STOKER]=6,[INCENDIARY]=2}),7)
    local n,d=h:sample(snapshot(9,{[STOKER]=7}),7)
    assert(n==9 and d==1)
    n,d=h:sample(snapshot(10,{[STOKER]=8,[INCENDIARY]=2}),7)
    assert(n==10 and d==1)
end)
check('invalid input never clears cumulative or allows more than 64 source blocks',function()
    local h=create_hits(allowed,K)
    h:sample(snapshot(1,{[STOKER]=1}),7)
    assert(h:sample(snapshot(1,{[STOKER]=-1}),7)==nil and h.total==1)
    assert(h:sample(snapshot(1,{[STOKER]=math.huge}),7)==nil and h.total==1)
    local values={[STOKER]=1};for i=1,63 do values['unknown'..i]=0 end
    assert(h:sample(snapshot(1,values),7)==1)
    values.unknown64=0
    assert(h:sample(snapshot(1,values),7)==nil and h.reason=='HIT_STATS_INVALID' and h.total==1)
end)
check('only unknown or spray native growth remains excluded rather than assigned to hit types',function()
    local h=create_hits(allowed,K)
    local n,d=h:sample(snapshot(50,{[TORCHER]=20,unknown=30}),7)
    assert(n==0 and d==0)
    n,d=h:sample(snapshot(60,{[TORCHER]=25,unknown=35}),7)
    assert(n==0 and d==0 and h.sources[STOKER]==nil)
end)

local state={sequence=1,kills=5,shots=12,deaths=1,history_kills=100,history_deaths=2,
    total_cents=100,ribbons={hit_total=7},mission_medals={}}
local battle=create_battle(state,function()return true end)
local ids,icons={},{}
for _,asset in ipairs(art.images)do ids[asset.id]=true end
for _,icon in ipairs(battle.icons)do if ids[icon.id]then icons[#icons+1]=icon end end
local awards=create_awards(state,icons)
awards:baseline(0)
check('late first hits appear in map collection without replaying temporary side icons',function()
    local closed=awards:snapshot(0,true,false)
    assert(#closed.items==0 and #closed.ribbons==0)
    local opened=awards:snapshot(0,true,true)
    local h;for _,item in ipairs(opened.ribbons)do if item.id=='H01' then h=item end end
    assert(h and h.count==7,'actual installed icon filter must retain H01')
end)
check('aggregate H01 growth stays collection-only and does not start a two-second result batch',function()
    state.ribbons.hit_total=9
    local closed=awards:snapshot(.1,true,false)
    assert(#closed.items==0 and closed.deadline==nil)
    local map=awards:snapshot(.1,true,true)
    local h;for _,item in ipairs(map.ribbons)do if item.id=='H01'then h=item end end
    assert(h and h.count==9)
    map=awards:snapshot(2.2,true,true)
    assert(#map.items==0 and #map.ribbons==1)
end)
check('actual native collected H01 has frame image and numeric count widget bindings',function()
    local feed={shown=true,hud=0x20000000,position={0,-96},scale={1,1},size={336,136},opacity=.82,
        shots='12',kills='5',fire='0',bill='1.00',kd='5.00',history_kd='50.00',map_open=true,
        ribbons=awards:snapshot(2.2,true,true).ribbons,medals={},side={},now=2.2}
    feed.layout=create_layout():build({kills=feed.kills,shots=feed.shots,bill_text=feed.bill,
        kd_text=feed.kd},{ribbons=feed.ribbons,medals={},hits={},items={}},true,336,{items={}},2.2,1)
    local native=create_native({art=art,publish=false,feed=function()return feed end})
    local view=native.compute.ledger_cached_feed.run(nil,nil,nil,nil,{hud=feed.hud})
    assert(view and view.collected_H01_texture and view.collected_H01_frame)
    assert(view.collected_H01_count=='x9','sanitized feed must carry actual H01 count')
    local rows={};for _,row in ipairs(native.screens[1].rows)do rows[row.id]=row end
    assert(rows.ledger_collected_H01_texture,'no H01 texture widget')
    assert(rows.ledger_collected_H01_frame,'no H01 ribbon-frame widget')
    assert(rows.ledger_collected_H01_count,'no H01 numeric count widget')
    assert(rows.ledger_collected_H01_count.source=='ledger.native.collected_H01_count')
end)
assert(#failures==0,table.concat(failures,'\n'))
print('Independent projectile hit review: '..total..' checks passed; actual native H01 bindings and stats anomaly boundaries covered.')
