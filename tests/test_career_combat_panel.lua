local model=dofile(assert(arg[1]))({},nil,dofile(assert(arg[2])))
local c={page_visible=true,personal=true,width=420,height=747,view='deaths',period='all',
    format_time=function()return '10-15 21:10'end,combat_state={mode='rank',pages={},related_pages={}},combat={rows={}}}
local function bounded(p)
    assert(#p.header_texts<=48 and #p.nav_controls<=32 and #p.decorations<=48 and #p.items==0)
    for _,list in ipairs({p.header_texts,p.nav_controls,p.decorations})do
        local ids={};for _,v in ipairs(list)do
            assert(v.x>=0 and v.y>=0 and v.width>0 and v.height>0 and v.x+v.width<=p.width+.01 and v.y+v.height<=p.height+.01)
            assert(not ids[v.id]);ids[v.id]=true
            assert(v.action~='delete_history' and v.action~='scroll_up' and v.action~='scroll_down')
        end
    end
end
local function layout()local p=model:layout({},c);bounded(p);return p end
local function find(p,action)for _,v in ipairs(p.nav_controls)do if v.action==action then return v end end end
local records={}
for i=1,12000 do records[i]={id='event-'..i,at=100000-i,match=5000-i,category='player',actor='队友',
    weapon='GL-21 榴弹发射器',attack='爆炸',player={name='演示玩家',peerId='FFFFFFFFFFFFFFFF',personaIndex=0}}end
records[12000].evidence={death_observed='dead_state',source_channel='native_health_last_owner_creditor',source_reason='CONFLICTING_SOURCE_EVIDENCE'}
c.combat.rows={}
for i=1,15 do c.combat.rows[i]={id='cause-'..i,name='来源 '..i,count=12000,records=records}end
local p=layout();assert(p.constructed_blocks==10 and p.source_rows==15 and p.combat_last_page==2)
assert(not find(p,'combat_related_page'),'closed groups never construct records or their pager')
c.combat_state.pages.rank=2;p=layout();assert(p.constructed_blocks==5 and p.combat_page==2)
local first=find(p,'combat_open');assert(first and first.text:find('11',1,true),'rank numbering crosses page boundary')
c.combat_state.pages.rank=1;c.combat_state.open_id='cause-1';p=layout()
assert(p.related_last==2400 and p.constructed_blocks==17,'one related heading, five rows, one pager only')
c.combat_state.related_pages['cause-1']=2400;c.combat_state.record_id='event-12000';p=layout()
assert(p.constructed_blocks<40,'one record facts only despite 12000 records')
local seen={}
for y=0,p.max_scroll+52,26 do c.scroll=math.min(y,p.max_scroll);local q=layout();for _,v in ipairs(q.header_texts)do seen[v.text]=true end end
assert(seen['FFFFFFFFFFFFFFFF'] and seen['0'],'full session ID and zero persona slot survive layout')
assert(seen['生命状态进入死亡']and seen['生命记录中的最后攻击方']and seen['来源线索冲突'],'structured evidence remains visible as short Chinese facts')
assert(not seen['事件编号']and not seen['event-12000'],'internal event identity is not shown in player-facing death facts')
assert(records[12000].id=='event-12000','hidden event identity stays available for record selection and deduplication')
local permanent=false;for value in pairs(seen)do if value:find('未取得',1,true)then permanent=true end end;assert(permanent)
c.scroll=0;c.combat_state.mode='recent';c.combat.rows=records;c.combat_state.pages.recent=1200;c.combat_state.record_id=nil
p=layout();assert(p.constructed_blocks==10 and p.combat_page==1200)
c.combat.rows={records[1]};p=layout();assert(p.combat_page==1 and p.combat_last_page==1 and not find(p,'combat_page'))
for _,view in ipairs({'weapons','enemies'})do
    c.view=view;c.combat_state.open_id='item';c.combat_state.query='机炮'
    c.combat={available_weapon_types={'机炮','霰弹枪'},totals={kills=8,known_kinds=1,linked_kills=0},rows={{id='item',name='示例',kills=8,
        detail_rows={{id='unknown',name='未知关联',kills=8}}}}}
    p=layout();assert(find(p,'combat_dropdown') and find(p,'search_focus'))
    if view=='weapons'then
        local found=false
        for _,v in ipairs(p.header_texts)do if v.id=='total_label_2'then assert(v.text=='种武器/战备');found=true end end
        assert(found,'weapon summary uses the native font supported ASCII slash')
    end
    for _,control in ipairs(p.nav_controls)do if control.action=='combat_association'then assert(not control.enabled)end end
end

-- Query supplies known rows followed by one unknown group, even when its
-- count is largest. Known identity and unknown classification are distinct.
for _,view in ipairs({'weapons','enemies'})do
    c.view=view;c.scroll=0
    c.combat_state={pages={},related_pages={},open_id='named'}
    c.combat={totals={kills=107,known_kinds=1},rows={
        {id='named',name='有名称的来源',known=true,category='unknown',kills=8,detail_rows={
            {id='raw-a',name='未知武器来源',known=false,kills=4},
            {id='named-detail',name='有名称的关联',known=true,category='unknown',kills=1},
            {id='raw-b',name='不可用类型',known=false,kills=3}}},
        {id='unknown',name='旧占位名称',known=false,kills=99}}}
    p=layout()
    local ranking,linked={},{}
    for _,v in ipairs(p.nav_controls)do
        if v.action=='combat_open'then ranking[#ranking+1]=v
        elseif v.action=='combat_association'then linked[#linked+1]=v end
    end
    assert(#ranking==2 and ranking[1].text:find('有名称的来源',1,true)
        and ranking[2].text:find('未知  99',1,true),'query bottom grouping and normalized rank labels must survive UI')
    assert(#linked==2 and linked[1].enabled and linked[1].text:find('有名称的关联',1,true))
    assert(linked[2].value=='unknown'and not linked[2].enabled and linked[2].text=='未知  7',
        'unknown association types collapse to one disabled bottom row')
end

local unknown_event={id='real-unknown',at=99,match=6,category='unknown',actor='未知来源'}
local unknown_group={id='unknown',name='未知死因',known=false,category='unknown',count=8,
    records={unknown_event},unrecorded_count=7}
c.view='deaths';c.scroll=0
c.combat_state={mode='rank',open_id='unknown',pages={},related_pages={}}
c.combat={rows={{id='fire',name='火焰',known=true,count=1,records={}},unknown_group}}
p=layout()
local real_rows,missing_note=0,false
for _,v in ipairs(p.nav_controls)do
    if v.action=='combat_record'then assert(v.value=='real-unknown');real_rows=real_rows+1 end
end
for _,v in ipairs(p.header_texts)do
    if v.id=='unrecorded_summary'then assert(v.text=='未知死因：7 次阵亡缺少明细。');missing_note=true end
    if v.id=='help'then assert(not v.text:find('单独保留',1,true))end
end
assert(real_rows==1 and missing_note,'unknown rank expands real evidence plus a count-only missing summary')

unknown_group.unknown_group=true
c.combat_state.mode='recent'
c.combat={rows={
    {id='recent-new',at=110,match=8,category='enemy',actor='武斗虫'},
    {id='recent-old',at=100,match=7,category='player',actor='队友',player={name='原队友昵称',peerId='1122334455667788'}},
    unknown_group}}
p=layout()
local recent_order,group_control={},nil
for _,v in ipairs(p.nav_controls)do
    if v.action=='combat_record'then recent_order[#recent_order+1]=v.value
    elseif v.action=='combat_open'and v.value=='unknown'then group_control=v end
end
assert(recent_order[1]=='recent-new'and recent_order[2]=='recent-old'and recent_order[3]=='real-unknown'
    and #recent_order==3,'recent mode preserves known chronology and only builds real unknown child events')
assert(group_control and group_control.text=='- 未知死因  8','recent unknown aggregate must use an expandable group, not a fabricated event')
local count_text
for _,v in ipairs(p.header_texts)do if v.id=='combat_count'then count_text=v.text end end
assert(count_text=='10 次阵亡','recent count includes all grouped real events and missing deaths')
unknown_group.records={};unknown_group.count=7;c.combat={rows={unknown_group}}
p=layout();assert(not find(p,'combat_record'),'missing-only deaths never receive event controls')
assert(p.constructed_blocks==3,'missing-only group contains its heading and one summary')
-- Associations show only the name and count; internal confidence still survives
-- for diagnostics, and the unknown remainder remains an ordinary final row.
c.view='weapons';c.scroll=0;c.combat_state={pages={},open_id='paired'}
c.combat={totals={kills=3,known_kinds=1,linked_kills=2},rows={{id='paired',name='测试步枪',known=true,kills=3,
    detail_rows={{id='Charger',name='强袭虫',known=true,kills=2,inferred=true},
        {id='unknown',name='未知',known=false,kills=1}}}}}
p=layout()
local paired_controls={}
for _,v in ipairs(p.nav_controls)do if v.action=='combat_association'then paired_controls[#paired_controls+1]=v end end
assert(#paired_controls==2 and paired_controls[1].text=='强袭虫  2 >'
    and paired_controls[1].enabled and paired_controls[1].value=='Charger')
assert(paired_controls[2].text=='未知  1'and not paired_controls[2].enabled)
assert(c.combat.rows[1].detail_rows[1].inferred==true,'presentation must not rewrite stored attribution evidence')
c.view='enemies';p=layout()
assert(find(p,'combat_association').text=='强袭虫  2 >','both association directions omit the confidence suffix')
c.view='deaths'
-- Cause evidence is shown in ordinary Chinese, with the weapon and mechanism
-- both retained in facts even when the short recent row has room for one.
for channel,expected in pairs({local_damage_queue='角色伤害记录',
    latest_native_damage_event='最近原生受伤记录',
    native_owned_health_death_cause='生命记录中的死亡机制',
    nearby_simultaneous_death='附近同时死亡线索'})do
    local row={id='cause-display',at=110,match=8,category='self',actor='自身',
        weapon='AC-8 机炮',attack='爆炸',confidence='inferred',
        evidence={source_channel=channel,source_reason='NATIVE_DAMAGE_WEAPON_UNRESOLVED',
            nearby_death_inferred=channel=='nearby_simultaneous_death'}}
    c.scroll=0;c.combat_state={mode='recent',pages={},related_pages={},record_id=row.id}
    c.combat={rows={row}};p=layout()
    local texts={}
    for y=0,p.max_scroll+26,26 do
        c.scroll=math.min(y,p.max_scroll)
        for _,v in ipairs(layout().header_texts)do texts[v.text]=true end
    end
    assert(texts[expected]and texts['伤害来源']and texts['AC-8 机炮']and texts['爆炸'],
        'local/native death evidence has readable Chinese cause facts')
    assert(not texts[channel]and not texts['NATIVE_DAMAGE_WEAPON_UNRESOLVED'],
        'internal source keys are not shown as player-facing prose')
    if channel=='nearby_simultaneous_death'then
        assert(texts['附近队友同时死亡'],'the cause evidence is readable without a confidence label')
    end
    for value in pairs(texts)do assert(not value:find('推测',1,true)and value~='来源可信度','confidence labels are not player-facing')end
    assert(row.confidence=='inferred','internal confidence stays available')
end
print('PASS bounded native combat model: five tabs, 12000-row paging 10/5, one facts block, slot 0, unknown bottom groups, native cause Chinese labels, clipping and fixed 48/32/48 pools.')
