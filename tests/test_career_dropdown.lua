-- Real dropdown behaviour through the pure model and sampled native input.
-- No process, clipboard, account or file writes are involved in this fixture.
local root=assert(arg[1])
local make_model=dofile(root..'/src/career-panel-model.lua')
local make_combat=dofile(root..'/src/career-combat-panel-model.lua')
local make_feed=dofile(root..'/src/career-panel-feed.lua')
local types={}
for i=1,30 do types[i]=string.format('类型 %02d',i)end
local model=make_model({},nil,make_combat)
local context={page_visible=true,personal=true,width=420,height=747,view='weapons',period='all',scroll=0,
    combat_state={role='all',weapon_type='all',category='all',faction='all',size='all',pages={},related_pages={}},
    combat={rows={},totals={kills=75,known_kinds=75,linked_kills=0},available_weapon_types=types}}
local function find_control(plan,id)
    for _,c in ipairs(plan.dropdown and plan.dropdown.controls or {})do if c.id==id or c.action==id then return c end end
    for _,c in ipairs(plan.nav_controls or {})do if c.id==id or c.action==id then return c end end
end
local function menu_bounds(plan)
    local d=assert(plan.dropdown,'open filter creates a dropdown')
    assert(d.x>=0 and d.y>=0 and d.width>0 and d.height>0 and d.x+d.width<=plan.width+.01 and d.y+d.height<=plan.height+.01,
        'dropdown is contained by the verified native parent')
    assert(#d.controls>0 and #d.controls<=6 and d.total>=#d.controls and d.max_scroll==math.max(0,d.total-#d.controls),
        'dropdown keeps at most six visible options and a bounded index scroll')
    assert(d.scroll>=0 and d.scroll<=d.max_scroll and d.first==d.scroll+1 and d.last==d.first+#d.controls-1)
    for _,c in ipairs(d.controls)do
        assert(c.action=='combat_filter' and c.filter==d.filter and c.id:match('^dropdown_option_%d+$'))
        assert(c.x>=d.x and c.y>=d.y and c.width>0 and c.height>0 and c.x+c.width<=d.x+d.width+.01 and c.y+c.height<=d.y+d.height+.01,
            'each selectable option is contained by the dropdown')
    end
    return d
end
local cases={
    {view='deaths',filter='category',values={'all','enemy','player','self','environment','unknown'}},
    {view='weapons',filter='role',values={'all','primary','secondary','support','throwable','stratagem'}},
    {view='enemies',filter='faction',values={'all','bugs','bots','illuminate'}},
    {view='enemies',filter='size',values={'all','轻型','中型','中型精英','重型','巨型','BOSS'}},
}
for _,case in ipairs(cases)do
    context.view=case.view;context.combat_state.dropdown=nil
    local closed=model:layout({},context)
    local trigger=assert(find_control(closed,'filter_'..case.filter))
    assert(trigger.action=='combat_dropdown' and trigger.filter==case.filter and trigger.value=='all',
        'filter trigger opens options without preselecting the next value: '..case.filter)
    assert(not closed.dropdown)
    local seen={}
    for scroll=0,math.max(0,#case.values-6)do
        context.combat_state.dropdown={filter=case.filter,scroll=scroll}
        local d=menu_bounds(model:layout({},context))
        assert(d.filter==case.filter and d.total==#case.values)
        for _,c in ipairs(d.controls)do seen[c.value]=true end
    end
    for _,value in ipairs(case.values)do assert(seen[value],'all filter values are reachable: '..case.filter..'/'..value)end
end
context.view='weapons';context.combat_state.dropdown=nil
local weapons=model:layout({},context)
assert(not find_control(weapons,'filter_weapon_type'),'weapon page exposes only the broad category filter')
local role_filter=assert(find_control(weapons,'filter_role'))
assert(role_filter.x*2+role_filter.width==weapons.width,'weapon category uses the full content width')
context.view='enemies';context.combat_state.dropdown={filter='size',scroll=10000}
local terminal=menu_bounds(model:layout({},context))
assert(terminal.scroll==1 and terminal.first==2 and terminal.last==7 and terminal.controls[#terminal.controls].value=='BOSS',
    'a seven-option size menu clamps and exposes the final option')

-- The native reader accepts parents down to 240x160. An anchor that no
-- longer fits cannot leave an orphaned or overflowing dropdown behind.
for _,width in ipairs({240,420})do
    for _,height in ipairs({160,180,200,240,243,263,300,639,747})do
        context.width=width;context.height=height
        for _,case in ipairs(cases)do
            context.view=case.view;context.combat_state.dropdown={filter=case.filter,scroll=10000}
            local p=model:layout({},context)
            local trigger=find_control(p,'filter_'..case.filter)
            if trigger then
                local d=menu_bounds(p)
                assert(d.last==#case.values,'the final option remains reachable at '..width..'x'..height..'/'..case.filter)
            else
                assert(not p.dropdown,'a clipped filter cannot generate an invisible-anchor menu at '..width..'x'..height)
            end
            for _,list in ipairs({p.nav_controls,p.header_texts,p.decorations})do
                for _,v in ipairs(list)do
                    assert(v.x>=0 and v.y>=0 and v.width>0 and v.height>0 and v.x+v.width<=width+.01 and v.y+v.height<=height+.01,
                        'small native parents retain fully clipped ordinary widgets')
                end
            end
        end
    end
end
context.width=420;context.height=747

local geometry={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,alpha_address=0x50000,
    local_peer='0000000000000011',position={732,-237},width=420,height=747,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local mouse={x=740,y=250,w=1920,h=1080,left=false}
local now,reads,wheel=0,0,0
local pressed,captures,last_filter={},{}
local rows={}
for i=1,75 do rows[i]={id='weapon-'..i,name='武器 '..i,kills=76-i,detail_rows={}}end
local api=make_feed({model=model,records=function()return {totals={}}end,
    mouse=function()return mouse end,gui_resolution=function()return 1920,1080 end,
    key_pressed=function(key)return pressed[key]==true end,key_down=function()return false end,
    wheel=function()local value=wheel;wheel=0;return value end,
    block_input=function(v)captures[#captures+1]=type(v)=='table'and{keyboard=v.keyboard,mouse=v.mouse}or false end,
    reader=function()return {read=function()reads=reads+1;return geometry end}end,
    combat=function(_,filters)
        last_filter={};for k,v in pairs(filters)do last_filter[k]=v end
        return {rows=rows,totals={kills=75,known_kinds=75,linked_kills=0},available_weapon_types=filters.role=='primary'and{'主分类类型'}or types}
    end})
local function step()
    now=now+.1
    api:step(now,{}, {state=3,mission=false},{{['local']=true,peer=geometry.local_peer}})
    local value=api:snapshot();return value and value.model
end
local function plan()return assert(api:snapshot()).model end
local function control(id)return assert(find_control(plan(),id),'missing control '..id)end
local function aim(x,y,left)mouse={x=732+x,y=237+y,w=1920,h=1080,left=left==true}end
local function click(id)
    local c=control(id)
    aim(c.x+c.width/2,c.y+c.height/2,false);step()
    mouse.left=true;step();mouse.left=false;step()
end
local function scroll_at(x,y,delta)
    aim(x,y,false);wheel=delta;step()
end
local function menu()return menu_bounds(plan())end
step();click('tab_weapons')
click('combat_next');assert(plan().combat_page==2)
local role_before=last_filter.role
click('filter_role')
assert(menu().filter=='role' and last_filter.role==role_before and plan().combat_page==2,
    'opening a dropdown leaves actual filters and main pagination unchanged')
click('dropdown_option_2')
assert(not plan().dropdown and last_filter.role=='primary' and last_filter.weapon_type=='all' and plan().combat_page==1,
    'one explicit option applies the selected category, resets dependent type and closes')
click('filter_role');click('dropdown_option_1');assert(last_filter.role=='all')

click('tab_enemies');click('filter_faction');click('filter_size')
assert(menu().filter=='size' and last_filter.faction=='all' and last_filter.size=='all' and last_filter.weapon_type=='all',
    'another filter trigger replaces the open dropdown without applying either filter')
local d=menu();local list_scroll=plan().scroll
scroll_at(d.x+d.width/2,d.y+d.controls[1].height/2,-20)
assert(menu().scroll>0 and plan().scroll==list_scroll and last_filter.size=='all',
    'wheel over options scrolls the menu, including the area above list_top, without applying selection')
for i=1,3 do d=menu();scroll_at(d.x+d.width/2,d.y+d.height/2,-20)end
assert(menu().scroll==menu().max_scroll and plan().scroll==list_scroll,'menu overscroll never passes to the main list')
click('dropdown_option_7')
assert(not plan().dropdown and last_filter.size=='BOSS','the last option beyond the six-item menu window is directly selectable')

-- An outside press dismisses rather than also activating the control below it.
click('filter_size');local page_before=plan().combat_page
click('combat_next')
assert(not plan().dropdown and plan().combat_page==page_before,'outside click does not advance the underlying main pager')
click('filter_faction');click('tab_weapons')
assert(not plan().dropdown and plan().view=='enemies','outside click does not switch an underlying tab')
click('tab_weapons');assert(plan().view=='weapons' and not find_control(plan(),'filter_weapon_type'))
click('tab_enemies');assert(plan().view=='enemies')
click('filter_faction');assert(menu().filter=='faction')
click('dropdown_option_3');assert(last_filter.faction=='bots' and not plan().dropdown)
click('filter_size');d=menu();scroll_at(d.x+d.width/2,d.y+d.height/2,-20)
click('dropdown_option_7');assert(last_filter.size=='BOSS' and not plan().dropdown)
click('tab_deaths');click('filter_category');click('dropdown_option_3')
assert(last_filter.category=='player' and not plan().dropdown,'death-source dropdown applies a precise option')

click('tab_weapons');click('filter_role')
local read_before=reads
pressed={ESCAPE=true};now=now+.016;api:sample_input(now);assert(reads==read_before,'menu key handling never reads native geometry')
pressed={};step();assert(not plan().dropdown,'Escape dismisses the menu')
click('filter_role');mouse=nil;step();assert(not plan().dropdown,'loss of pointer focus dismisses the menu')
aim(10,10,false);step();click('filter_role');api:clear('closed');assert(not api:snapshot())
step();assert(not plan().dropdown,'closed native page does not reopen a stale dropdown')
click('filter_role')
local original=geometry;geometry={};for k,v in pairs(original)do geometry[k]=v end;geometry.parent=geometry.parent+8
step();assert(not api:snapshot(),'changed native parent invalidates its open menu')
step();assert(not plan().dropdown,'replacement native page starts without the old popup')

-- A same-parent resize keeps a menu only while its visible trigger and
-- options still fit. Shrinking below that releases the keyboard lease and
-- invalidates an option press queued against the previous dimensions.
click('filter_role')
assert(captures[#captures].keyboard==true,'an open dropdown owns Escape before a resize')
geometry.width=240;geometry.height=300;step()
assert(menu().filter=='role','a compact parent keeps a fully bounded reachable dropdown')
click('dropdown_option_2');assert(last_filter.role=='primary' and not plan().dropdown,
    'a compact parent accepts the visible option')
click('filter_role');click('dropdown_option_1');assert(last_filter.role=='all')
geometry.width=420;geometry.height=747;step();click('filter_role')
local queued=control('dropdown_option_2')
aim(queued.x+queued.width/2,queued.y+queued.height/2,false);step()
mouse.left=true;now=now+.016;api:sample_input(now)
geometry.width=240;geometry.height=160;step()
assert(not plan().dropdown and last_filter.role=='all','a queued pre-resize option cannot apply through the hidden menu')
assert(captures[#captures]==false,'an unlayoutable menu immediately releases its input lease')
mouse.left=false;step()
geometry.width=420;geometry.height=747;step()
assert(not plan().dropdown,'restoring the original size does not reopen the dismissed menu')
assert(type(captures[#captures])~='table' or captures[#captures].keyboard==false,
    'restored native page never retains the old menu keyboard capture')

-- The ordinary archive wheel path still works after closing a dropdown.
local before=plan().scroll
scroll_at(20,plan().list_top+40,-2)
assert(plan().scroll>before and not plan().dropdown,'closed popup restores main-list scrolling')
click('filter_role');d=menu();before=plan().scroll
scroll_at(d.x+d.width/2,d.y+d.height/2,-20)
assert(menu().scroll==0 and plan().scroll==before,'a six-option menu consumes wheel even with no menu scroll range')
api:clear('done')
assert(captures[#captures]==false,'closing the page releases the requested input lease')
print('PASS native Career dropdowns: four filters, exact option selection, seven-size final option, full-width weapon category, six-item window, menu/main wheel isolation, outside press interception, Escape/focus/clear/parent lifetime cancellation, compact/minimum parent clipping and resize keyboard release.')
