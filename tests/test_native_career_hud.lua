-- Installed HUD+ Reader/Main declarations plus owned native parent headers.
local addon,career,host_path,art_path,fixture_test,reader_path,runtime,fixture_path,model_path,battle_path=
    assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5]),assert(arg[6]),
    assert(arg[7]),assert(arg[8]),assert(arg[9]),assert(arg[10])
local native_fixture_path=assert(arg[11],'existing native HUD fixture path required')
local function readfile(path)local f=assert(io.open(path,'rb'));local s=f:read('*a');f:close();return s end
local host_source=readfile(host_path)
local entry=assert(host_source:find('\nlocal __entry, __argument = __module_registry',1,true))
stingray={Application={},Vector2={},Vector3={}}
local host=assert(loadstring(host_source:sub(1,entry)..'\nreturn {modules=__module_registry,errors=__module_errors}'))()
assert(#host.errors==0)
-- Exercise the real Reader API for the selected installed host generation.
local compiled_reader=host_source:find('computers, compile)',1,true)~=nil
local reader_option=compiled_reader and loadstring or 4
local function step(reader,count)
    if not compiled_reader then return reader:step()end
    return reader:step(function(values)
        local awake={}
        for i=1,count do awake[i]=values['ledger.career.parent']~=nil end
        return awake
    end,.1)
end

arg={reader_path,runtime,fixture_path};HD2_CAREER_PANEL_FIXTURE_ONLY=true
local f=dofile(fixture_test);HD2_CAREER_PANEL_FIXTURE_ONLY=nil
local memory=f.memory()
local geometry=assert(f.M.new({clock=function()return 0 end}):read(memory.world,f.peer))
local combat_model_path=model_path:gsub('career%-panel%-model%.lua$','career-combat-panel-model.lua')
local model=dofile(model_path)(dofile(battle_path)({},function()return true end).icons,nil,dofile(combat_model_path))
local records={totals={ribbons={air=3,recon=2},medals={democracy_harvester=1}}}
local access_reads,safe_guard_reads=0,0
local function feed_of(overrides)
    local context={page_visible=true,personal=true,width=420,height=747}
    for key,value in pairs(overrides or {})do context[key]=value end
    if context.pointer==nil then
        local layout=model:layout(records,context)
        for _,item in ipairs(layout.items)do if item.id=='M01'then
            context.pointer={x=item.x+1,y=item.y+1};break
        end end
    end
    return {shown=true,parent=geometry.parent,parent_parent=geometry.parent_parent,gui_context=geometry.gui_context,
        alpha_address=geometry.alpha_address,root=geometry.root,position=geometry.position,size={geometry.width,geometry.height},
        guard_read=function(at,n)
            if not ((at==geometry.parent and n==256) or (at==geometry.alpha_address and n==4))then return nil end
            access_reads,safe_guard_reads=access_reads+1,safe_guard_reads+1
            local ok,raw=pcall(memory.world.view.read,at,n)
            return ok and type(raw)=='string' and #raw==n and raw or nil
        end,
        model=model:layout(records,context)}
end
local feed=feed_of()
local part=dofile(addon)({art=dofile(art_path),publish=false,career=dofile(career),career_feed=function()return feed end})
assert(#part.screens==2 and part.screens[2].parent=='ledger.career.parent')
do
    local declared={}
    for _,row in ipairs(part.screens[2].rows)do declared[row.id]=true end
    for _,id in ipairs({'G01','G06','T01','T18','M12'})do
        assert(declared['ledger_career_award_'..id..'_texture'],'native Career must declare new award artwork: '..id)
        assert(declared['ledger_career_award_'..id..'_count'],'native Career must declare new award count: '..id)
    end
end
local baked=host.modules.GameBaked
local combat_layer=baked.numbers.hud_text_layer
assert(combat_layer==551,'fixture uses the installed battle HUD foreground')
assert(host.modules.Main.merge(baked,part)==nil,'real HUD+ merge accepts a separate Career screen')
assert(baked.numbers.ledger_career_layer==24 and baked.numbers.hud_text_layer==combat_layer,
    'Career-local layer must not change the combat HUD layer')
local career_layers={
    'ledger_career_layer','ledger_career_art_layer','ledger_career_count_back_layer','ledger_career_text_layer',
    'ledger_career_tooltip_back_layer','ledger_career_tooltip_text_layer',
}
for index,key in ipairs(career_layers)do
    assert(baked.numbers[key]==23+index,
        'Career draw bands must explicitly order backing < artwork < labels < tooltip backing < tooltip labels: '..key)
end
local function expected_layer(row)
    if row.id:match('^ledger_career_award_.*_count_back$')then return 'ledger_career_count_back_layer'end
    if row.id:match('^ledger_career_tooltip_shape_')or row.id:match('^ledger_career_dropdown_shape_')then return 'ledger_career_tooltip_back_layer'end
    if row.kind=='text'then
        return (row.id:match('^ledger_career_tooltip')or row.id:match('^ledger_career_dropdown')) and 'ledger_career_tooltip_text_layer' or 'ledger_career_text_layer'
    end
    if row.id:match('^ledger_career_award_')or row.id:match('^ledger_career_chart_')then return 'ledger_career_art_layer'end
    return 'ledger_career_layer'
end
local layered={text=0,image=0};local text_seen=false
for _,row in ipairs(part.screens[1].rows)do
    if row.kind=='text'then
        assert(baked.numbers[row.font[1]]==2 and baked.numbers[row.font[2]]==1 and baked.numbers[row.font[3]]==1,
            'Career font isolation preserves the combat font variant/style')
    end
end
for _,row in ipairs(part.screens[2].rows)do
    if row.kind=='text' or row.kind=='image' then
        assert(row.layer==expected_layer(row),
            'Career draw order must be explicit rather than relying on equal-layer declaration order: '..row.id)
        layered[row.kind]=layered[row.kind]+1
        if row.kind=='text'then text_seen=true
        else
            assert(not text_seen or row.id:match('^ledger_career_tooltip_shape_')or row.id:match('^ledger_career_dropdown_shape_'),
                'Career backgrounds and artwork precede labels; tooltip background overlays them last')
            assert(row.material==nil and row.material_source==row.source,'each Career picture uses its packaged menu material')
        end
    end
end
assert(layered.text>0 and layered.image>0 and not part.native_career_status.pixels_verified)
-- Keep the host's real access facade. Its 0.2.4 API exposes text() rather
-- than 0.2.1's span()/pointer_in(). That text() directly dereferences memory;
-- only the snapshot's bounded safe read callback may replace span().
local unsafe_text_reads=0
local channel={ffi=require('ffi'),counted={}}
function channel:pinned()return true end
function channel:module()return memory.world.game end
function channel:rewind()end
function channel:read(at,n)access_reads=access_reads+1;return memory.world.view.read(at,n)end
function channel:text()unsafe_text_reads=unsafe_text_reads+1;error('unsafe host text must not read the Career lifetime header')end
function channel:pointer(raw,offset)return f.b.pointer(raw,offset)end
local actual_access=host.modules.Memory.open(baked,{open=function()return channel end})
assert(actual_access.read:status())
if compiled_reader then
    assert(actual_access.read.span==nil and actual_access.read.pointer_in==nil,
        'actual HUD+ 0.2.4 access does not provide old span/pointer_in helpers')
end
local actual_view=part.compute.ledger_career_feed.run(actual_access.read)
assert(actual_view and actual_view.parent==geometry.parent,
    'Career lifetime guard must accept the actual HUD+ access facade')
assert(access_reads==2,'actual access guard remains one 256-byte header plus 4-byte alpha')
assert(safe_guard_reads==(compiled_reader and 2 or 0),'old host keeps span; new host uses the safe snapshot boundary')
assert(unsafe_text_reads==0,'Career lifetime guard never calls the host unsafe text method')
if compiled_reader then
    local safe_read=feed.guard_read
    feed.guard_read=nil
    assert(part.compute.ledger_career_feed.run(actual_access.read)==nil and not part.native_career_status.ready,
        'new host without a safe callback hides rather than falling back to unsafe text')
    for _,failed_at in ipairs({geometry.parent,geometry.alpha_address})do
        for _,short in ipairs({false,true})do
            feed.guard_read=function(at,n)
                if at==failed_at then return short and string.rep('\0',n-1) or nil end
                return safe_read(at,n)
            end
            assert(part.compute.ledger_career_feed.run(actual_access.read)==nil and not part.native_career_status.ready,
                'failed or short safe parent/alpha reads hide the native panel')
        end
    end
    feed.guard_read=safe_read
    assert(part.compute.ledger_career_feed.run(actual_access.read),'safe read recovery restores the native panel')
    assert(unsafe_text_reads==0,'missing, failed and short safe reads never use unsafe text')
end
memory:patch(geometry.alpha_address,f.b.encode(0,'f32'))
assert(part.compute.ledger_career_feed.run(actual_access.read)==nil,'actual access closes with native alpha')
memory:patch(geometry.alpha_address,f.b.encode(1,'f32'))
assert(part.compute.ledger_career_feed.run(actual_access.read),'actual access reopens after alpha restores')
memory:patch(geometry.parent+0xF8,f.pointer(geometry.gui_context+8))
assert(part.compute.ledger_career_feed.run(actual_access.read)==nil,'actual access rejects replaced GUI context')
memory:patch(geometry.parent+0xF8,f.pointer(geometry.gui_context))
memory:patch(geometry.parent+0xF0,f.pointer(geometry.parent_parent+8))
assert(part.compute.ledger_career_feed.run(actual_access.read)==nil,'actual access rejects replaced native parent')
memory:patch(geometry.parent+0xF0,f.pointer(geometry.parent_parent))
assert(part.compute.ledger_career_feed.run(actual_access.read),'actual access restores only the proven native parent')
memory:patch(geometry.parent+0x24,f.b.encode(geometry.root.width+1,'f32'))
assert(part.compute.ledger_career_feed.run(actual_access.read)==nil,'actual access rejects changed native geometry')
memory:patch(geometry.parent+0x24,f.b.encode(geometry.root.width,'f32'))
assert(part.compute.ledger_career_feed.run(actual_access.read),'actual access restores proven native geometry')
assert(unsafe_text_reads==0,'all actual access lifetime checks use safe reads')
local raw_reads=0
local native_read={bytes={u32=f.b.u32,decode=f.b.value},
    span=function(_,at,n)raw_reads=raw_reads+1;return memory.world.view.read(at,n)end,
    pointer_in=function(_,raw,offset)return f.b.pointer(raw,offset)end,
    module=function()error('Career screen does not read the combat HUD manager')end}
local reader=host.modules.Reader.new(native_read,baked.sources,baked.numbers,nil,part.compute,reader_option)
local wanted={life={'ledger.career.parent'},value={'ledger.career.feed','ledger.career.award_R10_count',
    'ledger.career.award_M01_name1','ledger.career.tooltip_title','ledger.career.tooltip1','ledger.career.award_R02_count'},
    position={'ledger.career.position'},paint={'ledger.career.opacity'}}
if compiled_reader then wanted.parent=wanted.life;wanted.life={}end
assert(reader:plan({{wanted=wanted}}))
local values=step(reader,1)
assert(values['ledger.career.parent']==geometry.parent)
assert(values['ledger.career.position'][1]==732 and values['ledger.career.position'][2]==-237)
assert(values['ledger.career.award_R10_count']=='x2' and values['ledger.career.award_R02_count']==nil)
local readable=values['ledger.career.feed']
local count_at=readable.award_R10_count_position
local backing_at=assert(readable.award_R10_count_back_position)
local backing_size=assert(readable.award_R10_count_back_size)
assert(backing_at[1]<count_at[1]and backing_at[1]+backing_size[1]>count_at[1]
    and backing_at[2]>count_at[2]and backing_at[2]-backing_size[2]<count_at[2]-11,
    'bottom-right count remains at its old anchor and has an opaque border-clearing patch')
assert(values['ledger.career.award_M01_name1']=='民主收割机')
assert(values['ledger.career.tooltip_title']=='民主收割机  x1')
assert(values['ledger.career.tooltip1']:find('100',1,true))
assert(part.native_career_status.ready)
assert(raw_reads==2,'exactly one parent header plus alpha per native update')
local previous=values['ledger.career.feed'];local before=raw_reads
for i=1,20 do assert(step(reader,1)['ledger.career.feed']==previous)end
assert(raw_reads-before==40,'unchanged view cached; fresh lifetime guard still runs')
memory:patch(geometry.alpha_address,f.b.encode(0,'f32'))
assert(step(reader,1)['ledger.career.parent']==nil and not part.native_career_status.ready,'page close hides immediately')
memory:patch(geometry.alpha_address,f.b.encode(1,'f32'))
assert(step(reader,1)['ledger.career.parent']==geometry.parent)
memory:patch(geometry.parent+0xF8,f.pointer(geometry.gui_context+8))
assert(step(reader,1)['ledger.career.parent']==nil,'context reused before next 10 Hz sample is refused')
memory:patch(geometry.parent+0xF8,f.pointer(geometry.gui_context))
feed=nil;assert(step(reader,1)['ledger.career.parent']==nil,'cleared feed cannot hold old parent')
-- Fully acquire every current award. Page boundaries may change with the new
-- card layout; all 21 remain available with catalogue names and conditions.
records={totals={ribbons={},medals={}}}
for _,icon in ipairs(dofile(battle_path)({},function()return true end).icons)do
    records.totals[icon.kind=='medal' and 'medals' or 'ribbons'][icon.key]=1
end
feed=feed_of();values=step(reader,1);local view=values['ledger.career.feed']
local collected={}
for page=1,feed.model.award_page_count do
    feed=feed_of({award_page=page});values=step(reader,1);view=values['ledger.career.feed']
    for _,item in ipairs(feed.model.items)do
        assert(view['award_'..item.id..'_count']=='x1',item.id);collected[item.id]=true
    end
end
local collected_count=0;for _ in pairs(collected)do collected_count=collected_count+1 end
assert(collected_count==#dofile(battle_path)({},function()return true end).icons,'all catalogue awards remain reachable')
local full_catalog_records=records
records={totals={ribbons={air=1,recon=1},medals={democracy_harvester=1}}}
feed=feed_of();view=step(reader,1)['ledger.career.feed']
assert(view.nav1=='战果' and view.nav2=='对局' and view.nav5=='敌人')
local ids={}
for _,screen in ipairs(part.screens)do for _,row in ipairs(screen.rows)do
    assert(not ids[row.id],'independent screens have unique widget IDs');ids[row.id]=true
end end
assert(not ids.ledger_career_award_I01_texture and not ids.ledger_career_award_I02_texture,
    'KD direction indicators are not earnable career awards')
assert(memory.writes==0)
-- Reuse the existing real Widgets ABI fixture without running its combat tests.
-- Native constructors/setters still execute the unchanged installed host code.
local fixture_source=readfile(native_fixture_path)
local first=assert(fixture_source:find("local ffi=require('ffi')",1,true))
local last=assert(fixture_source:find('local complete=factory(',first,true))
local environment=setmetatable({host=host,baked=baked,feed={hud=geometry.parent-0x2944A0},
    HD2_CAREER_FLAT_FIXTURE=true},{__index=_G})
local fixture_chunk=assert(loadstring(fixture_source:sub(first,last-1)..[[
return {read=native_read,ui=native_ui,n=n,store=store,atvalue=atvalue,packf=packf,context=context,
 nodes=nodes,parent=parent}
]]))
setfenv(fixture_chunk,environment)
local widgets_fixture=fixture_chunk()
local wf=widgets_fixture
local root_bytes=memory.world.view.read(geometry.parent,256)
wf.store(geometry.parent,root_bytes)
wf.atvalue(geometry.parent+0xF8,wf.context)
wf.store(geometry.alpha_address,wf.packf(1))
geometry.gui_context=wf.context;feed=feed_of()
wf.read.pointer_in=function(_,raw,at)return f.b.pointer(raw,at)end
local render_reader=host.modules.Reader.new(wf.read,baked.sources,baked.numbers,nil,part.compute,reader_option)
local wants={}
for _,row in ipairs(part.screens[2].rows)do wants[#wants+1]={wanted=host.modules.Widgets.wanted(row)}end
wants[#wants+1]={wanted={value={},position={'ledger.career.parent'},paint={},life={}}}
if compiled_reader then wants[#wants].wanted.parent=wants[#wants].wanted.position;wants[#wants].wanted.position={}end
assert(render_reader:plan(wants))
local widgets=host.modules.Widgets.new(wf.read,wf.ui,{},wf.n)
local addresses,reason=widgets:make(geometry.parent,part.screens[2].rows)
assert(addresses,tostring(reason)..': '..tostring(widgets.failed_detail))
values=step(render_reader,#wants)
for _,row in ipairs(part.screens[2].rows)do assert(widgets:put(row.id,values),row.id..': '..tostring(widgets.failed_detail))end
for _,row in ipairs(part.screens[2].rows)do
    if row.kind=='text' or row.kind=='image' then
        assert(wf.nodes[addresses[row.id]].widget_layer_set==baked.numbers[expected_layer(row)],
            'real HUD+ Widgets must apply the declared native draw band: '..row.id)
    end
end
assert(wf.read:ptr(addresses.ledger_career_block+wf.n.widget_parent)==geometry.parent)
assert(wf.nodes[addresses.ledger_career_award_R10_count].text=='x1')
assert(wf.nodes[addresses.ledger_career_tooltip_title].text=='民主收割机  x1')
assert(wf.nodes[addresses.ledger_career_shape_1].shown,'flat solid resource actually renders the panel background')
for _,asset in ipairs(dofile(art_path).images)do
    local node=wf.nodes[addresses['ledger_career_award_'..asset.id..'_texture']]
    if asset.id:match('^[RHM]')and node.shown then
        assert(node.texture==asset.resource_hash and node.material==asset.resource_hash,'award uses own flat material')
        assert(node.uniforms[wf.n.mask_c2][1]==0)
        local c0=node.uniforms[wf.n.mask_c0]
        assert(c0[1]==1 and c0[2]==1 and math.abs(c0[3]-249/255)<.00001 and math.abs(c0[4]-237/255)<.00001,
            'menu material colour uniforms use intensity followed by RGB')
        assert(node.uniforms[baked.numbers.ledger_career_c3][1]==0,'menu background channel stays transparent')
    end
end
-- The same real native tree changes between collection/history/summary
-- views. The model owns navigation; these are its actual output strings and
-- positions, applied by installed HUD+ constructors/setters without rebuilding.
local initial_nodes=0;for _ in pairs(wf.nodes)do initial_nodes=initial_nodes+1 end
local history={version=1,revision=1,entries={
    {sequence=20,status='ended',started_at=1720000000,kills=120,deaths=2,
        ribbons={air=5},medals={},history_before={kills=100,deaths=2},history_after={kills=220,deaths=4}},
    {sequence=19,status='interrupted',started_at=1719990000,kills=4,deaths=0,
        ribbons={recon=2},medals={},history_before={kills=100,deaths=2}},
}}
local function historical(overrides)
    local context={view='history',history=history,expanded_sequence=false,scroll=0,
        format_time=function()return '2026-10-13 20:00'end,pointer=false}
    for key,value in pairs(overrides or {})do context[key]=value end
    return feed_of(context)
end
local function raw_node(field)return wf.nodes[assert(addresses['ledger_career_'..field],field)]end
local function alignment_suffix(align)
    return align==1 and '_right' or align==.5 and '_center' or '_left'
end
local function node(field)
    local prefix,index=field:match('^(%a+)(%d+)$')
    if prefix=='header' or prefix=='nav'or prefix=='dropdown'then
        local entries=prefix=='header'and feed.model.header_texts or prefix=='nav'and feed.model.nav_controls
            or(feed.model.dropdown and feed.model.dropdown.controls or{})
        local item=entries[tonumber(index)]
        return raw_node(field..alignment_suffix(item and item.align or 0))
    end
    return raw_node(field)
end
local function draw()
    local v=step(render_reader,#wants)
    for _,row in ipairs(part.screens[2].rows)do assert(widgets:put(row.id,v),row.id..': '..tostring(widgets.failed_detail))end
    if feed then
        local plan=feed.model
        for prefix,entries in pairs({header=plan.header_texts,nav=plan.nav_controls,dropdown=plan.dropdown and plan.dropdown.controls or{}})do
            local limit=prefix=='header'and 48 or prefix=='nav'and 32 or 6
            for index=1,limit do
                local item=entries[index]
                local frame=node(prefix..index..'_frame')
                assert(frame.shown==(item~=nil),'unused '..prefix..index..' slot hides its previous content')
                for _,suffix in ipairs({'_left','_center','_right'})do
                    local child=raw_node(prefix..index..suffix)
                    assert(child.shown==(item~=nil and suffix==alignment_suffix(item.align or 0)),
                        'only the selected fixed-pivot text child is visible')
                end
                if item then
                    local rendered=frame.widget_position_set
                    local x=prefix=='header' and item.x+(item.width or 0)*(item.align or 0) or item.text_x
                    local y=prefix=='header' and item.y or item.text_y
                    assert(math.abs(rendered[1]-x)<.001 and math.abs(rendered[2]+y)<.001,'label follows model alignment and text position')
                    assert(node(prefix..index).text==item.text,'slot text follows current model')
                    assert(item.y>=0 and item.y+item.height<=plan.height,'slot stays inside model area')
                    local scale=frame.widget_scale_set
                    assert(math.abs(scale[1]-item.font_size/14)<.001 and math.abs(scale[2]-scale[1])<.001,
                        'font size is applied as uniform wrapper scale')
                    local pivot=node(prefix..index).widget_pivot_set
                    assert(math.abs(pivot[1]-(item.align or 0))<.001 and pivot[2]==1,
                        'selected text child has the matching fixed pivot')
                    if prefix=='nav'then
                        local colour=node(prefix..index).colour
                        assert(math.abs(colour[1]-item.colour[1])<.001,'control paint follows the model')
                    end
                end
            end
        end
        local visible={}
        for _,item in ipairs(plan.items)do
            visible[item.id]=true
            assert(item.visible and item.y>=0 and item.y+item.height<=plan.height,'only completely visible model items')
            assert(node('award_'..item.id..'_texture').shown)
            assert(node('award_'..item.id..'_count').text=='x'..item.count)
        end
        for _,icon in ipairs(dofile(battle_path)({},function()return true end).icons)do
            if not visible[icon.id]then
                assert(not node('award_'..icon.id..'_texture').shown,'previous view image hidden: '..icon.id)
                assert(not node('award_'..icon.id..'_count_frame').shown,'previous view count hidden: '..icon.id)
                assert(not node('award_'..icon.id..'_name1_frame').shown,'previous view name hidden: '..icon.id)
            end
        end
        for index=1,2 do assert(node('section'..index..'_frame').shown==(plan.sections[index]~=nil))end
        assert(node('tooltip_title_frame').shown==(plan.tooltip~=nil),'old tooltip hides when not hovered')
        local picture_view=v['ledger.career.feed']
        for _,shape in ipairs({{'shape_',240},{'chart_',97},{'tooltip_shape_',5}})do
            for index=1,shape[2]do
                local field=shape[1]..index
                local native=node(field)
                assert(native.shown==(picture_view[field]~=nil),'unused flat shape hides: '..field)
                if native.shown then assert(native.material==native.texture,'shape uses own flat menu material')end
            end
        end
    end
    return v['ledger.career.feed']
end
local function control(action,sequence)
    for index,item in ipairs(feed.model.nav_controls)do
        if item.action==action and (sequence==nil or item.sequence==sequence)then return item,node('nav'..index)end
    end
end
local function contains_text(text)
    for _,item in ipairs(feed.model.header_texts)do if item.text:find(text,1,true)then return true end end
    for _,item in ipairs(feed.model.nav_controls)do if item.text:find(text,1,true)then return true end end
    return false
end
-- A selected historical match uses the same retained native text pools for
-- independent weapon/stratagem and enemy totals. It must never borrow another
-- match's sources or create an unproven source/victim pairing.
local combat_records_path=model_path:gsub('career%-panel%-model%.lua$','combat-records.lua')
local sources=dofile(combat_records_path)({weapon_catalog={
    A={id='rifle',name='本局测试步枪',category='primary'},
    B={id='orbital',name='本局轨道攻击',category='stratagem'},
    C={id='other',name='另一局武器',category='support'}},enemy_catalog={
    E={key='BigEnemy',name_zh='本局重型敌人',faction='bugs',class='重型'},
    F={key='SmallEnemy',name_zh='本局轻型敌人',faction='bugs',class='轻型'},
    G={key='OtherEnemy',name_zh='另一局敌人',faction='bots',class='轻型'}}})
sources:observe({sequence=20,status='ended',kills=120,deaths=2,
    weapon_stats={A={kills=100},B={kills=20}},unit_kills={BigEnemy={count=30},SmallEnemy={count=90}}})
sources:observe({sequence=19,status='interrupted',kills=4,deaths=0,
    weapon_stats={C={kills=4}},unit_kills={OtherEnemy={count=4}}})
local function selected_sources(lane,filters)
    assert(filters.sequence==20,'native history query is scoped to the expanded match')
    return sources:query(lane,filters)
end
feed=historical({expanded_sequence=20,combat_query=selected_sources})
local source_max=feed.model.max_scroll
local seen_source={}
for scroll=0,math.ceil(source_max/32)do
    feed=historical({expanded_sequence=20,combat_query=selected_sources,scroll=math.min(source_max,scroll*32)})
    draw()
    for index,label in ipairs(feed.model.header_texts)do
        if label.id:match('^match_weapons_')or label.id:match('^match_enemies_')then
            local displayed=node('header'..index).text
            assert(not displayed:find('另一局',1,true),'native history cannot leak another match sources')
            seen_source[displayed]=true
        end
    end
end
assert(seen_source['本局测试步枪']and seen_source['本局轨道攻击']and seen_source['本局重型敌人']and seen_source['本局轻型敌人'])
assert(seen_source['100']and seen_source['20']and seen_source['30']and seen_source['90'],
    'selected match native labels expose independent source and enemy kill counts')
-- Newly approved crush artwork participates in the same fixed native tree.
-- Old body-source counts are a read-only display addition in both locations.
local old_records=records
records={totals={ribbons={crush=3},medals={}}}
local old_body={entries={{sequence=31,status='ended',kills=676,deaths=1,ribbons={},medals={}}}}
local body=dofile(combat_records_path)({vehicle_body_sources={['16474112801385B6']={kind='vehicle_body'}}})
body:observe({sequence=31,status='ended',kills=676,deaths=1,weapon_stats={['16474112801385B6']={kills=154}}})
local derived=body:legacy_crush_summary(old_body)
feed=feed_of({legacy_crush=derived});draw()
assert(node('award_R12_count').text=='x157'and node('award_R12_texture').shown)
assert(node('award_R12_count_back').shown,'new crush count gets the same border-clearing backplate')
feed=historical({history=old_body,expanded_sequence=31,legacy_crush=derived});draw()
assert(node('award_R12_count').text=='x154'and node('award_R12_texture').shown)
assert(old_body.entries[1].ribbons.crush==nil and records.totals.ribbons.crush==3,
    'native legacy display never rewrites either history or the stored cumulative count')
records=old_records
feed=historical();view=draw()
assert(#feed.model.items==0 and control('toggle_match',20) and control('toggle_match',19),'collapsed history lists both matches')
feed=historical({expanded_sequence=20});view=draw()
assert(node('award_R01_count').text=='x5' and node('award_R01_texture').shown)
assert(contains_text('60.00') and contains_text('+5.0000'))
assert(not control('delete_history') and not contains_text('删除'),'history has no deletion control')
feed=historical({expanded_sequence=19});view=draw()
assert(contains_text('记录中断') and contains_text('4/0'))
assert(contains_text('基准未记录'),'missing after value never invents a delta')
-- The two newly merged unknown source/enemy rows can move this award below
-- the first viewport. Reach it by scrolling through the actual native tree.
local recon,recon_scroll
local recon_max=feed.model.max_scroll
for step=0,math.ceil(recon_max/16)do
    local offset=math.min(recon_max,step*16)
    feed=historical({expanded_sequence=19,scroll=offset});view=draw()
    for _,item in ipairs(feed.model.items)do if item.id=='R10'then recon,recon_scroll=item,offset;break end end
    if recon then break end
end
assert(recon,'unknown summaries cannot make the recon award unreachable')
assert(node('award_R10_count').text=='x2' and node('award_R10_texture').shown)
assert(not control('delete_history'))
feed=historical({expanded_sequence=19,scroll=recon_scroll,pointer={x=recon.x+1,y=recon.y+1}});view=draw()
assert(node('tooltip_title').text=='侦察  x2')
feed=historical({expanded_sequence=false});view=draw();assert(#feed.model.items==0,'collapsing hides every item and tooltip')
-- Scroll an expanded match with the full award catalogue through one fixed
-- native tree; each icon is eventually fully visible and every old slot hides.
local many={version=1,revision=1,entries={{sequence=21,status='ended',kills=21,deaths=1,
    ribbons=full_catalog_records.totals.ribbons,medals=full_catalog_records.totals.medals}}}
feed=historical({expanded_sequence=21,history=many});view=draw()
assert(feed.model.max_scroll>0 and contains_text('基准未记录'))
local all_awards={}
local max_scroll=feed.model.max_scroll
for scroll=0,max_scroll+16,16 do
    feed=historical({expanded_sequence=21,history=many,scroll=math.min(scroll,max_scroll)});view=draw()
    for _,item in ipairs(feed.model.items)do
        assert(item.y>=feed.model.list_top and item.y+item.height<=feed.model.list_bottom)
        all_awards[item.id]=true
    end
end
local award_count=0;for _ in pairs(all_awards)do award_count=award_count+1 end;assert(award_count==#dofile(battle_path)({},function()return true end).icons)
local summary={as_of=1720000100,current={kills=220,deaths=4,kd=55},periods={
    {key='24h',from_at=1719913700,to_at=1720000100,missions=2,kills=124,deaths=2,unknown_time=0,
        ribbons={air=5,recon=2},medals={},career={current_kd=55,
            baseline={at=1719913700,kills=100,deaths=2,kd=50},delta=5,
            series={{at=1719913700,kd=50},{at=1719950000,kd=52},{at=1720000100,kd=55}}}},
}}
history.entries[1].ended_at=1720000010;history.entries[2].ended_at=1719990010;history.revision=2
feed=historical({period='24h',summary=summary,summary_expanded=true});view=draw()
assert(feed.model.summary_expanded and control('toggle_summary'),'period summary is expandable')
assert(node('award_R01_count').text=='x5' and node('award_R10_count').text=='x2',
    'period summary displays its own aggregated awards')
assert(control('toggle_summary') and not control('tab_history'),'summary dialog does not expose underlying navigation')
feed=historical({period='24h',summary=summary,summary_expanded=false,expanded_sequence=false});view=draw()
assert(contains_text('55.00') and contains_text('+5.0000'),'period metadata returns after closing the summary')
assert(#feed.model.items==0,'collapsing a period summary hides its old awards')
local function chart_count(v)local n=0;for index=1,97 do if v['chart_'..index]then n=n+1 end end;return n end
assert(feed.model.sparkline and #feed.model.sparkline.points==3,'only real checkpoint samples produce the chart')
local with_chart=chart_count(view)
assert(with_chart==97,'chart has 96 single-pixel columns plus its latest endpoint')
for index=1,96 do
    local field='chart_'..index
    local size,position=view[field..'_size'],view[field..'_position']
    assert(size[1]<=1.00001,'curve uses narrow columns, never filled bounding boxes or regions')
    assert(view[field..'_opacity']==1 and view[field..'_colour'][1]>=.9,'whole curve has the same clear opaque ink')
    assert(node(field).widget_layer_set>baked.numbers.ledger_career_layer,'chart stays above the panel backing')
    if index>1 then
        local prior=view['chart_'..(index-1)..'_position']
        assert(math.abs(position[1]-prior[1]-1)<.00001,'adjacent curve columns stay connected')
    end
end
assert(view.chart_97_size[1]==3 and view.chart_97_size[2]==3,'latest observation has a visible endpoint')
summary.periods[1].career.series=nil
feed=historical({period='24h',summary=summary,summary_expanded=false,expanded_sequence=false});view=draw()
assert(not feed.model.sparkline and with_chart-chart_count(view)==97,'all curve columns and the final point hide without chart data')
feed=historical({history={version=1,revision=1,entries={}}});view=draw()
assert(node('empty_frame').shown and node('empty').text:find('历史',1,true))
assert(#feed.model.items==0)
-- New combat pages use the same retained native tree and flat menu font.
local death={id='death-native',occurred_at=1720000000,sequence=18,category='player',actor_name='队友',
    player={name='演示玩家',peer_id='DEMO-0001',slot=1,slot_index=0,persona_index=0},
    evidence={death_observed='dead_state',source_channel='native_health_last_owner_creditor'},confidence='low'}
feed=feed_of({view='deaths',combat_state={mode='recent',pages={},related_pages={}},combat={rows={death}}});view=draw()
assert(control('tab_deaths') and control('combat_record') and contains_text('队友'),'native death list has real controls')
feed=feed_of({view='weapons',combat_state={pages={},open_id='weapon'},combat={totals={kills=3,known_kinds=1,linked_kills=0},
    rows={{id='weapon',name='AC-8 机炮',kills=3,detail_rows={{id='not-provable',name='未知敌人',kills=3,known=false}}}}}});view=draw()
assert(control('tab_weapons') and contains_text('AC-8') and control('combat_association'),'weapon detail uses retained native controls')
assert(control('combat_association').enabled==false,'unproven associations never become clickable')
feed=feed_of({view='weapons',combat_state={pages={},dropdown={filter='role',scroll=0}},
    combat={totals={kills=3,known_kinds=1,linked_kills=0},rows={}}});view=draw()
assert(feed.model.dropdown and node('dropdown1').text=='* 全部分类' and node('dropdown6').text=='  战备',
    'native select draws its full six-option menu above list labels')
assert(node('dropdown_shape_1').shown,'opaque native dropdown backing is shown')
assert(contains_text('种武器/战备'),'native summary keeps the supported slash glyph')
feed=feed_of({view='enemies',combat_state={pages={}},combat={totals={kills=3,known_kinds=1,linked_kills=0},rows={{id='enemy',name='食腐虫',kills=3}}}});view=draw()
assert(control('tab_enemies') and contains_text('食腐虫'))
assert(not node('dropdown1_frame').shown and not node('dropdown6_frame').shown and not node('dropdown_shape_1').shown,
    'closing a select hides every retained popup slot')
local patriotic_bill={version=1,total_cents=2500,entries={{key='maintenance:las',name='激光维护折旧费',amount_cents=2500}}}
feed=feed_of({view='collection',billing_enabled=true,history={entries={{sequence=2,status='ended',patriotic_bill=patriotic_bill}}}});view=draw()
local bill_entry
for _,c in ipairs(feed.model.nav_controls)do if c.id=='collection_bill'then bill_entry=c end end
assert(bill_entry and bill_entry.action=='tab_bill'and contains_text('爱国账单：25.00 MC'),
    'the collection footer reuses retained native text controls for the actual bill entry')
feed=feed_of({view='bill',billing_enabled=true,history={entries={{sequence=2,status='ended',kills=1,deaths=0,ribbons={},medals={},patriotic_bill=patriotic_bill}}}});view=draw()
assert(control('tab_bill')and contains_text('累计爱国账单')and contains_text('25.00 MC')and contains_text('激光维护折旧费'),
    'real retained native widgets render the sixth tab, actual bill and maintenance name')
feed=feed_of({view='bill',billing_enabled=false});view=draw()
assert(not control('tab_bill')and not contains_text('25.00 MC'),'disabling hides retained bill slots')
-- Exercise every fixed slot, then shrink to one of each. This catches leftover
-- text/active paint when filtering replaces control IDs at the same indices.
feed=feed_of();feed.model.items={};feed.model.sections={};feed.model.tooltip=nil
feed.model.header_texts={};feed.model.nav_controls={}
for index=1,48 do feed.model.header_texts[index]={id='h'..index,text='H'..index,x=0,y=(index-1)*12,
    width=200,height=20,font_size=10+(index%3)*2,align=(index%3)/2,colour={.8,.82,.78,1}}end
for index=1,32 do feed.model.nav_controls[index]={id='dynamic_'..index,text='N'..index,x=210,y=(index-1)*20,
    width=200,height=20,text_x=310,text_y=(index-1)*20+4,align=.5,font_size=12,colour={.7,.8,.6,1},
    enabled=index%2==1,active=index==1,action='toggle_match',sequence=index}end
view=draw();assert(node('header48').text=='H48' and node('nav32').text=='N32')
feed=feed_of();feed.model.items={};feed.model.sections={};feed.model.tooltip=nil
feed.model.header_texts={{id='new',text='new header',x=0,y=10,width=200,height=20,align=0,font_size=12,colour={.8,.82,.78,1}}}
feed.model.nav_controls={{id='new control',text='new action',x=0,y=40,width=200,height=26,text_x=100,text_y=46,
    align=.5,font_size=12,colour={.7,.8,.6,1},enabled=true,active=false}}
view=draw();assert(node('nav1').text=='new action' and node('header1').text=='new header')
feed=feed_of();view=draw()
assert(math.abs(node('nav1').colour[1]-feed.model.nav_controls[1].colour[1])<.001 and node('award_R10_count').text=='x1')
assert(not node('empty_frame').shown)
assert(records.totals.ribbons.air==1 and records.totals.ribbons.recon==1,'render never modifies totals')
local final_nodes=0;for _ in pairs(wf.nodes)do final_nodes=final_nodes+1 end
assert(final_nodes==initial_nodes,'switching views reuses fixed native widgets')
for _,row in ipairs(part.screens[2].rows)do
    if row.kind=='text'then
        local font=wf.nodes[addresses[row.id]].font
        assert(font[1]==2 and font[2]==0 and font[3]==0,'Career labels use the flat menu font variant/style')
    end
end
local cached=step(render_reader,#wants)['ledger.career.feed']
assert(step(render_reader,#wants)['ledger.career.feed']==cached,'unchanged history/collection output stays cached')
feed=nil;draw();assert(not node('block').shown,'cleared feed hides the complete native panel')
assert(widgets:destroy('ledger_career_block'))
assert(wf.nodes[addresses.ledger_career_block].destroyed)
print('PASS: real HUD+ merge/Reader/Widgets, 48 header + 32 generic native slots, five tabs and combat pages, unknown association disabled, history without deletion, full catalogue award scrolling, stale-slot hiding, fixed tree/cache/flat font and materials, 260B lifetime guard.')
