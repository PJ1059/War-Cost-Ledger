-- Production translator and catalogue: language routing, dynamic text, bounded reads and aliases.
local create=dofile(assert(arg[1]))
local catalog=dofile(assert(arg[2]))
local base=arg[1]:gsub('localization.lua$','')
local function chinese(text)
    -- UTF-8 CJK BMP prefixes; excludes arrows, currency symbols and punctuation.
    return type(text)=='string' and text:find('[\228-\233][\128-\191][\128-\191]')~=nil
end
local api=create(catalog)
assert(api.language=='en' and api:text('战果档案')=='Service Record')
for _,code in ipairs({'cn','tc','CN','TC','zh-CN','zh-TW','zh-Hans','zh-Hant'})do
    api:set_language(code);assert(api:text('战果档案')=='战果档案',code)
end
for _,code in ipairs({'us','gb','de','jp','fr','ru','ko','unknown'})do
    api:set_language(code);assert(api:text('战果档案')=='Service Record',code)
end
api:set_language(nil);assert(api.language=='en')
local n=0
for source,expected in pairs(catalog.exact)do
    assert(api:text(source)==expected,'exact catalogue entry changed: '..source)
    assert(not chinese(expected),'Chinese remains in English catalogue: '..source..' -> '..expected)
    n=n+1
end
for _,text in ipairs({'阿尔法指挥官 [R-36 爆裂铳]','本场爱国账单：146225.15 USD',
    '击杀1个吐酸泰坦。','生涯 KD · 24小时对比','查看全部战果  ·  战果 23  成就 6',
    '已记录 32 场 · 未记录 0 场','相关死亡记录 · 14 条','未知死因：2 次阵亡缺少明细。',
    '1 / 2 页','3 种来源'})do
    assert(not chinese(api:text(text)),'dynamic display text is untranslated: '..text..' -> '..api:text(text))
end
local original='自由战士自己的昵称'
api:set_language('cn');assert(api:text(original)==original and api:english('阿尔法指挥官')=='Alpha Commander')
local revision=api.revision
assert(not api:set_language('tc') and api.revision==revision,'Chinese script switch keeps same original UI')
local calls,code=0,'us'
local function reader(runtime)assert(runtime.tag=='language');calls=calls+1;return code end
assert(api:poll({tag='language'},0,reader) and api.language=='en')
for i=1,9 do assert(not api:poll({tag='language'},i/10,reader))end
assert(calls==1)
code='tc';assert(api:poll({tag='language'},1,reader) and api.language=='zh')
assert(not api:poll({tag='language'},2,function()error('unreadable language')end) and api.language=='zh')
assert(not api:poll({tag='language'},3,function()return nil end) and api.language=='zh')
assert(calls==2,'failed reads use the same poll interval')

-- The two sync menu descriptions are composed at runtime, not copied from
-- the static settings catalogue. Exercise every visible status with totals.
api:set_language('us')
local sync_options={store={get=function(_,_,default)return default end}}
local page_sync=dofile(base..'career-page-sync.lua')(sync_options)
local ship_sync=dofile(base..'career-ship-sync.lua')(sync_options)
for _,case in ipairs({{page_sync,{'disabled','reading_page','unavailable','waiting_page'}},
    {ship_sync,{'disabled','waiting_initialization','reading_counters','waiting_settlement','synced','expired','unavailable','waiting_ship'}}})do
    for _,status in ipairs(case[2])do
        case[1].status=status;case[1].last={kills=123,deaths=4,synced_at='2026-10-18 22:00'}
        local displayed=api:text(case[1]:description())
        assert(not chinese(displayed),'dynamic sync description is untranslated: '..displayed)
        assert(displayed:find('123',1,true) and displayed:find('30.75',1,true)
            and displayed:find('2026-10-18 22:00',1,true),'sync translation must preserve real totals and timestamp')
    end
end
api:set_language('cn')

-- Actual combat search must use English aliases even while display remains Chinese.
local records=dofile(base..'combat-records.lua')({clock=function()return 2000000 end,
    search_alias=function(value)return api:english(value)end,
    weapon_catalog={['B6AFF2195568767F']={id='eruptor',name='R-36 爆裂铳',category='primary'}},
    enemy_catalog={['F79CD8BB654397DF']={key='Alpha Commander',name_zh='阿尔法指挥官',faction='terminids',class='中型'}}})
assert(records:observe({sequence=1,status='ended',ended_at=1999999,kills=2,deaths=0,
    weapon_stats={['B6AFF2195568767F']={kills=2}},unit_kills={['Alpha Commander']={count=2}},
    kill_pairs={['F79CD8BB654397DF']={['B6AFF2195568767F']=2}}}))
assert(#records:query('weapons',{query='eruptor'}).rows==1)
assert(#records:query('weapons',{query='爆裂铳'}).rows==1)
assert(#records:query('enemies',{query='alpha commander'}).rows==1)
assert(#records:query('enemies',{query='阿尔法'}).rows==1)
assert(#records:query('enemies',{query='nonexistent source'}).rows==0)
assert(records:snapshot().entries[1].weapons['B6AFF2195568767F'].kills==2)
api:set_language('us')
local icons=dofile(base..'battle-hud.lua')({},function()return true end).icons
local model=dofile(base..'career-panel-model.lua')(icons,nil,dofile(base..'career-combat-panel-model.lua'),
    function(value)return api:text(value)end)
local function english_plan(plan)
    for _,group in ipairs({'header_texts','nav_controls','items','sections'})do
        for _,row in ipairs(plan[group]or{})do
            for _,field in ipairs({'text','name','condition'})do
                assert(not chinese(row[field]),'untranslated Career '..group..'.'..field..': '..tostring(row[field]))
            end
        end
    end
    assert(not chinese(plan.empty_text))
    if plan.tooltip then
        assert(not chinese(plan.tooltip.name)and not chinese(plan.tooltip.condition),'untranslated real award tooltip')
    end
end
for _,icon in ipairs(icons)do
    local totals={ribbons={},medals={}}
    totals[icon.kind=='ribbon'and'ribbons'or'medals'][icon.key]=1
    local context={page_visible=true,personal=true,width=600,height=1000,view='collection'}
    local plan=model:layout({totals=totals},context)
    english_plan(plan)
    if plan.items[1]then
        context.pointer={x=plan.items[1].x+1,y=plan.items[1].y+1}
        english_plan(model:layout({totals=totals},context))
    end
end
print('PASS real localization: '..n..' exact entries, dynamic labels, cn/tc vs all other languages, one-second polling, failure retention, English/Chinese combat search and original saved counts.')
