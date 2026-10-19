-- A locale revision rebuilds retained presentation even when source tables are unchanged.
local base=assert(arg[1]):gsub('game%-hud.lua$','')
local make_hud=dofile(arg[1])
local make_battle=dofile(base..'battle-hud.lua')
local make_awards=dofile(base..'award-notifications.lua')
local make_charges=dofile(base..'charge-notifications.lua')
local make_layout=dofile(base..'hud-layout.lua')
local currency=dofile(base..'currency.lua')({rates={MC=1,SC=1,USD=1,CNY=7,EUR=.9,GBP=.8,SEK=10},mc_usd_rate=1})
local state={sequence=1,mission=true,shots=10,kills=2,deaths=0,history_kills=100,history_deaths=1,
    total_cents=250000,ribbons={},mission_medals={}}
local battle=make_battle(state,function()return true end,currency)
local awards=make_awards(state,battle.icons);awards:baseline(0)
local charges=make_charges();charges:emit('stim','治疗针',250000,.1)
local raw_notice='阿尔法指挥官 [R-36 爆裂铳]'
state.kill_source_notices={revision=1,items={{expires_at=5,lines={raw_notice}}}}
local lang,revision='en',1
local long_source=string.rep('需要完整翻译的敌人名称',12)
local dictionary={['治疗针']='Stim',[raw_notice]='Alpha Commander [R-36 Eruptor]',
    [long_source]='Charger [AC-8 Autocannon]'}
local function t(value)return lang=='en' and (dictionary[value] or value) or value end
local layout_calls,layout_clears=0,0
local function layout_factory(localize)
    assert(localize==t,'HUD must pass the translator to its layout factory')
    layout_calls=layout_calls+1
    local layout=make_layout(localize)
    local clear=layout.clear
    layout.clear=function(self)layout_clears=layout_clears+1;return clear(self)end
    return layout
end
local hud=make_hud({},state,battle,awards,{images={},frame={}},{currency=currency,charges=charges,
    layout=layout_factory,localize=t,locale_revision=function()return revision end})
local en=hud:native_model(.1,true)
assert(en.charges.items[1].name=='Stim' and en.charges.items[1].text=='Stim -2500.00 SC')
assert(en.kill_source_notices.items[1].lines[1]=='Alpha Commander [R-36 Eruptor]')
assert(hud:native_model(.1,true)==en,'same language and source data should reuse retained presentation')
local clears=layout_clears
lang,revision='zh',2
local zh=hud:native_model(.1,true)
assert(zh~=en and zh.layout~=en.layout and layout_clears==clears+1)
assert(zh.charges.items[1].name=='治疗针' and zh.charges.items[1].text=='治疗针 -2500.00 SC')
assert(zh.kill_source_notices.items[1].lines[1]==raw_notice)
assert(zh.kill_source_notices.items[1].expires_at==5,'switching language must not restart notice lifetime')
assert(state.kill_source_notices.items[1].lines[1]==raw_notice and charges:snapshot(.1,true).items[1].name=='治疗针',
    'translation must not mutate real source records')
lang,revision='en',3
local again=hud:native_model(.1,true)
assert(again.charges.items[1].name=='Stim' and again.kill_source_notices.items[1].lines[1]==dictionary[raw_notice])
state.kill_source_notices={revision=2,items={{expires_at=5,lines={long_source}}}}
local long=hud:native_model(.2,true)
assert(long.kill_source_notices.items[1].lines[1]=='Charger [AC-8 Autocannon]',
    'translation must run before source-byte/width clipping')
assert(#hud:native_model(5,true).kill_source_notices.items==0)
assert(layout_calls==1 and state.kills==2 and state.total_cents==250000)
print('PASS: HUD locale revisions refresh fee names, kill notices and retained layout; source text/counters/timers stay intact; translation precedes notice clipping.')
