local create=dofile(assert(arg[1]))
local create_combat=dofile(assert(arg[2]))
local english=true
local dictionary={
    ['战果档案']='Combat record',['战果']='Awards',['成就']='Achievements',
    ['近战杀敌']='Melee',['近战击杀 1 个敌方单位。']='Kill 1 enemy with melee.',
    ['测试武器中文名称非常非常长']='Weapon X',['本场武器与战备击杀']='Match weapon kills',
    ['本场击杀的敌人']='Match enemy kills',['未知']='Unknown',['未知死因']='Unknown cause',
    ['自身']='Self',['队友']='Squadmate',['搜索：']='Search: ',['未记录']='Not recorded',
    ['昵称未记录']='No name',['战备']='Stratagems',['轻型']='Light',
    ['全部分类']='All classes',['当时昵称']='Nickname',['会话标识']='Session ID',
    ['原生呼号']='Callsign',['伤害来源']='Source',['攻击单位']='Attacker',
    ['暂无战果记录']='No awards recorded',['暂无历史对局']='No matches recorded',
}
local function t(value)
    if not english then return value end
    if dictionary[value]then return dictionary[value]end
    return value
end
local function find(list,id)for _,v in ipairs(list)do if v.id==id then return v end end end
local icon={id='R05',key='melee',kind='ribbon',name='近战杀敌'}
local icons={icon}
local api=create(icons,nil,create_combat,t)
local records={totals={ribbons={melee=2},medals={}}}
local c={page_visible=true,personal=true,width=420,height=747,view='collection'}
local plan=api:layout(records,c)
assert(find(plan.header_texts,'panel_title').text=='Combat record')
assert(plan.items[1].name=='Melee'and plan.sections[1].name=='Awards')
c.pointer={x=plan.items[1].x+1,y=plan.items[1].y+1}
local tooltip=assert(api:layout(records,c).tooltip)
assert(tooltip.name=='Melee'and tooltip.condition=='Kill 1 enemy with melee.')
assert(icon.name=='近战杀敌'and records.totals.ribbons.melee==2,'localization must not mutate persisted award data')
c.pointer=nil
english=false
assert(api:layout(records,c).items[1].name=='近战杀敌','the same model follows language changes')
english=true
assert(api:layout({totals={ribbons={},medals={}}},c).empty_text=='No awards recorded')

-- A source translated into short English must survive even when its original
-- Chinese is far wider than the available row. Translate before clipping.
c.view='history';c.width=240;c.height=1200;c.expanded_sequence=1
c.history={revision=1,entries={{sequence=1,status='ended',kills=1,deaths=0,ribbons={},medals={},
    weapon_stats={test={name='测试武器中文名称非常非常长',kills=1}},unit_kills={}}}}
plan=api:layout(records,c)
local first=assert(find(plan.header_texts,'match_weapons_name1'))
assert(first.text=='Weapon X','source translation runs before text clipping')
assert(c.history.entries[1].weapon_stats.test.name=='测试武器中文名称非常非常长')

-- The translator must reach nested combat factories, but never translate a
-- player's nickname, callsign, session ID or search text that matches a label.
c.width=600;c.height=1100;c.view='deaths';c.scroll=0;c.period='all'
c.combat_state={mode='recent',query='未知',record_id='record-1',pages={},related_pages={}}
c.combat={rows={{id='record-1',match=1,category='player',actor='队友',weapon='测试武器中文名称非常非常长',
    player={name='自身',callsign='未知',peerId='战备'}}}}
plan=api:layout({},c)
assert(find(plan.header_texts,'panel_title').text=='Combat record','translator forwarded to combat factory')
assert(find(plan.nav_controls,'combat_search').text=='Search: 未知','search stays verbatim')
assert(find(plan.header_texts,'record_source_record-1').text=='Squadmate · 自身 · Weapon X','player name stays verbatim within a translated row')
local values={}
for _,v in ipairs(plan.header_texts)do
    if v.id:match('^fact_key_')then
        local serial=v.id:match('(%d+)$')
        values[v.text]=find(plan.header_texts,'fact_value_'..serial).text
    end
end
assert(values.Nickname=='自身'and values.Callsign=='未知'and values['Session ID']=='战备')
assert(values.Attacker=='Squadmate'and values.Source=='Weapon X')
assert(c.combat.rows[1].weapon=='测试武器中文名称非常非常长'and c.combat.rows[1].player.name=='自身')

c.view='enemies';c.combat={rows={}};c.combat_state={pages={},size='轻型',dropdown={filter='size'}}
plan=api:layout({},c)
local option
for _,v in ipairs(plan.dropdown.controls)do if v.value=='轻型'then option=v end end
-- Static decorated dropdown labels also pass through the translator. The root
-- translator handles surrounding punctuation; logical filter values stay raw.
assert(option and option.value=='轻型')
print('PASS career localization: nested model translation before clipping, awards/tooltips/empty states, live language change, unchanged identities and verbatim player/search fields.')
