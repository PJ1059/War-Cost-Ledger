-- Presentation-only source/victim inference through the real built addon.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local CANNON,MG='1FA1F596769225C2','439F9E65C18567DA'
local TITAN,CHARGER='9E2E17F2CCCCAFDD','1A7FCDFF98C664B0'
local UNKNOWN='FACEFACEFACEFACE'
native_types[UNKNOWN]={name='Synthetic Unknown Enemy',kill=true}
stats.totals[KILLS]=5;stats.sources[CANNON]={[KILLS]=5,[SHOTS]=0}
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind,life=0,credit=0}
    actors[#actors+1]=a;return a
end
local function kill(a,hash)
    a.life,a.credit=2,0x11;stats.totals[KILLS]=stats.totals[KILLS]+1
    if hash then
        local row=stats.sources[hash] or {[KILLS]=0,[SHOTS]=0};stats.sources[hash]=row
        row[KILLS]=row[KILLS]+1
    end
end
local function notices()return state.kill_source_notices and state.kill_source_notices.items or {}end
local function newest()
    assert(#notices()==1,'only the latest source notice may be visible')
    local row=assert(notices()[1],'new notice missing')
    assert(row.persistent~=true and row.expires_at>now and #row.lines==1 and row.lines[1]==row.text)
    assert(row.text==row.target_text..' ['..row.source_text..']','compact target [source] text changed')
    assert(not row.text:find('推测',1,true)and not row.text:find('→',1,true),'extra explanatory text leaked into HUD')
    return row
end
local function pause()
    local row=newest()
    tick(math.max(0,math.floor((row.expires_at-now)/.1)-1))
    assert(newest().id==row.id,'latest text vanished before five seconds')
    tick(3);assert(#notices()==0,'latest text must expire after five seconds without another kill')
end
tick(12)
assert(#notices()==0,'the first native kill/source totals are a baseline, never feedback')
local first=actor(TITAN);tick(4);kill(first,CANNON);tick(10)
local row=newest()
assert(row.status=='inferred' and row.per_victim_proven==false)
assert(row.source_hash==CANNON and row.target_hash==TITAN)
assert(state.kills==6 and ribbon_family(state.ribbons,'giant')==1 and state.ribbons.giant==0 and state.ribbons.crush==0,
    'notices cannot manufacture another kill, ribbon, or parent-body crush')
local old_id=row.id
stats.sources[MG]={[KILLS]=0,[SHOTS]=12};stats.totals[SHOTS]=12;tick(3)
assert(newest().id==old_id,'firing a different mounted weapon is not a new kill-source cue')
pause()
local left,right=actor(TITAN),actor(CHARGER);tick(4)
kill(left,CANNON);kill(right,MG);tick(10)
row=newest()
assert(row.status=='inferred' and row.per_victim_proven==false and row.observed_victims==1)
assert(row.target_hash==CHARGER and row.source_hash==MG,
    'FIFO source counts and observed victims must leave only the final compact target/source row')
pause()
local unsourced=actor(TITAN);tick(4);kill(unsourced,nil);tick(10)
row=newest()
assert(row.status=='unknown' and row.target_hash==TITAN and row.source_hash==nil)
assert(row.source_text=='未知来源','missing weapon evidence cannot be replaced with an expired or currently fired gun')
pause()
assert(#notices()==0)
stats.totals[KILLS]=stats.totals[KILLS]+1;tick(10)
assert(#notices()==0,'unattributed native kill batches must not invent an unknown target')
stats.totals[KILLS]=stats.totals[KILLS]+1;stats.sources[CANNON][KILLS]=stats.sources[CANNON][KILLS]+1;tick(10)
assert(#notices()==0,'source-only batches must not invent a victim')
tick(70);assert(#notices()==0)
local unknown=actor(UNKNOWN);tick(4);kill(unknown,CANNON);tick(10)
row=newest()
assert(row.target_hash==UNKNOWN and row.target_text=='Synthetic Unknown Enemy'
    and not row.text:find(UNKNOWN,1,true),
    'native enemy name should display compactly while its complete hash stays in metadata')
assert(state.unknown_unit_kills[UNKNOWN].count==1)
pause()
local lost=actor(TITAN);tick(4);available=false;tick();kill(lost,CANNON)
available=true;tick(12)
assert(#notices()==0,'read-gap restoration must not revive expired text or pair old death/source growth')
local fresh=actor(TITAN);tick(4);kill(fresh,CANNON);tick(10)
assert(newest().status=='inferred','a fresh verified source/death after the baseline is eligible')
assert(module.kill_source_snapshot().per_victim==false,'display inference does not create persisted victim/weapon proof')
pause()
local old_mg=stats.sources[MG];stats.sources[MG]=nil;tick(2)
local returned=actor(TITAN);tick(4);stats.sources[MG]=old_mg;kill(returned,CANNON);tick(10)
row=newest()
assert(row.status=='inferred' and row.source_hash==CANNON,
    'a disappeared source block returning cannot pollute a fresh single-source kill batch')
pause()
-- These actual Runtime types have info.kill=true, but reviewed Ledger roles
-- explicitly classify them as assets. They cannot become enemy-victim rows.
local SHIP,TRANSPORT='74E2285C01DA4F71','DB90077E76FAA025'
assert(native_types[SHIP].kill==true and native_types[TRANSPORT].kill==true)
local ship,transport,clean=actor(SHIP),actor(TRANSPORT),actor(TITAN)
local previous_demolition=state.ribbons.demolition
tick(4);ship.life,ship.credit=2,0x11;transport.life,transport.credit=2,0x11
kill(clean,CANNON);tick(10)
row=newest()
assert(row.status=='inferred' and row.kills==1 and row.observed_victims==1
    and row.target_hash==TITAN,
    'mapped asset exclusions override Runtime info.kill and cannot pollute a real enemy inference')
assert(state.ribbons.demolition==previous_demolition+2,'presentation filtering must preserve existing asset demolition awards')
pause()
local STRUCTURE='DEADDEADDEADDEAD'
native_types[STRUCTURE]={name='Synthetic Unmapped Structure',kill=true,kind='structure'}
local structure,other=actor(STRUCTURE),actor(TITAN)
tick(4);structure.life,structure.credit=2,0x11;kill(other,CANNON);tick(10)
row=newest()
assert(row.status=='inferred' and row.observed_victims==1
    and row.target_hash==TITAN,'unmapped structures cannot use the generic enemy fallback')
active=false;tick()
assert(#notices()==0,'ship return clears visible and pending source feedback')
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
actors={};active=true;tick(12)
assert(#notices()==0,'new mission cannot replay the previous match source/victim window')
-- The display option must not gate the observer, native source totals or awards.
assert(module.ui_settings:set('kill_source_enabled',false))
tick(2)
local hidden=actor(TITAN);tick(4)
local before_kills,before_giant=state.kills,ribbon_family(state.ribbons,'giant')
kill(hidden,CANNON);tick(10)
assert(state.kills==before_kills+1 and ribbon_family(state.ribbons,'giant')==before_giant+1
    and state.weapon_stats[CANNON].kills==1,
    'hiding kill-source text must keep recording real kills, sources and ribbons')
local hidden_model=module.game_hud:native_model(now,true)
assert(#(hidden_model.kill_source_notices.items or {})==0,
    'a real kill during display-off cannot appear in the HUD model')
local retained_kills,retained_giant=state.kills,ribbon_family(state.ribbons,'giant')
assert(module.ui_settings:set('kill_source_enabled',true))
assert(#notices()==0,'reopening cannot replay the last hidden kill')
tick(2)
assert(#notices()==0 and state.kills==retained_kills and ribbon_family(state.ribbons,'giant')==retained_giant,
    'display changes must neither replay feedback nor change earned totals')
local visible=actor(TITAN);tick(4);kill(visible,CANNON);tick(10)
assert(newest().source_hash==CANNON,'the next fresh kill must display after reopening')
print('PASS: actual built target [source], latest single line with five-second expiry, FIFO mixed sources, compact unknown names/raw metadata, no source-only targets, gap without stale pairing, asset/structure exclusions and ship/new-mission clearing; no persisted per-victim proof.')
print('PASS: actual settings callback hides kill-source text while real kill/source/ribbon totals advance; reopening clears the hidden latest and only fresh kills display.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@kill-source-notices-integration'))()
