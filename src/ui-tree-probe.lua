-- A finite, read-only witness of the native HUD tree, not a task relocator.
-- World must come from the Runtime's fingerprint/pin-proven event_world.open().
local profile = require('hd2runtime/schemas/current')
local json = require('hd2runtime/runtime/mod_store')
local ffi = require('ffi')
local M = {limits = {read_per_step = 16384, reserve = 11, nodes = 1024,
    depth = 24, attempts = 3, output = 1048576, stable_seconds = 0.5,
    nodes_per_step=16,operations_per_step=32,soft_seconds=0.002},
    source = {revision='root_base_v3',store_key='ui_tree_probe_v3',
        hud_global = 0x346D538, root = 0x258, mission = 0x24E340,widget_attach=0x144C5C0,
        self_panel = 0x60, child = 0xE0, sibling = 0xE8, parent = 0xF0,
        context = 0xF8, node_size = 0x100,
        setup_window = {rva = 0x12F0000, length = 0x2000},
        root_pattern = '488B1D????????488BD6488D8B58020000E8????????',
        reference = 'Actual 0.4.4 attach PIN / actual 0.4.5 kind-0 HUD root; HUD Plus 0.2.2 root_build/common widget base'},
    code_windows = {{name = 'mission_hud_code', rva = 0x12E8000, size = 0x10000},
        {name = 'widget_layout_code', rva = 0x143A000, size = 0x18000}}}
local Probe = {}; Probe.__index = Probe
local modes = {'map_closed', 'map_open'}
local function address(v)
    return type(v) == 'number' and v >= 65536 and v < 140737488355328 and v % 8 == 0
end
local function u32(s, o)
    local a,b,c,d = s:byte(o+1,o+4)
    return a + b*256 + c*65536 + d*16777216
end
local function ptr(s,o) return u32(s,o) + u32(s,o+4)*4294967296 end
local function i32(s,o)local n=u32(s,o);return n>=2147483648 and n-4294967296 or n end
local function hex(s) return (s:gsub('.',function(c)return string.format('%02X',c:byte())end)) end
local function unhex(s) return (s:gsub('..',function(c)return string.char(tonumber(c,16))end)) end
local function exists(path)
    if type(path) ~= 'string' then return false end
    local f = io.open(path,'rb'); if not f then return false end
    f:close(); return true
end
local function load(path)
    if not path then return nil end
    local f = io.open(path,'rb'); if not f then return nil end
    local ok,text = pcall(function() return f:read(16385) end); f:close()
    if not ok or type(text) ~= 'string' or #text > 16384 then return nil end
    local parsed,value = pcall(json.decode,text)
    return parsed and type(value) == 'table' and value or nil
end
local function save(path, value)
    local f = path and io.open(path,'wb'); if not f then return false end
    local ok,wrote = pcall(function() return f:write(json.encode(value)) end)
    local closed = f:close(); return ok and wrote ~= nil and closed ~= nil
end
local function source_state(s)
    return s and {hud=s.hud,mission=s.mission,map_open=s.map_open} or nil
end
local function mode(s) return s.map_open and 'map_open' or 'map_closed' end
local function kind(raw) return math.floor(u32(raw,0)/0x40000)%16 end
local function identity(raw)
    return {kind=kind(raw),parent=ptr(raw,0xF0),context=ptr(raw,0xF8),
        child=ptr(raw,0xE0),sibling=ptr(raw,0xE8)}
end
local function same(a,b)
    return a and b and a.kind==b.kind and a.parent==b.parent and a.context==b.context
        and a.child==b.child and a.sibling==b.sibling
end
local function f32(s,o)
    local v=ffi.new('float[1]'); ffi.copy(v,s:sub(o+1,o+4),4)
    local n=tonumber(v[0]); if n==n and math.abs(n)<1e9 then return n end
end
local function geometry(raw)
    return {x=f32(raw,0x94),y=f32(raw,0x98),width=f32(raw,0x24),height=f32(raw,0x28),
        local_x=f32(raw,4),local_y=f32(raw,8),scale_x=f32(raw,0x64),scale_y=f32(raw,0x78)}
end
local function sane(raw,parent,context)
    -- Root and frame are different constructors. Root kind 0 is a live widget
    -- base (actual 0.4.5 sample); nonzero flags + ownership validate the base.
    if u32(raw,0)==0 or not address(ptr(raw,0xF8)) then return false end
    for _,o in ipairs({0xE0,0xE8,0xF0}) do
        local p=ptr(raw,o); if p~=0 and not address(p) then return false end
    end
    return (parent==nil or ptr(raw,0xF0)==parent) and (not context or ptr(raw,0xF8)==context)
end

function M.new(options)
    options=options or {}
    local base=os.getenv('LOCALAPPDATA')
    local directory=options.directory or (base and base..'/HD2Runtime/mod_data')
    local bridge=options.bridge
    local source=bridge and bridge.source or {}
    local key=tostring(source.exe_sha or 'unknown'):sub(1,12)
    local self=setmetatable({bridge=bridge,store=options.store,directory=directory,
        log=options.log or function()end,enabled=options.enabled~=false,status='waiting_mission',
        attempts={map_closed=0,map_open=0},done={},saved={},sequence=0,
        read_last=0,read_peak=0,reserve=options.reserve_bytes==nil and 11 or options.reserve_bytes,
        nodes_last=0,operations_last=0,operations_peak=0,
        include_code=options.include_code~=false,build=source.exe_sha,dll_sha=source.dll_sha,
        prefix=directory and directory..'/ledger_ui_tree_v3_'..key},Probe)
    assert(type(self.reserve)=='number' and self.reserve>=0 and self.reserve<=1024,'invalid read reserve')
    self.state_path=self.prefix and self.prefix..'.state.json'
    local old=load(self.state_path)
    if self.store and type(self.store.get)=='function' then
        local ok,value=pcall(self.store.get,self.store,M.source.store_key,{})
        if ok and type(value)=='table' and value.build==self.build and value.dll_sha==self.dll_sha
            and value.source_revision==M.source.revision then old=value end
    end
    if old and old.build==self.build and old.dll_sha==self.dll_sha and old.source_revision==M.source.revision then
        for _,name in ipairs(modes)do
            local count=old.attempts and old.attempts[name]
            if type(count)=='number' and count>=0 then self.attempts[name]=math.min(3,math.floor(count)) end
            self.saved[name]=old.saved and old.saved[name]
        end
    end
    for _,name in ipairs(modes)do
        local marker_path=self.prefix and self.prefix..'_'..name..'.done.json'
        local marker=load(marker_path)
        local saved=self.saved[name]
        if marker and marker.build==self.build and marker.dll_sha==self.dll_sha and marker.source_revision==M.source.revision
            and marker.complete==true and marker.mode==name then saved=marker end
        if saved and saved.complete==true and saved.build==self.build and saved.dll_sha==self.dll_sha
            and saved.source_revision==M.source.revision and saved.mode==name
            and exists(saved.binary_path) and exists(saved.json_path) and exists(saved.marker_path) then
            self.saved[name],self.done[name]=saved,true
        else
            -- A success marker without its artifacts is not a completed mode.
            if saved and saved.complete==true then self.attempts[name]=0 end
            self.saved[name]=nil
        end
    end
    if not self.enabled then self.status='disabled'
    elseif self.done.map_open and self.done.map_closed then self.status='complete' end
    return self
end
function Probe:_persist()
    local state={format='HD2-UI-TREE-STATE-3',source_revision=M.source.revision,
        build=self.build,dll_sha=self.dll_sha,attempts=self.attempts,saved=self.saved}
    if self.store and type(self.store.set)=='function' then pcall(self.store.set,self.store,M.source.store_key,state) end
    return save(self.state_path,state)
end
function Probe:_read(world,at,n)
    if self.read_last+n>M.limits.read_per_step-self.reserve then return nil,'budget' end
    self.read_last=self.read_last+n; self.read_peak=math.max(self.read_peak,self.read_last)
    local ok,raw=pcall(world.view.read,at,n)
    if not ok or type(raw)~='string' or #raw~=n then
        if self.active then self.active.failure={address=at,requested=n,
            returned_length=type(raw)=='string' and #raw or nil,read_error=not ok and tostring(raw) or nil} end
        return nil,'UI_TREE_SHORT_READ'
    end
    return raw
end
function Probe:_put(file,text)
    local a=self.active
    if a.bytes+#text+16384>M.limits.output then return nil,'UI_TREE_OUTPUT_LIMIT' end
    local ok,wrote=pcall(file.write,file,text)
    if not ok or not wrote then return nil,'UI_TREE_FILE_WRITE' end
    a.bytes=a.bytes+#text; return true
end
function Probe:_binary(raw)
    local a=self.active; local offset=a.binary_bytes
    local ok,why=self:_put(a.binary,raw); if not ok then return nil,why end
    a.binary_bytes=a.binary_bytes+#raw; return offset
end
function Probe:_invalid_node(raw,at,reason,state,parent)
    -- The read already succeeded. Preserve this candidate, without following
    -- any untrusted links or counting it as a validated tree node.
    local a=self.active
    a.failure={phase=a.phase,address=at,requested=256,returned_length=#raw,
        flags=u32(raw,0),kind=kind(raw),parent=ptr(raw,0xF0),context=ptr(raw,0xF8),
        expected_parent=parent}
    local offset,err=self:_binary(raw)
    if offset then a.failure.binary_offset=offset;a.failure.binary_length=#raw end
    return self:_finish(err or reason,state)
end
function Probe:_close_handles()
    local a=self.active; if not a then return true end
    local ok=true
    for _,name in ipairs({'binary','metadata'})do
        local file=a[name]
        if file then
            local flushed,value=pcall(file.flush,file)
            local closed,result=pcall(file.close,file)
            ok=ok and flushed and value~=nil and closed and result~=nil
            a[name]=nil
        end
    end
    return ok
end
function Probe:_open_handles()
    local a=self.active
    if not a.binary then a.binary=io.open(a.binary_path,'ab') end
    if not a.metadata then a.metadata=io.open(a.json_path,'ab') end
    return a.binary~=nil and a.metadata~=nil
end
function Probe:_finish(reason,state)
    local a=self.active; if not a then return true end
    local summary={source_revision=M.source.revision,build=self.build,dll_sha=self.dll_sha,
        complete=reason==nil,error=reason,finished_at=os.time(),atomic=false,
        mode=a.mode,nodes=a.nodes,binary_bytes=a.binary_bytes,output_bytes=a.bytes,
        start_state=a.start_state,end_state=source_state(state),identity_consistent=reason==nil,
        root_identity=a.root_identity,root_end_identity=a.root_end_identity,
        self_root_corroborated=a.corroborated==true,ancestor_chain=a.ancestors,
        source_pin=a.pin,code_ranges=a.code_ranges,read_per_step=M.limits.read_per_step-self.reserve,
        max_nodes_per_step=M.limits.nodes_per_step,max_operations_per_step=M.limits.operations_per_step,
        operations_peak=self.operations_peak,soft_budget_ms=M.limits.soft_seconds*1000,
        read_peak=self.read_peak,binary_path=a.binary_path,json_path=a.json_path,
        failure=a.failure,status_path=a.status_path}
    local encoded_summary=json.encode(summary)
    local tail='],"summary":'..encoded_summary..'}'
    local opened=self:_open_handles()
    local ok,wrote=false,nil
    if opened and a.bytes+#tail+#encoded_summary<=M.limits.output then
        ok,wrote=pcall(a.metadata.write,a.metadata,tail)
    end
    local closed=self:_close_handles()
    if not opened or not ok or not wrote or not closed then summary.complete=false;summary.error='UI_TREE_CLOSE_WRITE_FAILED' end
    -- This valid companion survives an abrupt process exit while the streamed
    -- nodes array is still open. A partial main JSON is never a success marker.
    if not save(a.status_path,summary) then summary.complete=false;summary.error='UI_TREE_STATUS_WRITE_FAILED' end
    self.active=nil; self.last=summary; self.reason=summary.error
    self.last_path=a.json_path; self.status=summary.complete and 'complete' or 'incomplete'
    if summary.complete then
        local marker={format='HD2-UI-TREE-DONE-3',source_revision=M.source.revision,
            build=self.build,dll_sha=self.dll_sha,complete=true,mode=a.mode,
            binary_path=a.binary_path,json_path=a.json_path,status_path=a.status_path,
            marker_path=self.prefix..'_'..a.mode..'.done.json'}
        if exists(a.binary_path) and exists(a.json_path) and save(marker.marker_path,marker) then
            self.saved[a.mode],self.done[a.mode]=marker,true
        else
            self.status='incomplete';self.reason='UI_TREE_SUCCESS_MARKER_FAILED'
            summary.complete=false;summary.error=self.reason;save(a.status_path,summary)
        end
    end
    self:_persist();self.stable=nil;self.retry_at=(self.now or 0)+2
    self.log('自动UI定位 '..self.status..'：'..a.json_path)
    return summary
end
function Probe:cancel(reason)
    self.stable=nil
    return self:_finish(reason or 'UI_TREE_CANCELLED') -- zero additional game reads
end
function Probe:set_enabled(enabled)
    self.enabled=enabled==true
    if not self.enabled then self:cancel('UI_TREE_DISABLED');self.status='disabled' end
    return self.enabled
end
function Probe:status_snapshot()
    return {enabled=self.enabled,status=self.status,active=self.active~=nil,
        mode=self.active and self.active.mode or self.last and self.last.mode,
        attempts={map_closed=self.attempts.map_closed,map_open=self.attempts.map_open},
        done={map_closed=self.done.map_closed==true,map_open=self.done.map_open==true},
        last_path=self.last_path,reason=self.reason,read_last=self.read_last,read_peak=self.read_peak,
        nodes_last=self.nodes_last,operations_last=self.operations_last,
        max_nodes_per_step=M.limits.nodes_per_step,max_operations_per_step=M.limits.operations_per_step,
        soft_budget_ms=M.limits.soft_seconds*1000,
        nodes=self.active and self.active.nodes or self.last and self.last.nodes or 0}
end
function Probe:_start(world,state,now)
    local name=mode(state);self.attempts[name]=self.attempts[name]+1;self:_persist()
    local stem
    if self.prefix then for _=1,20 do
        self.sequence=self.sequence+1
        local candidate=self.prefix..'_'..os.date('!%Y%m%dT%H%M%SZ')..'_'..name..'_'..self.attempts[name]..'_'..self.sequence
        if not exists(candidate..'.bin') and not exists(candidate..'.json') and not exists(candidate..'.status.json') then stem=candidate;break end
    end end
    if not stem then self.reason='UI_TREE_DIRECTORY_UNAVAILABLE';self.status='incomplete';return nil end
    local binary=io.open(stem..'.bin','wb');local metadata=io.open(stem..'.json','wb')
    if not binary or not metadata then
        if binary then binary:close()end;if metadata then metadata:close()end
        self.reason='UI_TREE_FILE_OPEN_FAILED';self.status='incomplete';self.retry_at=now+2;self.stable=nil;return nil
    end
    self.active={binary=binary,metadata=metadata,binary_path=stem..'.bin',json_path=stem..'.json',
        status_path=stem..'.status.json',
        mode=name,start_state=source_state(state),world_key=world.key,game=world.game,exe=world.exe,
        root=state.hud+M.source.root,phase='pin',nodes=0,bytes=0,binary_bytes=0,
        ancestors={},code_ranges={},seen={},stack={},started=now,code_index=1,code_offset=0}
    self.status='capturing';self.reason=nil
    local header={format='HD2-UI-TREE-3',source_revision=M.source.revision,build=self.build,dll_sha=self.bridge.source.dll_sha,
        reference=M.source.reference,root_offset=M.source.root,node_size=256,atomic=false,
        started_at=os.time(),attempt=self.attempts[name],mode=name,game_base=world.game,exe_base=world.exe,
        start_state=source_state(state),binary_path=stem..'.bin',json_path=stem..'.json'}
    local text=json.encode(header);text=text:sub(1,-2)..',"nodes":['
    local ok,why=self:_put(metadata,text);if not ok then self:_finish(why,state);return nil end
    if not save(self.active.status_path,{format='HD2-UI-TREE-PROGRESS-3',source_revision=M.source.revision,
        build=self.build,dll_sha=self.dll_sha,
        complete=false,error='UI_TREE_CAPTURE_IN_PROGRESS',atomic=false,mode=name,
        start_state=source_state(state),binary_path=stem..'.bin',json_path=stem..'.json',
        started_at=header.started_at}) then self:_finish('UI_TREE_STATUS_WRITE_FAILED',state);return nil end
    return true
end
function Probe:_advance(world,state)
    local a=self.active
    if a.phase=='pin' then
        local w=M.source.setup_window
        local raw,why=self:_read(world,world.game+w.rva,w.length);if not raw then
            if why=='budget' then return false end;return self:_finish(why,state)
        end
        local prefix=unhex('488B1D');local suffix=unhex('488BD6488D8B58020000E8')
        local matches={};local first=1
        while true do
            local at=raw:find(prefix,first,true);if not at then break end
            if raw:sub(at+7,at+17)==suffix and at+21<=#raw then matches[#matches+1]=at end
            first=at+1
        end
        -- Keep the actual bounded code bytes even on a missing/ambiguous pin;
        -- they are offline evidence, never permission to enter an unproven tree.
        local offset,err=self:_binary(raw);if not offset then return self:_finish(err,state) end
        a.code_ranges[#a.code_ranges+1]={name='root_pin_window',rva=w.rva,length=#raw,binary_offset=offset}
        if #matches~=1 then return self:_finish('UI_TREE_ROOT_PIN_NOT_UNIQUE',state) end
        local at=matches[1];local rva=w.rva+at-1
        local hud_global=rva+7+i32(raw,at-1+3)
        local root_offset=u32(raw,at-1+13)
        local attach=rva+22+i32(raw,at-1+18)
        a.pin={rva=rva,length=22,bytes=hex(raw:sub(at,at+21)),
            pattern=M.source.root_pattern,root_offset=root_offset,hud_global=hud_global,
            widget_attach=attach,window_rva=w.rva,window_length=w.length}
        if hud_global~=M.source.hud_global or root_offset~=M.source.root or attach~=M.source.widget_attach then
            return self:_finish('UI_TREE_ROOT_PIN_TARGET_MISMATCH',state)
        end
        a.phase='root';return true
    elseif a.phase=='root' then
        local raw,why=self:_read(world,a.root,256);if not raw then
            if why=='budget' then return false end;return self:_finish(why,state)
        end
        if not sane(raw) or kind(raw)~=0 or ptr(raw,0xF0)~=0 or ptr(raw,0xE8)~=0 then
            return self:_invalid_node(raw,a.root,'UI_TREE_ROOT_INVALID',state)
        end
        a.root_identity=identity(raw);a.context=a.root_identity.context
        a.ancestor_at=state.hud+M.source.mission+M.source.self_panel;a.ancestor_seen={};a.phase='ancestors';return true
    elseif a.phase=='ancestors' then
        local at=a.ancestor_at
        if at==a.root then a.corroborated=true;a.phase='tree';a.stack[1]={at=a.root,depth=0};return true end
        if at==0 then a.phase='tree';a.stack[1]={at=a.root,depth=0};return true end
        if not address(at) or a.ancestor_seen[at] or #a.ancestors>=24 then return self:_finish('UI_TREE_ANCESTOR_CYCLE_LIMIT',state) end
        local raw,why=self:_read(world,at,256);if not raw then
            if why=='budget' then return false end;return self:_finish(why,state)
        end
        if not sane(raw,nil,a.context) then return self:_invalid_node(raw,at,'UI_TREE_ANCESTOR_CONTEXT_INVALID',state) end
        a.ancestor_seen[at]=true;a.ancestors[#a.ancestors+1]={address=at,parent=ptr(raw,0xF0),kind=kind(raw),context=ptr(raw,0xF8)}
        a.ancestor_at=ptr(raw,0xF0);return true
    elseif a.phase=='tree' then
        local item=a.stack[#a.stack]
        if not item then a.phase=self.include_code and 'code' or 'verify';return true end
        if a.nodes>=1024 then return self:_finish('UI_TREE_NODE_LIMIT',state) end
        if item.depth>24 or a.seen[item.at] then return self:_finish('UI_TREE_DEPTH_CYCLE',state) end
        local raw,why=self:_read(world,item.at,256);if not raw then
            if why~='budget' then self.nodes_last=self.nodes_last+1 end
            if why~='budget' then return self:_finish(why,state) end
            return false
        end
        self.nodes_last=self.nodes_last+1
        if not sane(raw,item.parent,a.context) then return self:_invalid_node(raw,item.at,'UI_TREE_CHILD_PARENT_CONTEXT_INVALID',state,item.parent) end
        if item.at==a.root and not same(a.root_identity,identity(raw)) then return self:_invalid_node(raw,item.at,'UI_TREE_ROOT_CHANGED',state) end
        local offset,err=self:_binary(raw);if not offset then return self:_finish(err,state) end
        local row={address=item.at,depth=item.depth,parent=ptr(raw,0xF0),child=ptr(raw,0xE0),
            sibling=ptr(raw,0xE8),context=a.context,kind=kind(raw),flags=u32(raw,0),
            geometry=geometry(raw),binary_offset=offset,binary_length=256}
        local ok,write_error=self:_put(a.metadata,(a.nodes>0 and ',' or '')..json.encode(row))
        if not ok then return self:_finish(write_error,state) end
        a.stack[#a.stack]=nil;a.nodes=a.nodes+1;a.seen[item.at]=true
        if item.at~=a.root and row.sibling~=0 then a.stack[#a.stack+1]={at=row.sibling,parent=item.parent,depth=item.depth} end
        if row.child~=0 then a.stack[#a.stack+1]={at=row.child,parent=item.at,depth=item.depth+1} end
        return true
    elseif a.phase=='code' then
        local window=M.code_windows[a.code_index]
        if not window then a.phase='verify';return true end
        local n=math.min(8192,window.size-a.code_offset,M.limits.read_per_step-self.reserve-self.read_last)
        -- A window can have a final tail smaller than 256 bytes after budget
        -- splitting. Read that tail; only defer a small *budget* remainder.
        if n<=0 or n<256 and n<window.size-a.code_offset then return false end
        local raw,why=self:_read(world,world.game+window.rva+a.code_offset,n)
        if not raw then
            a.failure=a.failure or {};a.failure.rva=window.rva+a.code_offset
            return self:_finish(why,state)
        end
        local offset,err=self:_binary(raw);if not offset then return self:_finish(err,state) end
        a.code_ranges[#a.code_ranges+1]={name=window.name,rva=window.rva+a.code_offset,length=n,binary_offset=offset}
        a.code_offset=a.code_offset+n
        if a.code_offset==window.size then a.code_index=a.code_index+1;a.code_offset=0 end
        return true
    elseif a.phase=='verify' then
        -- All final reads fit in one step; never half-verify then call complete.
        if self.read_last+290>M.limits.read_per_step-self.reserve then return false end
        local raw,why=self:_read(world,a.root,256)
        if not raw then return self:_finish(why,state) end
        a.root_end_identity=identity(raw)
        if not same(a.root_identity,a.root_end_identity) then return self:_invalid_node(raw,a.root,'UI_TREE_FINAL_IDENTITY_CHANGED',state) end
        local pin,err=self:_read(world,world.game+a.pin.rva,a.pin.length)
        if not pin or hex(pin)~=a.pin.bytes then return self:_finish(err or 'UI_TREE_ROOT_PIN_CHANGED',state) end
        local hud,fail=self:_read(world,world.game+M.source.hud_global,8)
        if not hud or ptr(hud,0)~=a.start_state.hud then return self:_finish(fail or 'UI_TREE_FINAL_HUD_CHANGED',state) end
        local offsets=self.bridge.source
        for _,entry in ipairs({{offsets.mission_hud+offsets.mission_shown,1},
            {offsets.mission_hud+offsets.mission_ready,1},{offsets.map_open,a.mode=='map_open' and 1 or 0}})do
            local value,failure=self:_read(world,a.start_state.hud+entry[1],1)
            if not value or value:byte()~=entry[2] then return self:_finish(failure or 'UI_TREE_FINAL_NATIVE_STATE_CHANGED',state) end
        end
        return self:_finish(nil,state)
    end
end
function Probe:step(world,state,now)
    self.read_last=0;self.nodes_last=0;self.operations_last=0
    self.now=type(now)=='number' and now or 0
    local step_started=os.clock()
    if not self.enabled then self.status='disabled';return self:status_snapshot() end
    if self.done.map_open and self.done.map_closed then self.status='complete';return self:status_snapshot() end
    if not self.bridge or not self.bridge.source or profile.exe_sha~=self.bridge.source.exe_sha
        or profile.dll_sha~=self.bridge.source.dll_sha then
        if self.active then self:_finish('UI_TREE_BUILD_MISMATCH',state) end
        self.status='incomplete';self.reason='UI_TREE_BUILD_MISMATCH';return self:status_snapshot()
    end
    local valid=type(world)=='table' and address(world.game) and address(world.exe) and type(world.view)=='table'
        and type(world.view.read)=='function' and type(state)=='table' and state.mission==true
        and address(state.hud) and type(state.map_open)=='boolean'
    local a=self.active
    if a and (not valid or world.game~=a.game or world.exe~=a.exe or world.key~=a.world_key
        or state.hud~=a.start_state.hud or state.map_open~=a.start_state.map_open) then
        self:_finish('UI_TREE_WORLD_MAP_OR_MISSION_CHANGED',state);return self:status_snapshot()
    end
    if not valid then self.stable=nil;self.status='waiting_mission';return self:status_snapshot() end
    local name=mode(state)
    if not a then
        if self.done[name] then self.status='waiting_map';return self:status_snapshot() end
        if self.attempts[name]>=3 then self.status='exhausted';return self:status_snapshot() end
        if self.retry_at and self.now<self.retry_at then return self:status_snapshot() end
        if not self.stable or self.stable.mode~=name or self.stable.hud~=state.hud or self.stable.world~=world.key then
            self.stable={mode=name,hud=state.hud,world=world.key,since=self.now}
        end
        self.status='waiting_stable'
        if self.now-self.stable.since<M.limits.stable_seconds then return self:status_snapshot() end
        if not self:_start(world,state,self.now) then return self:status_snapshot() end
        -- Start writes its small files alone. No PIN/tree read in this tick.
        if self.active and not self:_close_handles() then self:_finish('UI_TREE_FILE_FLUSH_FAILED',state) end
        return self:status_snapshot()
    end
    if self.now-self.active.started>30 then self:_finish('UI_TREE_ACTIVE_TIMEOUT',state);return self:status_snapshot() end
    if not self:_open_handles() then self:_finish('UI_TREE_FILE_REOPEN_FAILED',state);return self:status_snapshot() end
    -- A soft checkpoint between bounded operations, never a hard frame-time
    -- guarantee. One read, file write/flush/close or finalization can exceed it.
    while self.active and self.operations_last<M.limits.operations_per_step
        and self.nodes_last<M.limits.nodes_per_step do
        if self.operations_last>0 and os.clock()-step_started>=M.limits.soft_seconds then break end
        local phase=self.active.phase
        self.operations_last=self.operations_last+1
        self.operations_peak=math.max(self.operations_peak,self.operations_last)
        local advanced=self:_advance(world,state);if advanced==false then break end
        if self.active and self.active.phase~=phase then break end
    end
    if self.active and not self:_close_handles() then self:_finish('UI_TREE_FILE_FLUSH_FAILED',state) end
    return self:status_snapshot()
end
return M
