-- The HUD, root, five native layout records/widgets and code are exact captures.
-- Runtime reads/writes/calls, state changes and animation changes are synthetic adapters.
local source_path,runtime_path,fixture_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.preload['hd2runtime/schemas/current']=function()return dofile(runtime_path..'/schemas/current.lua')end
package.preload['hd2runtime/core/bytes']=function()return dofile(runtime_path..'/core/bytes.lua')end
package.preload['hd2runtime/runtime/log']=function()return {emit=function()end}end
package.preload['hd2runtime/runtime/events']=function()return {}end
package.preload['hd2runtime/runtime/mod_store']=function()return dofile(runtime_path..'/runtime/mod_store.lua')end
local bytes=require('hd2runtime/core/bytes')
local json=require('hd2runtime/runtime/mod_store')
local profile=require('hd2runtime/schemas/current')
local bit=require('bit')
local f=assert(io.open(fixture_path,'rb'));local data=json.decode(f:read('*a'));f:close()
local Module=dofile(source_path)
assert(data.source_binary_sha256==Module.source.fixture_sha)
local function patch(raw,o,s)return raw:sub(1,o)..s..raw:sub(o+#s+1)end
local function pointer(value)
    return bytes.encode(value%4294967296,'u32')..bytes.encode(math.floor(value/4294967296),'u32')
end
local function approx(a,b,tolerance)
    assert(type(a)=='number' and math.abs(a-b)<(tolerance or .001),tostring(a)..' differs from '..tostring(b))
end
local peak_reads=0
local function fixture()
    local f={mem={},reads={},writes={},calls={},read_bytes=0,sequence=0}
    f.hud,f.game=data.hud,data.game_base
    local function put(at,raw)f.mem[at]=raw end
    put(data.root_widget.address,bytes.unhex(data.root_widget.hex))
    for _,r in ipairs(data.layouts)do put(r.address,bytes.unhex(r.hex))end
    for _,w in ipairs(data.widgets)do put(w.address,bytes.unhex(w.hex))end
    for _,c in ipairs(data.code_windows)do put(f.game+c.rva,bytes.unhex(c.hex))end
    function f:peek(at,n)
        local out={}
        for off=0,n-1 do
            local v
            for base,raw in pairs(self.mem)do if at+off>=base and at+off<base+#raw then v=raw:sub(at+off-base+1,at+off-base+1);break end end
            if not v then return nil end
            out[#out+1]=v
        end
        return table.concat(out)
    end
    function f:poke(at,raw)
        local remaining=raw;local cursor=at
        while #remaining>0 do
            local base,value
            for candidate,s in pairs(self.mem)do if cursor>=candidate and cursor<candidate+#s then base,value=candidate,s;break end end
            assert(base,'write outside fixture '..string.format('%X',cursor))
            local n=math.min(#remaining,base+#value-cursor)
            self.mem[base]=patch(value,cursor-base,remaining:sub(1,n));cursor=cursor+n;remaining=remaining:sub(n+1)
        end
    end
    function f:set_field(at,o,value)self:poke(at+o,bytes.encode(value,'f32'))end
    function f:gap(i)return bytes.value(assert(self:peek(self.hud+Module.source.layout+i*128+0x2C,4)),0,'f32')end
    function f:set_shown(i,yes)
        local at=self.hud+Module.source.child_widgets[i]
        local flag=bytes.u32(assert(self:peek(at,4)),0)
        self:poke(at,bytes.encode(yes and bit.bor(flag,16) or bit.band(flag,bit.bnot(16)),'u32'))
    end
    local function read(at,n)
        f.read_bytes=f.read_bytes+n;f.reads[#f.reads+1]={at=at,n=n}
        if f.fail_read==at then return nil end
        if f.fail_read_once_at==at then
            f.read_hits=(f.read_hits or 0)+1
            if f.read_hits==(f.fail_read_hit or 1) then f.fail_read_once_at=nil;return nil end
        end
        return f:peek(at,n)
    end
    local function write(at,raw)
        f.sequence=f.sequence+1;f.writes[#f.writes+1]={at=at,raw=raw}
        if f.fail_write_at==at or f.fail_write_number==f.sequence then
            f.fail_write_at=nil;f.fail_write_number=nil
            if f.mutate_on_failure then f:poke(at,raw)end
            return false,'fixture write failed',f.mutate_on_failure and #raw or 0
        end
        f:poke(at,raw);return true,nil,#raw
    end
    f.world={game=f.game,exe=0x50000000,key='actual-captured-layout',runtime={mode='live',write=write,
        query=function(at)
            if f.not_writable then return {base=f.hud,size=0x480000,state=0x1000,protect=2,type=0x20000}end
            return {base=f.hud,size=0x480000,state=0x1000,protect=4,type=0x20000}
        end},view={read=read}}
    f.state={hud=f.hud,mission=true,map_open=true}
    f.layout=Module.new({place_factory=function(world)
        assert(world==f.world)
        return function(at)
            f.calls[#f.calls+1]=at
            assert(at==f.hud+Module.source.layout,'native call outside proved parent layout')
            if f.fail_call then return false end
            -- Boundary mock only: native clears dirty. It does NOT emulate actual game animations/layout.
            f:poke(at+0x28,'\0')
            return true
        end
    end})
    function f:reserve(options)
        self.read_bytes=0;self.reads={};self.writes={};self.calls={};self.sequence=0
        local opt=options or {visible=true,move_tasks=true,width=2560,height=1440,reserved_height=259.55556}
        local ok,why=self.layout:reserve(self.world,self.state,opt)
        peak_reads=math.max(peak_reads,self.read_bytes)
        assert(self.read_bytes<=4096,'all sample/apply/readback native reads exceeded 4KiB: '..self.read_bytes)
        assert(self.layout:status_snapshot().read_last==self.read_bytes,'diagnostic bytes must include guarded compare/readback/rollback reads')
        assert(#self.writes<=6 and #self.calls<=1,'bounded native write/call count')
        local at=self.hud+Module.source.layout
        for _,row in ipairs(self.writes)do
            assert((row.at==at+3*128+0x2C and #row.raw==4) or (row.at==at+4*128+0x2C and #row.raw==4)
                or (row.at==at+0x28 and #row.raw==1),'write outside two gaps/one dirty byte')
        end
        return ok,why,self.layout:status_snapshot()
    end
    return f
end
local tests,failures=0,{}
local function test(name,run)
    local ok,err=pcall(run);tests=tests+1
    if not ok then failures[#failures+1]=name..': '..tostring(err)end
end
test('exact fixture proves baseline153.6 and desired259.55556',function()
    local f=fixture();local ok,why,s=f:reserve();assert(ok,why)
    approx(s.baseline_top,153.6);approx(s.desired_top,259.55556)
    approx(s.extra_gap,(259.55556-153.6)/1.2)
    approx(f:gap(3),10+s.extra_gap);approx(f:gap(4),10)
    assert(s.selected==3 and #f.writes==2 and #f.calls==1)
end)
test('focus only consumes one independent objective gap',function()
    local f=fixture();f:set_shown(3,false);f:set_shown(4,true)
    local ok,why,s=f:reserve();assert(ok,why)
    assert(s.selected==4);approx(s.baseline_top,153.6);approx(f:gap(3),10);approx(f:gap(4),10+s.extra_gap)
end)
test('both visible adds space once at task list',function()
    local f=fixture();f:set_shown(4,true);local ok,why,s=f:reserve();assert(ok,why)
    assert(s.selected==3 and #f.writes==2);approx(f:gap(4),10)
end)
test('hidden leading resource or timer is skipped',function()
    for _,v in ipairs({{1,108},{2,96}})do
        local f=fixture();f:set_shown(v[1],false);local ok,why,s=f:reserve();assert(ok,why)
        approx(s.baseline_top,v[2])
    end
    local f=fixture();f:set_shown(1,false);f:set_shown(2,false)
    local ok,why,s=f:reserve();assert(ok,why);approx(s.baseline_top,50.4)
end)
test('room already sufficient has zero writes/calls',function()
    local f=fixture();local ok,why,s=f:reserve({visible=true,width=2560,height=1440,reserved_height=100})
    assert(ok,why);assert(s.extra_gap==0 and #f.writes==0 and #f.calls==0);approx(f:gap(3),10)
end)
test('long repeat and animation XY/cache changes never drift',function()
    local f=fixture();local ok,why=f:reserve();assert(ok,why);local applied=f:gap(3)
    for i=1,250 do
        f:set_field(f.hud+0x29B180,8,-96-i*.1)
        f:set_field(f.hud+0x3924A8,0x60,-96-i*.2)
        local good,reason,s=f:reserve();assert(good,reason)
        approx(s.baseline_top,153.6);approx(f:gap(3),applied)
        assert(#f.writes==0 and #f.calls==0)
    end
end)
test('branch switch restores old owned gap before applying new',function()
    local f=fixture();assert(f:reserve());f:set_shown(3,false);f:set_shown(4,true)
    local ok,why,s=f:reserve();assert(ok,why)
    assert(s.selected==4 and #f.writes==3);approx(f:gap(3),10);assert(f:gap(4)>10)
end)
test('disabled, invisible or nonmission restores native gaps',function()
    for _,option in ipairs({{visible=false},{visible=true,move_tasks=false},{visible=true}})do
        local f=fixture();assert(f:reserve())
        if option.visible and option.move_tasks==nil then f.state.mission=false end
        local ok,why,s=f:reserve(option);assert(ok,why)
        approx(f:gap(3),10);approx(f:gap(4),10);assert(s.status=='TASK_LAYOUT_RESTORED')
        f:reserve(option);assert(#f.writes==0 and #f.calls==0 and f.read_bytes==0)
    end
end)
test('both objective families hidden restores owned space',function()
    local f=fixture();assert(f:reserve());f:set_shown(3,false);f:set_shown(4,false)
    local ok,why,s=f:reserve();assert(ok,why);assert(not s.selected);approx(f:gap(3),10)
end)
test('hidden top-right parent restores owned space',function()
    local f=fixture();assert(f:reserve())
    local at=f.hud+Module.source.parent_widget
    f:poke(at,bytes.encode(bit.band(bytes.u32(assert(f:peek(at,4)),0),bit.bnot(16)),'u32'))
    local ok,why,s=f:reserve();assert(ok,why);assert(not s.selected);approx(f:gap(3),10)
end)
test('map/layout visibility transition recomputes without additive delta',function()
    local f=fixture();assert(f:reserve())
    f.state.map_open=false;f:set_shown(1,false);f:set_shown(2,false)
    local ok,why,s=f:reserve();assert(ok,why);approx(s.baseline_top,50.4)
    f.state.map_open=true;f:set_shown(1,true);f:set_shown(2,true)
    ok,why,s=f:reserve();assert(ok,why);approx(s.baseline_top,153.6)
    approx(f:gap(3),10+(259.55556-153.6)/1.2)
end)
test('foreign gap yields and restores only the other owned field',function()
    local f=fixture();f:set_shown(3,false);f:set_shown(4,true);assert(f:reserve())
    f:set_field(f.hud+0x3924A8,0x2C,77)
    local ok,why,s=f:reserve();assert(not ok and why=='TASK_LAYOUT_CHANGED_BY_OTHER_MOD')
    approx(f:gap(3),77);approx(f:gap(4),10);assert(not s.owned)
    f:reserve();assert(#f.writes==0 and #f.calls==0)
end)
test('same owned foreign gap is never overwritten',function()
    local f=fixture();assert(f:reserve());f:set_field(f.hud+0x3924A8,0x2C,33)
    local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_CHANGED_BY_OTHER_MOD')
    approx(f:gap(3),33);assert(#f.writes==0 and #f.calls==0)
end)
test('new context takes fresh layout state, not old owned baseline',function()
    local f=fixture();assert(f:reserve())
    local context=data.root_widget.context+0x1000
    -- Synthetic lifetime boundary: all new widgets retain real geometry, but a new context and original gaps.
    for _,row in ipairs(data.layouts)do f:poke(row.address,bytes.unhex(row.hex))end
    f:poke(data.root_widget.address+0xF8,pointer(context))
    for _,row in ipairs(data.widgets)do f:poke(row.address+0xF8,pointer(context))end
    local ok,why,s=f:reserve();assert(ok,why);approx(s.baseline_top,153.6);assert(s.selected==3)
end)
test('valid new HUD uses fresh source and never touches retained old objects',function()
    local f=fixture();assert(f:reserve())
    local oldhud,delta=f.hud,0x800000
    local oldgap=f:gap(3)
    -- Synthetic lifetime boundary only: rebase the exact captured objects and hierarchy.
    -- Original fixture bytes are never edited on disk. Other fields retain their real values.
    local function newraw(raw,offsets)
        for _,off in ipairs(offsets)do
            local value=bytes.pointer(raw,off)
            if value>=oldhud and value<oldhud+0x480000 then raw=patch(raw,off,pointer(value+delta))end
        end
        return raw
    end
    f.mem[data.root_widget.address+delta]=newraw(bytes.unhex(data.root_widget.hex),{0xE0,0xE8,0xF0})
    for _,row in ipairs(data.layouts)do f.mem[row.address+delta]=newraw(bytes.unhex(row.hex),{0,8,0x10,0x18})end
    for _,row in ipairs(data.widgets)do f.mem[row.address+delta]=newraw(bytes.unhex(row.hex),{0xE0,0xE8,0xF0})end
    f.hud=oldhud+delta;f.state.hud=f.hud
    local ok,why,s=f:reserve();assert(ok,why);approx(s.baseline_top,153.6)
    assert(s.selected==3 and f:gap(3)>10)
    approx(bytes.value(assert(f:peek(oldhud+0x3924A8+0x2C,4)),0,'f32'),oldgap)
    for _,write in ipairs(f.writes)do assert(write.at>=f.hud and write.at<f.hud+0x480000)end
end)
test('unmapped new HUD does not write old objects',function()
    local f=fixture();assert(f:reserve());f.state.hud=f.hud+0x800000
    local ok,why=f:reserve();assert(not ok and #f.writes==0 and #f.calls==0)
end)
test('short data or wrong hierarchy returns before writing',function()
    for _,name in ipairs({'read','parent','context','chain'})do
        local f=fixture()
        if name=='read' then f.fail_read=f.hud+0x29B180
        elseif name=='parent' then f:poke(f.hud+0x29B180+0xF0,pointer(f.hud+0x820))
        elseif name=='context' then f:poke(f.hud+0x38CA10+0xF8,pointer(0))
        else f:poke(f.hud+0x3924A8+0x18,pointer(f.hud+0x3924A8))end
        local ok=f:reserve();assert(not ok and #f.writes==0 and #f.calls==0,name)
    end
end)
for _,v in ipairs({{0x29B180,0x10},{0x3924A8,0x2C},{0x2944A0,0x9C}})do
    test(string.format('NaN field HUD+%X produces zero writes without exception',v[1]+v[2]),function()
        local f=fixture();f:poke(f.hud+v[1]+v[2],bytes.unhex('0000C07F'))
        local ok=f:reserve();assert(not ok and #f.writes==0 and #f.calls==0,
            string.format('NaN at HUD+%X: ok=%s writes=%d calls=%d',v[1]+v[2],tostring(ok),#f.writes,#f.calls))
    end)
end
test('nonwritable layout produces zero writes',function()
    local f=fixture();f.not_writable=true;local ok,why=f:reserve()
    assert(not ok and why=='TASK_LAYOUT_NOT_WRITABLE' and #f.writes==0)
end)
test('exact code PIN and schema mismatch prevent every write',function()
    for _,pin in ipairs(Module.pins)do
        local f=fixture();f:poke(f.game+pin.rva,'\0')
        local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_CODE_MISMATCH' and #f.writes==0)
    end
    for _,key in ipairs({'dll_sha','exe_sha'})do
        local f=fixture();local previous=profile[key];profile[key]='another-build'
        local ok,why=f:reserve();profile[key]=previous
        assert(not ok and why=='TASK_LAYOUT_BUILD_MISMATCH' and f.read_bytes==0 and #f.writes==0)
    end
end)
test('first write failure with no mutation leaves native gaps',function()
    local f=fixture();f.fail_write_number=1
    local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_WRITE_FAILED');approx(f:gap(3),10)
end)
test('failed write acknowledgement after actual mutation is rolled back',function()
    local f=fixture();f.fail_write_number=1;f.mutate_on_failure=true
    local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_WRITE_FAILED');approx(f:gap(3),10)
end)
test('one transient readback failure rolls back acknowledged mutation',function()
    local f=fixture();f.fail_read_once_at=f.hud+0x3924A8+0x2C;f.fail_read_hit=2
    local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_WRITE_FAILED');approx(f:gap(3),10)
end)
test('failed second gap or dirty write rolls back the first owned gap',function()
    local f=fixture();assert(f:reserve());f:set_shown(3,false);f:set_shown(4,true)
    local before=f:gap(3);f.fail_write_number=2
    local ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_WRITE_FAILED')
    approx(f:gap(3),before);approx(f:gap(4),10)
    f=fixture();f.fail_write_at=f.hud+0x392328+0x28
    ok,why=f:reserve();assert(not ok and why=='TASK_LAYOUT_WRITE_FAILED');approx(f:gap(3),10)
end)
test('native call failure restores exact original gaps',function()
    local f=fixture();f.fail_call=true;local ok,why=f:reserve()
    assert(not ok and why=='TASK_LAYOUT_CALL_FAILED');approx(f:gap(3),10);approx(f:gap(4),10)
end)
local function native(height,move)
    -- A native reservation is in the parent's local coordinates, so it must
    -- work before any flat overlay draw supplies viewport dimensions.
    return {visible=true,move_tasks=move~=false,native=true,native_height=height or 136}
end
test('native mode inserts local height and exports the unshifted parent geometry',function()
    local f=fixture();local ok,why,s=f:reserve(native());assert(ok,why)
    approx(f:gap(3),146);approx(f:gap(4),10);approx(s.extra_gap,136)
    local g=assert(f.layout:geometry_snapshot())
    assert(g.hud==f.hud and g.context==data.root_widget.context and g.selected==3)
    assert(type(g.key)=='string' and #g.key>0)
    approx(g.local_top,96);approx(g.scale,1.2)
    approx(g.width,bytes.value(assert(f:peek(f.hud+Module.source.parent_widget+0x24,4)),0,'f32'))
    assert(#f.writes==2 and #f.calls==1)
    f:reserve(native());approx(f.layout:geometry_snapshot().local_top,96)
    assert(#f.writes==0 and #f.calls==0,'native repeat added another reservation')
end)
test('native local height ignores a changed or missing viewport',function()
    local f=fixture();assert(f:reserve(native()));local g=f.layout:geometry_snapshot()
    local opts=native();opts.width,opts.height,opts.reserved_height=3440,1440,1
    assert(f:reserve(opts));approx(f:gap(3),146)
    approx(f.layout:geometry_snapshot().local_top,g.local_top)
    assert(#f.writes==0 and #f.calls==0)
end)
test('native height divides by the selected child local scale',function()
    local f=fixture();local at=f.hud+Module.source.child_widgets[3]
    f:set_field(at,0x18,2);f:set_field(at,0x8C,2.4)
    local ok,why,s=f:reserve(native());assert(ok,why)
    approx(s.extra_gap,68);approx(f:gap(3),78)
    local g=assert(f.layout:geometry_snapshot());approx(g.local_top,106);approx(g.scale,1.2)
end)
test('parent scale and native width follow without changing local reserved height',function()
    local f=fixture();assert(f:reserve(native()))
    f:set_field(f.hud+Module.source.parent_widget,0x8C,1.8)
    f:set_field(f.hud+Module.source.parent_widget,0x24,480)
    for _,off in ipairs(Module.source.child_widgets)do f:set_field(f.hud+off,0x8C,1.8)end
    local ok,why=f:reserve(native());assert(ok,why);approx(f:gap(3),146)
    local g=assert(f.layout:geometry_snapshot());approx(g.scale,1.8);approx(g.width,480);approx(g.local_top,96)
    assert(#f.writes==0 and #f.calls==0,'parent scaling restarted task placement')
end)
test('native map height switches the reserved branch once',function()
    local f=fixture();assert(f:reserve(native(166)));approx(f:gap(3),176)
    f.state.map_open=false;f:set_shown(1,false);f:set_shown(2,false);f:set_shown(3,false);f:set_shown(4,true)
    local ok,why,s=f:reserve(native(136));assert(ok,why);assert(s.selected==4)
    approx(f:gap(3),10);approx(f:gap(4),146);approx(f.layout:geometry_snapshot().local_top,10)
    f.state.map_open=true;f:set_shown(1,true);f:set_shown(2,true);f:set_shown(3,true);f:set_shown(4,false)
    assert(f:reserve(native(166)));approx(f:gap(3),176);approx(f:gap(4),10)
    approx(f.layout:geometry_snapshot().local_top,96)
end)
test('native move_tasks off restores gaps but retains fresh follow geometry',function()
    local f=fixture();assert(f:reserve(native()))
    local ok,why,s=f:reserve(native(136,false));assert(ok,why)
    approx(f:gap(3),10);approx(f:gap(4),10);assert(s.extra_gap==0)
    local g=assert(f.layout:geometry_snapshot());approx(g.local_top,96);assert(g.selected==3)
    f:reserve(native(136,false));assert(f.read_bytes>0 and #f.writes==0 and #f.calls==0)
    assert(f:reserve(native()));approx(f:gap(3),146)
end)
test('native F8 hide, nonmission and absent task nodes clear geometry and restore once',function()
    for _,mode in ipairs({'hide','ship','tasks','parent'})do
        local f=fixture();assert(f:reserve(native()));local opts=native()
        if mode=='hide' then opts.visible=false
        elseif mode=='ship' then f.state.mission=false
        elseif mode=='tasks' then f:set_shown(3,false);f:set_shown(4,false)
        else
            local at=f.hud+Module.source.parent_widget
            f:poke(at,bytes.encode(bit.band(bytes.u32(assert(f:peek(at,4)),0),bit.bnot(16)),'u32'))
        end
        local ok,why=f:reserve(opts);assert(ok,why);approx(f:gap(3),10)
        assert(f.layout:geometry_snapshot()==nil,mode..' retained geometry')
        f:reserve(opts);assert(#f.writes==0 and #f.calls==0)
    end
end)
test('native fresh context changes owner key without stale geometry',function()
    local f=fixture();assert(f:reserve(native()));local old=f.layout:geometry_snapshot()
    local context=data.root_widget.context+0x1000
    for _,row in ipairs(data.layouts)do f:poke(row.address,bytes.unhex(row.hex))end
    f:poke(data.root_widget.address+0xF8,pointer(context))
    for _,row in ipairs(data.widgets)do f:poke(row.address+0xF8,pointer(context))end
    assert(f:reserve(native()));local g=assert(f.layout:geometry_snapshot())
    assert(g.key~=old.key and g.context==context);approx(f:gap(3),146);approx(g.local_top,96)
end)
test('native foreign gap invalidates follow geometry and remains foreign',function()
    local f=fixture();assert(f:reserve(native()));f:set_field(f.hud+0x3924A8,0x2C,77)
    local ok,why=f:reserve(native());assert(not ok and why=='TASK_LAYOUT_CHANGED_BY_OTHER_MOD')
    approx(f:gap(3),77);assert(f.layout:geometry_snapshot()==nil)
    f:reserve(native());assert(f.layout:geometry_snapshot()==nil and #f.writes==0 and #f.calls==0)
end)
test('native stale HUD, invalid hierarchy or unreadable source clears follow geometry',function()
    for _,mode in ipairs({'hud','read','hierarchy','pin','writeable'})do
        local f=fixture();assert(f:reserve(native()))
        if mode=='hud' then f.state.hud=f.hud+0x800000
        elseif mode=='read' then f.fail_read=f.hud+0x29B180
        elseif mode=='hierarchy' then f:poke(f.hud+0x38CA10+0xF8,pointer(0))
        elseif mode=='pin' then f:poke(f.game+Module.pins[1].rva,'\0')
        else f.not_writable=true end
        local ok=f:reserve(native());assert(not ok and f.layout:geometry_snapshot()==nil,mode)
        assert(#f.writes==0 and #f.calls==0)
    end
end)
test('failed native gap, dirty write, readback or call clears all pending geometry',function()
    for _,mode in ipairs({'gap','dirty','readback','call'})do
        local f=fixture();assert(f:reserve(native()));local oldgap=f:gap(3)
        if mode=='gap' then f.fail_write_number=1
        elseif mode=='dirty' then f.fail_write_at=f.hud+Module.source.layout+0x28
        elseif mode=='readback' then f.fail_read_once_at=f.hud+0x3924A8+0x2C;f.fail_read_hit=2
        else f.fail_call=true end
        local ok=f:reserve(native(180));assert(not ok,mode)
        approx(f:gap(3),oldgap);assert(f.layout:geometry_snapshot()==nil,mode..' published unapplied geometry')
    end
end)
test('native acquired anchor follows actual geometry and detects onscreen versus retained offscreen rows',function()
    local path=fixture_path:gsub('[^/\\]+$','native-pickup-layout-0.4.40.json')
    local input=assert(io.open(path,'rb'));local pickup=json.decode(input:read('*a'));input:close()
    for _,sample in ipairs(pickup.samples)do
        local f=fixture()
        local context=bytes.pointer(f:peek(f.hud+Module.source.root,256),0xF8)
        local function header(raw,parent)
            return patch(patch(bytes.unhex(raw),0xF0,pointer(parent)),0xF8,pointer(context))
        end
        local p=Module.source.pickup
        f.mem[f.hud+p.anchor]=header(sample.anchor,f.hud+0x820)
        f.mem[f.hud+p.body]=header(sample.body,f.hud+p.anchor)
        f.mem[f.hud+p.title]=header(pickup.title_header,f.hud+p.title_parent)
        f.mem[f.hud+p.title+0x110]=bytes.encode(pickup.title_key,'u32')
        assert(f:reserve(native()))
        local g=assert(f.layout:geometry_snapshot().pickup)
        approx(g.right,450);approx(g.top,468)
        assert(g.occupied==sample.occupied,'shown bits remain true even when the old row has slid offscreen')
        f:poke(f.hud+p.title+0x110,bytes.encode(0,'u32'))
        assert(f:reserve(native()) and f.layout:geometry_snapshot().pickup==nil,'wrong native label is refused')
    end
end)
if #failures>0 then error(table.concat(failures,'\n'))end
print('Native task layout: '..tests..' tests passed; exact real fixture baseline153.6, synthetic write/call boundaries; peak native reads='..peak_reads..'B, calls<=1/step.')
