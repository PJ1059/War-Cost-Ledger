-- Built addon, actual 96B decoder/session/accept, owned Health/entity bytes,
-- real static catalog, notices, per-match career query and save/reload.
-- Reuse only the existing fixture's installer/transport boundary scaffold.
local addon,runtime,fixture,target_fixture,copy_fixture,damage_fixture=
    assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5]),assert(arg[6])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local copy=read(copy_fixture)
first=assert(copy:find('local function record(sequence,result)',1,true))
last=assert(copy:find('local kinds=',first,true))
local record_helper=copy:sub(first,last-1)
local damage=read(damage_fixture)
first=assert(damage:find('local before=[=[',1,true))+#'local before=[=['
last=assert(damage:find('\n]=]',first,true))
local before=damage:sub(first,last-1)
local scenario=[=[
local RL='26E40437EA275296'
local detail=assert(upvalue(module.career_combat_query,'combat_detail'))
local reverse=assert(detail.damage_catalog.reverse)
local function unique(kind,id,source)
    local row=assert(reverse[kind][tostring(id)],kind..id..' is absent from the actual built catalog')
    assert(#row.candidates==1 and row.candidates[1]==source and row.unresolved~=true,
        kind..id..' must be a genuinely unique native parent in the production catalog')
end
unique('projectile',284,AC);unique('damage_info',202,AC)
unique('projectile',312,RL);unique('damage_info',380,RL)
assert(reverse.damage_info['189'].unresolved==true and #reverse.damage_info['189'].candidates>1,
    'shared fragment189 must remain ambiguous in the real catalog')
local decoder=assert(upvalue(c.consumer.decoder.consume,'M'),'real decoder module')
local function typed_record(target,projectile,damage_id,valid_projectile)
    c.record_sequence=c.record_sequence+1
    local raw=record(c.record_sequence,'penetration')
    local function put(at,value)raw=raw:sub(1,at)..value..raw:sub(at+#value+1)end
    put(44,b.encode(target.id,'u32'));put(48,b.encode(42,'u32'));put(52,b.encode(42,'u32'))
    put(32,b.encode(projectile or 0,'u32'));put(36,b.encode(damage_id,'u32'))
    put(88,b.encode(0x1FF+512+1024+(valid_projectile and 2048 or 0),'u32'))
    assert(#raw==96)
    local decoded=assert(decoder.decode(raw))
    assert(decoded.damage_info_id==damage_id)
    assert(decoded.projectile_id==(valid_projectile and projectile or nil),
        'the actual decoder must require flag2048 before naming old +32 bytes as a ProjectileType')
    c.batches[#c.batches+1]=raw
end
local function die(projectile,damage_id,valid_projectile)
    local target=actor()
    typed_record(target,projectile,damage_id,valid_projectile)
    target.health,target.life=0,2
    stats.totals[KILLS]=stats.totals[KILLS]+1
    local raw=stats.sources[UNKNOWN]or{[KILLS]=0,[SHOTS]=0};stats.sources[UNKNOWN]=raw
    raw[KILLS]=raw[KILLS]+1
    tick(3)
    assert(state.ribbons.hit_penetration==0 and state.ribbons.hit_full_penetration==0,
        'attribution-only typed records cannot create additional native hit awards')
    return latest()
end
local line=die(284,202,true)
assert(line.source_hash==AC and state.weapon_stats[AC].kills==1,
    'actual P284+D202 tuple reaches the AC8 notice and permanent weapon counter')
line=die(312,380,true)
assert(line.source_hash==RL and state.weapon_stats[RL].kills==1,
    'actual P312+D380 tuple reaches the RL77 notice and permanent weapon counter')

-- +32=284 was a valid old slot value. Without bit2048, the unique D380
-- still identifies RL77; interpreting that slot as P284 would contradict it.
line=die(284,380,false)
assert(line.source_hash==RL and state.weapon_stats[RL].kills==2,
    'a legacy +32 slot does not enter the projectile namespace without explicit validity')
for _,tuple in ipairs({{284,380},{312,202}})do
    line=die(tuple[1],tuple[2],true)
    assert(line.source_text=='未知来源' and line.source_hash~=AC and line.source_hash~=RL,
        'contradictory actual ProjectileType/DamageInfo candidate sets must remain unknown')
end
line=die(201,189,false)
assert(line.source_text=='未知来源' and line.source_hash~=AC,
    'a shared unresolved DamageInfo cannot borrow unflagged slot bytes or the preceding target weapon')

assert(state.kills==6 and state.weapon_stats[AC].kills==1 and state.weapon_stats[RL].kills==2)
assert(c.consumer.decoder.accepted==6 and c.consumer.records==6,
    'all six actual records traversed the real transport decoder/session/accept path')
local sequence=state.sequence
local function career()
    local q=module.career_combat_query('weapons',{sequence=sequence})
    assert(q.totals.kills==6 and q.coverage.unknown_kills==3,
        'per-match career includes three known and three unknown kills without double counting')
    return q
end
career()
assert(ribbon_family(state.ribbons,'heavy')==6 and stats.sources[UNKNOWN][KILLS]==6,
    'source resolution changes neither actual enemy kill counts nor the native raw source counter')
assert(state.source_reassignments['4D1C334D294DFA97']==3,
    'three resolved kills retain their actual raw avatar correction provenance')
active=false;tick(3)
assert(saved.last_mission.kills==6 and saved.last_mission.source_reassignments['4D1C334D294DFA97']==3)
local raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons[UNKNOWN].kills==6 and raw.weapons[AC].kills==1 and raw.weapons[RL].kills==2,
    'the archive preserves native unknown rows separately from the reconstructed weapon counts')
rawset(_G,'HD2WarCostLedgerV1',nil)
module=assert(loadstring(built,'@actual-built-projectile-tuples-reloaded'))();state=module.state;tick(3)
career()
raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons[UNKNOWN].kills==6 and raw.weapons[AC].kills==1 and raw.weapons[RL].kills==2)
assert(ribbon_family(module.career_award_snapshot().totals.ribbons,'heavy')==6,
    'saved unit ribbons and source corrections survive reload without replay')
print('PASS built projectile tuples: actual96B flag2048+512+1024 -> decoder/session/contact/observer/real catalog -> AC8/RL77 notice + career; legacy slot exclusion, contradictory/shared unknown, count0, original totals and save/reload')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..before..'\n'..record_helper..scenario,
    '@built-projectile-tuples-end-to-end-owned'))()
