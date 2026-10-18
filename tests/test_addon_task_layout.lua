-- Actual built entry/bridge/layout integration. Saved real nodes and code pins
-- are rebased into isolated memory. The native layout call is an explicit
-- simulation, never an address called in a game or evidence of real FPS.
local addon_path, runtime_path, fixture_path = assert(arg[1]), assert(arg[2]), assert(arg[3])
package.preload['hd2runtime/schemas/current'] = function() return dofile(runtime_path .. '/schemas/current.lua') end
package.preload['hd2runtime/core/bytes'] = function() return dofile(runtime_path .. '/core/bytes.lua') end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime_path .. '/runtime/mod_store.lua') end
package.preload['hd2runtime/runtime/log'] = function() return {emit=function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
local bytes, codec, bit = require('hd2runtime/core/bytes'), require('hd2runtime/runtime/mod_store'), require('bit')
local original_open, count, failures = io.open, 0, {}
local file=assert(original_open(fixture_path,'rb'))
local evidence=assert(codec.decode(file:read('*a')));file:close()
assert(evidence.format=='HD2-ADDON-TASK-LAYOUT-FIXTURE-1')
assert(evidence.source_bin_sha256=='ee338b1688205b060d545a99659a36005fb3c9d370f52314df3acef92eab9648'
    and evidence.layout_bin_sha256=='2ede865741ec7c69a70162c6e051f331bbcc113a5b17c6c5935400fdc72b39a9'
    and evidence.outer_bin_sha256=='fdaf5e1961693bbeb7e910382286d333c5d6e65bce9607ed76232c1ebab9074b')
assert(#evidence.chunks==7 and #evidence.pins==3)
local prefix='hd2_costs.war_cost_ledger.'
local function copy(v) if type(v)~='table' then return v end;local out={};for k,x in pairs(v) do out[k]=copy(x) end;return out end
local function patch(raw,at,text) return raw:sub(1,at)..text..raw:sub(at+#text+1) end
local function pointer(n) return bytes.encode(n%4294967296,'u32')..bytes.encode(math.floor(n/4294967296),'u32') end
local function near(a,b,why) assert(math.abs(a-b)<.001,(why or 'values differ')..': '..tostring(a)..' / '..tostring(b)) end
local offsets={root=0x258,parent=0x2944A0,records=0x392328,timer=0x299BD8,resources=0x2949A0,tasks=0x29B180,focused=0x38CA10}
local widget_names={'timer','resources','tasks','focused'}
local modules={'mods/skyeshade/hd2runtime','hd2runtime/domains/metadata','hd2runtime/domains/event_natives',
    'hd2runtime/runtime/event_world','hd2runtime/runtime/beacon_redirect','hd2runtime/runtime/stratagem_loadout',
    'hd2runtime/runtime/windows_ffi'}
local function boot(options)
    options=options or {}
    local f={data={ui_settings={auto_ui_probe=false}},files={},writes={},messages={},options={},values={},callbacks={},bindings={},
        available=true,mission=options.ship~=true,map_open=true,native_readable=true,now=0,shots=2000,kills=12,deaths=0,
        read_bytes=0,reads=0,queries=0,stat_reads=0,write_count=0,calls=0,handles=0,draws=0,draw_scope=false,
        game=0x10000000,hud=0x20000000,width=2560,height=1440,scale=4/3,protect=options.protect or 4,allocations={},pins={}}
    for _, pin in ipairs(evidence.pins) do
        assert(pin.length==#pin.hex/2)
        f.pins[pin.rva]=bytes.unhex(pin.hex)
    end
    local function add_hud(hud)
        local chunks={}
        for _,item in ipairs(evidence.chunks) do
            local raw=bytes.unhex(item.hex);assert(#raw==item.length and item.hud_offset==offsets[item.name])
            local pointer_fields=item.name=='records' and {0,8,0x10,0x18,0x70,0x78} or {0xE0,0xE8,0xF0,0xF8}
            if item.name=='records' then
                for row=0,4 do for _,at in ipairs(pointer_fields) do
                    local n=bytes.pointer(raw,row*128+at)
                    if n>=evidence.source_hud and n<evidence.source_hud+0x800000 then
                        raw=patch(raw,row*128+at,pointer(hud+n-evidence.source_hud))
                    end
                end end
            else
                for _,at in ipairs(pointer_fields) do
                    local n=bytes.pointer(raw,at)
                    if n>=evidence.source_hud and n<evidence.source_hud+0x800000 then raw=patch(raw,at,pointer(hud+n-evidence.source_hud)) end
                end
            end
            chunks[item.name]=raw
        end
        f.allocations[hud]=chunks;return chunks
    end
    f.chunks=add_hud(f.hud)
    f.parent_anchor_top=f.height-(bytes.value(f.chunks.parent,0x9C,'f32')
        +bytes.value(f.chunks.parent,0x28,'f32')*bytes.value(f.chunks.parent,0x8C,'f32'))
    local function get_chunk(at,size)
        for hud,chunks in pairs(f.allocations) do for name,raw in pairs(chunks) do
            local start=hud+offsets[name]
            if at>=start and at+size<=start+#raw then return raw:sub(at-start+1,at-start+size),chunks,name,at-start end
        end end
    end
    local function memory(at,size)
        local found=get_chunk(at,size);if found then return found end
        local raw=string.rep('\0',size)
        for hud,chunks in pairs(f.allocations) do for name,text in pairs(chunks) do
            local start=hud+offsets[name];local first,last=math.max(at,start),math.min(at+size,start+#text)
            if first<last then raw=patch(raw,first-at,text:sub(first-start+1,last-start)) end
        end end
        return raw
    end
    function f:field(name,at) return bytes.value(self.chunks[name],at,'f32') end
    function f:set_field(name,at,n) self.chunks[name]=patch(self.chunks[name],at,bytes.encode(n,'f32')) end
    function f:gap(index) return self:field('records',index*128+0x2C) end
    function f:set_gap(index,value) self:set_field('records',index*128+0x2C,value) end
    function f:shown(name,value)
        local flags=bytes.u32(self.chunks[name],0)
        flags=value and bit.bor(flags,16) or bit.band(flags,bit.bnot(16))
        self.chunks[name]=patch(self.chunks[name],0,bytes.encode(flags,'u32'))
    end
    function f:is_shown(name) return bit.band(bytes.u32(self.chunks[name],0),16)~=0 end
    function f:replace_hud(hud) self.hud=hud;self.chunks=add_hud(hud) end
    -- Native parent placement model uses source sizes/gaps and updates matrices.
    -- Direct changes here represent the game; only runtime.write is Lua writes.
    function f:place(at)
        assert(not self.draw_scope,'native call in draw callback')
        assert(at==self.hud+offsets.records,'native call escaped proved parent layout')
        self.calls=self.calls+1
        if self.call_fail then return false end
        -- Native local anchors remain fixed; do not recursively accumulate a
        -- rounded inverse-world-coordinate result in the simulation itself.
        local parent_top=self.parent_anchor_top
        local cursor=self:field('records',0x3C)
        local tops={}
        for index,name in ipairs(widget_names) do if self:is_shown(name) then
            local local_scale=self:field(name,0x18)
            cursor=cursor+self:gap(index)*local_scale
            tops[name]=parent_top+cursor*self:field('parent',0x8C)
            if not self.freeze_tween then
                self:set_field(name,8,-cursor)
                local height=self:field(name,0x28)*self:field(name,0x8C)
                self:set_field(name,0x9C,self.height-tops[name]-height)
            end
            cursor=cursor+(self:field(name,0x10)+self:field('records',index*128+0x30))*local_scale
        end end
        self.source_tops=tops
        -- Parent size changes while keeping its native top anchor fixed.
        self:set_field('parent',0x28,cursor)
        self:set_field('parent',0x9C,self.height-parent_top-cursor*self:field('parent',0x8C))
        self.chunks.records=patch(self.chunks.records,0x28,'\0')
        return true
    end
    local world={game=f.game,exe=0x50000000,key='task-layout-fixture',view={},runtime={mode=options.mode or 'live'}};f.world=world
    function world.view.slot() return {} end
    function world.view.pointer(at)
        assert(not f.draw_scope,'native pointer read in draw')
        f.read_bytes,f.reads=f.read_bytes+8,f.reads+1
        assert(at==f.game+0x346D538,'unexpected native pointer read');return f.hud
    end
    function world.view.read(at,size)
        assert(not f.draw_scope,'native read in draw');f.read_bytes,f.reads=f.read_bytes+size,f.reads+1
        if size==1 and (at==f.hud+0x24E340+0x58 or at==f.hud+0x24E340+0x21F5B0 or at==f.hud+0x3EF2FD) then
            if not f.native_readable then return nil end
            return string.char((at==f.hud+0x3EF2FD and f.map_open or at~=f.hud+0x3EF2FD and f.mission) and 1 or 0)
        end
        for rva,raw in pairs(f.pins) do if at==f.game+rva and size==#raw then
            return f.bad_pin and string.rep('\0',size) or raw
        end end
        local hud_range=false
        for hud in pairs(f.allocations) do if at>=hud and at+size<=hud+0x480000 then hud_range=true end end
        assert(hud_range or (at>=f.game+0x12E8000 and at+size<=f.game+0x12F8000)
            or (at>=f.game+0x143A000 and at+size<=f.game+0x1452000),'read escaped proved layout or manual ranges')
        return memory(at,size)
    end
    function world.runtime.query(at)
        assert(not f.draw_scope,'native query in draw');f.queries=f.queries+1
        for hud in pairs(f.allocations) do if at>=hud and at<hud+0x800000 then
            return {allocation_base=hud,base=hud,size=0x800000,state=0x1000,protect=f.protect,type=0x20000}
        end end
        if at>=f.game and at<f.game+0x4000000 then return {allocation_base=f.game,base=f.game,size=0x4000000,state=0x1000,protect=0x20,type=0x1000000} end
        error('query escaped fixture allocation')
    end
    function world.runtime.write(at,raw)
        assert(not f.draw_scope,'native write in draw')
        local base=f.hud+offsets.records
        assert((at==base+3*128+0x2C or at==base+4*128+0x2C) and #raw==4 or at==base+0x28 and raw=='\1',
            'Lua write escaped the two objective gaps / parent dirty byte')
        f.write_count=f.write_count+1;f.writes[#f.writes+1]={at=at,raw=raw}
        if f.write_fail then return false,'fixture refused',0 end
        local _,chunks,name,relative=get_chunk(at,#raw);assert(chunks)
        chunks[name]=patch(chunks[name],relative,raw)
        if f.short_write then f.short_write=false;return true,nil,#raw-1 end
        return true,nil,#raw
    end
    if options.no_write then world.runtime.write=nil end
    package.preload['hd2runtime/runtime/windows_ffi']=function()
        return {fn=function(signature) assert(signature=='void (*)(uintptr_t)');return signature end,
            ffi={cast=function(signature,at)
                assert(signature=='void (*)(uintptr_t)' and at==f.game+0x18F5C70,'only proved parent placement may be cast')
                return function(parent) return f:place(parent) end
            end}}
    end
    io.open=function(path,mode)
        assert(path:gsub('\\','/'):find('/HD2Runtime/mod_data/ledger_',1,true),'test filesystem escaped own evidence')
        if mode=='rb' then
            local raw=f.files[path];if not raw then return nil end
            return {read=function(_,n)return type(n)=='number' and raw:sub(1,n) or raw end,close=function()return true end}
        end
        assert(mode=='wb' or mode=='ab');if mode=='wb' then f.files[path]='' end
        return {write=function(self,raw)f.files[path]=(f.files[path] or '')..raw;return self end,
            flush=function()return true end,close=function()return true end}
    end
    local store,mod={},{}
    function store:get(key,fallback)return copy(f.data[key]==nil and fallback or f.data[key]) end
    function store:set(key,value)f.data[key]=copy(value) end
    function store:save()return true end
    function mod:store()return store end
    function mod:log(message)f.messages[#f.messages+1]=tostring(message) end
    function mod:on_frame(fn)f.frame=fn end
    function mod:bind(id,spec)f.bindings[id]=spec;return {state='active'} end
    package.preload['mods/skyeshade/hd2runtime']=function()
        return {mod=function()return mod end,resources={image=function(id)f.handles=f.handles+1;return id end},
            ui={overlay=function(config)
                local overlay={visible=config.visible};f.overlay=overlay
                function overlay:draw(fn)f.draw_fn=fn end
                function overlay:show()self.visible=true end
                function overlay:hide()self.visible=false end
                return overlay
            end}}
    end
    package.preload['hd2runtime/domains/metadata']=function()return {version='0.30.3'} end
    package.preload['hd2runtime/domains/event_natives']=function()return {stats={keys={projectiles_fired=1,dealt_kills=2,received_deaths=3}}} end
    package.preload['hd2runtime/runtime/event_world']=function()
        return {open=function()return f.available and world or nil end,game_state=function()return {mission=f.mission} end,
            players=function()return {{['local']=true,entity=42}} end,stat_breakdown=function()
                f.stat_reads=f.stat_reads+1
                return {totals={[1]=f.shots,[2]=f.kills,[3]=f.deaths,[0xC7680A1B]=0},sources={}}
            end}
    end
    package.preload['hd2runtime/runtime/beacon_redirect']=function()return {prove=function()return false end,clock=function()return 0 end} end
    package.preload['hd2runtime/runtime/stratagem_loadout']=function()return {} end
    for _,name in ipairs(modules) do package.loaded[name]=nil end
    local menu={api=1,version=3}
    function menu.register_option(id,spec)f.options[id],f.values[id]=spec,spec.default;return true end
    function menu.get(id)return f.values[id] end
    function menu.set(id,value)f.values[id]=value;return true end
    function menu.on_change(id,callback)f.callbacks[id]=callback;return true end
    rawset(_G,'ModOptionsMenu',menu);rawset(_G,'HD2WarCostLedgerV1',nil)
    f.module=dofile(addon_path)
    assert(f.module.version=='0.4.66' and type(f.module.task_layout_status)=='function' and f.module.native_ui.task)
    assert(type(f.module.native_hud_snapshot)=='function','native feed must be public to the native HUD host')
    function f:status()return self.module.task_layout_status() end
    function f:apply(id,value)id=prefix..id;assert(self.callbacks[id]);self.values[id]=value;self.callbacks[id](value,id) end
    function f:draw()
        local reads,writes,calls,queries=self.reads,self.write_count,self.calls,self.queries
        self.draw_scope=true
        local d={width=self.width,height=self.height,scale=self.scale}
        function d:text()f.draws=f.draws+1 end
        function d:rect()f.draws=f.draws+1 end
        function d:image()f.draws=f.draws+1 end
        self.draw_fn(d);self.draw_scope=false
        assert(self.reads==reads and self.write_count==writes and self.calls==calls and self.queries==queries,'draw did native I/O')
    end
    function f:step(dt)
        local before=self.read_bytes;self.frame(dt or .1);self.now=self.now+(dt or .1)
        self.last_bytes=self.read_bytes-before;self:draw()
        -- Pickup placement adds at most three 256B nodes and a 4B title key.
        assert(self:status().read_last<=2270+772,'task observation escaped fixed small budget')
    end
    function f:tick(n)for _=1,n or 1 do self:step(.1) end end
    function f:ready()self:tick(3);assert(self:status().status=='TASK_LAYOUT_RESERVED',codec.encode(self:status()));return self end
    function f:expect_placed()
        local g=assert(self.module.native_ui.task:geometry_snapshot())
        local name=assert(widget_names[g.selected])
        local local_height=self:status().extra_gap*self:field(name,0x18)
        near(self.source_tops[name],self.parent_anchor_top+(g.local_top+local_height)*g.scale,'placed task top')
    end
    function f:stats_unchanged()assert(self.module.state.shots==2000 and self.module.state.kills==12 and self.module.state.total_cents==0) end
    return f
end
local function check(name,fn)
    local ok,why=pcall(fn);io.open=original_open
    if not ok then failures[#failures+1]=name..': '..tostring(why);return end
    count=count+1;print('PASS '..name)
end

check('actual bridge applies real PIN/node fixture to the first task gap only',function()
    local f=boot():ready();local status=f:status()
    -- The native API has no viewport height: compare the parent's local top
    -- with the saved native anchor, not diagnostics interpreted as screen Y.
    near(status.baseline_top,115.2,'map-open parent-relative scaled task top')
    -- The shared right-edge layout fits this ribbon next to the 109-unit
    -- metrics column. Default top adjustment is zero, plus a 12-unit task gap.
    local height=109+12
    assert(status.selected==3);near(status.extra_gap,height);near(f:gap(3),10+height)
    near(f:gap(1),0);near(f:gap(2),0);near(f:gap(4),10)
    f:expect_placed();near(f.source_tops.tasks,298.8)
    near(f.source_tops.timer,38.4);near(f.source_tops.resources,84)
    -- The native float32 parent matrix permits one small settling correction.
    assert(f.calls>=1 and f.calls<=2 and f.module.ui_settings.config.move_tasks and f.module.ui_tree_probe_status().status=='retired',
        'startup native calls: '..f.calls..'; '..codec.encode(status))
    local geometry=assert(f.module.native_ui.task:geometry_snapshot())
    local feed=assert(f.module.native_hud_snapshot())
    assert(feed.shown and feed.hud==f.hud and feed.key==geometry.key and feed.map_open)
    near(geometry.local_top,96);near(feed.position[2],-96)
    near(feed.position[1],geometry.width-(f.module.ui_settings.config.right_margin+600))
    near(feed.scale[1],1);near(feed.scale[2],1)
    assert(feed.kills=='12' and feed.shots=='2000' and f.draws==0,'combat rendered both native and flat HUDs')
    f:stats_unchanged()
end)

check('idle and incomplete native animation cannot accumulate spacing drift',function()
    local f=boot():ready();local gap,calls=f:gap(3),f.calls
    f.freeze_tween=true;f:set_field('tasks',8,-400);f:set_field('tasks',0x9C,900)
    f:tick(100);near(f:gap(3),gap);assert(f.calls==calls,'idle/tween caused repeated parent placement: '..f.calls..' vs '..calls..'; gap '..f:gap(3)..' vs '..gap)
    near(f.module.native_ui.task:geometry_snapshot().local_top,96);f:stats_unchanged()
end)

check('subpixel jitter is ignored but a larger reservation change and restoration still apply',function()
    local f=boot():ready();local calls,gap=f.calls,f:gap(3)
    local config=copy(f.module.ui_settings.config)
    config.task_gap=config.task_gap+.005/f:field('parent',0x8C)
    f.module.game_hud:configure(config);f:tick(3)
    assert(f.calls==calls,'sub-0.01px reservation jitter invoked native layout');near(f:gap(3),gap)
    config.task_gap=config.task_gap+.05/f:field('parent',0x8C)
    f.module.game_hud:configure(config);f:tick(3)
    assert(f.calls==calls+1,'larger reservation change was swallowed or repeatedly placed')
    assert(f:gap(3)>gap);f:expect_placed()
    f:apply('move_tasks',false);f:tick()
    assert(f.chunks.records:sub(3*128+0x2D,3*128+0x30)==bytes.encode(10,'f32'),
        'jitter suppression must never prevent exact original 4-byte restoration')
end)

check('map/focused/both-hidden transitions restore originals without cumulative drift',function()
    local f=boot():ready();local open_gap=f:gap(3)
    for _=1,6 do
        f.map_open=false;f:shown('timer',false);f:shown('resources',false);f:shown('tasks',false);f:shown('focused',true)
        f:tick(2);assert(f:status().selected==4);near(f:gap(3),10)
        near(f:gap(4),131);assert(not f.module.native_hud_snapshot().map_open)
        near(f.module.native_ui.task:geometry_snapshot().local_top,10,'closed focused baseline')
        f:expect_placed()
        f.map_open=true;f:shown('timer',true);f:shown('resources',true);f:shown('tasks',true);f:shown('focused',false)
        f:tick(2);near(f:gap(3),open_gap);near(f:gap(4),10)
    end
    f:shown('focused',true);f:tick();assert(f:status().selected==3);near(f:gap(4),10)
    f:shown('tasks',false);f:shown('focused',false);f:tick()
    near(f:gap(3),10);near(f:gap(4),10);assert(f:status().status=='TASK_LAYOUT_RESTORED')
    assert(f.module.native_ui.task:geometry_snapshot()==nil)
    f:tick() -- feed consumes geometry from the preceding 10 Hz observation
    assert(f.module.native_hud_snapshot()==nil)
end)

check('settings use native local reservation independent of flat draw dimensions',function()
    local f=boot():ready();local initial=f:gap(3)
    local handles=f.module.game_hud.image_count+1 -- one ribbon frame
    assert(f.handles==handles)
    f:apply('top_margin',72);f:apply('scale_percent',140);f:apply('task_gap',120);f:tick(2)
    assert(f:gap(3)>initial);f:expect_placed()
    local reservation=f.module.game_hud:reservation(true,true,f.now)
    near(reservation.native_height,(72+109+120)*1.4)
    near(f:gap(3),10+reservation.native_height)
    local feed=assert(f.module.native_hud_snapshot())
    near(feed.position[2],-(96+72*1.4));near(feed.scale[1],1.4)
    f:apply('enabled',false);f:tick();f.width,f.height,f.scale=1920,1080,1
    f:draw();reservation=f.module.game_hud:reservation(false,true,f.now)
    assert(reservation.native and not reservation.visible and reservation.width==nil and reservation.height==nil)
    assert(f.module.native_hud_snapshot()==nil)
    f:apply('enabled',true);f:tick(2)
    reservation=f.module.game_hud:reservation(true,true,f.now)
    near(f:gap(3),10+reservation.native_height)
    assert(f.draws==0,'combat settings revived the flat renderer')
    assert(f.handles==handles,'draw/settings allocated new image handles')
end)

check('native feed follows parent size and scale without flat viewport or layout drift',function()
    local f=boot():ready();local first=copy(f.module.native_hud_snapshot());local calls,gap=f.calls,f:gap(3)
    local width=f:field('parent',0x24)+80
    f:set_field('parent',0x24,width);f:set_field('parent',0x8C,1.8)
    for _,name in ipairs(widget_names)do f:set_field(name,0x8C,1.8*f:field(name,0x18))end
    f.width,f.height,f.scale=1280,720,2/3
    f:tick(3);near(f:gap(3),gap);assert(f.calls==calls,'parent scale changed local task gap')
    local g=assert(f.module.native_ui.task:geometry_snapshot())
    local feed=assert(f.module.native_hud_snapshot())
    near(g.scale,1.8);near(g.width,width);near(g.local_top,96)
    near(feed.position[1],first.position[1]+80);near(feed.position[2],first.position[2])
    near(feed.scale[1],1);near(feed.scale[2],1)
    local cached=codec.encode(feed);f:draw();assert(codec.encode(f.module.native_hud_snapshot())==cached)
    assert(f.draws==0);f:stats_unchanged()
end)

check('F8 and move_tasks restore on the next native update while statistics continue',function()
    local f=boot():ready();f.bindings['war_cost_ledger.toggle_hud'].on_press();f:tick()
    near(f:gap(3),10);assert(not f.overlay.visible and f.module.native_hud_snapshot()==nil)
    local stat_reads=f.stat_reads;f.shots,f.kills=2001,13;f:tick(3)
    assert(f.stat_reads>stat_reads and f.module.state.shots==2001 and f.module.state.kills==13)
    f.bindings['war_cost_ledger.toggle_hud'].on_press();f:tick();assert(f:gap(3)>10)
    f:apply('move_tasks',false);f:tick();near(f:gap(3),10);near(f:gap(4),10)
    assert(f.module.native_hud_snapshot() and f.module.native_ui.task:geometry_snapshot(),
        'disabling task movement also lost native HUD placement')
    f:apply('move_tasks',true);f:tick();assert(f:gap(3)>10)
    f:apply('enabled',false);f:tick();near(f:gap(3),10);assert(f.module.native_hud_snapshot()==nil)
end)

check('ship return restores and isolated ship preview never edits task layout',function()
    local f=boot():ready();f.mission=false;f:tick();near(f:gap(3),10)
    f:tick();assert(f.module.native_hud_snapshot()==nil)
    local calls,writes=f.calls,f.write_count;local real=codec.encode(f.module.state)
    f:apply('preview',4);f:tick(30)
    assert(f.calls==calls and f.write_count==writes and f.overlay.visible,
        'ship UI TEST: calls '..f.calls..'/'..calls..', writes '..f.write_count..'/'..writes..', visible '..tostring(f.overlay.visible))
    assert(codec.encode(f.module.state)==real,'preview changed real combat state')
    f:tick(51);assert(not f.overlay.visible and not f.module.game_hud:preview_active(f.now))
    assert(f.calls==calls and f.write_count==writes)
end)

check('queued/active manual UI capture restores and suppresses reservation',function()
    local f=boot():ready();f:apply('capture',3);f:tick();near(f:gap(3),10)
    assert(f.module.native_hud_snapshot()==nil,'capture retained combat feed')
    local calls,writes=f.calls,f.write_count;f:tick(45)
    assert(f.module.capture_status()=='queued' and f.calls==calls and f.write_count==writes)
    f:tick(7);assert(f.module.capture_status()=='capturing','manual sample must enter its actual reader')
    assert(f.calls==calls and f.write_count==writes,'active capture reapplied task spacing')
    f:apply('capture',4);f:tick();assert(f:gap(3)>10 and f.calls==calls+1)
    f:stats_unchanged()
end)

check('read-only and unproved boundaries do not call native layout or fabricate combat data',function()
    for _,spec in ipairs({{no_write=true},{protect=0x20},{mode='offline'}}) do
        local f=boot(spec);f:tick(3)
        assert(f.calls==0 and f.write_count==0 and f:status().status~='TASK_LAYOUT_RESERVED')
        assert(f.module.native_hud_snapshot()==nil)
        f:stats_unchanged()
    end
    local f=boot();f.bad_pin=true;f:tick(3)
    assert(f:status().status=='TASK_LAYOUT_CODE_MISMATCH' and f.calls==0 and f.write_count==0
        and f.module.native_hud_snapshot()==nil);f:stats_unchanged()
end)

check('world/HUD loss makes no stale writes; replacement owns its own original gaps',function()
    local f=boot():ready();local writes=f.write_count
    f.available=false;local reads=f.reads;f:tick(3)
    assert(f.reads==reads and f.write_count==writes,'lost world touched retained native addresses')
    assert(f.module.native_hud_snapshot()==nil,'lost world retained native feed')
    f.available=true;f.native_readable=false;f:tick();assert(f.write_count==writes and f.module.native_hud_snapshot()==nil)
    f.native_readable=true;f:replace_hud(0x30000000);f:tick(2)
    assert(f:gap(3)>10 and f:status().status=='TASK_LAYOUT_RESERVED')
    assert(f.module.native_hud_snapshot().hud==0x30000000)
    for index=writes+1,#f.writes do assert(f.writes[index].at>=0x30000000,'replacement tried to restore old HUD') end
    f:apply('enabled',false);f:tick();near(f:gap(3),10)
end)

check('foreign task gap is preserved and disables further ownership in that HUD',function()
    local f=boot():ready();f:set_gap(3,777);local calls=f.calls;f:tick(3)
    near(f:gap(3),777);near(f:gap(4),10)
    assert(f:status().status=='TASK_LAYOUT_CHANGED_BY_OTHER_MOD' and f.calls==calls and not f:status().owned
        and f.module.native_hud_snapshot()==nil)
    f:apply('enabled',false);f:tick();near(f:gap(3),777)
end)

check('failed/short writes roll back the current owned gap before any native call',function()
    local f=boot();f.write_fail=true;f:tick(3)
    near(f:gap(3),10);assert(f.calls==0 and f:status().status=='TASK_LAYOUT_WRITE_FAILED'
        and f.module.native_hud_snapshot()==nil);f:stats_unchanged()
    local g=boot();g:tick();g.short_write=true;g:tick()
    near(g:gap(3),10);assert(g.calls==0 and g:status().status=='TASK_LAYOUT_WRITE_FAILED'
        and g.module.native_hud_snapshot()==nil)
    g:tick();assert(g.calls==1 and g:gap(3)>10,'recovered field could not resume')
end)

assert(#failures==0,table.concat(failures,'\n'))
print('Addon task relocation integration tests: '..count..' passed; actual built 0.4.66, saved real nodes/PINs, native feed and simulated placement; live display/FPS remain unverified.')
