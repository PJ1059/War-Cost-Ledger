local root=assert(arg[1])
local model=dofile(root..'/src/career-panel-model.lua')({},nil,dofile(root..'/src/career-combat-panel-model.lua'))
local create=dofile(root..'/src/career-panel-feed.lua')
local input=dofile(root..'/src/career-search-input.lua')
local g={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,alpha_address=0x50000,
    local_peer='0000000000000011',position={732,-237},width=420,height=747,root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local now,reads,pastes,wheel=0,0,0,0
local mouse={x=740,y=250,w=1920,h=1080,left=false}
local pressed,down={},{};local captures={};local last_filter,last_view
local billing=true
local death_records={}
for i=1,12000 do death_records[i]={id='death-'..i,occurred_at=200000-i,sequence=100,category='player',actor_name='队友',
    player={name='演示昵称',peer_id='DEMO-0001',persona_index=0}}end
local api=create({model=model,records=function()return {totals={}}end,
    billing_enabled=function()return billing end,format_money=function(cents)return string.format('%.2f',cents/100),'MC'end,
    history=function()return {entries={{sequence=100,status='ended',kills=10,deaths=0,ribbons={},medals={},
        patriotic_bill={version=1,total_cents=1250,entries={{key='ammo:a',name='AC-8 弹药',amount_cents=1250}}}}}}end,
    search_input=input,key_pressed=function(k)return pressed[k]==true end,key_down=function(k)return down[k]==true end,
    paste_text=function()pastes=pastes+1;return '机炮'end,
    mouse=function()return mouse end,gui_resolution=function()return 1920,1080 end,
    wheel=function()local value=wheel;wheel=0;return value end,
    block_input=function(v)captures[#captures+1]=type(v)=='table'and{keyboard=v.keyboard,mouse=v.mouse}or false end,
    reader=function()return {read=function()reads=reads+1;return g end}end,
    combat=function(view,f)
        last_view=view;last_filter=f
        if view=='deaths'then
            if f.mode=='recent'then return {rows=death_records}end
            return {rows={{id='player',name='队友',category='player',count=12000,records=death_records}}}
        end
        local rows={};for i=1,75 do rows[i]={id='weapon-'..i,name='AC-'..i,kills=100-i,
            detail_rows={{id='enemy-1',name='食腐虫',kills=100-i,known=true}}}end
        if f.focus_id then rows={{id=f.focus_id,name='食腐虫',kills=10,detail_rows={{id='weapon-1',name='AC-1',kills=10,known=true}}}}end
        return {rows=rows,totals={kills=100,known_kinds=75,linked_kills=0},available_weapon_types={'机炮','反坦克'}}
    end})
local function step()now=now+.1;api:step(now,{}, {state=3,mission=false},{{['local']=true,peer=g.local_peer}});return api:snapshot().model end
local function plan()return api:snapshot().model end
local function control(id)
    for _,c in ipairs(plan().nav_controls)do if c.id==id or c.action==id then return c end end
    error('missing control '..id)
end
local function aim(c,left)mouse={x=732+c.x+3,y=237+c.y+c.height/2,w=1920,h=1080,left=left}end
local function click(id)aim(control(id),false);step();aim(control(id),true);step();mouse.left=false;step()end
local function keys(p,d)
    pressed=p or {};down=d or {};now=now+.016;local before=reads;api:sample_input(now);assert(reads==before,'keys never read native geometry');pressed={};down={};step()
end
step();click('tab_weapons');assert(plan().view=='weapons'and last_view=='weapons')
click('combat_rank_1');assert(control('combat_rank_1').active,'first click expands a weapon')
local expanded_height=plan().content_height
click('combat_rank_1');assert(not control('combat_rank_1').active and plan().content_height<expanded_height,'second click collapses the same weapon')
click('tab_bill');assert(plan().view=='bill')
local actual_bill=false
for _,text in ipairs(plan().header_texts)do if text.id=='bill_total'and text.text=='12.50 MC'then actual_bill=true end end
assert(actual_bill,'feed carries exact saved bill amounts to layout')
billing=false;step();assert(plan().view=='collection','disabling billing leaves an open bill page')
for _,c in ipairs(plan().nav_controls)do assert(c.id~='tab_bill')end
billing=true;click('tab_weapons')
click('combat_next');assert(plan().combat_page==2)
click('combat_search');assert(captures[#captures].keyboard==true and pastes==0)
keys({A=true});assert(last_filter.query=='a'and plan().combat_page==1)
keys({V=true},{CTRL=true});assert(last_filter.query=='a机炮'and pastes==1)
keys({ENTER=true});assert(captures[#captures].keyboard==false)
click('combat_search');mouse={x=10,y=10,w=1920,h=1080,left=false};step();mouse.left=true;step()
assert(captures[#captures]==false or captures[#captures].keyboard==false,'outside click releases keyboard')
mouse.left=false;step();keys({V=true},{CTRL=true});assert(pastes==1)
click('filter_role');assert(plan().dropdown and last_filter.role=='all','opening a select does not cycle filters')
local option=plan().dropdown.controls[2];aim(option,false);step();aim(option,true);step();mouse.left=false;step()
assert(not plan().dropdown and last_filter.role=='primary'and last_filter.weapon_type=='all')
click('combat_search_clear');assert(last_filter.query=='')
click('combat_jump');keys({A=true},{CTRL=true});keys({['7']=true});keys({ENTER=true});assert(plan().combat_page==7,'large main result jumps directly')
click('combat_rank_61');click('combat_association');assert(plan().view=='enemies'and last_filter.focus_id=='enemy-1')
assert(control('combat_rank_1').active)
click('combat_rank_1');assert(not control('combat_rank_1').active,'enemy detail opened by a reverse lookup can also collapse')
click('combat_rank_1');assert(control('combat_rank_1').active)
click('combat_back');assert(plan().view=='weapons'and last_filter.focus_id==nil and plan().combat_page==7,'back restores source page and clears absent focus')
click('tab_deaths');click('combat_rank_1');assert(control('combat_rank_1').active)
click('combat_rank_1');assert(not control('combat_rank_1').active,'death rankings also collapse')
click('death_recent');assert(plan().combat_last_page==1200)
click('combat_record');assert(control('combat_record').active)
click('combat_record');assert(not control('combat_record').active,'second click collapses death facts')
click('combat_jump');keys({A=true},{CTRL=true});keys({['1']=true});keys({['2']=true});keys({['0']=true});keys({['0']=true});keys({ENTER=true})
assert(plan().combat_page==1200,'12000-row recent list jumps directly to page1200')
click('period_24h');assert(plan().combat_page==1 and last_filter.period=='24h')
click('death_rank');click('combat_rank_1')
-- Reach the bounded related pager with the same native wheel path.
mouse={x=740,y=237+plan().list_top+50,w=1920,h=1080,left=false};wheel=-5;step()
click('related_jump');keys({A=true},{CTRL=true});keys({['2']=true});keys({['4']=true});keys({['0']=true});keys({['0']=true});keys({ENTER=true})
assert(plan().related_page==2400,'related list jumps directly with its own numeric input')
click('combat_search');assert(captures[#captures].keyboard==true)
mouse=nil;step();assert(captures[#captures]==false,'focus loss releases input lease')
keys({V=true},{CTRL=true});assert(pastes==1)
api:clear('closed');assert(not api:snapshot()and captures[#captures]==false)
print('PASS native combat feed: five tabs, real search input and explicit Unicode paste, filter/page reset, main1200 and related2400 direct jumps, outside/focus/close release, no per-frame native geometry reads.')
