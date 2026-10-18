-- Actual built addon: real decoder/classifier, mission session and accept sink,
-- owned Health/entity buffers, production resolver/trace/career/persistence.
-- Installation and FIFO transport are the only native bridge boundaries.
local addon,runtime,fixture,target_fixture,copy_fixture=
    assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local old_copy=read(copy_fixture)
local record_first=assert(old_copy:find('local function record(sequence,result)',1,true))
local record_last=assert(old_copy:find('local kinds=',record_first,true))
local record_helper=old_copy:sub(record_first,record_last-1)
local before=[=[
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
os.clock=function()return 0 end -- deterministic owned-memory replay; no performance claim
local function upvalue(fn,name)
    for i=1,255 do local key,value=debug.getupvalue(fn,i);if not key then break end;if key==name then return value end end
end
local PEER='0000000000000011'
local c={batches={},epoch=nil,consumer=nil,record_sequence=0,prepared=0,installed=0}
local function qword(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local function wire(s)return(s:gsub('..',function(pair)return string.char(tonumber(pair,16))end)):reverse()end
local explosion_callbacks={}
local base_mod_factory=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local value=base_mod_factory()
    value.events={on=function(name,fn,options)
        assert(name=='explosion' and options.id=='ledger_demolition_explosion')
        explosion_callbacks[#explosion_callbacks+1]=fn
        return{state='active'}
    end}
    return value
end
package.preload['hd2runtime/runtime/windows_ffi']=function()error('OWNED_WINDOWS_API_BOUNDARY',0)end
local handle={abi=1,stride=96,native_certified=true,addresses={},lifetime={functions_registered=true}}
rawset(_G,'HD2OwnedPackage',{prepare=function(_,profile)
    assert(profile.abi==1 and profile.record_bytes==96);c.prepared=c.prepared+1
    return handle
end})
rawset(_G,'HD2OwnedCopyController',{new=function(options)
    return{start=function(_,world,game)
            assert(game.state==3 and game.mission==false)
            local _,prepared=options.observer_factory({base=world.game,size=0x4744000})
            assert(prepared==handle);c.installed=c.installed+1;return{phase='running'}
        end,
        status=function()return{phase='running'}end,tick=function()return{phase='running'}end,
        observer_handle=function()return handle end}
end})
local transport={}
function transport.configure(given,peer,epoch,enabled)
    assert(given==handle and peer==PEER and enabled==true)
    c.epoch=epoch;return true
end
function transport.pause()return true end
function transport.resume()return true end
function transport.attach(given,options)
    assert(given==handle and options.peer==PEER and options.epoch==c.epoch)
    local decoder=options.decoder.new({peer=options.peer,epoch=options.epoch,
        accept=options.accept,observe_record=options.observe_record})
    local consumer={records=0,decoder=decoder,ready=true}
    function consumer:step(now)
        assert(self.ready)
        local raw=table.remove(c.batches,1)or''
        local ok,why=decoder:consume(raw,now,{abi=1,stride=96,connector_proven=true,
            epoch=c.epoch,count=#raw/96,dropped='0000000000000000'})
        if ok then self.records=self.records+#raw/96 end
        return ok,why
    end
    function consumer:detach()self.ready=false end
    c.consumer=consumer;return consumer
end
rawset(_G,'HD2OwnedTransport',transport)
local built=read(path)
assert(built:find("local VERSION = '0.4.65'",1,true))
local function replace_module(start,finish,replacement)
    local a=assert(built:find(start,1,true));local z=assert(built:find(finish,a,true))
    built=built:sub(1,a-1)..replacement..built:sub(z)
end
replace_module('-- Consume a lifetime-owned native bridge supplied by the verified installer.',
    '\n    end)()\n    hit_package=(function()',"return assert(rawget(_G,'HD2OwnedTransport'))")
replace_module('-- Prepare private native pages; never writes a game instruction or pauses a thread.',
    '\n    end)()\n    if NATIVE_HIT_PROFILE.demolition_diagnostic then',"return assert(rawget(_G,'HD2OwnedPackage'))")
local old='code=load_code_copy_controller(),package=hit_package'
local a,z=assert(built:find(old,1,true))
built=built:sub(1,a-1).."code=assert(rawget(_G,'HD2OwnedCopyController')),package=hit_package"..built:sub(z+1)
saved.ui_settings={auto_ui_probe=false,career_page_sync=false,career_ship_sync=false}
world.runtime={mode='live'}
api.game_state=function()return{state=active and 4 or 3,mission=active,host=true}end
api.unit_position=function()return{x=0,y=0,z=0}end
active=false
local module=assert(loadstring(built,'@actual-built-damage-ids-owned'))();state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
tick(26)
assert(c.installed==1 and c.prepared==1,'production host installs once at the owned native boundary')
active=true;tick(3)
assert(state.mission and c.consumer and c.epoch and module.native_hit_status().ready)
local function actor()
    next_id=next_id+1
    local row={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=0x11,owner=42,damage_kind=0}
    actors[#actors+1]=row;tick(3);return row
end
local UNKNOWN='FFFFFFFFFFFFFFFF'
local G6,R36='4CE9EAB785A79B7B','B6AFF2195568767F'
local function latest()return assert(state.kill_source_notices.items[1],'latest source notice')end
local function blast(source)
    assert(#explosion_callbacks>0,'real addon must register the public explosion callback')
    for _,callback in ipairs(explosion_callbacks)do
        callback({local_player=true,source_type=source,owner_id=42,
            position={x=0,y=0,z=0},name='owned-public-native-explosion'})
    end
end
]=]
local after=[=[
local function contact(a,damage_id,source,attribution_only,result)
    c.record_sequence=c.record_sequence+1
    local raw=record(c.record_sequence,result or 'penetration')
    local function put(at,value)raw=raw:sub(1,at)..value..raw:sub(at+#value+1)end
    put(44,b.encode(a.id,'u32'));put(48,b.encode(source or 42,'u32'));put(52,b.encode(42,'u32'))
    put(36,b.encode(damage_id or 202,'u32'))
    put(88,b.encode(0x1FF+(damage_id and 512 or 0)+(attribution_only and 1024 or 0),'u32'))
    c.batches[#c.batches+1]=raw
end
local function die(a,damage_id,source,only)
    contact(a,damage_id,source,only)
    a.health,a.life=0,2
    stats.totals[KILLS]=stats.totals[KILLS]+1
    local native_row=stats.sources[UNKNOWN]or{[KILLS]=0,[SHOTS]=0};stats.sources[UNKNOWN]=native_row
    native_row[KILLS]=native_row[KILLS]+1
    tick(3)
end
for i=1,20 do contact({id=9999},202,42,true,
    ({'ricochet','blocked','penetration','full_penetration'})[(i-1)%4+1])end
c.batches={table.concat(c.batches)};tick(2)
assert(#saved.native_hit_copy_evidence.records==16,
    'the actual diagnostic observer is already full before the tested kills; records='..#saved.native_hit_copy_evidence.records
    ..' accepted='..c.consumer.decoder.accepted..' unclassified='..c.consumer.decoder.unclassified
    ..' reason='..tostring(c.consumer.decoder.last_reason)..' observer='..tostring(c.consumer.decoder.observer_reason))
assert(state.kills==0 and state.ribbons.hit_penetration==0,
    'attribution-only records cannot create native kills or hit awards')
-- +36 carries 202, but it is accepted only when capture bit 512 names it.
local unique=actor();die(unique,202,42,false)
assert(latest().source_hash==AC and state.weapon_stats[AC].kills==1,
    'a genuine typed202 contact resolves an avatar-only AC8 kill in the actual addon')
assert(state.ribbons.hit_penetration==1,'ordinary typed contact still produces exactly one hit ribbon')
local initial=module.career_combat_query('weapons',{sequence=state.sequence})
print('OBS typed202/nativeUnknown/avatarRaw: native='..state.kills..' career='..initial.totals.kills
    ..' unknown='..initial.coverage.unknown_kills..' correctionNative='..tostring(state.source_reassignments[UNKNOWN])
    ..' correctionAvatar='..tostring(state.source_reassignments['4D1C334D294DFA97']))

local shared=actor();local hits=state.ribbons.hit_penetration;die(shared,189,42,true);tick(8)
assert(latest().source_hash~=AC and latest().source_hash~=G6 and latest().source_hash~=R36
    and latest().source_text=='未知来源',
    'the first shared189 fragment has no weapon without parent context; source='..tostring(latest().source_hash)
    ..' text='..tostring(latest().source_text))
assert(state.weapon_stats[AC].kills==1 and state.ribbons.hit_penetration==hits,
    'attribution-only512/1024 cannot add an extra hit ribbon')

-- Each target sees only its fragment, no previous AC8 primary hit; the final
-- Health kind is Gunfire0, so an Explosion4-only fallback cannot pass this.
for _,source in ipairs({AC,G6,R36})do
    tick(9)
    local victim=actor();blast(source);hits=state.ribbons.hit_penetration
    die(victim,189,42,true)
    assert(victim.damage_kind==0 and latest().source_hash==source,
        'first shared189 Gunfire fragment must use its actual local parent '..source)
    assert(state.ribbons.hit_penetration==hits,'shared fragment has no extra hit award')
end
assert(state.weapon_stats[AC].kills==2 and state.weapon_stats[G6].kills==1 and state.weapon_stats[R36].kills==1,
    'G6/R36 fragments must never become AC8')

tick(9)
local boundary=actor()
contact(boundary,nil,201,false);boundary.health,boundary.owner=75,201;tick(3)
contact(boundary,nil,203,false);boundary.health,boundary.owner=50,203;tick(3)
boundary.owner=0;die(boundary,nil,0,false);tick(8)
assert(latest().source_hash==AC and not latest().damage_source.barrier,
    'AC8 then unknown B then different unknown C stays attributed while real damage continues within1.5s')
assert(state.weapon_stats[AC].kills==3)

module.ui_settings:set('kill_source_enabled',false)
assert(module.game_hud.config.kill_source_enabled==false and #state.kill_source_notices.items==0)
local hidden=actor();die(hidden,202,42,true)
assert(state.weapon_stats[AC].kills==4 and ribbon_family(state.ribbons,'heavy')==7,
    'hidden source text keeps permanent weapon kills and ribbons running')
assert(#(module.game_hud:native_model(now,true,600).kill_source_notices.items or {})==0)
module.ui_settings:set('kill_source_enabled',true)
assert(#state.kill_source_notices.items==0,'reenabling cannot replay an older line')
local visible=actor();die(visible,202,42,true)
assert(latest().source_hash==AC and state.weapon_stats[AC].kills==5)

tick(9)
local old_abi=actor();die(old_abi,nil,42,false);tick(8)
assert(latest().source_hash~=AC and latest().source_text=='未知来源',
    'old records with unused +36 bytes cannot pretend to be typed202')
assert(state.weapon_stats[AC].kills==5)
local sequence=state.sequence
local q=module.career_combat_query('weapons',{sequence=sequence})
assert(state.kills==9 and q.totals.kills==9 and q.coverage.unknown_kills==2,
    'native unknown counter, resolved source observations and career total must represent the same9 kills; got '..q.totals.kills)
assert(ribbon_family(state.ribbons,'heavy')==9 and state.ribbons.heavy==0 and stats.sources[UNKNOWN][KILLS]==9,
    'source mapping never invents native kills or discards raw native totals')
assert(state.source_reassignments['4D1C334D294DFA97']==6,
    'target provenance keeps its actual raw avatar instead of fabricating a native counter identity')
assert(state.source_reassignments._unknown==1,
    'the owner0 continuous kill uses an anonymous correction budget without pretending to know its native hash')
active=false;tick(3)
assert(saved.last_mission.kills==9 and saved.last_mission.source_reassignments['4D1C334D294DFA97']==6
    and saved.last_mission.source_reassignments._unknown==1)
local raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons[UNKNOWN].kills==9 and raw.weapons[AC].kills==5,
    'native totals and reconstructed known sources are preserved separately')
rawset(_G,'HD2WarCostLedgerV1',nil)
module=assert(loadstring(built,'@actual-built-damage-ids-reloaded'))();state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==9 and q.coverage.unknown_kills==2,
    'source corrections and total kill count survive save/reload without duplication')
assert(ribbon_family(module.career_award_snapshot().totals.ribbons,'heavy')==9)
print('PASS built damage IDs: actual96B512/1024 decoder/session/accept, avatar202, first shared189 with public AC8/G6/R36 blasts, no-context unknown, continuous unknown B/C chain, toggle display-only, source reconciliation and save/reload')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..before..record_helper..after,
    '@built-damage-ids-end-to-end-owned'))()
