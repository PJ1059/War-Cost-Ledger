local create=dofile(assert(arg[1]))
local battle=dofile(assert(arg[2]))({ribbons={},mission_medals={}},function()return true end)
local api=create(battle.icons)
local function find(list,id)for _,v in ipairs(list)do if v.id==id then return v end end end
local function controls(plan,action)local out={};for _,v in ipairs(plan.nav_controls)do if v.action==action then out[#out+1]=v end end;return out end
local function bounded(plan)
    assert(#plan.nav_controls<=24 and #plan.header_texts<=32 and #plan.decorations<=48 and #plan.sections<=2 and #plan.items<=#battle.icons)
    for _,list in ipairs({plan.nav_controls,plan.header_texts,plan.decorations,plan.sections,plan.items})do
        local ids={}
        for _,v in ipairs(list)do
            assert(v.x>=0 and v.y>=0 and v.width>0 and v.height>0)
            assert(v.x+v.width<=plan.width+0.001 and v.y+v.height<=plan.height+0.001,'no drawing or hit target outside panel')
            if v.id then assert(not ids[v.id],'unique slots');ids[v.id]=true end
            assert(v.action~='delete_history' and v.id~='delete_history','deletion is no longer part of the UI')
            assert(v.id~='scroll_up' and v.id~='scroll_down' and v.action~='scroll_up' and v.action~='scroll_down',
                'history scrolling does not create retired up/down buttons')
            if v.text then assert(not v.text:find('\n',1,true))end
        end
    end
    if plan.view=='history'then
        assert(plan.scroll>=0 and plan.scroll<=plan.max_scroll)
        for _,v in ipairs(plan.items)do assert(v.y>=plan.list_top and v.y+v.height<=plan.list_bottom)end
        for _,v in ipairs(controls(plan,'toggle_match'))do
            assert(v.y>=plan.list_top and v.y+v.height<=plan.list_bottom)
            local suffix=v.id:match('history_row(%d+)');local line=assert(find(plan.header_texts,'history_stats'..suffix))
            assert(line.y==v.y+34 and line.y+line.height<=v.y+v.height,'whole-card target includes stats')
        end
    end
end
local records={totals={ribbons={air=8,recon=1,heavy=0},medals={democracy_harvester=2,fragrant=1}}}
local all={totals={ribbons={},medals={}}}
for _,icon in ipairs(battle.icons)do all.totals[icon.kind=='medal' and 'medals' or 'ribbons'][icon.key]=1 end
assert(not api:layout(records,{page_visible=false,personal=true}).shown)
assert(not api:layout(records,{page_visible=true,personal=false}).shown)
local c={page_visible=true,personal=true,width=420,height=747}
local view=api:layout(records,c);bounded(view)
assert(find(view.header_texts,'panel_title').text=='战果档案' and #view.items==4)
local crush_records={totals={ribbons={crush=154},medals={}}}
local crush_plan=api:layout(crush_records,c)
local crush_item=assert(find(crush_plan.items,'R12'))
assert(crush_item.name=='碾压'and crush_item.count==154
    and crush_item.condition=='载具车体来源每击杀1个敌方单位，获得1次。')
local stored_crush={totals={ribbons={crush=3},medals={}}}
c.legacy_crush={total=154,by_sequence={[31]=154}}
crush_plan=api:layout(stored_crush,c);crush_item=assert(find(crush_plan.items,'R12'))
assert(crush_item.count==157 and crush_item.condition:find('154',1,true))
assert(stored_crush.totals.ribbons.crush==3,'legacy display does not rewrite the lifetime accumulator')
c.legacy_crush=nil
local old_body_history={revision=1,entries={{sequence=31,status='ended',ended_at=100,kills=676,deaths=1,ribbons={},medals={}}}}
local body_context={page_visible=true,personal=true,width=420,height=747,view='history',history=old_body_history,
    expanded_sequence=31,legacy_crush={total=154,by_sequence={[31]=154}}}
local body_first=api:layout(stored_crush,body_context);local displayed_body
for scroll=0,math.ceil(body_first.max_scroll/16)do
    body_context.scroll=math.min(body_first.max_scroll,scroll*16)
    displayed_body=displayed_body or find(api:layout(stored_crush,body_context).items,'R12')
end
assert(displayed_body and displayed_body.count==154 and displayed_body.condition:find('旧局',1,true))
assert(old_body_history.entries[1].ribbons.crush==nil,'history source remains unchanged')
body_context.scroll=0;body_context.summary_expanded=true
assert(find(api:layout(stored_crush,body_context).items,'R12').count==154,'all-time summary matches the legacy history display')
body_context.period='24h';body_context.summary={periods={{key='24h',from_at=90,to_at=110,
    missions=1,kills=676,deaths=1,ribbons={},medals={}}}}
assert(find(api:layout(stored_crush,body_context).items,'R12').count==154,'time summaries include only matching legacy sequences')
body_context.summary.periods[1].from_at=101
assert(not find(api:layout(stored_crush,body_context).items,'R12'),'a different time window cannot inherit the legacy crush display')
assert(old_body_history.entries[1].ribbons.crush==nil and stored_crush.totals.ribbons.crush==3)
assert(find(view.nav_controls,'tab_collection').kind=='tab')
assert(find(view.decorations,'button_tab_collection').border,'visually bounded buttons')
local hovered=view.items[1];c.pointer={x=hovered.x+2,y=hovered.y+2}
assert(api:layout(records,c).tooltip.id==hovered.id)
c.pointer={x=421,y=746};assert(not api:layout(records,c).tooltip)
c.pointer=nil
-- Collection pagination keeps every one of the 21 real icons reachable.
for _,width in ipairs({120,240,360,420,600})do
    c.width=width;c.height=300;c.award_page=1
    local initial=api:layout(all,c);local seen={}
    for page=1,initial.award_page_count do
        c.award_page=page;view=api:layout(all,c);bounded(view)
        for _,v in ipairs(view.items)do assert(not seen[v.id]);seen[v.id]=true end
    end
    local n=0;for _ in pairs(seen)do n=n+1 end
    assert(n==#battle.icons,'all collection awards reached exactly once at width '..width)
end
local history={revision=1,limit=500,entries={
    {sequence=16,status='ended',kills=10,deaths=2,ribbons={air=1},medals={}},
    {sequence=18,status='interrupted',started_at=1234,kills=34,deaths=0,ribbons=all.totals.ribbons,medals=all.totals.medals,
        history_before={kills=100,deaths=2},history_after={kills=134,deaths=2}},
    {sequence=17,status='active',ribbons={},medals={}},
}}
local h={page_visible=true,personal=true,width=420,height=747,view='history',history=history,
    format_time=function()return '2026-10-13 20:00'end}
view=api:layout(records,h);bounded(view)
assert(view.history_count==3 and view.expanded_sequence==18 and view.list_top==366)
assert(history.entries[1].sequence==16 and history.entries[2].sequence==18,'source never sorted/mutated')
assert(find(view.nav_controls,'history_row1').sequence==18)
assert(find(view.nav_controls,'history_row1').text:sub(1,2)=='- ','expanded card has an ASCII collapse indicator')
assert(find(view.header_texts,'history_stats1').text=='击杀 34   阵亡 0   KD 34/0')
assert(find(view.header_texts,'match_delta').text=='+17.0000')
assert(find(view.header_texts,'career_current').text=='--','match KD is never misused as current career KD')
local button=find(view.nav_controls,'tab_history');h.pointer={x=button.x+3,y=button.y+3}
assert(find(api:layout(records,h).nav_controls,'tab_history').hovered)
h.pointer=nil
-- Expanding one match exposes two independent, scrollable source lanes. A
-- long roster must remain reachable without breaking fixed native slot pools.
local per_match={weapons={},enemies={}}
for index=1,40 do
    per_match.weapons[index]={id='weapon-'..index,name='本场武器 '..index,kills=index}
    per_match.enemies[index]={id='enemy-'..index,name='本场敌人 '..index,kills=index+100}
end
local calls={}
h.combat_query=function(lane,filters)
    assert(filters.sequence==18 and filters.period=='all','exact expanded match scope')
    calls[lane]=true;return {rows=per_match[lane]}
end
local roster=api:layout(records,h);local reached={}
for at=0,math.ceil(roster.max_scroll/10)do
    h.scroll=math.min(roster.max_scroll,at*10)
    local page=api:layout(records,h);bounded(page)
    for _,label in ipairs(page.header_texts)do
        if label.id:match('^match_weapons_name')or label.id:match('^match_enemies_name')then reached[label.text]=true end
    end
end
assert(calls.weapons and calls.enemies)
for index=1,40 do assert(reached['本场武器 '..index]and reached['本场敌人 '..index],'all match source rows reachable')end
h.combat_query=nil;h.scroll=0
-- The legacy raw fallback also merges hash-only rows and missing totals,
-- while useful names with unknown classifications remain visible.
local fallback_history={revision=99,entries={{sequence=7,status='ended',kills=100,deaths=2,ribbons={},medals={},
    weapon_stats={rifle={name='测试步枪',kills=3},named={name='已命名来源',category='unknown',kills=1},
        AAAAAAAAAAAAAAAA={name='AAAAAAAAAAAAAAAA',kills=6},BBBBBBBBBBBBBBBB={name='未知武器来源',kills=7}},
    unit_kills={bug={name_zh='测试敌人',count=5},CCCCCCCCCCCCCCCC={name='entity/v1/unresolved/CCCCCCCCCCCCCCCC',count=15}}}}}
local fallback_context={page_visible=true,personal=true,width=420,height=1200,view='history',period='all',
    history=fallback_history,expanded_sequence=7,scroll=0}
local fallback_view=api:layout(records,fallback_context)
local labels,values={},{}
for at=0,math.ceil(fallback_view.max_scroll/10)do
    fallback_context.scroll=math.min(fallback_view.max_scroll,at*10)
    local plan=api:layout(records,fallback_context);bounded(plan)
    for _,v in ipairs(plan.header_texts)do
        if v.id:match('^match_.+_name')then labels[v.id]=v.text end
        if v.id:match('^match_.+_kills')then values[v.id]=v.text end
    end
end
assert(labels.match_weapons_name1=='测试步枪'and labels.match_weapons_name2=='已命名来源')
assert(labels.match_weapons_name3=='未知'and values.match_weapons_kills3=='96'and not labels.match_weapons_name4)
assert(labels.match_enemies_name1=='测试敌人'and labels.match_enemies_name2=='未知'and values.match_enemies_kills2=='95')
assert(fallback_history.entries[1].weapon_stats.AAAAAAAAAAAAAAAA.kills==6,'display cannot rewrite saved identities')
-- A continuous scroll reaches all expanded awards without clipped hit targets.
for _,width in ipairs({120,240,420,600})do
    h.width=width;h.height=300;h.scroll=0
    local first=api:layout(records,h);local seen={}
    assert(first.total_items==#battle.icons and first.max_scroll>0)
    for step=0,math.ceil(first.max_scroll/8)do
        h.scroll=math.min(first.max_scroll,step*8);view=api:layout(records,h);bounded(view)
        for _,v in ipairs(view.items)do seen[v.id]=true;h.pointer={x=v.x+1,y=v.y+1};assert(api:layout(records,h).tooltip.id==v.id)end
        h.pointer=nil
    end
    local n=0;for _ in pairs(seen)do n=n+1 end;assert(n==#battle.icons,'every award fully reachable at width '..width)
end
h.width=420;h.height=747;h.scroll=0;h.expanded_sequence=false
view=api:layout(records,h);bounded(view);assert(#controls(view,'toggle_match')==3 and #view.items==0)
assert(find(view.nav_controls,'history_row1').text:sub(1,2)=='+ ','collapsed card has an ASCII expand indicator')
h.expanded_sequence=17;view=api:layout(records,h);bounded(view)
assert(find(view.header_texts,'history_stats2').text=='击杀 --   阵亡 --   KD --')
assert(find(view.header_texts,'match_delta').text=='基准未记录')
h.expanded_sequence=999;assert(api:layout(records,h).expanded_sequence==false)
history.entries[#history.entries+1]={sequence=19,status='ended',kills=4,deaths=1,ribbons={},medals={}}
history.revision=2;h.expanded_sequence=nil;assert(api:layout(records,h).expanded_sequence==19)
-- Dated interrupted records count in time filters, while active/undated/future
-- entries stay out. The independent career baseline is not fabricated.
local now=40*86400
local timed={revision=1,limit=500,entries={
    {sequence=1,status='ended',ended_at=now-86400,ribbons={air=2},medals={},kills=2,deaths=0},
    {sequence=2,status='ended',ended_at=now,ribbons={air=3},medals={fragrant=1},kills=3,deaths=1},
    {sequence=3,status='ended',ended_at=now-86401,ribbons={air=7},medals={},kills=7,deaths=2},
    {sequence=4,status='ended',ribbons={},medals={},kills=1,deaths=0},
    {sequence=5,status='interrupted',ended_at=now-10,ribbons={air=1},medals={},kills=1,deaths=0},
    {sequence=6,status='active',ended_at=now,ribbons={},medals={}},
    {sequence=7,status='ended',ended_at=now+1,ribbons={},medals={}},
    {sequence=8,status='ended',ended_at=now-7*86400-1,ribbons={},medals={},kills=0,deaths=0},
    {sequence=9,status='ended',ended_at=now-30*86400-1,ribbons={},medals={},kills=0,deaths=0},
}}
local summary={current={kills=200,deaths=2,kd=100},periods={}}
for _,p in ipairs({{'24h',86400,3},{'7d',7*86400,4},{'30d',30*86400,5}})do
    summary.periods[#summary.periods+1]={key=p[1],from_at=now-p[2],to_at=now,missions=p[3],kills=6,deaths=1,ribbons={air=6},medals={fragrant=1},
        career={current_kd=100,delta=50,baseline={at=now-p[2],kd=50},series={{at=now-p[2],kd=50},{at=now,kd=100}}}}
end
h.history=timed;h.summary=summary;h.expanded_sequence=false
for _,p in ipairs({{'24h',3},{'7d',4},{'30d',5}})do
    h.period=p[1];view=api:layout(records,h);bounded(view)
    assert(view.history_count==p[2] and find(view.nav_controls,'period_'..p[1]).active)
    assert(find(view.header_texts,'stat_value_1').text==tostring(p[2]))
    assert(find(view.header_texts,'stat_value_4').text=='6.00')
    assert(find(view.header_texts,'career_current').text=='100.00' and find(view.header_texts,'career_delta').text=='+50.0000')
    assert(view.sparkline and #view.sparkline.points==2,'only confirmed baseline produces a trend')
    assert(view.sparkline.interpolation=='monotone_cubic'and #view.sparkline.samples==97)
    assert(view.sparkline.samples[1].x==view.sparkline.points[1].x
        and view.sparkline.samples[1].y==view.sparkline.points[1].y
        and view.sparkline.samples[97].x==view.sparkline.points[2].x
        and view.sparkline.samples[97].y==view.sparkline.points[2].y,'smoothing preserves the real endpoints')
    local delta=find(view.header_texts,'career_delta')
    assert(delta.x+delta.width+8<=view.sparkline.x,'career delta text does not overlap the trend plot')
end
h.period='24h';h.summary_expanded=true
view=api:layout(records,h);bounded(view)
assert(view.modal and view.summary_expanded and view.expanded_sequence==false and #view.items==2)
assert(find(view.nav_controls,'close_summary').action=='toggle_summary')
assert(not find(view.nav_controls,'tab_history') and #controls(view,'toggle_match')==0,'modal prevents underlying interactions')
assert(view.items[2].count==6)
h.summary_expanded=false;summary.periods[1].career={current_kd=100}
view=api:layout(records,h);assert(not view.sparkline and find(view.header_texts,'career_delta').text=='暂无对比')
assert(find(view.header_texts,'period_baseline').text=='缺少该时点的生涯记录')
summary.periods[1].deaths=0;view=api:layout(records,h);assert(find(view.header_texts,'stat_value_4').text=='6/0')
summary.periods[1].deaths=nil;view=api:layout(records,h);assert(find(view.header_texts,'stat_value_4').text=='--')
h.summary=nil;view=api:layout(records,h);assert(view.history_count==0 and not find(view.nav_controls,'summary_toggle').enabled)
h.period='all';view=api:layout(records,h)
assert(view.history_count==9 and find(view.header_texts,'stat_value_2').text=='--','missing real counts poison the aggregate instead of becoming zero')
h.summary_expanded=true;view=api:layout(records,h);assert(view.modal and #view.items==2,'all-time awards also open')
h.summary_expanded=false
-- Fixed rendering slots never make any of 500 collapsed matches unreachable.
local many={revision=1,limit=500,entries={}}
for sequence=1,500 do many.entries[#many.entries+1]={sequence=sequence,status='ended',kills=sequence,deaths=0,ribbons={},medals={}}end
h.history=many;h.expanded_sequence=false
for _,height in ipairs({639,747,2160})do
    h.height=height;h.scroll=0
    local initial=api:layout(records,h);local seen={}
    for step=0,math.ceil(initial.max_scroll/32)do
        h.scroll=math.min(initial.max_scroll,step*32);view=api:layout(records,h);bounded(view)
        for _,v in ipairs(controls(view,'toggle_match'))do seen[v.sequence]=true end
    end
    local n=0;for _ in pairs(seen)do n=n+1 end
    assert(n==500,'500 matches reachable at height '..height)
    assert(view.capacity_full and view.scroll==view.max_scroll,'final history window reaches the lower bound')
    assert(find(view.decorations,'scroll_track') and find(view.decorations,'scroll_thumb'),
        'scrollbar remains available after removing up/down buttons')
    local help=assert(find(view.header_texts,'help'))
    assert(help.align==.5 and help.text=='滚轮浏览 · 悬停查看条件','centered wheel help remains visible')
end
-- Tiny/superwide panels still emit only complete local drawing/hit rectangles.
for _,width in ipairs({120,121,240,420,2048})do
    for _,height in ipairs({80,120,180,300,639,747,2160})do
        for _,which in ipairs({'collection','history'})do
            for _,period in ipairs({'all','24h'})do
                bounded(api:layout(all,{page_visible=true,personal=true,width=width,height=height,view=which,
                    history=history,period=period,summary=summary,summary_expanded=period=='24h',expanded_sequence=18,scroll=17}))
            end
        end
    end
end
print('PASS: native card/active-hover decorations; entire-card hit targets; collection and history catalogue awards reachable; no deletion controls; all/24h/7d/30d includes dated early-return records; independent career KD/baseline and bounded trend; modal blocks background; 500 rows reachable; 32 headers/24 controls/48 decorations with complete clipping.')
do
    local bill={version=1,total_cents=2000,entries={{key='ammo:ac8',name='AC-8 弹药',amount_cents=1600},
        {key='maintenance:las',name='激光维护折旧费',amount_cents=400}}}
    local history={revision=1,entries={{sequence=2,status='ended',kills=20,deaths=0,ribbons={},medals={},patriotic_bill=bill},
        {sequence=1,status='ended',kills=10,deaths=1,ribbons={},medals={}}}}
    local ctx={page_visible=true,personal=true,width=420,height=747,view='bill',billing_enabled=true,history=history,
        format_money=function(cents)return string.format('%.2f',cents/100*2),'USD'end}
    local p=api:layout(records,ctx);bounded(p)
    assert(find(p.nav_controls,'tab_bill')and find(p.header_texts,'bill_title').text=='累计爱国账单')
    assert(find(p.header_texts,'bill_total').text=='40.00 USD'and find(p.header_texts,'bill_coverage').text=='已记录 1 场 · 未记录 1 场')
    assert(find(p.header_texts,'bill_item_name_1').text=='AC-8 弹药')
    ctx.view='history';ctx.height=1200;ctx.expanded_sequence=2;p=api:layout(records,ctx);bounded(p)
    assert(find(p.header_texts,'match_bill_total').text=='40.00 USD','match details show that exact match bill')
    ctx.expanded_sequence=1;ctx.scroll=66;p=api:layout(records,ctx);bounded(p)
    assert(find(p.header_texts,'match_bill_total').text=='未记录','missing legacy bills are not displayed as zero')
    ctx.billing_enabled=false;p=api:layout(records,ctx)
    assert(not find(p.nav_controls,'tab_bill')and not find(p.header_texts,'match_bill_total'),'disabled billing hides both entry points')
    ctx.view='bill';p=api:layout(records,ctx);assert(p.view=='collection','disabled direct bill route falls back safely')
    ctx.billing_enabled=true;ctx.history={entries={}};p=api:layout(records,ctx);bounded(p)
    assert(find(p.header_texts,'bill_total').text=='未记录','no historical amount is invented')
    for _,width in ipairs({120,240,420,2048})do for _,height in ipairs({80,180,300,747,2160})do
        ctx.width,ctx.height=width,height;bounded(api:layout(records,ctx))
    end end
end
print('PASS patriotic bill view: real totals/items, currency conversion, legacy missing, conditional tabs and match details, bounded layout.')
do
    local points={{at=1,kd=76},{at=4,kd=76.1},{at=7,kd=76.55},{at=10,kd=76.3}}
    local ctx={page_visible=true,personal=true,width=420,height=747,view='history',expanded_sequence=false,
        summary={all={missions=0,ribbons={},medals={},career={baseline={at=1,kd=76},current_kd=76.3,series=points}}}}
    local chart=assert(api:layout(records,ctx).sparkline)
    local segment=1
    for _,sample in ipairs(chart.samples)do
        while segment<#chart.points-1 and sample.x>chart.points[segment+1].x do segment=segment+1 end
        local a,b=chart.points[segment],chart.points[segment+1]
        assert(sample.y>=math.min(a.y,b.y)-1e-8 and sample.y<=math.max(a.y,b.y)+1e-8,
            'smooth curve cannot overshoot its actual neighboring KD observations')
    end
    assert(chart.width==96 and chart.height==38,'the chart has space for a legible continuous line')
    for i=2,#chart.samples do assert(chart.samples[i].x-chart.samples[i-1].x<=1.000001,'sample at least once per logical pixel')end
    assert(points[2].kd==76.1 and points[3].kd==76.55 and #points==4,'chart interpolation leaves recorded KD samples untouched')
    ctx.view='collection';ctx.billing_enabled=true
    ctx.history={entries={{sequence=1,status='ended',patriotic_bill={version=1,total_cents=2500,entries={}}}}}
    ctx.summary=nil;ctx.format_money=function(cents)return string.format('%.2f',cents/100*2),'USD'end
    local p=api:layout(all,ctx);bounded(p)
    local entry=assert(find(p.nav_controls,'collection_bill'))
    assert(entry.text=='爱国账单：50.00 USD'and entry.action=='tab_bill')
    assert(entry.y+entry.height<=ctx.height-32,'bill entry is above the footer controls/hint')
    for page=1,p.award_page_count do
        ctx.award_page=page;p=api:layout(all,ctx);bounded(p)
        for _,award in ipairs(p.items)do assert(award.y+award.height<=entry.y-4,'ribbon pagination reserves the bill row')end
    end
    ctx.period='7d';ctx.summary={periods={{key='7d',from_at=1,to_at=10,
        patriotic_bill={version=1,total_cents=600,recorded_missions=1,missing_missions=0,entries={}}}}}
    p=api:layout(records,ctx)
    assert(find(p.nav_controls,'collection_bill').text=='爱国账单：12.00 USD','footer uses the selected period and current currency')
    ctx.billing_enabled=false;p=api:layout(records,ctx)
    assert(not find(p.nav_controls,'collection_bill'),'billing off hides the footer entry and releases its layout space')
    ctx.billing_enabled=true;ctx.period='all';ctx.summary=nil;ctx.history={entries={}}
    assert(find(api:layout(records,ctx).nav_controls,'collection_bill').text=='爱国账单：未记录','missing legacy amounts stay unrecorded')
end
print('PASS bounded shape-preserving KD interpolation and one-line period/currency bill entry above the footer, including paginated awards and billing off.')
do
    local records={totals={ribbons={heavy=7,giant=3,heavy_charger=2,giant_bile_titan=4},medals={tyranny_speed_bump=1}}}
    local ctx={page_visible=true,personal=true,width=420,height=747}
    local first=api:layout(records,ctx);local found={}
    for page=1,first.award_page_count do
        ctx.award_page=page
        for _,award in ipairs(api:layout(records,ctx).items)do found[award.id]=award end
    end
    assert(found.R02.count==7 and found.R03.count==3,'old class ribbons remain separate and unchanged')
    assert(found.T01.count==2 and found.G02.count==4,'specific unit ribbons stay distinct from their old class aggregate')
    assert(found.T01.condition=='击杀1个强袭虫。'and found.G02.condition=='击杀1个吐酸泰坦。')
    assert(found.M12.condition=='一场战斗中碾压击杀 100 个敌方单位。')
end
print('PASS unit-ribbon Career identities/conditions, preserved generic legacy totals, and M12 tooltip.')

do
    local ctx={page_visible=true,personal=true,width=520,height=1500,view='history',billing_enabled=true,
        history={entries={{sequence=64,status='ended',ended_at=100,kills=12,deaths=1,ribbons={air=2},medals={fragrant=1},
            weapon_stats={laser={name='激光武器',kills=12}},unit_kills={bug={name='虫子',kills=12}},
            patriotic_bill={version=1,total_cents=1250,entries={{key='ammo',name='测试弹药',amount_cents=1250}}}}}},
        format_money=function(cents)return string.format('%.2f',cents/100),'USD'end}
    local closed=api:layout(records,ctx);bounded(closed)
    local toggle=assert(find(closed.nav_controls,'match_bill'),'match bill is a clickable collapsed summary')
    assert(toggle.action=='toggle_match_bill'and toggle.sequence==64 and toggle.text:sub(1,2)=='+ ')
    assert(closed.expanded_bill_sequence==false and not find(closed.header_texts,'bill_item_name_1'))
    local total=assert(find(closed.header_texts,'match_bill_total'));assert(total.text=='12.50 USD')
    for _,award in ipairs(closed.items)do assert(award.y+award.height<=toggle.y,'match bill is below all match awards')end
    for _,header in ipairs(closed.header_texts)do
        if header.id:find('^combat_')then assert(header.y+header.height<=toggle.y,'match bill is below combat breakdowns')end
    end
    ctx.expanded_bill_sequence=64
    local open=api:layout(records,ctx);bounded(open)
    assert(find(open.nav_controls,'match_bill').text:sub(1,2)=='- 'and open.expanded_bill_sequence==64)
    assert(find(open.header_texts,'bill_item_name_1').text=='测试弹药')
    assert(open.content_height==closed.content_height+36,'only expanding the bill adds charge rows')
    ctx.expanded_bill_sequence=false;assert(not find(api:layout(records,ctx).header_texts,'bill_item_name_1'))
    ctx.billing_enabled=false;ctx.expanded_bill_sequence=64
    local hidden=api:layout(records,ctx)
    assert(not find(hidden.nav_controls,'match_bill')and not find(hidden.header_texts,'match_bill_total'))
    ctx.billing_enabled=true;ctx.expanded_sequence=false
    assert(not find(api:layout(records,ctx).nav_controls,'match_bill'),'closed match never exposes its bill')
    ctx.expanded_sequence=64;ctx.period='24h';ctx.summary={periods={{key='24h',from_at=0,to_at=120,
        missions=1,kills=12,deaths=1,ribbons={},medals={},career={partial=true,current_kd=12,delta=2,
            baseline={at=30,kd=10},series={{at=30,kd=10},{at=120,kd=12}}}}}}
    ctx.format_time=function(at)return '实际时间 '..at end
    local partial=api:layout(records,ctx)
    assert(partial.sparkline and find(partial.header_texts,'period_baseline').text:find('记录起点 实际时间 30',1,true))
end
print('PASS 0.4.64 collapsed match bill at the bottom with independent expansion and actual partial-period checkpoint labels.')
