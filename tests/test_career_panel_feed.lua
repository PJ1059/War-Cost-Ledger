local make=dofile(assert(arg[1]))
local model=dofile(assert(arg[2]))(dofile(assert(arg[3]))({},function()return true end).icons)
local g={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,
    alpha_address=0x50000,local_peer='0000000000000011',position={732,-237},width=420,height=747,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local mouse={x=10,y=10,w=1920,h=1080,left=false}
local gui={1920,1080};local now,reads,wheel,latest=0,0,0,nil
local records={totals={ribbons={air=3},medals={democracy_harvester=2}}}
local history={revision=1,limit=500,entries={}}
for i=1,20 do history.entries[i]={sequence=21-i,status='ended',kills=21-i,deaths=1,
    ended_at=200000-i*60,ribbons={air=i},medals={}}end
local periods={}
for _,key in ipairs({'24h','7d','30d'})do periods[#periods+1]={key=key,from_at=190000,to_at=200000,
    missions=20,kills=210,deaths=20,ribbons={air=210},medals={},unknown_time=0,
    career={current_kd=75.96,delta=.2,baseline={at=190000,kd=75.76}}}end
local deletes={}
local billing=false
-- Even a leftover control supplied by an older renderer has no delete handler.
local legacy_delete=false
local original_layout=model.layout
function model:layout(data,opts)
    local out=original_layout(self,data,opts)
    assert(opts.confirm_delete==nil,'feed no longer carries deletion state')
    if legacy_delete then table.insert(out.nav_controls,1,{id='delete_history',action='delete_history',
        sequence=20,text='删除本局',x=0,y=28,width=420,height=10,enabled=true})end
    return out
end
local api=make({model=model,records=function()return records end,history=function()return history end,
    summary=function()return {periods=periods,all=billing and{patriotic_bill={version=1,total_cents=1234,recorded_missions=1,entries={}}}or nil}end,latest_ended=function()return latest end,
    billing_enabled=function()return billing end,format_money=function(cents)return string.format('%.2f',cents/100),'USD'end,
    format_time=function(t)return '2026-10-13 20:00'end,
    remove_history=function(sequence)
        for i,e in ipairs(history.entries)do if e.sequence==sequence then
            table.remove(history.entries,i);history.revision=history.revision+1;deletes[#deletes+1]=sequence;return true
        end end
    end,
    mouse=function()return mouse end,gui_resolution=function()return unpack(gui)end,
    wheel=function()local v=wheel;wheel=0;return v end,
    reader=function()return {read=function()reads=reads+1;return g,'CAREER_PANEL_TIME_BUDGET'end}end})
local function step(dt)
    now=now+(dt or .1)
    api:step(now,{}, {state=3,mission=false},{{['local']=true,peer='0000000000000011'}})
    return api:snapshot()
end
local function plan()return assert(api:snapshot()).model end
local function no_scroll_buttons()
    for _,c in ipairs(plan().nav_controls)do
        assert(c.id~='scroll_up' and c.id~='scroll_down' and c.action~='scroll_up' and c.action~='scroll_down',
            'wheel-only history has no up/down button')
    end
end
local function control(id)
    for _,c in ipairs(plan().nav_controls)do if c.id==id or c.action==id then return c end end
    error('missing control '..id)
end
local function aim(c,left)
    mouse={x=g.position[1]+c.x+4,y=-g.position[2]+c.y+c.height/2,w=1920,h=1080,left=left}
end
local function click(id)
    aim(control(id),false);step();aim(control(id),true);step()
end
step();assert(plan().view=='collection')
-- A 16ms press is released before the next native sample, yet dispatched once.
aim(control('tab_history'),false);step()
aim(control('tab_history'),true);now=now+.016;api:sample_input(now)
mouse.left=false;now=now+.016;api:sample_input(now)
assert(plan().view=='collection');step()
assert(plan().view=='history' and plan().expanded_sequence==20)
assert(reads==3,'per-frame input never reads native memory')
local before=plan().expanded_sequence
click('toggle_match');assert(plan().expanded_sequence==false,'click collapses accordion')
click('toggle_match');assert(plan().expanded_sequence==before,'click expands same entry')
legacy_delete=true;step()
click('delete_history');step();step();click('delete_history')
assert(#deletes==0 and #history.entries==20,'old deletion controls never call remove_history')
assert(api.delete_status==nil,'no deletion status is produced')
legacy_delete=false;step()
assert(records.totals.ribbons.air==3,'browsing leaves lifetime awards')
local previous=plan().scroll
mouse={x=740,y=237+plan().list_top+100,w=1920,h=1080,left=false};wheel=-3
step();assert(plan().scroll>previous,'wheel scrolls hovered list')
previous=plan().scroll;mouse.x=10;wheel=-3;step();assert(plan().scroll==previous,'outside wheel does not scroll list');wheel=0
mouse={x=740,y=237+plan().list_top+100,w=1920,h=1080,left=false};wheel=3
step();assert(plan().scroll==0,'wheel scrolls back up to the start')
-- Traverse both ways through actual feed input. Every saved record remains
-- reachable without the removed up/down actions, and overscroll clamps.
local function wheel_traversal(direction)
    local seen={}
    local maximum=plan().max_scroll
    for index=0,math.ceil(maximum/52)+1 do
        no_scroll_buttons()
        for _,c in ipairs(plan().nav_controls)do if c.action=='toggle_match'then seen[c.sequence]=true end end
        local before_scroll=plan().scroll
        wheel=direction;step()
        if direction<0 then assert(plan().scroll>=before_scroll and plan().scroll<=maximum)
        else assert(plan().scroll<=before_scroll and plan().scroll>=0)end
    end
    for _,entry in ipairs(history.entries)do assert(seen[entry.sequence],
        'wheel traversal reaches saved record '..entry.sequence..' in direction '..direction)end
end
wheel_traversal(-1);assert(plan().scroll==plan().max_scroll,'downward wheel reaches the oldest record')
wheel_traversal(1);assert(plan().scroll==0,'upward wheel returns to the newest record')
click('period_24h');assert(plan().period=='24h' and plan().scroll==0)
click('toggle_summary');assert(plan().summary_expanded and #plan().items>0,'period awards expand')
click('close_summary');assert(not plan().summary_expanded,'summary closes before using underlying filters')
click('period_all');assert(plan().period=='all' and not plan().summary_expanded)
-- A refused geometry hides the native view and keeps tab/selection.
local saved=g;g=nil;step();assert(not api:snapshot())
g=saved;step();assert(plan().view=='history')
-- Stale queued press cannot dispatch into a destroyed/rebuilt page.
aim(control('tab_collection'),false);step();mouse.left=true;now=now+.01;api:sample_input(now)
g=nil;step();g=saved;step();assert(plan().view=='history')
-- Resize/client projection and missing projection.
click('tab_collection');local item=plan().items[1]
mouse={x=(732+item.x+5)*4/3,y=(237+item.y+5)*4/3,w=2560,h=1440,left=false}
step();assert(plan().tooltip,'client resolution maps consistently')
gui={};step();assert(not plan().tooltip);gui={1920,1080}
-- A completed mission becomes the default even after browsing old entries.
latest=30;history.entries[#history.entries+1]={sequence=30,status='ended',kills=4,deaths=0,ribbons={air=1},medals={}}
history.revision=history.revision+1;step()
assert(plan().view=='history' and plan().expanded_sequence==30 and plan().scroll==0)
click('tab_collection');step();assert(plan().view=='collection','same latest sequence does not steal browsing focus')
billing=true;step();assert(control('collection_bill').text=='爱国账单：12.34 USD')
click('collection_bill');assert(plan().view=='bill'and plan().period=='all','bottom entry opens the existing bill view')
periods[2].patriotic_bill={version=1,total_cents=2000,recorded_missions=1,entries={}}
click('period_7d');click('tab_collection')
assert(control('collection_bill').text=='爱国账单：20.00 USD','returning to collection keeps the selected period')
click('collection_bill');assert(plan().view=='bill'and plan().period=='7d')
billing=false;step();assert(plan().view=='collection')
for _,c in ipairs(plan().nav_controls)do assert(c.id~='collection_bill'and c.id~='tab_bill')end
-- The match bill is a separate accordion below combat/awards and resets when
-- opening a different match, switching periods, or disabling billing.
billing=true;g.height=1500;step();click('tab_history');click('period_all')
history.entries[#history.entries].patriotic_bill={version=1,total_cents=1250,
    entries={{key='test',name='测试费用',amount_cents=1250}}}
history.revision=history.revision+1;step()
assert(plan().expanded_sequence==30 and plan().expanded_bill_sequence==false)
local function bill_rows()
    for _,header in ipairs(plan().header_texts)do if header.id=='bill_item_name_1'then return header.text end end
end
assert(not bill_rows());click('toggle_match_bill')
assert(plan().expanded_bill_sequence==30 and bill_rows()=='测试费用','click opens only this match bill')
click('toggle_match_bill');assert(plan().expanded_bill_sequence==false and not bill_rows(),'second click closes it')
click('toggle_match_bill');click('toggle_match');assert(plan().expanded_sequence==false)
click('toggle_match');assert(plan().expanded_sequence==30 and plan().expanded_bill_sequence==false,'reopened match starts with collapsed bill')
click('toggle_match_bill');click('period_24h');assert(plan().expanded_bill_sequence==false,'period switch does not carry an open bill')
click('period_all');click('toggle_match_bill');billing=false;step()
assert(plan().expanded_bill_sequence==false and not bill_rows(),'billing off hides details and resets the bill accordion')
billing=true;step();assert(plan().expanded_bill_sequence==false)
api:step(now+.1,nil,nil,nil);assert(not api:snapshot())
print('PASS career input: 16ms click, retired deletion controls ignored, every history record reachable by wheel in both directions without up/down buttons, filters/accordion, timeout/rebuild cancellation, resize hover, newest completed default, unchanged history and lifetime awards.')
