-- Actual built addon and its public explosion callback, owned native Health
-- bytes, real attribution/rewards/career/persistence. No synthetic kill event
-- or replacement production module supplies the missing gas source anchor.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local expected_version=arg[5]and arg[5]:match('([^/\\]+)$')or'0.4.65'
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
assert(read(addon):find("local VERSION = '"..expected_version.."'",1,true),'actual built '..expected_version)
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
os.clock=function()return 0 end -- deterministic owned-memory replay, not a performance claim
local callbacks={}
local base_mod_factory=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local value=base_mod_factory()
    value.events={on=function(name,fn,options)
        assert(name=='explosion'and options.id=='ledger_demolition_explosion')
        callbacks[#callbacks+1]=fn;return{state='active'}
    end}
    return value
end
local positions={}
api.unit_position=function(_,unit)return positions[unit]end
local UNKNOWN='FFFFFFFFFFFFFFFF'
local contexts={
    {'throwable/g4_gas/detonation','0416984F4922757B'},
    {'stratagem/orbital_gas_strike/shell_impact','05F3C83A91075766'},
    {'stratagem/agm17_gas_mortar_sentry/impact','299C0D3DFD2F0994'},
    {'support_weapon/s11_speargun/expiry','3828E2051AA9E897'},
    {'stratagem/md8_gas_mines/mine','A9982969137F3D77'},
    {'stratagem/eagle_gas_airstrike/payload_impact','DBB286AD7ED9DF96'},
}
local GAS=contexts[1][2]
local module=dofile(path);state=module.state
local now,actual=0,0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(options)
    options=options or{};next_id=next_id+1
    local row={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
        credit=options.credit==nil and 0x11 or options.credit,owner=0,
        damage_kind=options.kind or 2,element=options.element==nil and 5 or options.element,token=0}
    actors[#actors+1]=row
    if options.position~=false then positions[row.id*7]=options.position or{x=0,y=0,z=0}end
    tick(3);return row
end
local function explosion(name,options)
    options=options or{}
    assert(#callbacks>0,'actual addon must subscribe to the public explosion event')
    local pos=options.position
    if pos==nil then pos={x=0,y=0,z=0}end
    local event={name=name or contexts[1][1],local_player=options.local_player~=false,
        owner_id=42,position=pos~=false and pos or nil}
    -- The live regression has NO resource type in this event. The exact
    -- native explosion name must establish it through the reviewed catalogue.
    assert(event.source_type==nil and event.owner_type==nil)
    callbacks[#callbacks](event)
end
local function hit(row,health,owner)
    row.health,row.owner,row.token=health,owner or 900,row.token+1;tick(3)
end
local function die(row,credited)
    row.life=2
    if credited~=false then
        actual=actual+1;stats.totals[KILLS]=stats.totals[KILLS]+1
        local source=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=source
        source[KILLS]=source[KILLS]+1
    end
    hit(row,0,row.owner);tick(2)
    assert(state.kills==actual,'attribution must never manufacture a native kill')
end
local function latest()return assert(state.kill_source_notices.items[1],'latest source notice')end
local function no_gas(label)
    local notice=latest()
    for _,context in ipairs(contexts)do assert(notice.source_hash~=context[2],label..' must not claim gas source')end
end
local function expire()tick(65)end
tick(3)

for i,context in ipairs(contexts)do
    expire();local row=actor(i==1 and{kind=10,element=0}or nil);explosion(context[1]);tick(20)
    hit(row,70,900);die(row)
    local notice=latest()
    assert(notice.source_hash==context[2]and notice.damage_source.inferred
        and notice.attribution=='same_target_local_poison_status_area',
        'exact source-less public gas event must seed its own native poison kill: '..context[1]
            ..'; got '..tostring(notice.source_hash)..'/'..tostring(notice.attribution))
    assert(state.weapon_stats[context[2]].kills==1 and state.poison_kills==i and state.ribbons.poison==i,
        'all six actual gas resources reach weapon kills and poison ribbons exactly once')
end
assert(actual==6 and stats.sources[UNKNOWN][KILLS]==6,
    'six observed deaths retain the original native unknown source pool')

expire();local foreign=actor();explosion(nil,{local_player=false});tick(20);die(foreign)
no_gas('foreign public explosion')
expire();local wrong=actor();explosion('throwable/g4_gas/not-a-native-detonation');tick(20);die(wrong)
no_gas('different unreviewed explosion name')
expire();local missing_event_pos=actor();explosion(nil,{position=false});tick(20);die(missing_event_pos)
no_gas('missing public explosion position')
expire();local old=actor();explosion();tick(61);die(old)
no_gas('gas area older than six seconds')
expire();local far=actor({position={x=8,y=0,z=0}});explosion();tick(20);die(far)
no_gas('target outside the verified G4 seven-metre radius')
expire();local bullet=actor({kind=0,element=0});explosion();tick(20);die(bullet)
no_gas('a proven gunfire death near gas')
expire();local fire=actor({kind=2,element=1});explosion();tick(20);die(fire)
no_gas('a proven fire death near gas')
expire();local metadata=actor();explosion();metadata.owner=42;metadata.token=700;tick(3)
tick(61);die(metadata)
no_gas('metadata without actual HP loss cannot establish a gas anchor')
assert(state.weapon_stats[GAS].kills==1,
    'nearby unrelated, expired or unpositioned deaths do not inflate G4 kills')

expire();local missing_target_pos=actor({position=false});explosion();tick(20);die(missing_target_pos)
no_gas('missing native target position')
expire();local missing_credit=actor({credit=0});explosion();tick(20);hit(missing_credit,65,0);die(missing_credit)
assert(latest().source_hash==GAS and state.weapon_stats[GAS].kills==2,
    'a genuinely missing creditor still requires and consumes the real native local-kill quota')

expire();local enemy=actor({kind=4,element=0});enemy.owner=205;die(enemy)
assert(latest().damage_source.mechanism=='enemy_damage'and latest().source_hash==TYPE
    and latest().source_text:find('（友伤）',1,true),
    'a verified other-enemy owner is displayed as enemy friendly fire without a weapon guess')
expire();local self=actor({kind=4,element=0});owners[self.id]=TYPE;self.owner=self.id;die(self);owners[self.id]=nil
assert(latest().damage_source.mechanism=='self_explosion'and latest().source_hash==TYPE
    and latest().source_text:find('（自爆）',1,true),
    'the actual target as explosion owner is displayed as self-explosion')

expire();local other_credit=actor({credit=0x22});explosion();tick(20)
local before=ribbon_family(state.ribbons,'heavy');die(other_credit,false)
assert(ribbon_family(state.ribbons,'heavy')==before and #state.kill_source_notices.items==0,
    'explicit foreign final credit cannot borrow a local gas area or create a kill reward')
assert(actual==18 and state.kills==18 and ribbon_family(state.ribbons,'heavy')==18 and state.ribbons.heavy==0,
    'native totals, classifications and heavy ribbons remain one per native credited kill')
local sequence=state.sequence
local q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==18 and q.coverage.unknown_kills==9,
    'six gas families plus missing-credit G4 plus two enemy mechanisms leave nine genuine unknown kills; got '
        ..q.totals.kills..'/'..q.coverage.unknown_kills)
local poison=state.ribbons.poison
assert(poison>=7,'all seven known gas-source kills are represented in poison ribbons')
active=false;tick(3)
local raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons[UNKNOWN].kills==18 and raw.weapons[GAS].kills==2
    and raw.source_reassignments._unknown==9,
    'source correction preserves all raw native unknown kills and seven gas plus two enemy-mechanism anchors')
assert(saved.last_mission.kills==18 and saved.last_mission.ribbons.poison==poison)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==18 and q.coverage.unknown_kills==9
    and module.career_award_snapshot().totals.ribbons.poison==poison,
    'real saved history reload retains source corrections and poison ribbons without duplicate kills')
print('PASS built gas-status057: six exact source-less public gas callbacks, owned HP/cause attribution, poison/weapon/career/save-reload; foreign/name/position/radius/expiry/nonpoison/metadata negatives; missing-credit native quota, enemy friendly fire/self-explosion, no invented kills')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@built-gas-status-owned'))()
