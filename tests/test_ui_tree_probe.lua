-- Actual module + Runtime codec, with only memory/files as bounded fixtures.
local probe_path,bridge_path,runtime_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.preload['hd2runtime/schemas/current']=function()return dofile(runtime_path..'/schemas/current.lua')end
package.preload['hd2runtime/runtime/log']=function()return {emit=function()end}end
package.preload['hd2runtime/runtime/events']=function()return {}end
package.preload['hd2runtime/runtime/mod_store']=function()return dofile(runtime_path..'/runtime/mod_store.lua')end
local codec=require('hd2runtime/runtime/mod_store')
local ffi=require('ffi')
local Native=dofile(bridge_path);local Module=dofile(probe_path)
local original_open,original_clock,tests=io.open,os.clock,0
local fixture_file=assert(original_open(assert(probe_path:match('^(.*)/src/'))..'/tests/fixtures/ui-root-window-0.4.4.bin','rb'))
local actual_window=fixture_file:read('*a');fixture_file:close();assert(#actual_window==8192)
local root_file=assert(original_open(assert(probe_path:match('^(.*)/src/'))..'/tests/fixtures/ui-root-node-0.4.5.bin','rb'))
local actual_root=root_file:read('*a');root_file:close();assert(#actual_root==256)
local function u32(n)
    local out={};for i=1,4 do out[i]=string.char(n%256);n=math.floor(n/256)end
    return table.concat(out)
end
local function pointer(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function float(n)local v=ffi.new('float[1]',n);return ffi.string(v,4)end
local function patch(raw,o,s)return raw:sub(1,o)..s..raw:sub(o+#s+1)end
local function node(parent,child,sibling,context,kind)
    local raw=string.rep('\0',256)
    for _,v in ipairs({{0,u32((kind or 1)*0x40000+0x10)},{0x24,float(180)},
        {0x28,float(40)},{0x64,float(1)},{0x78,float(1)},
        {0x94,float(1200)},{0x98,float(200)},{0xE0,pointer(child or 0)},
        {0xE8,pointer(sibling or 0)},{0xF0,pointer(parent or 0)},
        {0xF8,pointer(context)}})do raw=patch(raw,v[1],v[2])end
    return raw
end
local function fixture(options)
    options=options or {}
    local f={files=options.files or {},data=options.data or {},chunks={},bytes=0,reads=0,
        peak=0,writes=0,now=0,mission=options.mission~=false,map=false,closed=0,
        probe_bytes=0,records={}}
    -- Only root/PIN bytes are real captures. All descendants, the self-panel,
    -- memory reader, game bases and lifecycle changes are synthetic boundaries.
    local game,exe,hud,context=0x10000000,0x50000000,68993637784,69001015392
    local root=hud+0x258;f.game,f.hud,f.root,f.context=game,hud,root,context
    local count=options.nodes or 3;f.nodes={}
    f.chunks[#f.chunks+1]={root,actual_root}
    f.chunks[#f.chunks+1]={hud+0x24E340+0x60,node(root,0,0,context)}
    for i=1,count-1 do
        local at=0x10105765B8+(i-1)*0x200;f.nodes[i]=at
        f.chunks[#f.chunks+1]={at,node(root,0,i<count-1 and at+0x200 or 0,context,3)}
    end
    local pin_at=0x133A;local window=actual_window
    local pin=actual_window:sub(pin_at+1,pin_at+22)
    if options.pin==false then window=patch(window,pin_at,string.rep('\0',22))end
    if options.multiple_pin then window=patch(window,0x420,pin)end
    if options.corrupt_pin then
        local offset=pin_at+(options.corrupt_pin=='rip' and 3 or options.corrupt_pin=='call' and 18 or 13)
        window=patch(window,offset,string.char((window:byte(offset+1)+1)%256))
    end
    f.chunks[#f.chunks+1]={game+0x12F0000,window}
    f.chunks[#f.chunks+1]={game+0x346D538,pointer(hud)}
    for _,chunk in ipairs(f.chunks)do f.records[chunk[1]]=chunk[2]end
    function f:replace(at,raw)
        for _,v in ipairs(self.chunks)do if v[1]==at then v[2]=raw;self.records[at]=raw;return end end
        self.chunks[#self.chunks+1]={at,raw}
        self.records[at]=raw
    end
    local function read(at,n)
        f.bytes,f.reads=f.bytes+n,f.reads+1
        if at==game+0x12F133A then f.final_pin_length=n end
        if f.fail_at and at==f.fail_at then return f.short and string.rep('\0',math.max(0,n-1)) or nil end
        if n==1 then
            if at==hud+0x24E340+0x58 or at==hud+0x24E340+0x21F5B0 then return string.char(f.mission and 1 or 0)end
            if at==hud+0x3EF2FD then return string.char(f.map and 1 or 0)end
            error('unexpected state byte')
        end
        local exact=f.records[at];if exact and #exact>=n then return exact:sub(1,n)end
        local raw=string.rep('\0',n)
        for _,v in ipairs(f.chunks)do
            local start,finish=math.max(at,v[1]),math.min(at+n,v[1]+#v[2])
            if start<finish then raw=patch(raw,start-at,v[2]:sub(start-v[1]+1,finish-v[1]))end
        end
        return raw
    end
    f.world={game=game,exe=exe,key='fixture',view={read=read,pointer=function(at)
        assert(at==game+0x346D538);read(at,8);return hud
    end,write=function()f.writes=f.writes+1;error('native write prohibited')end,
        call=function()error('native call prohibited')end}}
    io.open=function(path,mode)
        if path:sub(1,8)~='fixture/' then return original_open(path,mode)end
        if mode=='rb' then
            local item=f.files[path];if not item then return nil end
            return {read=function(_,n)local s=table.concat(item.parts);return n=='*a' and s or s:sub(1,n)end,
                close=function()return true end}
        end
        assert(mode=='wb' or mode=='ab','unexpected write mode '..tostring(mode))
        if f.fail_file and path:find(f.fail_file,1,true) then return nil end
        local item=f.files[path]
        if mode=='wb' then
            assert(not item or path:sub(-11)=='.state.json' or path:sub(-12)=='.status.json' or path:sub(-10)=='.done.json',
                'sample evidence overwritten '..path)
            item={parts={}};f.files[path]=item
        elseif not item then item={parts={}};f.files[path]=item end
        item.closed=false
        return {write=function(self,s)item.parts[#item.parts+1]=s;return self end,
            flush=function()return true end,close=function()item.closed=true;f.closed=f.closed+1;return true end}
    end
    f.bridge=Native.new()
    f.store={get=function(_,key,default)return f.data[key] or default end,
        set=function(_,key,value)f.data[key]=codec.decode(codec.encode(value));return true end}
    function f:new_probe(extra)
        extra=extra or {};extra.bridge=self.bridge;extra.store=self.store;extra.directory='fixture/probe'
        return Module.new(extra)
    end
    f.probe=f:new_probe(options)
    function f:step(now,state,world)
        self.now=now or self.now+.1;self.bytes=0
        if state==nil then state=self.bridge:poll(self.world)end
        local result=self.probe:step(world==false and nil or world or self.world,state,self.now)
        self.probe_bytes=self.probe_bytes+result.read_last
        self.peak=math.max(self.peak,self.bytes)
        assert(self.bytes<=16384,'combined bridge+probe native budget '..self.bytes)
        assert(result.read_last<=16373 and self.writes==0)
        assert(result.nodes_last<=16 and result.operations_last<=32)
        for _,item in pairs(self.files)do assert(item.closed,'file left open between steps')end
        return result
    end
    function f:until_status(predicate,max)
        for _=1,max or 250 do local s=self:step();if predicate(s)then return s end end
        error('bounded outcome missing: '..codec.encode(self.probe:status_snapshot()))
    end
    function f:sample()
        local s=self.probe:status_snapshot();local item=assert(self.files[s.last_path])
        return codec.decode(table.concat(item.parts))
    end
    return f
end
local function check(name,fn)
    local ok,why=pcall(fn);io.open=original_open;os.clock=original_clock
    assert(ok,name..': '..tostring(why));tests=tests+1;print('PASS '..name)
end
check('actual 0.4.4 bytes reproduce absent old prefix and verify the new unique pin',function()
    local old_prefix=('410FB6D7488D8F58020000E8'):gsub('..',function(s)return string.char(tonumber(s,16))end)
    assert(not actual_window:find(old_prefix,1,true),'old failed rule must be reproduced by actual bytes')
    local f=fixture({include_code=false});f:until_status(function(s)return s.done.map_closed end)
    local pin=f:sample().summary.source_pin
    assert(pin.rva==0x12F133A and pin.length==22
        and pin.bytes=='488B1DF7C11702488BD6488D8B58020000E870B21500')
end)
check('actual kind-0 root stays unmodified; synthetic kind-0 child uses common base validation',function()
    local f=fixture({include_code=false})
    f:replace(f.nodes[1],node(f.root,0,f.nodes[2],f.context,0))
    f:until_status(function(s)return s.done.map_closed end)
    local sample=f:sample();local row=sample.nodes[1]
    local binary=table.concat(f.files[sample.summary.binary_path].parts)
    assert(binary:sub(row.binary_offset+1,row.binary_offset+256)==actual_root)
    assert(row.kind==0 and row.flags==0x101D and row.parent==0 and row.sibling==0
        and row.context==69001015392 and sample.nodes[2].kind==0)
    assert(sample.format=='HD2-UI-TREE-3' and sample.summary.source_revision=='root_base_v3')
end)
check('kind-0 root still rejects zero flags, invalid pointers and non-root parent/sibling',function()
    for _,damage in ipairs({'flags','child','context','parent','sibling','kind'})do
        local f=fixture({include_code=false});local raw=actual_root
        if damage=='flags'then raw=patch(raw,0,u32(0))
        elseif damage=='child'then raw=patch(raw,0xE0,pointer(0x800000000000))
        elseif damage=='context'then raw=patch(raw,0xF8,pointer(f.context+1))
        elseif damage=='parent'then raw=patch(raw,0xF0,pointer(f.root+8))
        elseif damage=='sibling'then raw=patch(raw,0xE8,pointer(f.root+8))
        else raw=patch(raw,0,u32(0x4101D))end
        f:replace(f.root,raw);f:until_status(function(s)return s.status=='incomplete'end)
        local summary=f:sample().summary
        assert(summary.error=='UI_TREE_ROOT_INVALID' and summary.nodes==0 and summary.failure.binary_length==256)
    end
end)
check('damaged RIP and CALL displacements never authorize root reads',function()
    for _,damage in ipairs({'rip','call','root'})do
        local f=fixture({corrupt_pin=damage})
        f:until_status(function(s)return s.status=='incomplete'end)
        local summary=f:sample().summary
        assert(summary.nodes==0 and summary.binary_bytes==8192 and not summary.complete)
        assert(summary.error==(damage=='root' and 'UI_TREE_ROOT_PIN_NOT_UNIQUE' or 'UI_TREE_ROOT_PIN_TARGET_MISMATCH'))
    end
end)
check('v1/v2 exhausted records stay untouched and do not block v3 sampling',function()
    local old={format='HD2-UI-TREE-STATE-1',build=Native.source.exe_sha,dll_sha=Native.source.dll_sha,
        attempts={map_closed=3,map_open=3},saved={}}
    local old_text=codec.encode(old)
    local old_path='fixture/probe/ledger_ui_tree_'..Native.source.exe_sha:sub(1,12)..'.state.json'
    local files={[old_path]={parts={old_text},closed=true}}
    local data={ui_tree_probe_v1=codec.decode(old_text)}
    local old_v2={format='HD2-UI-TREE-STATE-2',source_revision='root_attach_v2',
        build=Native.source.exe_sha,dll_sha=Native.source.dll_sha,attempts={map_closed=3,map_open=3},saved={}}
    local old_v2_text=codec.encode(old_v2)
    local old_v2_path='fixture/probe/ledger_ui_tree_v2_'..Native.source.exe_sha:sub(1,12)..'.state.json'
    files[old_v2_path]={parts={old_v2_text},closed=true};data.ui_tree_probe_v2=codec.decode(old_v2_text)
    local f=fixture({files=files,data=data,include_code=false})
    assert(f.probe:status_snapshot().attempts.map_closed==0 and f.probe.prefix:find('/ledger_ui_tree_v3_',1,true))
    f:until_status(function(s)return s.done.map_closed end)
    assert(codec.encode(f.data.ui_tree_probe_v1)==old_text and table.concat(f.files[old_path].parts)==old_text)
    assert(codec.encode(f.data.ui_tree_probe_v2)==old_v2_text and table.concat(f.files[old_v2_path].parts)==old_v2_text)
    assert(f.data.ui_tree_probe_v3.source_revision=='root_base_v3')
end)
check('waits beyond 120 seconds; disabled probe does zero native reads',function()
    local f=fixture({mission=false})
    for _,n in ipairs({0,120,1200,9000})do local s=f:step(n);assert(s.status=='waiting_mission' and s.read_last==0 and s.attempts.map_closed==0)end
    f.probe:set_enabled(false);local before=f.reads;f.probe:step(nil,nil,9001)
    assert(f.reads==before and f.probe:status_snapshot().status=='disabled')
    f.probe:set_enabled(true);f.mission=true
    f:until_status(function(s)return s.done.map_closed end)
end)
check('unique pin, tree geometry, code bytes and final identity fit hard budget',function()
    -- Fast deterministic boundary: verifies scheduling, not real frame time.
    os.clock=function()return 0 end
    local f=fixture({nodes=1024})
    local s=f:until_status(function(v)return v.done.map_closed end)
    local sample=f:sample();local summary=sample.summary
    assert(#sample.nodes==1024 and summary.nodes==1024 and summary.complete)
    assert(f.now<=13 and summary.max_nodes_per_step==16 and summary.max_operations_per_step==32)
    assert(summary.atomic==false and summary.self_root_corroborated and summary.identity_consistent)
    assert(summary.source_pin.rva==0x12F133A and summary.read_peak<=16373 and f.peak<=16384)
    assert(summary.source_pin.length==22 and f.final_pin_length==22
        and summary.source_pin.hud_global==0x346D538 and summary.source_pin.root_offset==0x258
        and summary.source_pin.widget_attach==0x144C5C0 and summary.source_revision=='root_base_v3')
    assert(#summary.code_ranges>=21 and summary.binary_bytes==8192+1024*256+0x28000)
    assert(sample.nodes[2].geometry.width==180 and sample.nodes[2].geometry.x==1200)
    local status=codec.decode(table.concat(f.files[summary.status_path].parts));assert(status.complete)
    local total=0;for _,path in ipairs({summary.binary_path,summary.json_path,summary.status_path})do total=total+#table.concat(f.files[path].parts)end
    assert(total<=1048576,'bounded sample output '..total)
    f:step();assert(f.probe:status_snapshot().read_last==0)
end)
check('normal map opening saves other mode and reload does zero tree reads',function()
    local f=fixture();f:until_status(function(s)return s.done.map_closed end)
    f.map=true;f:until_status(function(s)return s.done.map_closed and s.done.map_open end)
    local count=0;for _ in pairs(f.files)do count=count+1 end;assert(count<=9)
    f.probe=f:new_probe();local s=f:step(5000);assert(s.done.map_open and s.done.map_closed and s.read_last==0)
    assert(f.data.ui_tree_probe_v3.saved.map_open.complete)
    local old=f.data.ui_tree_probe_v3.saved.map_open
    f.files[old.binary_path]=nil;f.probe=f:new_probe()
    assert(not f.probe:status_snapshot().done.map_open and f.probe:status_snapshot().attempts.map_open==0)
    f:until_status(function(v)return v.done.map_open end)
end)
check('foreign DLL success markers never suppress current-build collection',function()
    local f=fixture();f:until_status(function(s)return s.done.map_closed end)
    f.data.ui_tree_probe_v3.dll_sha='OTHER_DLL'
    local persisted=codec.decode(table.concat(f.files[f.probe.state_path].parts))
    persisted.dll_sha='OTHER_DLL';f.files[f.probe.state_path].parts={codec.encode(persisted)}
    local saved=f.data.ui_tree_probe_v3.saved.map_closed
    local marker=codec.decode(table.concat(f.files[saved.marker_path].parts))
    marker.dll_sha='OTHER_DLL';f.files[saved.marker_path].parts={codec.encode(marker)}
    f.probe=f:new_probe();assert(not f.probe:status_snapshot().done.map_closed)
    f:until_status(function(s)return s.done.map_closed end)
end)
check('partial progress is valid and cancel leaves honest metadata with no native reads',function()
    local f=fixture({nodes=1024});f:step(0);local s=f:step(.6);assert(s.active)
    local a=f.probe.active;local progress=codec.decode(table.concat(f.files[a.status_path].parts))
    assert(progress.complete==false and progress.error=='UI_TREE_CAPTURE_IN_PROGRESS')
    assert(not a.binary and not a.metadata)
    local reads=f.reads;f.probe:cancel('MANUAL_PRIORITY');assert(f.reads==reads)
    local sample=f:sample();assert(sample.summary.complete==false and sample.summary.error=='MANUAL_PRIORITY')
    assert(not f.probe:status_snapshot().done.map_closed)
end)
check('start tick reads no PIN; slow clock yields and resumes with bounded nodes/operations',function()
    local clock=0;os.clock=function()clock=clock+.0008;return clock end
    local f=fixture({nodes=40,include_code=false});f:step(0)
    local started=f:step(.6)
    assert(started.active and started.read_last==0 and started.nodes_last==0 and started.operations_last==0)
    assert(f.bytes==11,'standalone start cannot read PIN or tree')
    local yielded=false;local last_nodes=0
    f:until_status(function(s)
        assert(s.nodes_last<=3 and s.operations_last<=3,'slow clock must yield between bounded operations')
        if s.active and s.nodes>last_nodes then yielded=true end
        last_nodes=s.nodes
        return s.done.map_closed
    end)
    assert(yielded and f:sample().summary.nodes==40 and f:sample().summary.soft_budget_ms==2)
    local binary=table.concat(f.files[f:sample().summary.binary_path].parts)
    assert(binary:sub(8193,8448)==actual_root)
end)
check('a slow step still advances one operation instead of starving after file open',function()
    local clock=0;os.clock=function()clock=clock+.01;return clock end
    local f=fixture({nodes=3,include_code=false});f:step(0);f:step(.6)
    f:until_status(function(s)
        assert(s.operations_last==1,'soft checkpoint must allow the first operation')
        return s.done.map_closed
    end)
    assert(f:sample().summary.complete)
end)
check('world/map/mission change cancels partial sample instead of mixing states',function()
    for _,change in ipairs({'map','hud','world','mission'})do
        local f=fixture({nodes=1024});f:step(0);f:step(.6)
        local state={mission=true,map_open=false,hud=f.hud};local world=f.world
        if change=='map'then state.map_open=true elseif change=='hud'then state.hud=f.hud+8
        elseif change=='world'then world={game=f.game,exe=f.world.exe,key='other',view=f.world.view}
        else state.mission=false end
        local s=f:step(.7,state,world);assert(s.status=='incomplete' and s.read_last==0)
        assert(f:sample().summary.error=='UI_TREE_WORLD_MAP_OR_MISSION_CHANGED')
    end
end)
check('missing or duplicate pins produce finite failures with persistent attempt limit',function()
    for _,options in ipairs({{pin=false},{multiple_pin=true}})do
        local f=fixture(options)
        for i=1,3 do
            f:until_status(function(s)return s.attempts.map_closed==i and not s.active and s.status=='incomplete'end,100)
            local summary=f:sample().summary
            assert(summary.error=='UI_TREE_ROOT_PIN_NOT_UNIQUE' and summary.binary_bytes==8192
                and #summary.code_ranges==1 and summary.build==Native.source.exe_sha
                and summary.dll_sha==Native.source.dll_sha and summary.nodes==0)
            f.now=f.now+2
        end
        local s=f:step();assert(s.status=='exhausted' and s.read_last==0)
        f.probe=f:new_probe();assert(f:step().status=='exhausted')
        local count=0;for _ in pairs(f.files)do count=count+1 end;assert(count<=10)
    end
end)
check('nil/short node reads and malformed child relationships stay incomplete',function()
    for _,failure in ipairs({'nil','short','parent','context','cycle','limit','depth'})do
        local f=fixture({nodes=failure=='limit' and 1025 or failure=='depth' and 27 or 3,include_code=false})
        local first=f.nodes[1]
        if failure=='nil' or failure=='short'then f.fail_at=first;f.short=failure=='short'
        elseif failure=='parent'then f:replace(first,node(f.root+8,0,0,f.context,3))
        elseif failure=='context'then f:replace(first,node(f.root,0,0,f.context+8,3))
        elseif failure=='cycle'then f:replace(first,node(f.root,0,first,f.context,3))
        elseif failure=='depth'then
            for i,at in ipairs(f.nodes)do f:replace(at,node(i==1 and f.root or f.nodes[i-1],f.nodes[i+1] or 0,0,f.context,3))end
        end
        f:until_status(function(s)return s.status=='incomplete' end)
        assert(not f.probe:status_snapshot().done.map_closed and not f:sample().summary.complete)
        if failure=='short'then
            local bad=f:sample().summary.failure
            assert(bad.requested==256 and bad.returned_length==255 and not bad.binary_length)
        end
    end
end)
check('invalid root and child preserve exact raw candidates without fake nodes or extra reads',function()
    for _,phase in ipairs({'root','tree'})do
        local f=fixture({include_code=false})
        local at=phase=='root' and f.root or f.nodes[1]
        local raw=node(phase=='root' and 0 or f.root+8,0,0,f.context,1)
        f:replace(at,raw)
        f:until_status(function(s)return s.status=='incomplete'end)
        local summary=f:sample().summary;local failure=summary.failure
        local binary=table.concat(f.files[summary.binary_path].parts)
        assert(failure.phase==phase and failure.address==at and failure.requested==256
            and failure.returned_length==256 and failure.binary_length==256)
        assert(binary:sub(failure.binary_offset+1,failure.binary_offset+256)==raw)
        assert(failure.flags==0x40010
            and failure.kind==1 and failure.context==f.context
            and failure.parent==(phase=='root' and 0 or f.root+8))
        assert(summary.nodes==(phase=='root' and 0 or 1))
        assert(f.probe_bytes==8192+(phase=='root' and 256 or 1024), 'failed structure must not add native reads')
        assert(not f.probe:status_snapshot().done.map_closed)
    end
end)
check('final native state is rechecked rather than trusting stale polled state',function()
    local f=fixture({include_code=false});f:step(0)
    local stale={hud=f.hud,mission=true,map_open=false};f.map=true
    local s=f:step(.6,stale)
    for _=1,30 do if s.status=='incomplete'then break end;s=f:step(nil,stale)end
    assert(s.status=='incomplete')
    assert(f:sample().summary.error=='UI_TREE_FINAL_NATIVE_STATE_CHANGED')
end)
check('lost file destination stays bounded and never records fake success',function()
    local f=fixture();f.fail_file='.bin'
    for _=1,80 do f:step();f.now=f.now+.2 end
    local s=f.probe:status_snapshot();assert(s.attempts.map_closed==3 and not s.done.map_closed and not s.active)
end)
print('PASS ui-tree-probe '..tests..' scenarios')
