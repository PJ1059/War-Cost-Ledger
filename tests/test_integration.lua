-- Built entry + production kill observer; only native memory boundaries are replaced.
local path, runtime_root = assert(arg[1]), assert(arg[2])
table.insert(package.loaders, 2, function(name)
    if name:sub(1, 11) == 'hd2runtime/' then return assert(loadfile(runtime_root .. '/' .. name:sub(12) .. '.lua')) end
end)
local native = require('hd2runtime/domains/event_natives')
local H, b = native.health, require('hd2runtime/core/bytes')
local native_types = require('hd2runtime/domains/event_entities').entities
local SHOTS, KILLS, DEATHS = native.stats.keys.projectiles_fired, native.stats.keys.dealt_kills, native.stats.keys.received_deaths
local saved, frame, draw, state = {}, nil, nil, nil
local active, available, host, peers = true, true, true, 1
local health_readable, bulk_readable = true, true
local actors, beacons, barrages, next_id = {}, {}, {}, 100
local stats = {totals = {[SHOTS] = 0, [KILLS] = 0, [DEATHS] = 0, [0xC7680A1B] = 0}, sources = {}}
local avatar, health_life = 42, 0
local function ribbon_family(ribbons,kind)
    local total=0
    for key,value in pairs(ribbons or{})do
        if (key==kind or key:sub(1,#kind+1)==kind..'_')and type(value)=='number'then total=total+value end
    end
    return total
end
local function copy(v) if type(v) ~= 'table' then return v end; local x = {}; for k,i in pairs(v) do x[k] = copy(i) end; return x end
local store, mod, overlay = {}, {}, {}
function store:get(k,v) return copy(saved[k] == nil and v or saved[k]) end
function store:set(k,v) saved[k] = copy(v) end
function store:save() end
function mod:store() return store end
function mod:log() end
function mod:bind() end
function mod:on_frame(fn) frame = fn end
function overlay:draw(fn) draw = fn end
function overlay:show() end
function overlay:hide() end
package.preload['mods/skyeshade/hd2runtime'] = function() return {mod=function() return mod end,ui={overlay=function() return overlay end}} end
package.preload['hd2runtime/domains/metadata'] = function() return {version='0.30.3'} end
package.preload['hd2runtime/domains/bombardment_payload'] = function() return {manager={global=700,instances=0,barrages=4}} end
local clock = 1000000
local view = {slot=function() return {} end, pointer=function() return 10000 end,
    u32=function() return #barrages end}
local world = {game=1, view=view}
local function bucket_capacity() local n=64; while n < #actors*2 do n=n*2 end; return n end
function view.fill(_, address)
    if not bulk_readable then return nil end
    if address == 1 then return {u32=function(_,offset)
        local i=math.floor(offset/8)+1; local a=actors[i]
        if offset%8==0 then return a and a.id or 0xFFFFFFFF end
        return i-1
    end} end
    if address == 2 then return {u32=function(_,offset)
        local a=actors[math.floor(offset/H.stride)+1]; if not a then return nil end
        local field=offset%H.stride
        if field==H.record.life then return a.life end
        if field==H.record.lastCreditor then return a.credit or 0 end
        if field==H.record.lastCreditor+4 then return 0 end
        if field==H.record.downCreditor then return a.down_credit or 0 end
        if field==H.record.downCreditor+4 then return 0 end
    end} end
    if address == 3 then return {ptr=function(_,offset) return actors[offset/8+1].pointer end} end
end
function view.read(pointer, size)
    for _, a in ipairs(actors) do if a.pointer == pointer then
        local raw = string.rep('\0', size)
        local function set(offset, value) raw=raw:sub(1,offset)..b.encode(value,'u32')..raw:sub(offset+5) end
        set(H.descriptor.type,tonumber(a.kind:sub(9),16)); set(H.descriptor.type+4,tonumber(a.kind:sub(1,8),16))
        set(H.descriptor.entity,a.id)
        return raw
    end end
end
package.preload['hd2runtime/runtime/event_world'] = function() return {
    open=function() return available and world end,
    game_state=function() return {mission=active,host=host} end,
    players=function() local out={{['local']=true,entity=77,peer='0000000000000011',avatar=avatar,lifecycle=3}}
        if peers>1 then out[2]={['local']=false,entity=88,peer='0000000000000022'} end; return out end,
    entity_state=function(_,entity) assert(entity==avatar); return {life=health_life,health=100,max_health=100,descriptor={entity=avatar,owned=true}} end,
    stat_breakdown=function(_,entity) assert(entity==77); return stats end,
    health_header=function() if not health_readable then return nil end; return {live=#actors,hash_capacity=bucket_capacity(),hash_empty=0xFFFFFFFF,buckets=1,records=2,descriptors=3} end,
    type_info=function(kind) return native_types[kind] end,
} end
package.preload['hd2runtime/runtime/beacon_redirect'] = function() return {
    prove=function() return true end, beacons=function() return beacons end,
    clock=function() return clock end,
    bombardment=function() return {list=barrages} end,
} end
package.preload['hd2runtime/runtime/stratagem_loadout'] = function() return {prove=function() return true end,id_of=function(_,v) return v end} end
state=dofile(path).state
-- This fixture checks functional results with simulated game ticks. Real CPU
-- budgets are verified separately by the observer fixtures and benchmarks.
-- Keep this after the shared fixture prefix so those checks retain their clock.
local actual_cpu_clock=os.clock
os.clock=function()return 0 end
local function tick(n) for _=1,n or 1 do clock=clock+100000; frame(0.1) end end
local function mission()
    active=false; tick()
    stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
    actors,beacons,barrages,peers,host,avatar,health_life={}, {}, {}, 1, true,42,0
    active=true; tick()
end
local function actor(kind)
    next_id=next_id+1; local a={id=next_id,pointer=100000+next_id*256,kind=kind,life=0,credit=0}
    actors[#actors+1]=a; return a
end
local function kill(a,credit)
    a.life,a.credit=2,credit or 0x11
    if a.credit==0x11 and native_types[a.kind] and native_types[a.kind].kill then stats.totals[KILLS]=stats.totals[KILLS]+1 end
end
tick()
local titan=actor('9E2E17F2CCCCAFDD'); local charger=actor('1A7FCDFF98C664B0')
local alpha=actor('F79CD8BB654397DF'); local boss=actor('D465D9C7F77A07CB')
tick(4); kill(titan);kill(charger);kill(alpha);kill(boss);tick(2)
assert(state.unit_kills['Bile Titan'].count==1 and state.unit_kills['Bile Titan'].name_zh=='吐酸泰坦')
assert(ribbon_family(state.ribbons,'heavy')==1 and ribbon_family(state.ribbons,'giant')==1)
assert(state.ribbons.heavy==0 and state.ribbons.giant==0
    and state.ribbons.heavy_charger==1 and state.ribbons.giant_bile_titan==1,
    'known units earn one specific ribbon instead of duplicating the generic award')
assert(state.class_kills['中型精英']==1 and state.class_kills.BOSS==1)
assert(state.classified_kills==4 and state.kills==4)
tick(8); assert(state.classified_kills==4,'never duplicate retained corpses/dead records')
local other=actor('1A7FCDFF98C664B0');other.credit=0x11;tick(2);kill(other,0x22);tick(2)
assert(ribbon_family(state.ribbons,'heavy')==1,'an earlier local hit cannot override the current final creditor')
local vanished=actor('1A7FCDFF98C664B0');vanished.credit=0x11;tick(2)
table.remove(actors);tick(2);assert(ribbon_family(state.ribbons,'heavy')==1,'disappearance is not a local kill')
local old=actor('1A7FCDFF98C664B0');old.life=2;old.credit=0x11;tick(2)
assert(ribbon_family(state.ribbons,'heavy')==1,'already dead first observations must not backfill')
local gap=actor('1A7FCDFF98C664B0');tick(2);health_readable=false;tick(2);kill(gap);health_readable=true;tick(2)
assert(ribbon_family(state.ribbons,'heavy')==1,'an unreadable gap starts a new health baseline')
local fresh=actor('1A7FCDFF98C664B0');tick(2);fresh.pointer=fresh.pointer+64;kill(fresh);tick(2)
assert(ribbon_family(state.ribbons,'heavy')==1,'a changed descriptor is a new object identity')
local unknown=actor('FD5247653C897803');tick(2);kill(unknown);tick(2)
assert(state.unknown_unit_kills[unknown.kind].count==1 and state.classified_kills==4)
print('PASS: actual observer to enemy classes, Chinese roles, BOSS separation, final peer ownership, no corpse inference, no duplicate/dead-baseline/despawn/gap/reused-descriptor kills, explicit unresolved hash.')

mission(); peers=2;host=false
for i=1,99 do actor('51EEA86BF6997E4E') end
tick(8); for _,a in ipairs(actors) do kill(a) end;tick(2)
assert(state.life_light_kills==99 and not state.medals.democracy_harvester)
local hundred=actor('51EEA86BF6997E4E');tick(2);kill(hundred);tick(2)
assert(state.life_light_kills==100 and state.medals.democracy_harvester)
stats.totals[DEATHS]=1;health_life=2;tick(2);assert(state.life_light_kills==0 and state.medals.democracy_harvester)
avatar=43;health_life=0;tick(2)
local next_light=actor('51EEA86BF6997E4E');tick(2);kill(next_light);tick(2);assert(state.life_light_kills==1)
print('PASS: 99/100 light one-life threshold, local multiplayer client counting, death/reinforcement reset and retained earned medal.')

for _,case in ipairs({{'282EB766C1FFA6A1',12,'automatons'},{'64090088502435DD',36,'terminids'},{'19E18B46EC55D94A',24,'illuminate'}}) do
    mission()
    for i=1,case[2]-1 do actor(case[1]) end;tick(4)
    for _,a in ipairs(actors) do kill(a) end;tick(2)
    assert(state.air_kills[case[3]]==case[2]-1 and not state.medals.air_expert)
    local last=actor(case[1]);tick(2);kill(last);tick(2)
    assert(state.air_kills[case[3]]==case[2] and state.medals.air_expert)
    assert(state.ribbons.air==case[2])
end
mission()
for i=1,9 do actor('74E2285C01DA4F71') end;tick(4)
for _,a in ipairs(actors) do kill(a) end;tick(2)
assert(state.ribbons.demolition==9 and not state.medals.foreign_parking)
local ship=actor('74E2285C01DA4F71');tick(2);kill(ship);tick(2)
assert(state.medals.foreign_parking and state.ribbons.demolition==10)
local asset=actor('4FB8EB356AC8553E');tick(2);kill(asset);tick(2)
assert(state.ribbons.demolition==11 and state.classified_kills==10,'assets do not add to enemy KillScore')
active=false;tick()
assert(saved.last_mission.medals.foreign_parking and saved.combat_history.medals.democracy_harvester)
assert(saved.last_mission.asset_kills['机器人构造者']==1)
print('PASS: exact 12/36/24 faction air thresholds, 9/10 ship threshold, air/heavy overlap, structures separated from native kills, mission and career persistence.')

mission()
local function fire(kind,amount,kills)
    local source=stats.sources[kind] or {[SHOTS]=0,[KILLS]=0};stats.sources[kind]=source
    source[SHOTS]=source[SHOTS]+amount;source[KILLS]=source[KILLS]+(kills or 0)
    stats.totals[SHOTS]=stats.totals[SHOTS]+amount;stats.totals[KILLS]=stats.totals[KILLS]+(kills or 0)
    tick()
end
fire('968211C0033DCE64',10,2);assert(state.total_cents==350 and #state.entries==1)
assert(state.weapon_stats['968211C0033DCE64'].name=='AR-23 解放者' and state.weapon_stats['968211C0033DCE64'].kills==2)
fire('46183B50961D1328',11);assert(state.total_cents==402,'11 pellets are one shell')
fire('46183B50961D1328',5);assert(state.total_cents==402)
fire('46183B50961D1328',6);assert(state.total_cents==454 and state.entries[2].quantity==2)
fire('25AA2FD4643CF4EE',1);assert(state.total_cents==15000454,'Spear uses its approved guided-missile price')
fire('0101010101010101',100);assert(state.total_cents==15000454)
local function call(id,entity)
    beacons[entity]={entity=entity,type=id,activated=false};tick();beacons[entity].activated=true;tick()
end
call(1238358532,1001);assert(state.total_cents==20700454,'Eagle Airstrike includes payload once')
call(3572024208,1002);assert(state.total_cents==23820454,'chainsaw is whole equipment')
call(3413606544,1003);assert(state.total_cents==27560454,'disposable includes prepaid ammunition')
tick(20);assert(state.total_cents==27560454)
peers=2;call(1238358532,1004);assert(state.total_cents==27560454,'no teammate call fees')
fire('968211C0033DCE64',1);assert(state.total_cents==27560489,'local ammo remains active in multiplayer')
print('PASS: varied weapon/missile prices, Chinese source kills, shell/pellet conversion and remainder, unknown sources, whole melee equipment, disposable/eagle prepaid policy, beacon dedup and multiplayer separation.')

mission()
call(3108516875,2001)
barrages={{entity=3001,payload='0xEF66B417EDC3B1D6',fired=0}};tick()
assert(state.total_cents==0,'unfired barrage has no platform or shell charge')
barrages[1].fired=3;tick();assert(state.total_cents==6300000 and #state.entries==2)
barrages[1].fired=27;tick();assert(state.total_cents==20700000 and state.entries[2].quantity==27)
tick(20);assert(state.total_cents==20700000,'unchanged shell counter is not recharged')
barrages={};tick()
-- A different ship's upgrade can produce a different number; no default salvo count.
call(3108516875,2002);barrages={{entity=3002,payload='0xEF66B417EDC3B1D6',fired=36}};tick()
assert(state.total_cents==46800000 and state.entries[4].quantity==36)
call(1063322614,2003);barrages[#barrages+1]={entity=3003,payload='0x2D3BD00B1ED411B1',fired=24};tick()
assert(state.total_cents==54180000 and state.entries[6].quantity==24)
call(2084654169,2004);barrages[#barrages+1]={entity=3004,payload='0x2F257B91037AC421',fired=100};tick()
assert(state.total_cents==58980000 and state.entries[8].quantity==100)
print('PASS: first-shell platform fee, 380mm 27/36 actual shells, 120mm 24 shells, gatling 100 shells, aggregated per-barrage detail, no child-explosion billing.')
mission();barrages={{entity=4000,payload='0xEF66B417EDC3B1D6',fired=20}};tick();barrages[1].fired=36;tick()
assert(state.total_cents==0,'an unassociated existing barrage is never back-charged')
local scan_start=state.kill_observer.scans
for i=1,600 do frame(1/60) end
assert(state.kill_observer.scans-scan_start==100,'health observer is 10Hz, not every frame')
local before=state.kill_observer.scans;frame(3);assert(state.kill_observer.scans==before+1,'slow frame must not replay polls')
assert(state.ribbons.air==0 and not state.medals.foreign_parking,'new mission clears earned match state')
print('PASS: existing/unassociated barrage baseline, 100/600-frame health budget, no long-frame catch-up, clear new-mission classification.')

os.clock=actual_cpu_clock
