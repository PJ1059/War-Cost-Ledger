local make_model=dofile(assert(arg[1]))
local make_feed=dofile(assert(arg[2]))
local icons=dofile(assert(arg[3]))({},function()return true end).icons
local make_history=dofile(assert(arg[4]))
local model=make_model(icons)
local function find(rows,id)for _,row in ipairs(rows or {})do if row.id==id then return row end end end
local history={revision=1,entries={}}
for i=1,30 do history.entries[i]={sequence=i,status='ended',started_at=i*100,ended_at=i*100+60,
    kills=i,deaths=1,ribbons={air=i},medals={}}end
history.entries[1].kills=900;history.entries[1].deaths=20
history.entries[2].kills=100;history.entries[2].deaths=0
history.entries[4].medals.fragrant=1
history.entries[8].medals.fragrant=2;history.entries[8].medal_last_at={fragrant=825}
history.entries[29].ribbons.air=40;history.entries[30].ribbons.air=40
history.entries[31]={sequence=31,status='active',kills=9999,deaths=9999,ribbons={},medals={}}
local records={totals={ribbons={air=1000},medals={fragrant=3}}}
local ctx={page_visible=true,personal=true,width=420,height=747,view='history',history=history,expanded_sequence=false,
    format_time=function(at)return 'time '..at end}
local p=model:layout(records,ctx)
assert(find(p.nav_controls,'record_kills').sequence==1)
assert(find(p.nav_controls,'record_kd').sequence==2)
assert(find(p.nav_controls,'record_deaths').sequence==1)
assert(find(p.header_texts,'record_value_kd').text=='100/0')
ctx.period='24h';ctx.summary={periods={{key='24h',from_at=2800,to_at=3100}}}
p=model:layout(records,ctx);assert(find(p.nav_controls,'record_kills').sequence==30,'records follow the visible period')
ctx.summary.periods[1].from_at=99999;p=model:layout(records,ctx)
assert(not find(p.nav_controls,'record_kills').enabled,'missing records have no jump')
ctx.period='all';ctx.view='collection';ctx.summary=nil
p=model:layout(records,ctx);local ribbon=assert(find(p.items,'R01'));ctx.pointer={x=ribbon.x+5,y=ribbon.y+5}
p=model:layout(records,ctx);assert(p.tooltip.sequence==30 and p.tooltip.details[1]:find('40',1,true),'latest match wins equal ribbon counts')
local medal=assert(find(p.items,'M06'));ctx.pointer={x=medal.x+5,y=medal.y+5}
p=model:layout(records,ctx);assert(p.tooltip.sequence==8 and p.tooltip.details[1]:find('825',1,true))
history.entries[8].medal_last_at=nil;history.revision=2
p=model:layout(records,ctx);assert(p.tooltip.details[1]:find('上次获得对局：time 860',1,true),'legacy time is explicitly a match date')
ctx.view='history';ctx.pointer=nil;ctx.expanded_sequence=1;ctx.jump_sequence=1
p=model:layout(records,ctx)
assert(p.scroll>0 and find(p.nav_controls,'history_row1').sequence==1,'oldest destination scrolls into view expanded')
assert(p.expanded_sequence==1)
for _,height in ipairs({300,480,747})do
    ctx.height=height;ctx.jump_sequence=nil;ctx.expanded_sequence=false;ctx.scroll=0
    p=model:layout(records,ctx);assert(find(p.nav_controls,'history_row1'),'history remains reachable in compact panels')
end
-- Real feed input: two distinct press edges jump; holding or widely spaced clicks do not.
local g={parent=65536,gui_context=0x40000,local_peer='11',position={0,0},width=420,height=747,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local mouse={x=10,y=10,w=1920,h=1080,left=false};local now=0
local feed=make_feed({model=model,records=function()return records end,history=function()return history end,
    mouse=function()return mouse end,gui_resolution=function()return 1920,1080 end,
    reader=function()return{read=function()return g end}end})
local function step(dt)now=now+(dt or .1);feed:step(now,{}, {state=3},{{['local']=true,peer='11'}});return feed:snapshot().model end
local function aim(c,left)mouse.x=c.x+5;mouse.y=c.y+5;mouse.left=left end
local function click(c,dt)aim(c,false);step(dt);aim(c,true);return step(.05)end
p=step();medal=find(p.items,'M06')
p=click(medal);assert(p.view=='collection')
for i=1,3 do p=step(.05)end;assert(p.view=='collection','held button never creates a double click')
p=click(medal,.5);assert(p.view=='collection','slow clicks keep award details')
p=click(medal,.05);assert(p.view=='history' and p.expanded_sequence==8 and p.period=='all')
assert(find(p.nav_controls,'history_row1').sequence==8,'award jump reveals older match')
p=click(find(p.nav_controls,'record_kills'));assert(p.expanded_sequence==1 and find(p.nav_controls,'history_row1').sequence==1)
-- Persist only observed award increases. Never timestamp an imported positive snapshot.
local h=make_history({icons=icons})
local s={sequence=1,mission=true,status='active',stats_ready=false,kills=0,deaths=0,ribbons={},mission_medals={}}
h:observe(s,100);s.mission_medals.fragrant=1;h:observe(s,125)
assert(h:entries()[1].medal_last_at.fragrant==125)
h:observe(s,130);assert(h:entries()[1].medal_last_at.fragrant==125)
s.mission_medals.fragrant=2;h:observe(s,135);assert(h:entries()[1].medal_last_at.fragrant==135)
local saved=h:snapshot();local restored=make_history({icons=icons,saved=saved})
assert(restored:entries()[1].medal_last_at.fragrant==135)
local legacy=make_history({icons=icons,legacy=s});assert(not legacy:entries()[1].medal_last_at)
print('PASS .67 saved match records, filtered maxima, old-match scroll, ribbon/medal history, edge-trigger double click and observed-only timestamps.')
