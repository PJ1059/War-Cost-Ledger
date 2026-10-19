-- Real presentation/award modules; synthetic geometry and combat totals only.
-- No native memory, game process, UI host or flat renderer is used here.
local make_feed=dofile(assert(arg[1],'native-hud-feed.lua required'))
local make_hud=dofile(assert(arg[2],'game-hud.lua required'))
local make_battle=dofile(assert(arg[3],'battle-hud.lua required'))
local make_awards=dofile(assert(arg[4],'award-notifications.lua required'))
local art=dofile(assert(arg[5],'built game-icons.lua required'))
local make_layout=dofile(arg[2]:gsub('game%-hud.lua$','hud-layout.lua'))
local total,failures=0,{}
local function near(a,b)assert(type(a)=='number' and math.abs(a-b)<.0001,tostring(a)..' differs from '..tostring(b))end
local function copy(x)if type(x)~='table' then return x end;local out={};for k,v in pairs(x)do out[k]=copy(v)end;return out end
local function equal(a,b)
    if type(a)~='table' or type(b)~='table' then return a==b end
    for k,v in pairs(a)do if not equal(v,b[k])then return false end end
    for k in pairs(b)do if a[k]==nil then return false end end
    return true
end
local function fixture(initial)
    local state={sequence=1,shots=2000,kills=12,deaths=0,fire_kills=6,
        history_kills=1200,history_deaths=30,total_cents=123456,ribbons={},mission_medals={}}
    local battle=make_battle(state,function()return true end)
    local ids,icons={},{}
    for _,asset in ipairs(art.images)do ids[asset.id]=true end
    for _,icon in ipairs(battle.icons)do if ids[icon.id]then
        icons[#icons+1]=icon
        if icon.kind=='ribbon'then state.ribbons[icon.key]=0 end
    end end
    if initial then initial(state,icons)end
    local awards=make_awards(state,icons);awards:baseline(0)
    local allocated=0
    local hd2={resources={image=function(id)allocated=allocated+1;return id end}}
    setmetatable(hd2,{__index=function(_,key)error('feed attempted game API: '..tostring(key))end})
    local hud=make_hud(hd2,state,battle,awards,art,{battle=make_battle,awards=make_awards,layout=make_layout})
    hud:set_map({hud=0x20000000,mission=true,map_open=false})
    local model_calls,real_model=0,hud.native_model
    function hud:native_model(now,visible,width)model_calls=model_calls+1;return real_model(self,now,visible,width)end
    local feed=make_feed(hud,state,battle,awards)
    local geometry={hud=0x20000000,context=0x800000,key='game:hud:context1',
        local_top=96,width=480,scale=1.2,selected=3}
    local f={state=state,battle=battle,awards=awards,hud=hud,feed=feed,geometry=geometry,icons=icons,
        allocations=function()return allocated end,model_calls=function()return model_calls end}
    function f:update(now,visible)self.feed:update(self.geometry,now,visible~=false);return self.feed:snapshot()end
    return f
end
local function check(name,fn)
    total=total+1;local ok,why=pcall(fn)
    if not ok then failures[#failures+1]=name..': '..tostring(why)end
end
check('source notices are retained at center below other feedback and cleared on ship or F8',function()
    local f=fixture();f.state.mission=true
    f.state.kill_source_notices={revision=1,items={{expires_at=5,lines={'同期来源（对应未确认）：#0123456789ABCDEF','确认击杀：测试敌人'}}}}
    local s=f:update(1)
    assert(s.kill_source_notices and #s.kill_source_notices.items==1)
    assert(s.kill_source_notices.items[1].lines[1]:find('0123456789ABCDEF',1,true))
    assert(f:update(1,false)==nil,'F8 discards the native source feed')
    s=f:update(1,true);assert(#s.kill_source_notices.items==1)
    s=f:update(6);assert(#s.kill_source_notices.items==0,'same retained source snapshot expires')
    f.state.mission=false;s=f:update(6)
    assert(not s.kill_source_notices.items,'ship view cannot revive an expired battle source')
end)
check('source display toggle is explicit in native feed and does not change combat totals',function()
    local f=fixture();f.state.mission=true
    f.state.kill_source_notices={revision=1,items={{expires_at=5,lines={'追猎虫 [AC-8 机炮]'}}}}
    local before=copy(f.state);local shown=f:update(1)
    assert(shown.kill_source_enabled==true and #shown.kill_source_notices.items==1)
    f.hud:configure({kill_source_enabled=false})
    local hidden=f:update(1.1)
    assert(hidden.kill_source_enabled==false and not hidden.kill_source_notices.items)
    assert(hidden.kills==shown.kills and hidden.bill==shown.bill and equal(f.state,before),
        'hiding source text must retain combat counts and account')
    -- The addon resets the pending notice on every setting change. Reflect
    -- that boundary here, then verify only a subsequent kill becomes visible.
    f.state.kill_source_notices={revision=2,items={}}
    f.hud:configure({kill_source_enabled=true})
    assert(#f:update(1.2).kill_source_notices.items==0)
    f.state.kill_source_notices={revision=3,items={{expires_at=7,lines={'食腐虫 [G-4 毒气手雷]'}}}}
    assert(f:update(2).kill_source_notices.items[1].lines[1]=='食腐虫 [G-4 毒气手雷]')
end)

check('native model and reservation work before any viewport draw',function()
    local f=fixture();local model=f.hud:native_model(0,true)
    assert(not model.collected and model.state==f.state and not model.testing)
    near(model.height,109)
    local r=f.hud:reservation(true,true,0)
    assert(r.native and r.visible and r.move_tasks and r.width==nil and r.height==nil)
    near(r.native_height,121)
    local s=f:update(0);near(s.block_height,109);assert(not s.map_open)
end)
check('feed formats real bill and finite current/history KD for native fonts',function()
    local f=fixture();local s=f:update(0)
    assert(s.shown and s.shots=='2000' and s.kills=='12' and s.fire=='6')
    assert(s.bill=='1234.56' and s.bill_text=='1234.56 SC' and s.currency=='SC' and s.kd=='12/0' and s.kd_text=='12/0［40.00↓］' and s.history_kd=='40.00')
    f.state.deaths=3;f.state.history_deaths=0;s=f:update(.1)
    assert(s.kd=='4.00' and s.history_kd=='1200.00')
end)
check('unavailable statistics remain unavailable rather than zero',function()
    local f=fixture();f.state.shots=nil;f.state.kills=nil;f.state.fire_kills=nil;f.state.deaths=nil
    f.state.history_kills=nil;local s=f:update(0)
    assert(s.shots=='--' and s.kills=='--' and s.fire=='--' and s.kd=='--' and s.history_kd=='--')
end)
check('feed anchors in native parent local coordinates and carries its identity',function()
    local f=fixture();local s=f:update(0)
    assert(s.hud==f.geometry.hud and s.key==f.geometry.key)
    near(s.position[1],-120);near(s.position[2],-96)
    near(s.scale[1],1);near(s.scale[2],1);near(s.size[1],600);near(s.size[2],109);near(s.opacity,.82)
    -- Parent world transform belongs to the host: do not multiply it into a
    -- local position/scale a second time.
    f.geometry.scale=2.4;f.geometry.width=620;f.geometry.local_top=42
    s=f:update(.1);near(s.position[1],20);near(s.position[2],-42);near(s.scale[1],1)
end)
check('configured scale top/right margin and opacity share native reservation units',function()
    local f=fixture();f.hud:configure({scale=1.4,right_margin=40,top_margin=72,task_gap=120,opacity=.6})
    local s=f:update(0);near(s.position[1],480-(40+600)*1.4)
    near(s.position[2],-(96+72*1.4));near(s.scale[1],1.4);near(s.opacity,.6)
    near(f.hud:reservation(true,true,0).native_height,(72+109+120)*1.4)
    f.hud:configure({move_tasks=false});local r=f.hud:reservation(true,true,.1)
    assert(r.native and not r.move_tasks);assert(f:update(.1).shown)
end)
check('map collection height reserves only visible collected ribbon rows',function()
    local f=fixture(function(state,icons)
        local n=0;for _,icon in ipairs(icons)do if icon.kind=='ribbon' and n<5 then
            state.ribbons[icon.key]=7;n=n+1
        end end
    end)
    local s=f:update(0);assert(not s.map_open and #s.ribbons==0);near(s.block_height,109)
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=true});s=f:update(.1)
    assert(s.map_open and #s.ribbons==5 and #s.side==0);near(s.block_height,109)
    near(f.hud:reservation(true,true,.1).native_height,109+12)
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=false});s=f:update(.2)
    assert(not s.map_open and #s.ribbons==0);near(s.block_height,109)
end)
check('F8 hidden geometry loss and explicit clear discard cached feed without model reads',function()
    local f=fixture();assert(f:update(0));local calls=f.model_calls()
    assert(f:update(.1,false)==nil and f.model_calls()==calls)
    assert(f:update(.2));calls=f.model_calls()
    f.feed:update(nil,.3,true);assert(f.feed:snapshot()==nil and f.model_calls()==calls)
    assert(f:update(.4));f.feed:clear();assert(f.feed:snapshot()==nil)
end)
check('fresh native HUD/context replaces identity and local geometry',function()
    local f=fixture();local first=f:update(0)
    f.geometry={hud=0x30000000,context=0x900000,key='game:hud:context2',local_top=10,width=500,scale=1.8,selected=4}
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=false});local s=f:update(.1)
    assert(s.hud==0x30000000 and s.key~=first.key);near(s.position[1],-100);near(s.position[2],-10)
end)
check('same-kind increases merge into one side item and fold after two idle seconds',function()
    local f=fixture();f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=true});f:update(0)
    f.state.ribbons.air=3;local s=f:update(1)
    assert(#s.side==1 and s.side[1].id=='R01' and s.side[1].count==3 and #s.ribbons==0)
    f.state.ribbons.air=5;s=f:update(1.5)
    assert(#s.side==1 and s.side[1].count==5 and #s.ribbons==0)
    s=f:update(3.499);assert(#s.side==1 and #s.ribbons==0)
    s=f:update(3.5);assert(#s.side==0 and #s.ribbons==1 and s.ribbons[1].count==5)
    for _,t in ipairs({3.6,4,10})do s=f:update(t);assert(#s.side==0 and #s.ribbons==1 and s.ribbons[1].count==5)end
    assert(f.state.ribbons.air==5,'display folding double counted or changed ledger totals')
end)
check('ribbon and medal share the two-second batch without replay on map or F8 toggles',function()
    local f=fixture();f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=true});f:update(0)
    f.state.ribbons.heavy=2;f:update(1)
    f.state.mission_medals.democracy_harvester=true;local s=f:update(1.5)
    assert(#s.side==2 and #s.medals==0 and #s.ribbons==0)
    f:update(2,false);s=f:update(3.499);assert(#s.side==2)
    s=f:update(3.5);assert(#s.side==0 and #s.medals==1 and #s.ribbons==1)
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=false});s=f:update(4)
    assert(#s.side==0 and #s.medals==1 and #s.ribbons==0)
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=true});s=f:update(4.1)
    assert(#s.side==0 and #s.medals==1 and #s.ribbons==1 and s.ribbons[1].count==2)
end)
check('missing pickup anchor falls back to the screen right midpoint, retaining top reservation',function()
    local f=fixture();f.geometry.available_height=900
    f.hud:set_map({hud=f.geometry.hud,mission=true,map_open=true})
    local initial=f:update(0);local reserved=f.hud:reservation(true,true,0).native_height
    f.state.ribbons.air=1;local s=f:update(1)
    near(-s.position[2]+s.side_top*s.scale[2],450)
    assert(s.popup_shift>0 and #s.side==1 and #s.ribbons==0)
    near(s.position[1],initial.position[1]);near(s.position[2],initial.position[2])
    near(f.hud:reservation(true,true,1).native_height,reserved)
    f.hud:configure({scale=1.4});s=f:update(1.1)
    near(-s.position[2]+s.side_top*s.scale[2],450)
    assert(s.side_top+s.layout.side_height<=s.available_height-16)
    s=f:update(3);assert(#s.side==0 and #s.ribbons==1)
    near(s.layout.collected.ribbons[1].icon_y,0)
    near(s.size[2],s.layout.top_height)
end)
check('right fallback uses the root center even when the native parent is inset',function()
    local f=fixture();f.geometry.available_height=900;f.geometry.center_y=420
    f:update(0);f.state.ribbons.heavy=1
    for _,scale in ipairs({.75,1,1.4})do
        f.hud:configure({scale=scale,right_margin=36,top_margin=24})
        local s=f:update(1)
        near(-s.position[2]+s.side_top*s.scale[2],420)
    end
end)
check('popups use the native pickup position when free and fit above it when occupied',function()
    local f=fixture();f.geometry.available_height=900
    f.geometry.pickup={right=456,top=480,occupied=false}
    f:update(0);f.state.ribbons.heavy=1;local s=f:update(1)
    near(s.popup_scale,1.5)
    near(-s.position[2]+s.side_top*s.scale[2],480)
    near(s.position[1]+(s.layout.width+s.popup_shift_x)*s.scale[1],456)
    local reserved=f.hud:reservation(true,true,1).native_height
    f.geometry.pickup.occupied=true;s=f:update(1.1)
    near(-s.position[2]+(s.side_top+s.side_height+12)*s.scale[2],480)
    assert(s.pickup_occupied and s.side_height==s.layout.side_height*1.5)
    near(f.hud:reservation(true,true,1.1).native_height,reserved)
    f.hud:configure({scale=1.4,right_margin=40,top_margin=24});s=f:update(1.2)
    near(s.position[1]+(s.layout.width+s.popup_shift_x)*s.scale[1],456)
    near(-s.position[2]+(s.side_top+s.side_height+12)*s.scale[2],480)
end)
check('central anchor keeps screen center and follows configured notice scale',function()
    local f=fixture();f.geometry.center_x=240;f.geometry.center_y=450
    for _,scale in ipairs({.75,1,1.4})do
        f.hud:configure({scale=scale,hit_position='center',charge_position='center'})
        local s=f:update(scale)
        near(s.position[1]+s.center_position[1]*scale,240)
        near(-s.position[2]-s.center_position[2]*scale,450+70*scale)
    end
end)
check('pickup notices stay inside the root bottom when its right parent is inset',function()
    local f=fixture();f.geometry.available_height=900;f.geometry.center_y=420
    f.geometry.pickup={right=456,top=890,occupied=false}
    f:update(0);f.state.ribbons.heavy=1
    for _,scale in ipairs({.75,1,1.4})do
        f.hud:configure({scale=scale,right_margin=40,top_margin=24})
        local s=f:update(1)
        local bottom=-s.position[2]+(s.side_top+s.side_height)*s.scale[2]
        near(bottom+16*scale,870)
        assert(bottom<f.geometry.pickup.top,'offscreen pickup anchor is bounded by the root viewport')
    end
end)
check('feed snapshots allocate no images and do not refresh observed data on read',function()
    local f=fixture();local s=f:update(0);local allocations,calls=f.allocations(),f.model_calls()
    f.state.kills=20
    for _=1,100 do assert(f.feed:snapshot()==s and f.feed:snapshot().kills=='12')end
    assert(f.allocations()==allocations and f.model_calls()==calls)
    s=f:update(.1);assert(s.kills=='20' and f.allocations()==allocations)
end)
check('isolated eight-second preview never mutates real combat state',function()
    local f=fixture();local before=copy(f.state)
    assert(f.hud:start_preview(4,0));local s=f:update(0)
    assert(s.kills=='648' and s.shots=='56222' and s.bill=='72431285.00' and s.currency=='SC' and s.map_open)
    f:update(1);f:update(2);s=f:update(4);assert(#s.side==0)
    assert(equal(f.state,before),'native preview changed real ledger totals')
    s=f:update(8);assert(s.kills=='12' and s.shots=='2000' and s.bill=='1234.56' and not s.map_open)
    assert(equal(f.state,before))
end)

assert(#failures==0,table.concat(failures,'\n'))
print('Native HUD feed: '..total..' tests passed; real presentation/award modules, local geometry/cache and two-second fold; no game reads or live FPS claim.')
