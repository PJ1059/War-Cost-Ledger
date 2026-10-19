-- Actual built addon + owned native observer/source-stat fixture; no game/account access.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local cases={
    {id='G01',key='giant_dragonroach',unit='Dragonroach',hashes={'960B48A421A3FAAA'}},
    {id='G02',key='giant_bile_titan',unit='Bile Titan',hashes={'9E2E17F2CCCCAFDD'}},
    {id='G03',key='giant_spore_burst_bile_titan',unit='Spore Burst Bile Titan',hashes={'EF04CB84D097A497'}},
    {id='G04',key='giant_vox_engine',unit='Vox Engine',hashes={'BC242702FB46B7E7'}},
    {id='G05',key='giant_factory_strider',unit='Factory Strider',hashes={'D37E8D120D2836E3'}},
    {id='G06',key='giant_leviathan',unit='Leviathan',hashes={'F22D027B37BEF107'}},
    {id='T01',key='heavy_charger',unit='Charger',hashes={'1A7FCDFF98C664B0'}},
    {id='T02',key='heavy_charger_behemoth',unit='Charger Behemoth',hashes={'3AFF5FD7D5450B99','A05BD1EC67B3AC4C'}},
    {id='T03',key='heavy_spore_charger',unit='Spore Charger',hashes={'6B202392F4AB605E'}},
    {id='T04',key='heavy_rupture_charger',unit='Rupture Charger',hashes={'0AB7B92B131C228C'}},
    {id='T05',key='heavy_impaler',unit='Impaler',hashes={'AE57FCDB49F74E98','DCF8E74212FBEE3B'}},
    {id='T06',key='heavy_hulk_bruiser',unit='Hulk Bruiser',hashes={'137988CEA16458F7','32CDEADA234FB8DF'}},
    {id='T07',key='heavy_hulk_scorcher',unit='Hulk Scorcher',hashes={'3E0537D606438FEA','E44EC9F9B3FE1D2A'}},
    {id='T08',key='heavy_hulk_obliterator',unit='Hulk Obliterator',hashes={'1E66EE1F6F7FD00E'}},
    {id='T09',key='heavy_hulk_firebomber',unit='Hulk Firebomber',hashes={'6DAB2EADF5D8B692'}},
    {id='T10',key='heavy_annihilator_tank',unit='Annihilator Tank',hashes={'53D8919D7B8ABD67'}},
    {id='T11',key='heavy_barrager_tank',unit='Barrager Tank',hashes={'63DF3D07B7424588'}},
    {id='T12',key='heavy_shredder_tank',unit='Shredder Tank',hashes={'C6449FFD9EA3779C'}},
    {id='T13',key='heavy_war_strider',unit='War Strider',hashes={'EF570293245A17C2'}},
    {id='T14',key='heavy_veracitor',unit='Veracitor',hashes={'20B9C7734DAEAD65'}},
    {id='T15',key='heavy_gatekeeper',unit='Gatekeeper',hashes={'453FE22C634EB30F'}},
    {id='T16',key='heavy_fleshmob',unit='Fleshmob',hashes={'67DC32DCA4F02D33'}},
    {id='T17',key='heavy_crusher',unit='Crusher',hashes={'905809A4C28D8A45'}},
    {id='T18',key='heavy_harvester',unit='Harvester',hashes={'965EAE5A51ACDD4A','D63FCBFF0851B7AF'}},
}
saved.mission_sequence=7
saved.last_mission={sequence=7,status='ended',kills=10,deaths=0,ribbons={heavy=7,giant=3},mission_medals={}}
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind,life=0,credit=0}
    actors[#actors+1]=a;return a
end
local function kill(a,credit)
    a.life,a.credit=2,credit or 0x11
    if a.credit==0x11 then stats.totals[KILLS]=stats.totals[KILLS]+1 end
end
local function find(rows,id)for _,v in ipairs(rows)do if v.id==id then return v end end end
local function totals()return module.career_award_snapshot().totals end
local expected,total={},0
tick(3)
assert(state.sequence==8 and state.ribbons.heavy==0 and state.ribbons.giant==0)
assert(totals().ribbons.heavy==7 and totals().ribbons.giant==3,'old generic records remain unsplit')
for _,case in ipairs(cases)do
    assert(state.ribbons[case.key]==0,'the first unit kill needs an observed zero baseline: '..case.id)
    for _,hash in ipairs(case.hashes)do
        local a=actor(hash);tick(4);kill(a);tick(2)
        expected[case.key]=(expected[case.key]or 0)+1;total=total+1
        assert(state.ribbons[case.key]==expected[case.key],case.id..' alias did not earn its own variant')
        assert(state.unit_kills[case.unit].count==expected[case.key])
        assert(state.ribbons.heavy==0 and state.ribbons.giant==0,'one target cannot also earn a generic class ribbon')
        local popup=module.game_hud:native_model(now,true,600)
        local notice=assert(find(popup.awards.items,case.id),'first acquisition must reach actual notification path: '..case.id)
        assert(notice.count==1 and notice.total==expected[case.key])
        local rendered
        for _,glyph in ipairs(popup.layout.glyphs)do if glyph.id==case.id then rendered=true end end
        assert(rendered,'new unit texture/glyph did not reach native layout: '..case.id)
        assert(totals().ribbons[case.key]==expected[case.key])
        assert(module.mission_history_snapshot().entries[1].ribbons[case.key]==expected[case.key])
        tick(21)
        assert(state.ribbons[case.key]==expected[case.key],'retained corpses cannot repeat a ribbon')
    end
end
-- The full 4000-HP Impaler has no positive native score flag. Its exact SDK body
-- identity is eligible, but independent tentacles are never another enemy.
local impaler_before=state.ribbons.heavy_impaler
local tentacle=actor('672F7DA17F3BA34A');tick(4)
tentacle.life,tentacle.credit=2,0x11;tick(10)
assert(state.ribbons.heavy_impaler==impaler_before and state.classified_kills==total,
    'killing an independent Impaler tentacle must not earn T05')
local foreign_impaler=actor('DCF8E74212FBEE3B');tick(4);kill(foreign_impaler,0x22);tick(4)
assert(state.ribbons.heavy_impaler==impaler_before and state.classified_kills==total,
    'another player killing the exact Impaler body cannot earn T05')
local uncredited_impaler=actor('DCF8E74212FBEE3B');tick(4)
uncredited_impaler.life,uncredited_impaler.credit=2,0;tick(10)
assert(state.ribbons.heavy_impaler==impaler_before and state.classified_kills==total,
    'a missing-creditor Impaler without a matching native local kill cannot earn T05')
local quota_impaler=actor('DCF8E74212FBEE3B');tick(4)
quota_impaler.life,quota_impaler.credit=2,0;stats.totals[KILLS]=stats.totals[KILLS]+1;tick(4)
expected.heavy_impaler=expected.heavy_impaler+1;total=total+1
assert(state.ribbons.heavy_impaler==expected.heavy_impaler and state.classified_kills==total,
    'the full Impaler body retains the existing missing-creditor local native-kill gate')
-- Other players' final credit cannot be converted into a local unit ribbon.
peers=2
local foreign=actor('1A7FCDFF98C664B0');foreign.credit=0x11;tick(4)
local before=state.ribbons.heavy_charger
kill(foreign,0x22);tick(4)
assert(state.ribbons.heavy_charger==before and state.kills==total)
local local_target=actor('1A7FCDFF98C664B0');tick(4);kill(local_target);tick(2)
expected.heavy_charger=expected.heavy_charger+1;total=total+1
assert(state.ribbons.heavy_charger==expected.heavy_charger and state.kills==total,'local multiplayer deaths stay eligible')
local sum=0
for _,case in ipairs(cases)do sum=sum+state.ribbons[case.key]end
assert(sum==total and state.classified_kills==total,'unit and native/classified totals have no second class increment')
active=false;tick(2)
local history=module.mission_history_snapshot().entries
assert(history[1].sequence==8 and history[2].sequence==7)
assert(history[2].ribbons.heavy==7 and history[2].ribbons.giant==3)
for _,case in ipairs(cases)do
    assert(history[1].ribbons[case.key]==expected[case.key] and not history[2].ribbons[case.key])
    assert(module.career_period_summary().all.ribbons[case.key]==expected[case.key])
end
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state;tick(2)
for _,case in ipairs(cases)do assert(totals().ribbons[case.key]==expected[case.key],'reload replayed a unit ribbon')end
assert(#module.game_hud:native_model(now,true,600).awards.items==0)
-- M12 uses new local body-source growth, never old baseline or mounted weapons.
local TANK,CANNON,MG='16474112801385B6','1FA1F596769225C2','439F9E65C18567DA'
local function add(hash,n)
    local row=stats.sources[hash]
    if not row then row={[KILLS]=0,[SHOTS]=0};stats.sources[hash]=row end
    row[KILLS]=row[KILLS]+n;stats.totals[KILLS]=stats.totals[KILLS]+n
end
stats={totals={[SHOTS]=0,[KILLS]=154,[DEATHS]=0,[0xC7680A1B]=0},
    sources={[TANK]={[KILLS]=154,[SHOTS]=0}}}
actors={};peers=1;avatar=42;health_life=0;active=true;tick(3)
assert(state.sequence==9 and state.ribbons.crush==0 and not state.mission_medals.tyranny_speed_bump,
    'late native baseline above 100 and legacy display cannot award M12')
for _,case in ipairs(cases)do assert(state.ribbons[case.key]==0,'new mission resets the specific ribbon baseline')end
add(CANNON,100);add(MG,100);tick(2)
assert(state.ribbons.crush==0 and not state.mission_medals.tyranny_speed_bump,'cannon and MG are not parent-body crush kills')
peers=2
local other=actor('1A7FCDFF98C664B0');tick(4);kill(other,0x22);tick(3)
assert(state.ribbons.crush==0 and not state.mission_medals.tyranny_speed_bump,'foreign deaths cannot mint M12')
add(TANK,99);tick()
assert(state.ribbons.crush==99 and not state.mission_medals.tyranny_speed_bump)
stats.totals[DEATHS]=1;health_life=2;tick(2);avatar=43;health_life=0;tick(2)
add(TANK,1);tick()
assert(state.ribbons.crush==100 and state.mission_medals.tyranny_speed_bump==1,'100 mission-level crushes survive life reset')
assert(totals().medals.tyranny_speed_bump==1 and module.mission_history_snapshot().entries[1].medals.tyranny_speed_bump==1)
local medal=assert(find(module.game_hud:native_model(now,true,600).awards.items,'M12'))
assert(medal.count==1 and medal.total==1,'M12 reaches live acquisition popup')
add(TANK,1);tick(3)
assert(state.ribbons.crush==101 and state.mission_medals.tyranny_speed_bump==1,'101 does not repeat M12')
active=false;tick(2)
assert(saved.last_mission.mission_medals.tyranny_speed_bump==1)
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state;tick(2)
assert(totals().medals.tyranny_speed_bump==1 and #module.game_hud:native_model(now,true,600).awards.items==0)
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
actors={};peers=1;avatar=42;health_life=0;active=true;tick(3)
add(TANK,100);tick()
assert(state.sequence==10 and state.mission_medals.tyranny_speed_bump==1 and totals().medals.tyranny_speed_bump==2,
    'next mission can earn one more M12')
assert(totals().ribbons.heavy==7 and totals().ribbons.giant==3,'legacy generic totals remain unchanged after new missions')
print('PASS built 24 unit ribbons/29 exact hash aliases: local gates, first popup/glyph, no generic double count, full Impaler body/tentacle/foreign/no-quota distinction, career/match/period/reload; M12 baseline/99/100/101/life/new mission, cannon-MG/foreign exclusion and persistence.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@unit-ribbons-058-integration'))()

