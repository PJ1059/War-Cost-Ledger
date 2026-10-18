local create=dofile(assert(arg[1]))
local tests=0
local function check(name,fn)fn();tests=tests+1;print('PASS '..name)end
local function fixture()
    local state={sequence=1,mission=true,health_ready=true,life_light_kills=0,
        ribbons={},mission_medals={}}
    local api=create({state=state,award=function(key,repeated,amount)
        assert(repeated==true,'new repeated awards must not use a one-shot unlock gate')
        state.mission_medals[key]=(state.mission_medals[key] or 0)+(amount or 1)
    end})
    api:reset();api:baseline()
    return api,state
end
local function enemy(id,local_killer,same_life)
    return {entity_id=id,local_killer=local_killer~=false,same_life=same_life~=false}
end
local light={kill=true,class='轻型',faction='terminids'}
local giant={kill=true,class='巨型',faction='terminids'}
local bot={kill=true,class='重型',faction='automatons'}
check('100 200 and 300 light kills repeat in one life and new lives begin another block',function()
    local api,s=fixture()
    for i=1,99 do api:on_kill(enemy(i),light,i*.01)end
    assert(not s.mission_medals.democracy_harvester)
    api:on_kill(enemy(100),light,1)
    assert(s.mission_medals.democracy_harvester==1)
    for i=101,300 do api:on_kill(enemy(i),light,i*.01)end
    assert(s.mission_medals.democracy_harvester==3 and s.life_light_kills==300)
    api:reset_life()
    for i=301,399 do api:on_kill(enemy(i),light,i*.01)end
    assert(s.mission_medals.democracy_harvester==3 and s.life_light_kills==99)
    api:on_kill(enemy(400),light,4)
    assert(s.mission_medals.democracy_harvester==4)
end)
check('light kills require current continuous life readable health and local ownership',function()
    local api,s=fixture()
    for i=1,100 do api:on_kill(enemy(i,false),light,i)end
    for i=1,100 do api:on_kill(enemy(i,true,false),light,i)end
    s.health_ready=false
    for i=1,100 do api:on_kill(enemy(i),light,i)end
    assert(s.life_light_kills==0 and next(s.mission_medals)==nil)
end)
check('two distinct giant deaths within 750ms pair exactly once and subsequent pairs repeat',function()
    local api,s=fixture()
    api:on_kill(enemy(1),giant,1)
    api:on_kill(enemy(1),giant,1.25)
    assert(not s.mission_medals.double_giant,'a duplicate corpse is not a second giant')
    api:on_kill(enemy(2),giant,1.750)
    assert(s.mission_medals.double_giant==1,'750ms inclusive boundary')
    api:on_kill(enemy(3),giant,1.8)
    assert(s.mission_medals.double_giant==1,'paired giant cannot be reused')
    api:on_kill(enemy(4),giant,2)
    assert(s.mission_medals.double_giant==2)
    api:on_kill(enemy(4),giant,2.1)
    assert(s.mission_medals.double_giant==2)
end)
check('outside 750ms foreign heavy stale and cross-life deaths do not manufacture a pair',function()
    local api,s=fixture()
    api:on_kill(enemy(1),giant,1)
    api:on_kill(enemy(2),giant,1.751)
    assert(not s.mission_medals.double_giant)
    api:on_kill(enemy(3,false),giant,1.8)
    api:on_kill(enemy(4),bot,1.8)
    api:on_kill(enemy(5),giant,.5)
    assert(not s.mission_medals.double_giant)
    api:gap();api:on_kill(enemy(6),giant,2)
    assert(not s.mission_medals.double_giant,'a read gap cannot join the pair')
    api:reset_life();api:on_kill(enemy(8),giant,2.1)
    assert(not s.mission_medals.double_giant)
    s.mission=false;api:on_kill(enemy(7),giant,2.1)
    assert(not s.mission_medals.double_giant)
end)
check('native local counter growth reaches the 70-kill streak without enemy type coverage',function()
    local api,s=fixture()
    for i=1,70 do api:on_stats(1,i*.1)end
    assert(s.killstreak==70 and s.killstreak_peak==70 and s.ribbons.killstreak==14)
    assert(s.mission_medals.democracy_star==1)
    assert(not s.mission_medals.super_democracy_star and not s.mission_medals.supreme_democracy_star)
    api:on_stats(10,7.2);assert(s.mission_medals.super_democracy_star==1)
    api:on_stats(20,7.3);assert(s.mission_medals.supreme_democracy_star==1)
    api:on_stats(50,7.4)
    assert(s.mission_medals.democracy_star==1,'each tier awards once per continuous chain')
end)
check('five seconds inclusive continues and timeout or death starts a fresh chain',function()
    local api,s=fixture()
    api:on_stats(4,1);api:on_stats(1,6)
    assert(s.killstreak==5 and s.ribbons.killstreak==1)
    api:on_stats(4,11.001)
    assert(s.killstreak==4 and s.ribbons.killstreak==1,'new chain cannot inherit a leftover remainder')
    api:on_stats(46,11.1);assert(s.mission_medals.democracy_star==1)
    api:on_stats(50,16.101);assert(s.mission_medals.democracy_star==2)
    api:reset_life();api:on_stats(4,16.2)
    assert(s.killstreak==4 and s.ribbons.killstreak==21,'death resets only progress, never earned awards')
end)
check('30 50 and 60 observed robot kills use lower tiers while a lone robot does not classify unknown kills',function()
    local api,s=fixture()
    api:on_stats(30,1);api:on_kill(enemy(1),bot,1.05)
    assert(not s.mission_medals.democracy_star)
    for i=2,30 do api:on_kill(enemy(i),bot,1.05+i*.001)end
    assert(s.mission_medals.democracy_star==1 and not s.mission_medals.super_democracy_star)
    api:on_stats(20,1.1)
    for i=31,50 do api:on_kill(enemy(i),bot,1.1+i*.001)end
    assert(s.mission_medals.super_democracy_star==1)
    api:on_stats(10,1.2)
    for i=51,60 do api:on_kill(enemy(i),bot,1.2+i*.001)end
    assert(s.mission_medals.supreme_democracy_star==1)
end)
check('initial values read gaps and a death counter batch are baselines without replay',function()
    local api,s=fixture()
    api:gap();api:on_stats(70,1)
    assert(s.killstreak==0 and not s.ribbons.killstreak and next(s.mission_medals)==nil)
    api:on_stats(4,1.1);api:gap();api:on_stats(50,1.2)
    assert(s.killstreak==0 and next(s.mission_medals)==nil)
    api:on_stats(5,1.3);assert(s.ribbons.killstreak==1)
    s.sequence=2;api:on_stats(100,1.4)
    assert(s.killstreak==0 and s.ribbons.killstreak==1)
end)
check('robot proof survives one-poll native lag without awarding before native 30 50 and 60',function()
    local api,s=fixture()
    api:on_stats(29,1)
    for i=1,30 do api:on_kill(enemy(i),bot,1.01+i*.001)end
    assert(s.killstreak==29 and not s.mission_medals.democracy_star,'robot proof cannot bypass the native count')
    api:on_stats(1,1.1)
    assert(s.killstreak==30 and s.mission_medals.democracy_star==1,'the 30th kill must not require a 31st')
    api:on_stats(19,1.2)
    for i=31,50 do api:on_kill(enemy(i),bot,1.21+i*.001)end
    assert(s.killstreak==49 and not s.mission_medals.super_democracy_star)
    api:on_stats(1,1.3)
    assert(s.mission_medals.super_democracy_star==1)
    api:on_stats(9,1.4)
    for i=51,60 do api:on_kill(enemy(i),bot,1.41+i*.001)end
    assert(s.killstreak==59 and not s.mission_medals.supreme_democracy_star)
    api:on_stats(1,1.5)
    assert(s.mission_medals.supreme_democracy_star==1)
end)
check('unknown kills do not inherit low robot tiers from a handful of robot observations',function()
    local api,s=fixture()
    api:on_stats(30,1);api:on_kill(enemy(1),bot,1.1)
    assert(not s.mission_medals.democracy_star)
    api:on_stats(30,1.2)
    assert(s.mission_medals.democracy_star==1 and not s.mission_medals.super_democracy_star
        and not s.mission_medals.supreme_democracy_star)
    api:on_stats(20,1.3)
    assert(s.mission_medals.super_democracy_star==1 and not s.mission_medals.supreme_democracy_star)
    api:on_stats(20,1.4)
    assert(s.mission_medals.supreme_democracy_star==1)
end)
check('low AP award uses the same target source and native maximum attack AP on heavy or giant',function()
    local low,medium='968211C0033DCE64','A8CFFB316F0B5C5F'
    local awards={}
    local state={mission=true,sequence=1,ribbons={}}
    local api=create({state=state,traits={[low]={armor_penetration_max=2},[medium]={armor_penetration_max=4}},
        award=function(key)awards[key]=(awards[key]or 0)+1 end})
    api:reset()
    local function kill(id,kind,source,barrier)
        local event=enemy(id);event.damage_source={type=source,target_bound=true,barrier=barrier==true}
        api:on_kill(event,kind,id)
    end
    kill(1,bot,low);kill(2,giant,low);kill(3,light,low);kill(4,bot,medium)
    kill(5,bot,low,true);kill(6,bot,nil)
    assert(awards.level_not_problem==2,'never uses a global currently held gun or lower-AP secondary branch')
    local event=enemy(7,false);event.damage_source={type=low,target_bound=true,barrier=false}
    api:on_kill(event,bot,7);assert(awards.level_not_problem==2)
end)
check('final target fire and poison element counts deaths once; explicit non-elemental deaths do not inherit ignite',function()
    local flame,gas='4FB0F8C02F55C82B','88F61AFFF48AC8A4'
    local seen={fire=0,poison=0}
    local state={mission=true,sequence=1,ribbons={}}
    local api=create({state=state,traits={[flame]={fire=true},[gas]={poison=true}},award=function()end,
        on_elemental_kill=function(kind,event,proof)
            seen[kind]=seen[kind]+1;assert(event.entity_id and(proof==nil or proof.target_bound))
        end})
    api:reset()
    local function kill(id,source,element,barrier)
        local event=enemy(id)
        event.damage_source={type=source,target_bound=true,barrier=barrier==true}
        if element then event.damage_cause={kind=2,element=element,life=2,owned=true,current=true,source='native_health_extension'}end
        api:on_kill(event,light,id);return event
    end
    local fire=kill(1,nil,1,true);kill(2,nil,5,true)
    api:on_kill(fire,light,2.1)
    kill(3,flame,0);kill(4,gas,0)
    assert(seen.fire==1 and seen.poison==1,'physical direct kills are not burning or poison deaths')
    kill(5,flame,nil);kill(6,gas,nil)
    assert(seen.fire==2 and seen.poison==2,'known damaging source fallback retains approximate credit when element is unavailable')
    kill(7,flame,nil,true);kill(8,gas,nil,true)
    assert(seen.fire==2 and seen.poison==2,'a blocked source cannot be revived by source-family fallback')
    local no_kind=enemy(9)
    no_kind.damage_source={type=gas,target_bound=true,barrier=false}
    no_kind.damage_cause={kind=10,element=0,life=2,owned=true,current=true,source='native_health_extension'}
    api:on_kill(no_kind,light,9)
    assert(seen.poison==3,'native kind10 none must not suppress a known gas-source kill')
    local gunfire=enemy(10)
    gunfire.damage_source={type=gas,target_bound=true,barrier=false}
    gunfire.damage_cause={kind=0,element=0,life=2,owned=true,current=true,source='native_health_extension'}
    api:on_kill(gunfire,light,10)
    assert(seen.poison==3,'native kind0 is Gunfire and must not be mislabeled as unknown poison')
end)
check('one hundred current-mission vehicle-body kills award once across deaths and gaps, then reset next mission',function()
    local api,s=fixture()
    for _,n in ipairs({0,1,99})do assert(not api:on_crush(n))end
    assert(not s.mission_medals.tyranny_speed_bump)
    assert(api:on_crush(100)and s.mission_medals.tyranny_speed_bump==1)
    assert(not api:on_crush(101)and not api:on_crush(200))
    api:reset_life();api:gap();assert(not api:on_crush(300))
    assert(s.mission_medals.tyranny_speed_bump==1,'one life or read-gap transition cannot mint another per-match medal')
    s.sequence=2;s.mission_medals={}
    assert(not api:on_crush(99)and not s.mission_medals.tyranny_speed_bump)
    assert(api:on_crush(100)and s.mission_medals.tyranny_speed_bump==1,'a new mission can earn the medal again')
    s.sequence=3;s.mission_medals={};api:reset();s.mission=false
    assert(not api:on_crush(100))
    s.mission=true
    for _,n in ipairs({-1,99.5,0/0,math.huge})do assert(not api:on_crush(n))end
    assert(not s.mission_medals.tyranny_speed_bump,'ship state and invalid samples cannot create an acquisition')
end)
print('Combat achievement cases passed: '..tests)
