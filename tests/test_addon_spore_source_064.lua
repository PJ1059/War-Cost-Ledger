-- Owned native Health bytes and real built addon: death-triggered target self
-- explosion must not replace the local weapon that actually damaged it.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'6B202392F4AB605E'")
local scenario=[=[
os.clock=function()return 0 end -- deterministic replay; no performance claim
local OTHER,UNKNOWN='F79CD8BB654397DF','FFFFFFFFFFFFFFFF'
owners[210]=OTHER
local module=dofile(path);state=module.state
local now,total=0,0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(credit,kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind or TYPE,life=0,health=100,
        credit=credit==nil and 0x11 or credit,owner=0}
    actors[#actors+1]=a;owners[a.id]=a.kind;tick(3);return a
end
local function hit(a,owner,health)
    a.health,a.owner,a.damage_kind=health or 30,owner,0;tick()
end
local function prepare_death(a,owner,counted)
    a.health,a.owner,a.damage_kind,a.life=0,owner or a.id,4,2
    if counted~=false then
        total=total+1;stats.totals[KILLS]=stats.totals[KILLS]+1
        local raw=owner==210 and OTHER or a.kind
        local row=stats.sources[raw]or{[SHOTS]=0,[KILLS]=0};stats.sources[raw]=row
        row[KILLS]=row[KILLS]+1
    end
end
local function die(a,owner,counted)prepare_death(a,owner,counted);tick(4)end
local function latest()return assert(state.kill_source_notices.items[1])end
local function weapon(expected,label)
    local n=latest()
    assert(n.target_text=='孢子强袭虫'and n.source_hash==expected and not n.damage_source.mechanism,
        label..'; got '..tostring(n.source_hash)..'/'..tostring(n.damage_source.mechanism))
    assert(n.damage_source.inferred and n.attribution=='same_target_weapon_before_self_explosion')
end
tick(12)
local a=actor();hit(a,201);tick(39);die(a)
weapon(AC,'AC8 hit then same target death explosion after four seconds must retain AC8')
assert(state.weapon_stats[AC].kills==1 and state.kill_pairs[TYPE][AC]==1)
local b=actor();hit(b,201,70);hit(b,206);die(b)
weapon(R36,'the latest different weapon, Eruptor, wins')
local no_anchor=actor();die(no_anchor)
assert(latest().source_hash==TYPE and latest().damage_source.mechanism=='self_explosion')
local expired=actor();hit(expired,201);tick(50);die(expired)
assert(latest().source_hash==TYPE and latest().damage_source.mechanism=='self_explosion',
    '5.1 seconds without damage cannot reuse an old weapon')
local enemy=actor();hit(enemy,201);die(enemy,210)
assert(latest().source_hash==OTHER and latest().damage_source.mechanism=='enemy_damage',
    'a different real enemy owner keeps its friendly-fire source')
-- Missing creditor must consume one real native local kill quota.
local missing=actor(0);hit(missing,201);die(missing)
assert(latest().source_hash==TYPE and latest().damage_source.mechanism=='self_explosion',
    'a source without local weapon provenance is not retrospectively made local')
-- A known other peer may never borrow the local weapon or add rewards.
local before=state.ribbons.heavy_spore_charger
local remote=actor();hit(remote,201);remote.credit=0x22;die(remote,nil,false)
assert(state.kills==total and state.ribbons.heavy_spore_charger==before)
-- Several victims share the same poll, each counts once and retains its weapon.
local many={}
for i=1,8 do many[i]=actor();hit(many[i],201)end
for _,a in ipairs(many)do prepare_death(a)end
tick(10)
assert(state.kills==total and total==14 and state.classified_kills==14
    and state.ribbons.heavy_spore_charger==14,'one reward per native local death, even a simultaneous batch')
assert(state.weapon_stats[AC].kills==9 and state.weapon_stats[R36].kills==1
    and state.kill_pairs[TYPE][AC]==9 and state.kill_pairs[TYPE][R36]==1)
-- Four actual Spore Burst resources, kept distinct from three Rupture
-- burrower resources. These are offline mechanism replays, not evidence that
-- every Rupture unit necessarily emits a death explosion in the live game.
local variants={
    {'DB964631BE1CF501','孢裂食腐虫','Spore Burst Scavenger'},
    {'1F0A91729C0004E0','孢裂追猎虫','Spore Burst Hunter'},
    {'728421351D440EBC','孢裂武斗虫','Spore Burst Warrior'},
    {'EF04CB84D097A497','孢裂吐酸泰坦','Spore Burst Bile Titan'},
    {'A35207C6F2150806','爆裂武斗虫','Rupture Warrior'},
    {'A381A11C07D3EB94','爆裂喷涌虫','Rupture Spewer'},
    {'0AB7B92B131C228C','爆裂强袭虫','Rupture Charger'},
}
for _,v in ipairs(variants)do
    local a=actor(nil,v[1]);hit(a,201);die(a)
    local n=latest()
    assert(n.target_hash==v[1]and n.target_text==v[2]and n.source_hash==AC
        and n.damage_source.inferred and not n.damage_source.mechanism,
        v[2]..' must retain the actual local weapon when the verified final owner is itself')
    assert(state.kill_pairs[v[1]][AC]==1 and state.unit_kills[v[3]].count==1,
        v[2]..' must count once under its own identity')
end
assert(state.kills==21 and state.classified_kills==21 and state.weapon_stats[AC].kills==16)
assert(state.class_kills['轻型']==2 and state.class_kills['中型']==2
    and state.class_kills['中型精英']==1 and state.class_kills['重型']==15
    and state.class_kills['巨型']==1,'all real variant classes remain separate and counted once')
local seq=state.sequence
local function verify_query()
    local q=module.career_combat_query('weapons',{sequence=seq})
    assert(q.totals.kills==21 and q.coverage.unknown_kills==0 and q.coverage.inferred_pairs==21)
    local counts={};for _,r in ipairs(q.rows)do counts[r.id]=r.kills end
    assert(counts[AC]==16 and counts[R36]==1 and counts[TYPE]==3 and counts[OTHER]==1,
        'weapon correction removes only the seventeen self-explosion source counters reassigned to weapons')
    for _,v in ipairs(variants)do assert(not counts[v[1]]or counts[v[1]]==0,
        v[2]..' self-explosion must not duplicate its weapon-attributed kill')end
end
verify_query();active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
verify_query()
print('PASS built self explosion: Spore Charger + four exact Spore Burst + three distinct Rupture resources; recent/local/new weapon, no anchor, expiry, enemy owner, missing/foreign creditor, simultaneous kills, corrected career totals, save/reload.')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-spore-source-064'))()
