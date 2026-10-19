-- Exercise the shipping retained model and its fallback draw with real packed
-- artwork. All state/geometry is synthetic; no native game APIs are involved.
local make_hud=dofile(assert(arg[1]))
local make_battle=dofile(assert(arg[2]))
local make_awards=dofile(assert(arg[3]))
local art=dofile(assert(arg[4]))
local base=arg[1]:gsub('game%-hud.lua$','')
local make_layout=dofile(base..'hud-layout.lua')
local make_charges=dofile(base..'charge-notifications.lua')
local make_currency=dofile(base..'currency.lua')
local currency=make_currency({rates={MC=1,SC=1,USD=1,CNY=7,EUR=.9,GBP=.8,SEK=10},mc_usd_rate=1})
local state={sequence=1,shots=1145,kills=240,deaths=0,history_kills=7596,history_deaths=100,
    total_cents=13056438,ribbons={},mission_medals={}}
local battle=make_battle(state,function()return true end,currency)
for _,icon in ipairs(battle.icons)do if icon.kind=='ribbon'then state.ribbons[icon.key]=0 end end
local awards=make_awards(state,battle.icons);awards:baseline(0)
local charges=make_charges()
local assets,handles={},{}
for _,asset in ipairs(art.images)do assets[asset.image_id]=asset end
for _,asset in ipairs(art.metrics or {})do assets[asset.image_id]=asset end
for _,asset in ipairs(art.indicators or {})do assets[asset.image_id]=asset end
assets[art.frame.image_id]=art.frame
local allocations=0
local hd2={resources={image=function(id)
    assert(assets[id] and not handles[id]);allocations=allocations+1
    handles[id]={id=id};return handles[id]
end}}
setmetatable(hd2,{__index=function(_,key)error('unexpected game read '..key)end})
local hud=make_hud(hd2,state,battle,awards,art,{battle=make_battle,awards=make_awards,
    layout=make_layout,charges=charges,create_charges=make_charges,currency=currency})
assert(allocations==#art.images+#(art.metrics or {})+#(art.indicators or {})+1)
local model=hud:native_model(0,true)
assert(model.stats.kd=='240/0' and model.stats.kd_text=='240/0［75.96↑］')
assert(model.layout.width==600 and model.height==109 and not model.map_open)
local function frame(w,h,now)
    local d={width=w,height=h,scale=math.min(w/1920,h/1080),texts={},images={},count_backs={}}
    function d:rect(x,y,width,height,colour,z)
        assert(colour=='#0E0E0EFF'and z==2,'only the count text has a small border-clearing backing')
        assert(width>0 and height>0 and height<40,'no HUD backing card')
        self.count_backs[#self.count_backs+1]={x=x,y=y,width=width,height=height}
    end
    function d:text(value,x,y,opts)
        assert(x>=0 and x<=w+.001 and y>=0 and y+opts.size<=h+.001,'text outside viewport')
        local text=tostring(value)
        assert(text~='SHOTS' and text~='KILLS' and text~='FIRE','old metric labels remain')
        self.texts[text]={x=x,y=y,size=opts.size,colour=opts.colour,align=opts.align}
    end
    function d:image(handle,x,y,width,height,opts)
        assert(handles[handle.id]==handle)
        assert(x>=0 and y>=0 and x+width<=w+.001 and y+height<=h+.001,'image quad outside viewport')
        self.images[#self.images+1]=handle.id
    end
    hud:draw(d,now,true);return d
end
local baseline=frame(1920,1080,0)
assert(baseline.texts['240/0[75.96'] and baseline.texts[']'] and baseline.texts['130564.38 SC'])
local function has_image(frame,id)
    for _,name in ipairs(frame.images)do if name==id then return true end end
    return false
end
assert(has_image(baseline,art.indicators[1].image_id) and not has_image(baseline,art.indicators[2].image_id))
state.deaths=4
local lower=frame(1920,1080,0)
assert(lower.texts['60.00[75.96'] and lower.texts[']'])
assert(has_image(lower,art.indicators[2].image_id) and not has_image(lower,art.indicators[1].image_id))
state.history_kills,state.history_deaths=6000,100
local equal=frame(1920,1080,0)
assert(equal.texts['60.00[60.00]'])
for _,asset in ipairs(art.indicators)do assert(not has_image(equal,asset.image_id),'tie leaves no arrow')end
state.deaths,state.history_kills,state.history_deaths=0,7596,100
state.ribbons.air=1;state.ribbons.hit_penetration=7;state.mission_medals.democracy_harvester=true
charges:emit('stim','治疗针',250000,.1)
hud:observe(.1)
model=hud:native_model(.1,true)
local plan=model.layout
assert(#plan.side.hits==1 and #plan.side.ribbons==1 and #plan.side.medals==1 and #plan.charges==1)
assert(plan.charges[1].text=='治疗针 -2500.00 SC')
local right=frame(1920,1080,.1)
assert(math.abs(right.texts.x7.y-(540+18*1.5))<.001,
    'missing native pickup keeps fallback notifications at the right midpoint')
hud:configure({hit_position='center',charge_position='center'})
local central=frame(1920,1080,.1)
assert(math.abs(central.texts.x7.x-(960+31*1.5/2))<.001
    and math.abs(central.texts.x7.y-(610+18*1.5))<.001,'central hit is below the reticle')
local fee=central.texts['治疗针 -2500.00 SC']
assert(fee.x==960 and math.abs(fee.y-(610+(29+6)*1.5))<.001 and fee.align=='center',
    'central fee is centered below the central hit')
assert(central.texts.x1.x==1920,'earned ribbons remain right when hit and fee move centrally')
hud:configure({hit_position='right',charge_position='right'})
for _,group in ipairs({'hits','ribbons','medals'})do
    local last=plan.side[group][#plan.side[group]]
    assert(last.x+last.width==plan.width and last.count_x==plan.width)
end
assert(plan.side.medals[1].name_lines[1]=='民主收割机')
local before=plan.height
state.ribbons.air=2;hud:observe(.2)
model=hud:native_model(.2,true)
assert(#model.layout.side.ribbons==1 and model.layout.side.ribbons[1].count==2 and model.height==before)
charges:emit('stim','治疗针',250000,1.8);hud:observe(1.8)
model=hud:native_model(2.3,true)
assert(#model.awards.items==3 and model.charges.items[1].amount_text=='-5000.00 SC','fee prolongs common batch')
hud:configure({currency='USD',ribbon_mode='always'})
model=hud:native_model(2.4,true)
assert(model.charges.items[1].text=='治疗针 -5000.00$')
assert(not model.map_open and #model.layout.collected.hits==0,'always ribbons must not force hit detail')
hud:set_map({mission=true,map_open=true,hud=0x12340000})
model=hud:native_model(2.4,true)
assert(#model.layout.collected.hits==1 and model.layout.collected.hits[1].count==7,'TAB sees active total')
for _,size in ipairs({{640,360},{1280,720},{1920,1080},{2560,1440},{3440,1440}})do frame(size[1],size[2],2.4)end
model=hud:native_model(3.8,true)
assert(#model.awards.items==0 and #model.charges.items==0 and model.layout.side_height==0)
assert(#model.layout.collected.ribbons==1 and #model.layout.collected.medals==1 and #model.layout.collected.hits==1)
local reservation=hud:reservation(true,true,3.8)
assert(reservation.native_height==(model.height+12)*hud.config.scale)
-- Idle render reuses native presentation and handles without allocations.
local d={width=1920,height=1080,scale=1,image=function()end,text=function()end}
hud:draw(d,4,true)
local stable=hud:native_model(4,true)
for _=1,1000 do hud:draw(d,4,true) end
collectgarbage('collect');collectgarbage('stop');local memory=collectgarbage('count')
for _=1,1000 do hud:draw(d,4,true);assert(hud:native_model(4,true)==stable)end
local growth=collectgarbage('count')-memory;collectgarbage('restart')
assert(growth<32,'idle renderer allocated '..growth..' KiB')
assert(allocations==#art.images+#(art.metrics or {})+#(art.indicators or {})+1,'resources rebuilt after startup')
local real_kills,real_bill=state.kills,state.total_cents
assert(hud:start_preview(4,10))
model=hud:native_model(10,true)
assert(model.testing and #model.layout.side.hits>0 and #model.layout.side.ribbons>0 and #model.layout.side.medals>0)
assert(#model.charges.items==1 and model.stats.kills=='648')
model=hud:native_model(12,true);assert(#model.charges.items==2)
model=hud:native_model(14,true);assert(#model.awards.items==0 and #model.charges.items==0)
assert(not hud:preview_active(18) and state.kills==real_kills and state.total_cents==real_bill)
hud:draw(d,18,false)
-- Source/target attribution notices form an independent central text area.
state.mission=true
local source_hash,target_hash='0123456789ABCDEF','FEDCBA9876543210'
state.kill_source_notices={revision=1,items={{expires_at=25,lines={
    '同期来源（对应未确认）：'..string.rep('长名称',12)..'#'..source_hash..' #'..target_hash,
    '确认击杀：测试敌人'}},{expires_at=30,lines={'推测：测试步枪 -> 测试敌人'}}}}
model=hud:native_model(20,true)
assert(#model.kill_source_notices.items==1 and #model.kill_source_notices.items[1].lines==1)
local shown_line=model.kill_source_notices.items[1].lines[1]
assert(shown_line:find(source_hash,1,true)and shown_line:find(target_hash,1,true)and shown_line:find('...',1,true),
    'long labels elide without losing either full unknown hash')
local source_frame=frame(1920,1080,20)
local source_text=assert(source_frame.texts[shown_line])
assert(source_text.align=='center'and source_text.size==16.5 and source_text.y>1080/2+70)
hud:configure({kill_source_enabled=false})
assert(not hud:native_model(20,true).kill_source_notices.items,'source display off must suppress cached model immediately')
local off_frame=frame(1920,1080,20)
assert(not off_frame.texts[shown_line] and off_frame.texts['240/0[75.96'],
    'source display off hides only attribution text, retaining combat metrics')
assert(state.kills==real_kills and state.total_cents==real_bill and state.kill_source_notices.items[1].lines[1],
    'source display toggle must not change real combat or raw latest snapshot')
hud:configure({kill_source_enabled=true})
assert(hud.config.kill_source_enabled==true)
local hidden={width=1920,height=1080,text=function()error('F8 hidden source notices still drew')end}
hud:draw(hidden,20,false)
local old_model=model
model=hud:native_model(31,true)
assert(#model.kill_source_notices.items==0,'fallback cached model removes source text after five seconds')
state.kill_source_notices={revision=2,items={{expires_at=40,lines={'未结束的来源提示'}}}}
assert(#hud:native_model(31,true).kill_source_notices.items==1)
state.mission=false
assert(not hud:native_model(31,true).kill_source_notices.items,'returning to ship hides stale source snapshots')
-- Small positive ammo costs remain visible after conversion; switching the old
-- display code selects SC and never rewrites any charge or total in the account.
hud:configure({currency='MC'})
charges:emit('single-round','单发弹药',1,40);hud:observe(40)
model=hud:native_model(40,true)
assert(hud.config.currency=='SC' and model.stats.currency=='SC')
assert(model.charges.items[1].amount_text=='-0.01 SC' and model.charges.items[1].text=='单发弹药 -0.01 SC')
assert(state.total_cents==real_bill and charges:snapshot(40,true).items[1].amount_cents==1)
hud:configure({currency='GBP'})
model=hud:native_model(40,true)
assert(model.charges.items[1].amount_text=='-<0.01£' and model.charges.items[1].text=='单发弹药 -<0.01£')
local tiny=frame(1920,1080,40)
assert(tiny.texts['单发弹药 -<0.01£'],'flat renderer must retain the less-than sign and negative charge prefix')
print('PASS: approved native/fallback layout, exact metrics/KD/currencies, common three rows and 2s charge batch, shared task height, five viewport sizes, isolated preview and idle retained draw.')
