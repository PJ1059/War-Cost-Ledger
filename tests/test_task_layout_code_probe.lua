-- Actual caller bytes/Runtime codec; memory, lifecycle and missing callee bodies are synthetic boundaries.
local module_path,runtime_path,fixture_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.preload['hd2runtime/schemas/current']=function()return dofile(runtime_path..'/schemas/current.lua')end
package.preload['hd2runtime/runtime/log']=function()return {emit=function()end}end
package.preload['hd2runtime/runtime/events']=function()return {}end
package.preload['hd2runtime/runtime/mod_store']=function()return dofile(runtime_path..'/runtime/mod_store.lua')end
local codec=require('hd2runtime/runtime/mod_store')
local profile=require('hd2runtime/schemas/current')
local original_open,tests=io.open,0
local function read_file(path)
    local f=assert(original_open(path,'rb'));local raw=f:read('*a');f:close();return raw
end
local reference=codec.decode(read_file(fixture_path))
local Module=dofile(module_path)
local function unhex(s)return (s:gsub('..',function(c)return string.char(tonumber(c,16))end))end
local function patch(s,at,raw)return s:sub(1,at)..raw..s:sub(at+#raw+1)end
local function copy(t)return codec.decode(codec.encode(t))end
local project=assert(module_path:match('^(.*)/src/'))
local research_root=os.getenv('HD2_RESEARCH_FIXTURES_ROOT')
local source_path=research_root and (research_root..'/'..reference.source_binary:gsub('^dist/','')) or (project..'/'..reference.source_binary)
local actual_callers=read_file(source_path)
assert(reference.source_sha256==Module.source.source_sha and #actual_callers==reference.source_length)
for i,pin in ipairs(reference.pins)do
    assert(actual_callers:sub(pin.source_binary_offset+1,pin.source_binary_offset+pin.length)==unhex(pin.hex))
    assert(pin.rva==Module.pins[i].rva and pin.length==Module.pins[i].length)
    assert(pin.hex:upper()==Module.pins[i].hex and pin.target==Module.pins[i].target)
end
-- This 64-byte prefix is actual previously captured widget_position_set code.
-- Repeating it is ONLY a bounded IO payload fixture, not a claimed missing callee.
local setter=unhex(reference.setter_payload.hex);assert(#setter==64)
local fset=original_open(reference.setter_payload.source_binary,'rb')
if fset then
    assert(fset:seek('set',reference.setter_payload.source_binary_offset))
    assert(fset:read(#setter)==setter);fset:close()
end
local function fixture(options)
    options=options or {}
    local f={files=options.files or {},data=options.data or {},bytes=0,reads=0,peak=0,
        native_writes=0,native_calls=0,binwrites=0,read_sizes={},regions=true}
    local game,exe=0x10000000,0x50000000
    f.game,f.exe=game,exe;f.mem={}
    for _,pin in ipairs(Module.pins)do f.mem[game+pin.rva]=unhex(pin.hex)end
    for _,r in ipairs(Module.ranges)do f.mem[game+r.rva]=setter:rep(r.length/#setter)end
    local function read(at,n)
        f.bytes=f.bytes+n;f.reads=f.reads+1;f.read_sizes[#f.read_sizes+1]=n
        if f.fail_read==at then return f.short and string.rep('\0',n-1) or nil end
        for base,raw in pairs(f.mem)do
            if at>=base and at+n<=base+#raw then return raw:sub(at-base+1,at-base+n)end
        end
        error('unplanned native read '..string.format('%X',at)..' length '..n)
    end
    f.world={game=game,exe=exe,key='proven-fixture',runtime={mode='live',query=function(at)
        f.query_count=(f.query_count or 0)+1
        if not f.regions then return nil end
        return {base=game,size=0x4000000,state=0x1000,type=0x1000000,protect=0x20}
    end},view={read=read,write=function()f.native_writes=f.native_writes+1;error('native write prohibited')end,
        call=function()f.native_calls=f.native_calls+1;error('native call prohibited')end}}
    io.open=function(path,mode)
        if path:sub(1,8)~='fixture/' then return original_open(path,mode)end
        if f.fail_open and path:find(f.fail_open,1,true) and mode~='rb' then return nil end
        if mode=='rb' then
            local item=f.files[path];if not item then return nil end
            return {read=function(_,n)local s=item.raw;return n=='*a' and s or s:sub(1,n)end,
                close=function()return true end}
        end
        assert(mode=='wb' or mode=='ab')
        local item=f.files[path]
        if mode=='wb' then
            assert(not item or path:sub(-5)=='.json','binary evidence overwritten')
            item={raw=''};f.files[path]=item
        elseif not item then item={raw=''};f.files[path]=item end
        item.closed=false
        return {write=function(self,s)
            if f.fail_write and path:find(f.fail_write,1,true) then return nil,'fixture IO failure' end
            if path:sub(-4)=='.bin' then f.binwrites=f.binwrites+1 end
            item.raw=item.raw..s;return self
        end,flush=function()return true end,close=function()item.closed=true;return true end}
    end
    f.store={get=function(_,key,default)return copy(f.data[key] or default)end,
        set=function(_,key,value)f.data[key]=copy(value);return true end}
    function f:new_probe(extra)
        extra=extra or {};extra.store=self.store;extra.directory='fixture/task-code'
        return Module.new(extra)
    end
    f.probe=f:new_probe(options)
    function f:step(world)
        self.bytes,self.binwrites=0,0
        local target=self.world
        if world==false then target=nil elseif world~=nil then target=world end
        local s=self.probe:step(target,9999)
        self.peak=math.max(self.peak,self.bytes)
        assert(self.bytes<=4200 and self.bytes==s.read_last,'native byte budget')
        assert(self.binwrites<=1,'more than one code chunk write this tick')
        assert(self.native_writes==0 and self.native_calls==0)
        for _,file in pairs(self.files)do assert(file.closed,'file handle left open between ticks')end
        return s
    end
    function f:until_status(predicate,max)
        for _=1,max or 20 do local s=self:step();if predicate(s)then return s end end
        error('bounded completion missing: '..codec.encode(self.probe:status_snapshot()))
    end
    function f:meta()
        return codec.decode(assert(self.files[assert(self.probe:status_snapshot().last_path)]).raw)
    end
    return f
end
local function test(name,run)
    local ok,err=pcall(run);io.open=original_open
    assert(ok,name..': '..tostring(err));tests=tests+1
end
test('ship capture, real caller pins and exact chunk bounds',function()
    local f=fixture();local s=f:step();assert(s.active and s.read_last==0)
    local initial=codec.decode(f.files[f.probe.active.meta.json_path].raw)
    assert(initial.complete==false and initial.bytes_written==0 and initial.atomic==false)
    f:until_status(function(v)return v.done end)
    local meta=f:meta();local raw=f.files[meta.binary_path].raw
    assert(meta.complete and meta.identity_consistent and meta.bytes_written==14336 and #raw==14336)
    assert(meta.game_base==f.game and meta.exe_base==f.exe and meta.source_sha==reference.source_sha256)
    assert(meta.native_called==false and meta.native_written==false and #meta.chunks==4)
    assert(meta.ranges[1].binary_offset==0 and meta.ranges[2].binary_offset==2048)
    assert(meta.start_pins[1].actual_target==0x17CF8A0 and meta.start_pins[2].actual_target==0x184B700)
    assert(#meta.end_pins==2 and meta.end_pins[2].valid)
    assert(meta.chunks[1].length==2048)
    for i=2,4 do assert(meta.chunks[i].length==4096)end
    local total=0;for _,item in pairs(f.files)do total=total+#item.raw end
    assert(total<32768 and f.peak==4096)
end)
test('successful restart and later steps have zero native reads',function()
    local f=fixture();f:until_status(function(s)return s.done end)
    f.probe=f:new_probe();assert(f.probe.done)
    for _=1,10 do assert(f:step().read_last==0)end
end)
test('disabled preserves old UI tree state and reads nothing',function()
    local old={ui_tree_probe_v3={sentinel='leave untouched'}}
    local f=fixture({enabled=false,data=old})
    for _=1,5 do assert(f:step().status=='disabled')end
    assert(old.ui_tree_probe_v3.sentinel=='leave untouched' and f.reads==0)
end)
test('waits indefinitely then captures on ship without mission state',function()
    local f=fixture()
    for _=1,1300 do assert(f:step(false).status=='waiting_world')end
    assert(f.reads==0);f:until_status(function(s)return s.done end)
end)
test('offline runtime and malformed module bases never read',function()
    local f=fixture();f.world.runtime.mode='offline'
    assert(f:step().status=='waiting_world' and f.reads==0)
    f.world.runtime.mode='live';f.world.game=0;assert(f:step().read_last==0)
    f.world.game=f.game;f.world.exe=140737488355328;assert(f:step().read_last==0)
end)
test('schema fingerprint mismatch never reads',function()
    local f=fixture();local previous=profile.dll_sha;profile.dll_sha='unmatched'
    local s=f:step();profile.dll_sha=previous
    assert(s.reason=='TASK_CODE_BUILD_MISMATCH' and not s.active and f.reads==0)
end)
test('corrupt real caller displacement rejects without callee reads',function()
    local f=fixture();local pin=Module.pins[2];local at=f.game+pin.rva
    f.mem[at]=patch(f.mem[at],12,'\0');f:step();local s=f:step()
    assert(s.attempts==1 and s.status=='incomplete' and s.read_last==28)
    local meta=f:meta();assert(not meta.complete and #meta.chunks==0)
    assert(meta.start_pins[2].valid==false and meta.start_pins[2].actual_hex)
    assert(meta.error=='TASK_CODE_CALLER_PIN_MISMATCH')
end)
test('final caller drift leaves honest incomplete payload',function()
    local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase=='verify'end)
    local at=f.game+Module.pins[1].rva;f.mem[at]=string.rep('\0',12)
    local s=f:step();assert(not s.done and s.attempts==1)
    local meta=f:meta();assert(not meta.complete and #f.files[meta.binary_path].raw==14336)
end)
test('short code read exhausts two failures across restart',function()
    local f=fixture();f.fail_read=f.game+Module.ranges[1].rva;f.short=true
    f:until_status(function(s)return s.attempts==1 end)
    local first=f:meta();assert(not first.complete and first.failure.requested==2048 and first.failure.returned_length==2047)
    f.probe=f:new_probe();assert(f.probe.attempts==1)
    f:until_status(function(s)return s.status=='exhausted'end)
    f.probe=f:new_probe();for _=1,5 do assert(f:step().read_last==0)end
    assert(f.probe.attempts==2 and not f.probe.done)
end)
test('bad executable region fails without native read',function()
    local f=fixture();f.regions=false;f:step();local s=f:step()
    assert(s.read_last==0 and s.attempts==1 and s.reason=='TASK_CODE_REGION_UNREADABLE')
end)
test('normal cancellation and disabled do not spend failures',function()
    local f=fixture();f:step();f:step();f:step();local before=f.reads
    local s=f.probe:cancel('manual_capture_priority');assert(not s.active and s.attempts==0 and f.reads==before and s.read_last==0)
    local meta=f:meta();assert(not meta.complete and meta.bytes_written==2048)
    f.probe:set_enabled(false);for _=1,5 do assert(f:step().read_last==0)end
    f.probe:set_enabled(true);f:until_status(function(v)return v.done end)
end)
test('lost or changed proven world cancels without reads',function()
    local f=fixture();f:step();f:step();local before=f.reads
    assert(f:step(false).status=='waiting_world' and f.probe.attempts==0 and f.reads==before)
    f:step();f.world.key='another_world';local s=f:step()
    assert(s.reason=='TASK_CODE_WORLD_CHANGED' and s.read_last==0 and s.attempts==0)
end)
test('binary write failure counts but does not publish success',function()
    local f=fixture();f:step();f:step();f.fail_write='.bin';local s=f:step()
    assert(s.attempts==1 and not s.done and not f:meta().complete)
    assert(f:meta().error=='TASK_CODE_BINARY_WRITE')
end)
test('missing or truncated successful artifact can retry without overwriting',function()
    local f=fixture();f:until_status(function(s)return s.done end)
    local old=f.probe.saved.binary_path;local old_json=f.probe.saved.json_path
    f.files[old].raw=f.files[old].raw:sub(1,14335)
    f.probe=f:new_probe();assert(not f.probe.done and f.probe.attempts==0)
    f:until_status(function(s)return s.done end)
    assert(f.probe.saved.binary_path~=old and #f.files[old].raw==14335 and f.files[old_json])
    f.files[f.probe.saved.json_path]=nil;f.probe=f:new_probe();assert(not f.probe.done)
end)
test('foreign build or source state cannot suppress current sampling',function()
    for _,key in ipairs({'exe_sha','dll_sha','source_sha','source_revision'})do
        local f=fixture();f:until_status(function(s)return s.done end)
        local state=copy(f.data[Module.source.store_key]);state[key]='other'
        f.data[Module.source.store_key]=state;f.files[f.probe.state_path].raw=codec.encode(state)
        f.probe=f:new_probe();assert(not f.probe.done and f.probe.attempts==0)
    end
end)
test('metadata write failure cannot create a success marker',function()
    local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase=='verify'end)
    f.fail_write=f.probe.active.meta.json_path
    local s=f:step();assert(not s.done and s.attempts==1 and not f.data[Module.source.store_key].saved)
end)
test('cancel is read-free even before pins or after all code chunks',function()
    for _,phase in ipairs({'pins','verify'})do
        local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase==phase end)
        local before=f.reads;f.probe:cancel('user_stop')
        assert(f.reads==before and f.probe.attempts==0)
        for _,file in pairs(f.files)do assert(file.closed)end
    end
end)
test('BIN and final JSON share the 32 KiB ceiling',function()
    local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase=='verify'end)
    f.probe.active.meta.test_oversized=string.rep('X',20000)
    local s=f:step();assert(not s.done and s.reason=='TASK_CODE_METADATA_LIMIT' and s.attempts==1)
    local meta=f:meta();assert(not meta.complete)
    assert(#f.files[meta.binary_path].raw+#f.files[meta.json_path].raw<32768)
end)
test('success output remains complete while persistence failure is observable',function()
    local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase=='verify'end)
    f.fail_open=f.probe.state_path
    local s=f:step();assert(s.done and s.status=='complete' and s.persistence_saved==false)
    assert(s.reason=='TASK_CODE_FILE_OPEN' and f:meta().complete)
end)
test('failed public store save is reported, never silently ignored',function()
    local f=fixture();f:until_status(function()return f.probe.active and f.probe.active.phase=='verify'end)
    f.store.set=function()return false end
    local s=f:step();assert(s.done and s.persistence_saved==false and s.reason=='TASK_CODE_STORE_WRITE')
end)
io.open=original_open
print('Task layout code probe: '..tests..' tests passed; actual caller/setter prefixes, synthetic missing bodies; peak 4096B/step.')
