-- Executes the installed HUD+ 0.2.1 Reader and Main.merge in an isolated LuaJIT.
-- Only its final installation entry is removed; no game calls or GUI are made.
local module_path,host_path=assert(arg[1]),assert(arg[2])
local art=arg[3] and assert(dofile(arg[3])) or nil
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a');f:close();return s end
local host_source=read(host_path)
local entry=assert(host_source:find('\nlocal __entry, __argument = __module_registry',1,true))
local old_stingray=rawget(_G,'stingray')
stingray={Application={},Vector2={},Vector3={}}
local host=assert(loadstring(host_source:sub(1,entry)..'\nreturn {modules=__module_registry,errors=__module_errors}'))()
assert(type(host.modules.Reader)=='table' and type(host.modules.Main)=='table','real HUD+ modules did not load')
-- Exercise the real Reader API for the selected installed host generation.
local compiled_reader=host_source:find('computers, compile)',1,true)~=nil
local reader_option=compiled_reader and loadstring or 4
local function step(reader,count)
    if not compiled_reader then return reader:step()end
    return reader:step(function(values)
        local awake={}
        for i=1,count do awake[i]=values['ledger.native.parent']~=nil end
        return awake
    end,.1)
end

assert(type(host.modules.GameBaked)=='table','real baked native profile did not load')
assert(#host.errors==0,table.concat(host.errors,'\n'))
local factory=assert(dofile(module_path))
local make_layout=assert(dofile(arg[4] or module_path:gsub('native%-hud%-addon%.lua$','hud-layout.lua')))
local layout=make_layout()
local animation_time=0
local feed={shown=true,hud=68993637784,position={0,-96},scale={1,1},opacity=.82,
    kills=11,shots=120,bill='346.60 SC',kd='11.00',history_kd='34.50',map_open=true,
    block_height=109,size={600,109},now=0,sequence=1}
local function refresh_layout()
    if not feed or (feed.immutable and feed.layout) then return feed end
    feed.layout=layout:build({kills=feed.kills,shots=feed.shots,bill_text=feed.bill,
        kd_text=feed.kd..'［'..feed.history_kd..(feed.arrow or '')..'］'},
        {ribbons=feed.ribbons or {},medals=feed.medals or {},hits=feed.hits or {},
            items=feed.side or {},deadline=feed.deadline},feed.map_open,600,
        {items=feed.charges or {},deadline=feed.deadline},feed.now,feed.sequence,
        {hit_position=feed.hit_position,charge_position=feed.charge_position})
    return feed
end
local function tick(value) animation_time=value;feed.now=value end
local part=factory({feed=refresh_layout,publish=false,clock=function()return animation_time end})
local baked=host.modules.GameBaked
local count=#baked.screens
assert(host.modules.Main.merge(baked,part)==nil,'native host rejected real addon shape')
assert(#baked.screens==count+1 and baked.screens[#baked.screens].id=='ledger.native.stats')
assert(baked.sources['ledger.native.parent'].offset=='ledger_native_right_parent')
assert(baked.numbers.ledger_native_right_parent==0x2944A0)
local read_calls,native_calls=0,0
local reader_api={module=function(_,name)assert(name=='game');return 1000000 end,
    ptr=function(_,at)read_calls=read_calls+1;assert(at==1000000+baked.numbers.roots_hud_manager_rva);return feed and feed.hud or 68993637784 end}
reader_api.loads={ptr=function(at)return reader_api:ptr(at)end}
local reader=host.modules.Reader.new(reader_api,baked.sources,baked.numbers,nil,part.compute,reader_option)
local wanted={value={'ledger.native.kills','ledger.native.shots','ledger.native.kd','ledger.native.bill','ledger.native.feed'},
    position={'ledger.native.parent','ledger.native.position','ledger.native.scale','ledger.native.size'},
    paint={'ledger.native.opacity'},life={}}
if compiled_reader then wanted.parent={'ledger.native.parent'};table.remove(wanted.position,1)end
assert(reader:plan({{wanted=wanted}}))
local tests=0
local function check(label,fn)fn();tests=tests+1;print('PASS '..label)end
check('installed HUD+ merge and real Reader produce cached ledger text',function()
    local values=step(reader,1)
    assert(values['ledger.native.kills']=='11')
    assert(values['ledger.native.shots']=='120')
    assert(values['ledger.native.bill']=='346.60 SC')
    assert(values['ledger.native.kd']=='11.00[34.50]')
    assert(values['ledger.native.parent']==feed.hud+0x2944A0)
    assert(part.native_hud_status.ready and part.native_hud_status.status=='feed_ready')
end)
check('same feed table mutated in place refreshes every native Reader step',function()
    local before=part.native_hud_status.feed_runs
    for n=12,20 do
        feed.kills=n
        assert(step(reader,1)['ledger.native.kills']==tostring(n))
    end
    assert(part.native_hud_status.feed_runs==before+9)
end)
check('unchanged frames reuse the sanitized view and do not read native statistics',function()
    local a=step(reader,1)['ledger.native.feed']
    local accepted=part.native_hud_status.accepted
    for _=1,100 do assert(step(reader,1)['ledger.native.feed']==a)end
    assert(part.native_hud_status.accepted==accepted)
    assert(native_calls==0 and read_calls<=112,'only existing HUD-manager identity may be read; '..read_calls..' reads')
end)
check('zero deaths and ASCII KD stay legible when indicator art is unavailable',function()
    local kd,history=feed.kd,feed.history_kd
    feed.kd='109/0';feed.history_kd='75.94';feed.arrow='↑'
    assert(step(reader,1)['ledger.native.kd']=='109/0[75.94]')
    feed.arrow='↓';assert(step(reader,1)['ledger.native.kd']=='109/0[75.94]')
    feed.arrow='';assert(step(reader,1)['ledger.native.kd']=='109/0[75.94]')
    feed.kd=kd;feed.history_kd=history
end)
check('map geometry and user scale stay local to original parent',function()
    feed.position={15,-140};feed.scale={.8,.8};feed.size={600,200};feed.map_open=false
    local v=step(reader,1)
    assert(v['ledger.native.position'][1]==15 and v['ledger.native.position'][2]==-140)
    assert(v['ledger.native.size'][2]==200 and v['ledger.native.scale'][1]==.8)
    local row=part.screens[1].rows[1]
    assert(row.anchor[2]==1 and row.pivot[2]==1 and row.transform.position=='ledger.native.position')
end)
check('F8 hidden feed clears all native content and readiness',function()
    feed.shown=false
    local v=step(reader,1)
    assert(v['ledger.native.feed']==nil and v['ledger.native.kills']==nil and v['ledger.native.parent']==nil)
    assert(not part.native_hud_status.ready)
    feed.shown=true
    assert(step(reader,1)['ledger.native.kills']=='20')
end)
check('lost cache hides native group',function()
    local saved=feed;feed=nil
    assert(step(reader,1)['ledger.native.feed']==nil and not part.native_hud_status.ready)
    feed=saved
end)
check('identity mismatch never mounts cached view on a different HUD',function()
    local run=part.compute.ledger_cached_feed.run
    assert(run(nil,nil,nil,nil,{hud=feed.hud+8})==nil)
    assert(part.native_hud_status.status=='hud_identity_changed')
end)
check('invalid geometry and control text are hidden before native setters',function()
    local position=feed.position;feed.position={0,0/0}
    assert(step(reader,1)['ledger.native.feed']==nil)
    feed.position=position
    local kills=feed.kills;feed.kills='1\n2'
    assert(step(reader,1)['ledger.native.kills']==nil)
    feed.kills=kills
    local opacity=feed.opacity;feed.opacity=2
    assert(step(reader,1)['ledger.native.feed']==nil)
    feed.opacity=opacity
end)
check('native text uses the shipped HUD font family and variant, not screen font',function()
    assert(baked.numbers.hud_text_font==2 and baked.numbers.hud_text_variant==1)
    for i=2,#part.screens[1].rows do
        local row=part.screens[1].rows[i]
        if row.kind=='text' then
            assert(row.parent==row.id..'_frame')
            assert(row.font[1]=='hud_text_font' and row.font[2]=='hud_text_variant' and row.font[3]=='hud_text_variant')
        else assert(row.kind=='frame') end
    end
end)
check('default bridge consumes only exported cached snapshot and reports its state',function()
    local calls=0
    rawset(_G,'HD2WarCostLedgerV1',{native_hud_snapshot=function()calls=calls+1;return refresh_layout() end})
    local p=factory()
    local value=p.compute.ledger_cached_feed.run(nil,nil,nil,nil,{hud=feed.hud})
    assert(value and calls==1 and rawget(_G,'HD2WarCostLedgerNativeHUDV1')==p.native_hud_status)
    assert(p.native_hud_status.ready and not p.native_hud_status.pixels_verified)
    rawset(_G,'HD2WarCostLedgerV1',nil)
    assert(p.compute.ledger_cached_feed.run(nil,nil,nil,nil,{hud=feed.hud})==nil)
end)
check('feed errors remain contained without disabling native host',function()
    local p=factory({feed=function()error('offline fixture')end,publish=false})
    assert(p.compute.ledger_cached_feed.run(nil,nil,nil,nil,{hud=feed.hud})==nil)
    assert(p.native_hud_status.status=='feed_error' and not p.native_hud_status.ready)
end)
check('real native host rejects wrong builds and conflicting addon identities',function()
    assert(host.modules.Main.merge(baked,part)=='conflict')
    local p=factory({publish=false});p.pin.game='wrong'
    assert(host.modules.Main.merge(baked,p)=='pin')
end)
-- The real shipped Widgets module below runs unchanged. Only native IO is a
-- deterministic in-memory fixture. This validates its actual ABI/data contract,
-- constructor/context lifecycle and setters; it does not claim engine pixels.
local ffi=require('ffi')
local Bytes=host.modules.Bytes
local n=baked.numbers
local memory,nodes,calls={}, {}, {}
local next_at,base,context,slot=100000000,200000000,200000000+n.gui_context_stride,1
local function store(at,raw)for i=1,#raw do memory[at+i-1]=raw:sub(i,i) end end
local function packf(v)return ffi.string(ffi.new('float[1]',v),4)end
local function atvalue(at,v,width)store(at,Bytes.pack(v,width or 8))end
local function span(at,size)
    local bytes={}
    for i=0,size-1 do if not memory[at+i] then return nil end;bytes[#bytes+1]=memory[at+i] end
    return table.concat(bytes)
end
local native_read={bytes=Bytes,module=function()return 1000000 end,
    span=function(_,at,size)return span(at,size)end,
    value=function(_,at,form)local raw=span(at,Bytes.WIDTH[form]);return raw and Bytes.decode(raw,0,form)end,
    ptr=function(_,at)local raw=span(at,8);if not raw then return nil end;local v=Bytes.u32(raw,0)+Bytes.u32(raw,4)*4294967296;return v~=0 and v or nil end}
-- HUD+ 0.2.4 batches adjacent native fields through layout/value.
native_read.layout=function(fields)
    local layout={n=#fields,at={},form={}}
    for i,field in ipairs(fields)do layout.at[i],layout.form[i]=field[1],field[2]end
    return layout
end
local single_value=native_read.value
native_read.vector=function(self,at,count)
    local value={}
    for i=1,count do
        value[i]=single_value(self,at+(i-1)*4,'f32')
        if value[i]==nil then return nil end
    end
    return value
end
native_read.loads={ptr=function(at)return native_read:ptr(at)end}
for form in pairs(Bytes.WIDTH)do
    local kind=form
    native_read.loads[kind]=function(at)return single_value(native_read,at,kind)end
end
native_read.value=function(self,at,form,got)
    if type(form)=='table'then
        got=got or {}
        for i=1,form.n do got[i]=single_value(self,at+form.at[i],form.form[i])end
        return got
    end
    return single_value(self,at,form or 'u32')
end
local native_ui={}
function native_ui:status()return true end
function native_ui:routine(name)assert(type(n[name])=='number','missing actual native ABI '..name);return name end
function native_ui:own(raw)
    local at=next_at;next_at=next_at+math.ceil(#raw/16)*16+16;store(at,raw);return at
end
function native_ui:pair(x,y)return{x,y}end
function native_ui:bits(v)return Bytes.u32(packf(v),0)end
function native_ui:uint64_of(v)assert(type(v)=='string' and #v==16);return v end
function native_ui:buffer(_,count)local v={};for i=0,count-1 do v[i]=0 end;return v end
local function record(name,...)local args={...};calls[#calls+1]={name=name,args=args};return args end
local function initialize(at,kind)
    assert(native_read:value(base+n.gui_context_top,'i32')==0,'constructor without pushed native context')
    assert(native_read:value(base+n.gui_context_stack,'u8')==slot)
    atvalue(at,1,4);atvalue(at+n.widget_gui_context,context);atvalue(at+n.widget_parent,0)
    store(at+n.widget_local_position,packf(0)..packf(0));store(at+n.widget_local_size,packf(0)..packf(0))
    store(at+n.widget_local_opacity,packf(1))
    nodes[at]={kind=kind,children={},shown=true,uniforms={}}
end
local function detach(at)
    local parent=native_read:ptr(at+n.widget_parent)
    if parent and nodes[parent] then nodes[parent].children[at]=nil end
    atvalue(at+n.widget_parent,0)
end
local function destroy(at)
    for child in pairs(nodes[at].children)do destroy(child)end
    detach(at);atvalue(at,0,4);nodes[at].destroyed=true
end
function native_ui:call(name,...)
    local a=record(name,...);local at=a[1]
    if name=='ui_context_push' then
        assert(a[1]==base and a[2]==slot);atvalue(base+n.gui_context_top,0,4);atvalue(base+n.gui_context_stack,slot,1)
    elseif name=='ui_context_pop' then atvalue(base+n.gui_context_top,4294967295,4)
    elseif name=='widget_init' or name=='string_text_make' or name=='picture_init' then initialize(at,name)
    elseif name=='widget_attach' then
        local child=a[2];assert(nodes[at] and nodes[child]);assert(native_read:ptr(child+n.widget_parent)==nil,'already attached')
        assert(native_read:ptr(at+n.widget_gui_context)==native_read:ptr(child+n.widget_gui_context))
        nodes[at].children[child]=true;atvalue(child+n.widget_parent,at)
    elseif name=='widget_detach' then detach(at)
    elseif name=='widget_destroy' then destroy(at)
    elseif name=='widget_shown_set' then nodes[at].shown=a[2]==1
    elseif name=='widget_position_set' or name=='widget_size_set' then
        local offset=name=='widget_position_set' and n.widget_local_position or n.widget_local_size
        store(at+offset,packf(a[2][1])..packf(a[2][2]));nodes[at][name]=a[2]
    elseif name=='widget_opacity_set' then store(at+n.widget_local_opacity,packf(a[2]));nodes[at].opacity=a[2]
    elseif name=='text_font_set' then nodes[at].font={a[2],a[3],a[4]};assert(a[5]==1 and a[6]==0)
    elseif name=='text_string_set' then nodes[at].text=a[2]
    elseif name=='text_size_set' then nodes[at].font_height=a[2]
    elseif name=='measure_widget' then
        local node=nodes[at];local glyphs=0
        for b in (node.text or ''):gmatch('.')do if b:byte()<128 or b:byte()>=192 then glyphs=glyphs+1 end end
        local h=node.font_height or 14
        store(at+n.widget_local_size,packf(glyphs*h*.60)..packf(h))
    elseif name=='picture_set' then
        -- This is the shipped NativeWidgets call order: widget, material,
        -- texture, flags. Compiled texture hashes are used directly.
        assert((a[2]==n.mask_material or (HD2_CAREER_FLAT_FIXTURE and a[2]==a[3]))
            and type(a[3])=='string' and #a[3]==16 and a[4]==0)
        nodes[at].material=a[2];nodes[at].texture=a[3]
    elseif name=='picture_texture_set' then nodes[at].texture=a[2]
    elseif name=='widget_material_get' then assert(nodes[at].material);return at+4096
    elseif name=='material_var_set' then
        local v={};for i=0,3 do v[i+1]=a[3][i] end;nodes[at].uniforms[a[2]]=v
    elseif name=='widget_color_set' then
        nodes[at].colour={a[2][0],a[2][1],a[2][2]}
    elseif name:match('^widget_.*_set$') then nodes[at][name]=a[2]
    else error('unmodeled native call '..name) end
end
atvalue(1000000+n.gui_contexts,base);atvalue(context,1,1)
atvalue(base+n.gui_context_top,4294967295,4);atvalue(base+n.gui_context_stack,0,1)
local parent=feed.hud+0x2944A0
local function parent_node(at)
    nodes[at]={children={},native=true};atvalue(at,1,4);atvalue(at+n.widget_gui_context,context);atvalue(at+n.widget_parent,0)
end
parent_node(parent)
atvalue(1000000+n.roots_hud_manager_rva,feed.hud)
local curve_at=1000000+n.picture_bend_data
store(curve_at,packf(.01)..packf(.02)..packf(.03)..packf(.04))
local complete=factory({feed=refresh_layout,publish=false,art=art,clock=function()return animation_time end})
local sources={};for k,v in pairs(baked.sources)do sources[k]=v end
for k,v in pairs(complete.sources)do sources[k]=v end
local native_reader=host.modules.Reader.new(native_read,sources,n,nil,complete.compute,reader_option)
local wanted_rows={}
for _,row in ipairs(complete.screens[1].rows)do wanted_rows[#wanted_rows+1]={wanted=host.modules.Widgets.wanted(row)}end
wanted_rows[#wanted_rows+1]={wanted={value={},position={'ledger.native.parent'},paint={},life={}}}
if compiled_reader then wanted_rows[#wanted_rows].wanted.parent=wanted_rows[#wanted_rows].wanted.position;wanted_rows[#wanted_rows].wanted.position={}end
assert(native_reader:plan(wanted_rows))
local widgets=host.modules.Widgets.new(native_read,native_ui,{},n)
local addresses
check('real Widgets validates constructors and mounts every component in native parent context',function()
    local why,observed
    addresses,why,observed=widgets:make(parent,complete.screens[1].rows)
    assert(addresses,why..': '..tostring(widgets.failed_detail))
    assert(observed.stack_before==-1 and observed.stack_after==-1 and observed.context_slot==1)
    assert(native_read:ptr(addresses.ledger_block+n.widget_parent)==parent)
    for _,row in ipairs(complete.screens[1].rows)do
        local at=addresses[row.id]
        assert(at and native_read:ptr(at+n.widget_gui_context)==context)
        if row.parent then assert(native_read:ptr(at+n.widget_parent)==addresses[row.parent])end
    end
    assert(not complete.native_hud_status.pixels_verified)
end)
local function put_all()
    local values=step(native_reader,#wanted_rows)
    for _,row in ipairs(complete.screens[1].rows)do assert(widgets:put(row.id,values),row.id..': '..tostring(widgets.failed_detail))end
    return values
end
check('real Widgets renders icon statistics and right-aligned values with native font',function()
    feed.bill='12,345,678.90$';feed.kd='99999.00';feed.history_kd='99999.00'
    local v=put_all()
    assert(nodes[addresses.ledger_bill].text==feed.bill and not addresses.ledger_bill_label)
    assert(not addresses.ledger_fire)
    assert(nodes[addresses.ledger_kd].text=='99999.00[99999.00]')
    for _,field in ipairs({'bill','kd'})do
        local row
        for _,r in ipairs(complete.screens[1].rows)do if r.id=='ledger_'..field then row=r end end
        local width=native_read:value(addresses[row.id]+n.widget_local_size,'f32')
        assert(row.pivot[1]==1 and row.position[1]==0 and 600-width>=450,'stats exceed native block')
        assert(native_read:value(addresses[row.id..'_frame']+n.widget_local_position,'f32')==600)
        assert(nodes[addresses[row.id]].font[1]==2 and nodes[addresses[row.id]].font[2]==1 and nodes[addresses[row.id]].font[3]==1)
    end
    assert(v['ledger.native.parent']==parent and nodes[addresses.ledger_block].shown)
end)
check('bill and charge notices show each selected currency without a text label',function()
    for _, symbol in ipairs({' SC','$','¥','€','£','kr'}) do
        feed.bill='2500.00'..symbol
        feed.charges={{id='stims',name='治疗针',text='治疗针 -2500.00'..symbol}}
        put_all()
        assert(nodes[addresses.ledger_bill].text==feed.bill)
        assert(nodes[addresses.ledger_charge_1].text=='治疗针 -2500.00'..symbol)
        assert(native_read:value(addresses.ledger_charge_1_frame+n.widget_local_position,'f32')==600)
    end
    feed.bill='2500.00 SC';feed.charges={};put_all()
    assert(not nodes[addresses.ledger_charge_1_frame].shown)
end)
check('fractional GBP charges retain the less-than marker in native widgets',function()
    feed.bill='<0.01£'
    feed.charges={{id='ammo',name='单发弹药',text='单发弹药 -<0.01£'}}
    put_all()
    assert(nodes[addresses.ledger_bill].text=='<0.01£')
    assert(nodes[addresses.ledger_charge_1].text=='单发弹药 -<0.01£')
    feed.charges={};put_all()
end)
if art then
    check('compiled resource_require wrapper returns a complete native addon table',function()
        local compiled_path=arg[3]:gsub('native%-game%-art%.lua$','native-hud-addon.lua')
        local compiled=read(compiled_path)
        assert(compiled:find((read(module_path):gsub('\r\n','\n')),1,true),'compiled wrapper must contain current module')
        local resource='mods/hd2_costs/war_cost_native_hud'
        package.preload[resource]=function()return assert(loadstring(compiled))()end
        package.loaded[resource]=nil
        local loaded,why=host.modules.ResourceLoad.load(resource)
        assert(loaded,why);assert(type(loaded)=='table' and loaded.native_hud_status.art_count==#art.images)
        assert(loaded.native_hud_status.metric_count==4)
        assert(loaded.native_hud_status.indicator_count==2)
        assert(#loaded.screens[1].rows==#complete.screens[1].rows)
        -- Fresh real GameBaked from the immutable original, not the fixture
        -- already merged above: Core.merge validates the deployment artifact.
        local original=assert(loadstring(host_source:sub(1,entry)..'\nreturn __module_registry'))()
        assert(original.Main.merge(original.GameBaked,loaded)==nil)
        package.preload[resource]=nil;package.loaded[resource]=nil
    end)
    check('native KD arrows sit after history inside ASCII brackets and hide on equality',function()
        local kd,history=feed.kd,feed.history_kd
        feed.kd='109/0';feed.history_kd='75.94'
        local owned=next_at
        for _,case in ipairs({{arrow='↑',id='I01',other='I02'},{arrow='↓',id='I02',other='I01'}})do
            feed.arrow=case.arrow;put_all()
            assert(nodes[addresses.ledger_kd].text=='109/0[75.94')
            assert(nodes[addresses.ledger_kd_suffix].text==']' and nodes[addresses.ledger_kd_suffix_frame].shown)
            local icon=addresses['ledger_indicator_'..case.id..'_texture']
            assert(nodes[icon].shown and not nodes[addresses['ledger_indicator_'..case.other..'_texture']].shown)
            assert(native_read:ptr(icon+n.widget_parent)==addresses.ledger_block)
            assert(nodes[icon].uniforms[n.mask_c2][1]>.009)
            local body_x=native_read:value(addresses.ledger_kd_frame+n.widget_local_position,'f32')
            local suffix_x=native_read:value(addresses.ledger_kd_suffix_frame+n.widget_local_position,'f32')
            local suffix_width=native_read:value(addresses.ledger_kd_suffix+n.widget_local_size,'f32')
            local ix=native_read:value(icon+n.widget_local_position,'f32')
            local iw=native_read:value(icon+n.widget_local_size,'f32')
            assert(body_x<ix and ix+iw<suffix_x-suffix_width,'arrow between history digits and bracket without overlap')
        end
        feed.arrow='';put_all()
        assert(nodes[addresses.ledger_kd].text=='109/0[75.94]')
        assert(not nodes[addresses.ledger_kd_suffix_frame].shown)
        assert(not nodes[addresses.ledger_indicator_I01_texture].shown and not nodes[addresses.ledger_indicator_I02_texture].shown)
        assert(next_at==owned,'direction changes reuse the native widget tree')
        feed.kd=kd;feed.history_kd=history;put_all()
    end)
    check('all 24 unit ribbons mount and draw bound frames and count backings in collection and side groups',function()
        local rows,units={},{}
        for _,row in ipairs(complete.screens[1].rows)do rows[row.id]=row end
        for _,asset in ipairs(art.images)do
            if asset.id:match('^[GT]')then units[asset.id]=asset end
        end
        local ids={}
        for _,family in ipairs({{'G',6},{'T',18}})do
            for index=1,family[2]do ids[#ids+1]=string.format('%s%02d',family[1],index)end
        end
        local actual=0;for _ in pairs(units)do actual=actual+1 end
        assert(actual==24,'exactly six giant and eighteen heavy native ribbon assets')
        for _,id in ipairs(ids)do
            assert(units[id],id..' unit asset is missing')
            for _,group in ipairs({'collected','side'})do
                local prefix=group..'_'..id..'_'
                for _,suffix in ipairs({'frame','count_back'})do
                    local widget='ledger_'..prefix..suffix
                    local row=assert(rows[widget],widget..' native image control is missing')
                    assert(row.kind=='image' and row.parent=='ledger_block',widget..' must be a native image child')
                    assert(addresses[widget] and nodes[addresses[widget]],widget..' was not actually constructed')
                    assert(row.source=='ledger.native.'..prefix..suffix,widget..' source alias')
                    assert(complete.sources[row.source].from=='ledger.native.feed'
                        and complete.sources[row.source].part==prefix..suffix,widget..' cached field binding')
                    local position=prefix..(suffix=='frame' and 'frame_position' or 'count_back_position')
                    local size=prefix..(suffix=='frame' and 'frame_size' or 'count_back_size')
                    assert(row.transform.position=='ledger.native.'..position
                        and row.transform.size=='ledger.native.'..size,widget..' geometry binding')
                end
            end
        end
        for _,asset in ipairs(art.images)do
            if asset.id:sub(1,1)=='M'then
                for _,group in ipairs({'collected','side'})do
                    local prefix='ledger_'..group..'_'..asset.id..'_'
                    assert(not rows[prefix..'frame'] and not rows[prefix..'count_back'],
                        asset.id..' medals must not gain horizontal ribbon frames or count backings')
                end
            end
        end
        local owned=next_at
        for _,group in ipairs({'collected','side'})do
            feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{}
            for _,id in ipairs(ids)do
                local item={id=id,kind='ribbon',count=123,total=123}
                table.insert(group=='collected' and feed.ribbons or feed.side,item)
            end
            table.insert(group=='collected' and feed.hits or feed.side,
                {id='H04',kind='ribbon',side_icon=true,count=2,total=2})
            table.insert(group=='collected' and feed.medals or feed.side,
                {id='M12',kind='medal',name='摧毁暴政减速带',count=1,total=1})
            feed.map_open=true;tick(group=='collected' and 9.4 or 9.6);put_all()
            tick(group=='collected' and 9.6 or 9.8)
            local view=put_all()['ledger.native.feed']
            for _,id in ipairs(ids)do
                local prefix=group..'_'..id..'_'
                local texture=nodes[addresses['ledger_'..prefix..'texture']]
                assert(texture.shown and texture.texture==units[id].resource_hash,id..' native glyph draw')
                for _,suffix in ipairs({'frame','count_back'})do
                    local at=addresses['ledger_'..prefix..suffix]
                    local node=nodes[at]
                    assert(node.shown,id..' '..group..' '..suffix..' must be drawn')
                    assert(node.texture==(suffix=='frame' and art.frame.resource_hash or art.ui.solid.resource_hash),
                        id..' '..group..' '..suffix..' native texture binding')
                    assert(node.material==n.mask_material and native_read:ptr(at+n.widget_parent)==addresses.ledger_block)
                    local position=view[prefix..(suffix=='frame' and 'frame_position' or 'count_back_position')]
                    local size=view[prefix..(suffix=='frame' and 'frame_size' or 'count_back_size')]
                    for axis=1,2 do
                        assert(math.abs(native_read:value(at+n.widget_local_position+(axis-1)*4,'f32')-position[axis])<.001)
                        assert(math.abs(native_read:value(at+n.widget_local_size+(axis-1)*4,'f32')-size[axis])<.001)
                    end
                end
                assert(nodes[addresses['ledger_'..prefix..'count']].text=='x123',id..' fixed counter text')
                local counter=addresses['ledger_'..prefix..'count_frame']
                for axis=1,2 do
                    assert(math.abs(native_read:value(counter+n.widget_local_position+(axis-1)*4,'f32')
                        -view[prefix..'count_position'][axis])<.001,id..' counter position must retain its own binding')
                end
            end
            assert(nodes[addresses['ledger_'..group..'_H04_texture']].shown)
            assert(not nodes[addresses['ledger_'..group..'_H04_frame']].shown
                and not nodes[addresses['ledger_'..group..'_H04_count_back']].shown,
                'H side_icon remains borderless in both placements')
            assert(nodes[addresses['ledger_'..group..'_M12_texture']].shown)
            assert(next_at==owned,'unit ribbon displays reuse the existing native control tree')
        end
        feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{}
    end)
    check('catalogue awards and four metrics use native pictures with curved mask uniforms',function()
        assert(#art.images>=21 and #art.metrics==4 and complete.native_hud_status.art_count==#art.images)
        feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{}
        for _,asset in ipairs(art.images)do
            local item={id=asset.id,kind=asset.id:match('^[RHGT]') and 'ribbon' or 'medal',count=3,total=3}
            if asset.id:sub(1,1)=='H' and asset.id~='H01' then
                item.side_icon=true;table.insert(feed.hits,item)
            else table.insert(item.kind=='ribbon' and feed.ribbons or feed.medals,item) end
        end
        feed.map_open=true;tick(10)
        put_all()
        for _,asset in ipairs(art.images)do
            local node=nodes[addresses['ledger_collected_'..asset.id..'_texture']]
            assert(node.shown and node.texture==asset.resource_hash and node.material==n.mask_material)
            assert(node.uniforms[n.mask_c0][1]==1 and node.uniforms[n.mask_c1][4]==1)
            assert(math.abs(node.uniforms[n.mask_c2][1]-.01)<.000001)
            if asset.id:match('^[RGT]') or asset.id=='H01' then
                local frame_node=nodes[addresses['ledger_collected_'..asset.id..'_frame']]
                assert(frame_node.shown and frame_node.texture==art.frame.resource_hash)
            end
        end
        for _,asset in ipairs(art.metrics)do
            local node=nodes[addresses['ledger_metric_'..asset.id..'_texture']]
            assert(node.shown and node.texture==asset.resource_hash and node.material==n.mask_material)
            assert(node.uniforms[n.mask_c2][1]>.009)
        end
    end)
    check('three right-aligned side rows render bottom-right counts and wrapped medal name',function()
        feed.medals,feed.ribbons,feed.hits={},{},{}
        feed.side={{id='H04',kind='ribbon',side_icon=true,count=7,total=7},
            {id='R01',kind='ribbon',count=1,total=1},
            {id='M04',kind='medal',name='血管中全是自由的香气',count=1,total=1}}
        local owned=next_at;tick(11);put_all();tick(11.2);put_all()
        local positions={}
        for _,id in ipairs({'H04','R01','M04'})do
            local owner=addresses['ledger_side_'..id..'_count_frame']
            assert(nodes[addresses['ledger_side_'..id..'_texture']].shown)
            assert(native_read:value(owner+n.widget_local_position,'f32')==600,'shared right edge')
            positions[#positions+1]=native_read:value(owner+n.widget_local_position+4,'f32')
        end
        assert(positions[1]>positions[2] and positions[2]>positions[3],'three distinct rows top to bottom')
        assert(nodes[addresses.ledger_side_R01_count].text=='x1')
        assert(nodes[addresses.ledger_side_M04_name1].text=='血管中全是自由的香')
        assert(nodes[addresses.ledger_side_M04_name2].text=='气')
        assert(native_read:value(addresses.ledger_side_M04_name1_frame+n.widget_local_position,'f32')==600)
        local icon_y=native_read:value(addresses.ledger_side_R01_frame+n.widget_local_position+4,'f32')
        assert(math.abs(positions[2]-(icon_y-20))<.001,'ribbon count is at bottom right')
        local readable=step(native_reader,#wanted_rows)['ledger.native.feed']
        local mask=nodes[addresses.ledger_side_R01_count_back]
        assert(mask.shown and mask.texture==art.ui.solid.resource_hash)
        assert(baked.numbers.ledger_count_back_layer>baked.numbers.hud_text_layer
            and baked.numbers.ledger_count_text_layer>baked.numbers.ledger_count_back_layer,
            'native depth orders original border < count backing < fixed-position number')
        assert(mask.uniforms[n.mask_c0][1]<.06 and mask.uniforms[n.mask_c0][4]==1,
            'full-R solid uses the dark primary channel with opaque alpha')
        assert(readable.side_R01_count_back_position[1]<readable.side_R01_count_position[1])
        assert(next_at==owned,'notification changes may not allocate another widget tree')
    end)
    check('popup shift moves transient icons counts names and charges while metrics and collection stay fixed',function()
        local function y(id)return native_read:value(addresses[id]+n.widget_local_position+4,'f32')end
        local moving={'ledger_side_H04_texture','ledger_side_H04_count_frame',
            'ledger_side_R01_frame','ledger_side_R01_texture','ledger_side_R01_count_frame',
            'ledger_side_M04_texture','ledger_side_M04_count_frame','ledger_side_M04_name1_frame',
            'ledger_side_M04_name2_frame','ledger_charge_1_frame'}
        local fixed={'ledger_metric_U01_texture','ledger_kills_frame','ledger_kd_frame',
            'ledger_collected_R02_texture','ledger_collected_R02_count_frame'}
        feed.ribbons={{id='R02',kind='ribbon',count=4,total=4}}
        feed.charges={{id='stims',name='治疗针',text='治疗针 -2500.00 SC'}}
        feed.popup_shift=0;put_all()
        local positions={}
        for _,ids in ipairs({moving,fixed})do for _,id in ipairs(ids)do positions[id]=y(id)end end
        feed.popup_shift=360;put_all()
        for _,id in ipairs(moving)do assert(math.abs(y(id)-(positions[id]-360))<.001,id)end
        for _,id in ipairs(fixed)do assert(y(id)==positions[id],id)end
        local side=feed.side
        feed.side={};feed.ribbons[#feed.ribbons+1]=side[2];feed.medals={side[3]};put_all()
        local ribbon_y,medal_y=y('ledger_collected_R01_texture'),y('ledger_collected_M04_texture')
        feed.popup_shift=0;put_all()
        assert(y('ledger_collected_R01_texture')==ribbon_y and y('ledger_collected_M04_texture')==medal_y,
            'stored awards do not inherit transient shift')
        feed.side=side;feed.ribbons={};feed.medals={};feed.charges={};put_all()
    end)
    check('150 percent popup art and text preserve one right edge and leave top metrics unchanged',function()
        feed.charges={{id='stims',name='治疗针',text='治疗针 -2500.00 SC'}}
        local before=put_all()['ledger.native.feed']
        local count_scale=nodes[addresses.ledger_side_R01_count_frame].widget_scale_set[1]
        local owned=next_at
        feed.popup_scale=1.5;feed.popup_shift_x=-24
        local view=put_all()['ledger.native.feed']
        assert(math.abs(view.side_R01_frame_size[1]/before.side_R01_frame_size[1]-1.5)<.001)
        assert(math.abs(nodes[addresses.ledger_side_R01_count_frame].widget_scale_set[1]-count_scale*1.5)<.001)
        assert(nodes[addresses.ledger_side_M04_name1_frame].widget_scale_set[1]==1.5)
        assert(nodes[addresses.ledger_charge_1_frame].widget_scale_set[1]==1.5)
        assert(view.charge_1_position[1]==576 and math.abs(view.side_M04_name1_position[1]-603)<.001,
            'new medal starts its 27px (18 x 1.5) entry slide before settling; actual '..tostring(view.side_M04_name1_position[1]))
        tick(11.4);view=put_all()['ledger.native.feed']
        assert(view.charge_1_position[1]==576 and view.side_M04_name1_position[1]==576,
            'settled 150 percent medal name and charge share the right edge')
        assert(view.kills_position[1]==before.kills_position[1] and view.kills_position[2]==before.kills_position[2])
        assert(next_at==owned,'larger notices reuse the same native widgets')
        feed.popup_scale=nil;feed.popup_shift_x=nil;feed.charges={};put_all()
    end)
    check('all nine hit and charge choices reach real Widgets while ribbons remain right',function()
        local owned=next_at
        feed.charges={{id='stims',name='治疗针',text='治疗针 -2500.00 SC'}}
        feed.center_position={220,-420};feed.popup_scale=1.5
        feed.popup_shift_x=-24;feed.popup_shift=360
        for _,hit in ipairs({'right','center','hidden'})do
            for _,charge in ipairs({'right','center','hidden'})do
                feed.hit_position,feed.charge_position=hit,charge
                local view=put_all()['ledger.native.feed']
                assert(nodes[addresses.ledger_side_H04_count].shown==(hit~='hidden'))
                assert(nodes[addresses.ledger_charge_1].shown==(charge=='right'))
                assert(nodes[addresses.ledger_center_charge_1].shown==(charge=='center'))
                if hit=='center'then
                    local box=feed.layout.center_hits[1]
                    local x=220+feed.layout.center_hit_width*1.5/2
                    assert(math.abs(view.side_H04_count_position[1]-x)<.001)
                    assert(math.abs(view.side_H04_count_position[2]-(-420-box.count_y*1.5))<.001)
                elseif hit=='right'then
                    assert(view.side_H04_count_position[1]==576)
                end
                if charge=='center'then
                    assert(view.center_charge_1_position[1]==220)
                    assert(view.center_charge_1_position[2]==-420-feed.layout.center_charges[1].text_y*1.5)
                    assert(nodes[addresses.ledger_center_charge_1].widget_pivot_set[1]==.5)
                end
                assert(nodes[addresses.ledger_side_R01_texture].shown)
                assert(view.side_R01_count_position[1]==576,'ribbons follow the right pickup anchor')
                assert(next_at==owned,'changing notice position must reuse native widgets')
            end
        end
        feed.hit_position,feed.charge_position=nil,nil
        feed.center_position=nil;feed.popup_scale=nil;feed.popup_shift_x=nil;feed.popup_shift=0
        feed.charges={};put_all()
    end)
    check('latest target and source expires after five seconds across different clocks',function()
        local owned=next_at
        feed.center_position={220,-300};feed.popup_scale=1.5
        feed.hit_position,feed.charge_position='center','center'
        feed.charges={{id='ammo',name='测试扣费',text='测试扣费 -<0.01£'}}
        feed.kill_source_notices={revision=1,items={{expires_at=16.3,lines={'追猎虫 [GL-21 榴弹发射器]'}},
            {expires_at=16.3,lines={'不应叠加的旧提示'}}}}
        feed.now=11.3;animation_time=1011.3
        local view=put_all()['ledger.native.feed']
        assert(nodes[addresses.ledger_kill_notice_1_1].shown)
        assert(nodes[addresses.ledger_kill_notice_1_1].text=='追猎虫 [GL-21 榴弹发射器]')
        assert(not addresses.ledger_kill_notice_1_2 and not addresses.ledger_kill_notice_2_1)
        assert(view.kill_notice_1_1_position[1]==220 and view.kill_notice_1_1_scale[1]==1.5)
        local first=view.kill_notice_1_1_position
        assert(first[2]<view.center_charge_1_position[2]-22*1.5,'source text stays below central fees and hits')
        feed.kill_source_enabled=false
        put_all()
        assert(not nodes[addresses.ledger_kill_notice_1_1].shown,
            'display off removes already-created native attribution widget immediately')
        assert(nodes[addresses.ledger_kills].shown and nodes[addresses.ledger_side_R01_texture].shown,
            'display off must not hide metrics or ribbon widgets')
        assert(next_at==owned,'source toggle reuses the existing native widget')
        feed.kill_source_enabled=true;put_all()
        assert(nodes[addresses.ledger_kill_notice_1_1].shown)
        feed.immutable=true;animation_time=1016.299;put_all()
        assert(nodes[addresses.ledger_kill_notice_1_1].shown,'kill stays visible before five seconds')
        animation_time=1016.301;put_all()
        assert(not nodes[addresses.ledger_kill_notice_1_1].shown,'cached native text hides after five seconds')
        assert(next_at==owned,'single fixed source text widget is retained')
        feed.immutable=nil;feed.now=16.4;animation_time=1016.4
        feed.kill_source_notices={revision=2,items={{expires_at=21.4,lines={'掠食追踪虫 [测试武器]'}}}}
        put_all();assert(nodes[addresses.ledger_kill_notice_1_1].text=='掠食追踪虫 [测试武器]')
        feed.kill_notice_bottom=420
        put_all()
        assert(not nodes[addresses.ledger_kill_notice_1_1].shown,
            'insufficient vertical space hides an entire notice rather than a half attribution')
        feed.kill_source_notices=nil;feed.kill_notice_bottom=nil;feed.kill_source_enabled=nil
        feed.center_position=nil;feed.popup_scale=nil;feed.hit_position=nil;feed.charge_position=nil;feed.charges={}
        tick(11.2);put_all()
    end)
    check('count growth flashes and scales for 180 ms then settles without reallocating',function()
        local owned=next_at
        feed.side[2].count=2;tick(11.5);put_all()
        local counter=nodes[addresses.ledger_side_R01_count_frame]
        assert(nodes[addresses.ledger_side_R01_count].text=='x2')
        assert(counter.widget_scale_set[1]>1.17)
        assert(nodes[addresses.ledger_side_R01_count].colour[1]>.99)
        tick(11.59);put_all();assert(counter.widget_scale_set[1]>1 and counter.widget_scale_set[1]<1.1)
        tick(11.7);put_all();assert(counter.widget_scale_set[1]==1)
        assert(nodes[addresses.ledger_side_R01_count].colour[1]<.90)
        assert(next_at==owned)
        feed.ribbons={feed.side[2]};feed.medals={feed.side[3]};feed.hits={feed.side[1]};feed.side={}
        tick(13.5);put_all()
        assert(not nodes[addresses.ledger_side_R01_texture].shown and nodes[addresses.ledger_collected_R01_texture].shown)
        assert(not nodes[addresses.ledger_side_M04_name1_frame].shown and not nodes[addresses.ledger_side_M04_name2_frame].shown)
        assert(nodes[addresses.ledger_collected_M04_texture].shown)
    end)
    check('four hit types stay borderless and only positive totals show while map is open',function()
        feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{}
        for _,id in ipairs({'H02','H03','H04','H05'})do
            feed.side[#feed.side+1]={id=id,kind='ribbon',side_icon=true,count=2,total=4}
        end
        tick(14);put_all()
        local owned=next_at
        for _,id in ipairs({'H02','H03','H04','H05'})do
            assert(nodes[addresses['ledger_side_'..id..'_texture']].shown)
            assert(not nodes[addresses['ledger_side_'..id..'_frame']].shown)
            assert(nodes[addresses['ledger_side_'..id..'_count']].text=='x2')
        end
        tick(16);feed.hits=feed.side;feed.side={};put_all()
        for _,id in ipairs({'H02','H03','H04','H05'})do
            assert(not nodes[addresses['ledger_side_'..id..'_texture']].shown)
            assert(nodes[addresses['ledger_collected_'..id..'_texture']].shown)
            assert(not nodes[addresses['ledger_collected_'..id..'_frame']].shown)
            assert(nodes[addresses['ledger_collected_'..id..'_count']].text=='2')
        end
        assert(next_at==owned,'hit notifications allocated a second widget tree')
        feed.hits[1].count=0;put_all();assert(not nodes[addresses.ledger_collected_H02_texture].shown)
        feed.map_open=false;put_all()
        for _,id in ipairs({'H02','H03','H04','H05'})do assert(not nodes[addresses['ledger_collected_'..id..'_texture']].shown)end
    end)
    check('native curvature input refreshes for awards and metrics',function()
        store(curve_at,packf(.25)..packf(.02)..packf(.03)..packf(.04))
        feed.map_open=false;feed.ribbons={};feed.medals={{id='M01',kind='medal',count=1}}
        for _=1,4 do put_all()end
        assert(not nodes[addresses.ledger_collected_R01_texture].shown and nodes[addresses.ledger_collected_M01_texture].shown)
        assert(nodes[addresses.ledger_collected_M01_texture].uniforms[n.mask_c2][1]==.25)
        assert(nodes[addresses.ledger_metric_U01_texture].uniforms[n.mask_c2][1]==.25)
    end)
    check('cached native feed and real Reader stay stable over 10000 frames',function()
        local function performance(label)
            for _=1,8 do step(native_reader,#wanted_rows)end
            collectgarbage('collect')
            local accepted=complete.native_hud_status.accepted
            local before=os.clock()
            for _=1,10000 do step(native_reader,#wanted_rows)end
            local mean=(os.clock()-before)*1000000/10000
            assert(complete.native_hud_status.accepted==accepted,'static feed must reuse its sanitized native view')
            collectgarbage('collect');collectgarbage('stop')
            local kb=collectgarbage('count')
            for _=1,1000 do step(native_reader,#wanted_rows)end
            local allocated=(collectgarbage('count')-kb)*1024/1000
            collectgarbage('restart');collectgarbage('collect')
            print(string.format('PERF native real Reader %s: mean %.2f us/frame, allocation %.0f bytes/frame, sanitized accepted delta 0',label,mean,allocated))
        end
        feed.immutable=true
        feed.layout=nil;feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{};feed.map_open=true;tick(50)
        for _,asset in ipairs(art.images)do
            local is_hit=asset.id:sub(1,1)=='H' and asset.id~='H01'
            local item={id=asset.id,kind=asset.id:sub(1,1)=='M' and 'medal' or 'ribbon',
                side_icon=is_hit,count=3,total=3}
            table.insert(is_hit and feed.hits or (item.kind=='ribbon' and feed.ribbons or feed.medals),item)
        end
        performance('20 collected plus four metrics')
        -- Root's immutable contract publishes a different table each update.
        -- In-place mutable fixtures above retain their existing semantics.
        local next_feed={};for key,value in pairs(feed)do next_feed[key]=value end;feed=next_feed;feed.layout=nil
        feed.medals,feed.ribbons,feed.hits,feed.side={},{},{},{{id='R01',kind='ribbon',count=2,total=2},{id='M01',kind='medal',count=1,total=1}}
        tick(100);put_all();tick(100.2);put_all()
        performance('two side awards')
        local accepted=complete.native_hud_status.accepted
        local next_feed={};for key,value in pairs(feed)do next_feed[key]=value end;feed=next_feed;feed.layout=nil
        tick(101);feed.side={{id='R01',kind='ribbon',count=8,total=8}}
        local values=put_all()
        assert(values['ledger.native.side_R01_count']=='x8' and complete.native_hud_status.accepted>accepted)
        tick(101.2);local cached=put_all()['ledger.native.feed']
        for _=1,10 do assert(step(native_reader,#wanted_rows)['ledger.native.feed']==cached)end
        feed.immutable=false
    end)
end
check('native hidden state clears content without a screen-space fallback',function()
    feed.shown=false;put_all()
    assert(not nodes[addresses.ledger_block].shown and not complete.native_hud_status.ready)
    feed.shown=true;put_all();assert(nodes[addresses.ledger_block].shown)
end)
check('real Widgets detaches and remounts the whole block without severing child transforms',function()
    local other=parent+10000000;parent_node(other)
    assert(widgets:mount('ledger_block',other))
    assert(native_read:ptr(addresses.ledger_block+n.widget_parent)==other)
    assert(nodes[parent].children[addresses.ledger_block]==nil and nodes[other].children[addresses.ledger_block])
    assert(native_read:ptr(addresses.ledger_shots+n.widget_parent)==addresses.ledger_shots_frame)
    assert(native_read:ptr(addresses.ledger_shots_frame+n.widget_parent)==addresses.ledger_block)
    assert(widgets:mount('ledger_block',parent))
end)
check('real Widgets destroy removes the complete native tree and supports reconstruction',function()
    assert(widgets:destroy('ledger_block'))
    for _,at in pairs(addresses)do assert(native_read:value(at,'u32')==0,'native child survived destroy')end
    assert(widgets:destroy('ledger_block'))
    local again,why=widgets:make(parent,complete.screens[1].rows)
    assert(again,why);assert(again.ledger_block==addresses.ledger_block)
    assert(native_read:value(base+n.gui_context_top,'i32')==-1)
end)
stingray=old_stingray
print('Native HUD addon real HUD+ contract tests passed: '..tests..' (native IO fixture; engine pixels unverified)')
