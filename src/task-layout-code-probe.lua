-- A finite read-only capture of two missing task-layout code windows.
-- Input is the fingerprint/pin-proven event_world.open() world; no HUD is read.
local profile = require('hd2runtime/schemas/current')
local json = require('hd2runtime/runtime/mod_store')
local M = {
    limits = {code_per_step = 4096, read_per_step = 4200, output = 32768, attempts = 2},
    source = {revision = 'task_layout_code_v1', store_key = 'task_layout_code_v1', build = 25480438,
        exe_sha = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
        dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
        source_sha = 'fdaf5e1961693bbeb7e910382286d333c5d6e65bce9607ed76232c1ebab9074b',
        reference = 'dist/task-module-update-58132.bin; captured game RVA 17D0000, length 6000'},
    pins = {
        {name = 'component_layout_caller', rva = 0x17D0863, length = 12, call_offset = 7,
            target = 0x17CF8A0, hex = '410F28C8488BCDE831F0FFFF'},
        {name = 'task_list_update_caller', rva = 0x17D08BD, length = 16, call_offset = 11,
            target = 0x184B700, hex = '488D8DF06D0000410F28C8E833AE0700'}},
    ranges = {{name = 'component_layout_helpers', rva = 0x17CF800, length = 0x800},
        {name = 'task_list_update', rva = 0x184B700, length = 0x3000}}}
local Probe = {}; Probe.__index = Probe
local function canonical(n)
    return type(n) == 'number' and n >= 65536 and n < 140737488355328 and n % 4096 == 0
end
local function hex(raw) return (raw:gsub('.', function(c) return string.format('%02X', c:byte()) end)) end
local function i32(raw, at)
    local a,b,c,d = raw:byte(at+1, at+4)
    local n = a+b*256+c*65536+d*16777216
    return n >= 2147483648 and n-4294967296 or n
end
local function exists(path)
    if type(path) ~= 'string' then return false end
    local f = io.open(path, 'rb'); if not f then return false end
    f:close(); return true
end
local function binary_complete(path)
    local f = type(path)=='string' and io.open(path,'rb');if not f then return false end
    local ok,raw=pcall(f.read,f,14337);f:close()
    return ok and type(raw)=='string' and #raw==14336
end
local function load(path)
    local f = path and io.open(path, 'rb'); if not f then return nil end
    local ok,raw = pcall(f.read, f, M.limits.output+1); f:close()
    if not ok or type(raw) ~= 'string' or #raw > M.limits.output then return nil end
    local parsed,value = pcall(json.decode, raw)
    return parsed and type(value) == 'table' and value or nil
end
local function save(path, value, limit)
    local encoded = json.encode(value)
    if #encoded > (limit or M.limits.output) then return nil, 'TASK_CODE_METADATA_LIMIT' end
    local f = path and io.open(path, 'wb'); if not f then return nil, 'TASK_CODE_FILE_OPEN' end
    local ok,result = pcall(f.write, f, encoded)
    local flushed,flush = pcall(f.flush, f)
    local closed,close = pcall(f.close, f)
    if not ok or not result or not flushed or not flush or not closed or not close then
        return nil, 'TASK_CODE_FILE_WRITE'
    end
    return true, #encoded
end
local function compatible(value)
    return type(value) == 'table' and value.source_revision == M.source.revision
        and value.exe_sha == M.source.exe_sha and value.dll_sha == M.source.dll_sha
        and value.source_sha == M.source.source_sha and value.build == M.source.build
end
local function world_valid(world)
    if profile.exe_sha ~= M.source.exe_sha or profile.dll_sha ~= M.source.dll_sha then
        return nil, 'TASK_CODE_BUILD_MISMATCH'
    end
    if type(world) ~= 'table' or not canonical(world.game) or not canonical(world.exe)
        or type(world.runtime) ~= 'table' or world.runtime.mode ~= 'live'
        or type(world.runtime.query) ~= 'function' or type(world.view) ~= 'table'
        or type(world.view.read) ~= 'function' then return nil, 'TASK_CODE_WORLD_UNAVAILABLE' end
    return true
end
local function readable(world, at, n)
    local ok,r = pcall(world.runtime.query, at)
    -- Code stays inside one committed, executable image region. No target scan.
    if not ok or not r or type(r.base) ~= 'number' or type(r.size) ~= 'number'
        or r.base > at or r.base+r.size < at+n or r.state ~= 0x1000 or r.type ~= 0x1000000
        or type(r.protect) ~= 'number' or r.protect % 512 >= 256 then return nil end
    local p = r.protect % 256
    return p == 0x20 or p == 0x40 or p == 0x80
end

function M.new(options)
    options = options or {}
    local localapp = os.getenv('LOCALAPPDATA')
    local directory = options.directory or (localapp and localapp..'/HD2Runtime/mod_data')
    local self = setmetatable({enabled = options.enabled ~= false, directory = directory,
        store = options.store, log = options.log or function() end, status = 'waiting_world',
        done = false, attempts = 0, sequence = 0, read_last = 0, read_peak = 0}, Probe)
    self.prefix = directory and directory..'/ledger_task_layout_code_v1_'..M.source.exe_sha:sub(1,12)
    self.state_path = self.prefix and self.prefix..'.state.json'
    local old = load(self.state_path)
    if self.store and type(self.store.get) == 'function' then
        local ok,value = pcall(self.store.get, self.store, M.source.store_key, {})
        if ok and compatible(value) then old = value end
    end
    if compatible(old) then
        self.attempts = math.min(2, math.max(0, math.floor(tonumber(old.attempts) or 0)))
        self.sequence = math.max(0, math.floor(tonumber(old.sequence) or 0))
        local saved = old.saved
        if compatible(saved) and saved.complete == true and binary_complete(saved.binary_path) then
            local metadata = load(saved.json_path)
            if compatible(metadata) and metadata.complete == true and metadata.bytes_written == 14336 then
                self.done, self.saved, self.last_path = true, saved, saved.json_path
            end
        end
    end
    if not self.enabled then self.status = 'disabled'
    elseif self.done then self.status = 'complete'
    elseif self.attempts >= 2 then self.status = 'exhausted' end
    return self
end
function Probe:_persist()
    local value = {format = 'HD2-TASK-LAYOUT-CODE-STATE-1', source_revision = M.source.revision,
        build = M.source.build, exe_sha = M.source.exe_sha, dll_sha = M.source.dll_sha,
        source_sha = M.source.source_sha, attempts = self.attempts, sequence = self.sequence, saved = self.saved}
    local store_ok=true
    if self.store and type(self.store.set) == 'function' then
        local ok,result=pcall(self.store.set,self.store,M.source.store_key,value)
        store_ok=ok and result~=false
    end
    local written,why=save(self.state_path,value)
    if not written then return nil,why end
    if not store_ok then return nil,'TASK_CODE_STORE_WRITE' end
    return true
end
function Probe:_read(world, at, n)
    if self.read_last+n > M.limits.read_per_step then return nil, 'TASK_CODE_READ_BUDGET' end
    if not readable(world, at, n) then return nil, 'TASK_CODE_REGION_UNREADABLE' end
    self.read_last = self.read_last+n; self.read_peak = math.max(self.read_peak,self.read_last)
    local ok,raw = pcall(world.view.read, at, n)
    if not ok or type(raw) ~= 'string' or #raw ~= n then
        if self.active then self.active.meta.failure = {address = at, requested = n,
            returned_length = type(raw) == 'string' and #raw or 0, error = not ok and tostring(raw) or nil} end
        return nil, 'TASK_CODE_SHORT_READ'
    end
    return raw
end
function Probe:_pins(world, final)
    local records = {}
    for _,pin in ipairs(M.pins) do
        local raw,why = self:_read(world,world.game+pin.rva,pin.length)
        local record = {name = pin.name, rva = pin.rva, address = world.game+pin.rva,
            requested = pin.length, actual_hex = raw and hex(raw), expected_hex = pin.hex, target = pin.target,
            valid = false, error = why}
        records[#records+1] = record
        if raw then
            record.actual_target = pin.rva+pin.call_offset+5+i32(raw,pin.call_offset+1)
            record.valid = hex(raw) == pin.hex and raw:byte(pin.call_offset+1) == 0xE8
                and record.actual_target == pin.target
        end
        self.active.meta[final and 'end_pins' or 'start_pins'] = records
        if not record.valid then return nil, why or 'TASK_CODE_CALLER_PIN_MISMATCH' end
    end
    return true
end
function Probe:_finish(reason, failure)
    local a = self.active; if not a then return self:status_snapshot() end
    local meta = a.meta
    meta.finished_at, meta.error = os.time(), reason
    meta.complete = not reason and meta.bytes_written == meta.bytes_planned and #meta.chunks == 4
    meta.identity_consistent = a.identity_checked == true
    meta.read_peak = self.read_peak
    local written,why = save(meta.json_path, meta, M.limits.output-meta.bytes_planned)
    if not written then meta.complete,meta.error,failure = false,why,true end
    self.active,self.last_path,self.reason = nil,meta.json_path,meta.error
    if meta.complete then
        self.saved = {complete = true, source_revision = M.source.revision, build = M.source.build,
            exe_sha = M.source.exe_sha, dll_sha = M.source.dll_sha, source_sha = M.source.source_sha,
            binary_path = meta.binary_path, json_path = meta.json_path}
        self.done,self.status = true,'complete'
    else
        if failure then self.attempts = math.min(2,self.attempts+1) end
        self.status = failure and (self.attempts >= 2 and 'exhausted' or 'incomplete') or 'cancelled'
    end
    local persisted,persist_error=self:_persist()
    if not persisted then
        self.reason=persist_error;self.persistence_saved=false
        self.log('任务布局代码持久标记保存失败：'..tostring(persist_error))
    else self.persistence_saved=true end
    self.log('任务布局代码采集 '..self.status..'：'..meta.json_path)
    return self:status_snapshot()
end
function Probe:_start(world)
    local stem
    for _ = 1,100 do
        self.sequence = self.sequence+1
        local candidate = self.prefix..'_'..os.date('!%Y%m%dT%H%M%SZ')..'_'..self.sequence
        if not exists(candidate..'.bin') and not exists(candidate..'.json') then stem=candidate; break end
    end
    if not stem then self.reason='TASK_CODE_NAME_UNAVAILABLE';self.status='incomplete';return end
    local ranges,offset = {},0
    for _,r in ipairs(M.ranges) do
        ranges[#ranges+1] = {name=r.name,rva=r.rva,address=world.game+r.rva,length=r.length,binary_offset=offset}
        offset=offset+r.length
    end
    local meta = {format='HD2-TASK-LAYOUT-CODE-1',source_revision=M.source.revision,
        build=M.source.build,exe_sha=M.source.exe_sha,dll_sha=M.source.dll_sha,
        source_sha=M.source.source_sha,source_reference=M.source.reference,
        game_base=world.game,exe_base=world.exe,world_key=world.key,started_at=os.time(),
        atomic=false,complete=false,error='TASK_CODE_CAPTURE_IN_PROGRESS',native_called=false,native_written=false,
        read_budget=M.limits.read_per_step,code_per_step=M.limits.code_per_step,output_limit=M.limits.output,
        binary_path=stem..'.bin',json_path=stem..'.json',bytes_written=0,bytes_planned=offset,
        ranges=ranges,chunks={}}
    self.active = {meta=meta,world=world,game=world.game,exe=world.exe,key=world.key,
        runtime=world.runtime,view=world.view,phase='pins',range=1,offset=0}
    local file = io.open(meta.binary_path,'wb')
    if not file then return self:_finish('TASK_CODE_BINARY_OPEN',true) end
    local closed,value = pcall(file.close,file)
    if not closed or not value then return self:_finish('TASK_CODE_BINARY_CLOSE',true) end
    local ok,why=save(meta.json_path,meta,M.limits.output-meta.bytes_planned)
    if not ok then return self:_finish(why,true) end
    local persisted,err=self:_persist()
    if not persisted then return self:_finish(err,true) end
    self.reason,self.status=nil,'capturing'
end
function Probe:cancel(reason)
    -- Cancellation uses no native reads and does not spend a failure allowance.
    self.read_last=0
    if self.active then return self:_finish(reason or 'TASK_CODE_CANCELLED',false) end
    return self:status_snapshot()
end
function Probe:set_enabled(enabled)
    self.enabled = enabled == true
    if not self.enabled then self:cancel('TASK_CODE_DISABLED');self.status='disabled'
    elseif self.done then self.status='complete'
    elseif self.attempts>=2 then self.status='exhausted'
    elseif not self.active then self.status='waiting_world' end
    return self:status_snapshot()
end
function Probe:status_snapshot()
    return {enabled=self.enabled,status=self.status,active=self.active~=nil,done=self.done,
        attempts=self.attempts,read_last=self.read_last,read_peak=self.read_peak,
        source_revision=M.source.revision,last_path=self.last_path,reason=self.reason,
        persistence_saved=self.persistence_saved,
        bytes_written=self.active and self.active.meta.bytes_written or nil}
end
function Probe:step(world)
    self.read_last=0
    if not self.enabled then self.status='disabled';return self:status_snapshot() end
    if self.done then self.status='complete';return self:status_snapshot() end
    if self.attempts>=2 then self.status='exhausted';return self:status_snapshot() end
    local valid,why=world_valid(world)
    if not valid then
        if self.active then self:cancel(why) end
        self.status,self.reason='waiting_world',why;return self:status_snapshot()
    end
    if not self.directory then self.status,self.reason='unavailable','TASK_CODE_DIRECTORY_UNAVAILABLE';return self:status_snapshot() end
    local a=self.active
    if not a then self:_start(world);return self:status_snapshot() end
    if world.game~=a.game or world.exe~=a.exe or world.key~=a.key or world.runtime~=a.runtime or world.view~=a.view then
        return self:_finish('TASK_CODE_WORLD_CHANGED',false)
    end
    if a.phase=='pins' then
        local ok,err=self:_pins(world,false)
        if not ok then return self:_finish(err,true) end
        a.phase='code';return self:status_snapshot()
    end
    if a.phase=='verify' then
        local ok,err=self:_pins(world,true)
        if not ok then return self:_finish(err,true) end
        a.identity_checked=true;return self:_finish(nil,false)
    end
    local range=a.meta.ranges[a.range]
    local n=math.min(M.limits.code_per_step,range.length-a.offset)
    local at=range.address+a.offset
    local raw,err=self:_read(world,at,n)
    local chunk={range=range.name,rva=range.rva+a.offset,address=at,requested=n,
        binary_offset=a.meta.bytes_written,length=raw and #raw or 0,success=false,error=err}
    a.meta.chunks[#a.meta.chunks+1]=chunk
    if not raw then return self:_finish(err,true) end
    local f=io.open(a.meta.binary_path,'ab')
    if not f then return self:_finish('TASK_CODE_BINARY_OPEN',true) end
    local ok,written=pcall(f.write,f,raw)
    local flushed,flush=pcall(f.flush,f);local closed,close=pcall(f.close,f)
    if not ok or not written or not flushed or not flush or not closed or not close then
        return self:_finish('TASK_CODE_BINARY_WRITE',true)
    end
    chunk.success=true;a.meta.bytes_written=a.meta.bytes_written+#raw
    a.offset=a.offset+n
    if a.offset==range.length then a.range=a.range+1;a.offset=0 end
    if not a.meta.ranges[a.range] then a.phase='verify' end
    return self:status_snapshot()
end
return M
