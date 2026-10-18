-- Personal Career COUNT source, proven on cold Ship without an Armory page.
-- One bounded read call, no Engine/native invocation, write, UI or polling loop.
local b = require('hd2runtime/core/bytes')
local profile = require('hd2runtime/schemas/current')
local M = {source = {
    exe_sha = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    code_sha = '1cbd121e5e0f558b053804fd600465764ddbbe93b020a0f97622020e19a7f27a',
    cold_fixture_sha = 'e4ca945417f3d0dd6931a7acdc194923b46bebec96f6d72d1d744990c8918426',
    state = 0x3326340, state_offset = 705052,
    local_user = 0x347CEF0, local_peer = 0xB398,
    counters = 0x347CF28, kills = 4, deaths = 36,
    names = 0x21E95D0,
}, pins = {
    {rva = 0x18E6E10, hex = '4c8b3d1161b901'},
    {rva = 0x18E6E17, hex = '4c8d35b2279000'},
    {rva = 0x18E6F7A, hex = '458bc4'},
    {rva = 0x18E6F89, hex = 'e8425bb5ff'},
}, names = {
    {slot = 0, text = 'hud_PlayerStatType_totalEnemyKills'},
    {slot = 8, text = 'hud_PlayerStatType_totalDeaths'},
}}
local Reader = {}; Reader.__index = Reader
local LIMIT_READS, LIMIT_BYTES, LIMIT_SECONDS = 32, 512, .002
local FIELDS = {'game', 'state_context', 'local_user', 'local_peer', 'counter_pointer'}
local function finite(v)
    return type(v) == 'number' and v == v and v > -math.huge and v < math.huge
end
local function integer(v, max) return finite(v) and v >= 0 and v <= max and v % 1 == 0 end
local function address(v) return integer(v, 140737488355327) and v >= 65536 end
local function pointer(v) return address(v) and v % 8 == 0 end
local function same(a, c)
    for _, key in ipairs(FIELDS) do if a[key] ~= c[key] then return false end end
    return true
end

function M.new(options)
    options = options or {}
    local reads, bytes, seconds = options.max_reads or LIMIT_READS,
        options.max_bytes or LIMIT_BYTES, options.seconds or LIMIT_SECONDS
    assert(integer(reads, LIMIT_READS) and reads > 0, 'invalid read limit')
    assert(integer(bytes, LIMIT_BYTES) and bytes > 0, 'invalid byte limit')
    assert(finite(seconds) and seconds > 0 and seconds <= LIMIT_SECONDS, 'invalid time limit')
    assert(options.clock == nil or type(options.clock) == 'function', 'invalid clock')
    return setmetatable({clock = options.clock or os.clock, max_reads = reads,
        max_bytes = bytes, seconds = seconds, diagnostics = {
            ready = false, reason = 'NOT_READ', reads = 0, bytes = 0, reads_peak = 0,
            bytes_peak = 0, elapsed_ms = 0, source_cached = false,
            server_ready = false, backend_ready = false}}, Reader)
end

function Reader:reset()
    self.proven_game, self.proven_view, self.proven_read = nil, nil, nil
    self.diagnostics.source_cached = false
end

function Reader:read(world, local_peer)
    local d = self.diagnostics
    d.ready, d.reads, d.bytes, d.elapsed_ms = false, 0, 0, 0
    local function reject(reason)
        self:reset(); d.reason = reason
        return nil, reason
    end
    if profile.exe_sha ~= M.source.exe_sha or profile.dll_sha ~= M.source.dll_sha then
        return reject('CAREER_COUNTER_BUILD_MISMATCH')
    end
    if type(world) ~= 'table' or not pointer(world.game) or world.game % 4096 ~= 0
        or type(world.view) ~= 'table' or type(world.view.read) ~= 'function'
        or type(world.runtime) ~= 'table' or world.runtime.mode ~= 'live' then
        return reject('CAREER_COUNTER_WORLD_UNAVAILABLE')
    end
    if type(local_peer) ~= 'string' or #local_peer ~= 16 or local_peer:find('[^%x]')
        or local_peer == '0000000000000000' then
        return reject('CAREER_COUNTER_LOCAL_PEER_UNAVAILABLE')
    end
    local_peer = local_peer:upper()
    if self.proven_game ~= world.game or self.proven_view ~= world.view
        or self.proven_read ~= world.view.read then self:reset() end
    local clock_ok, started = pcall(self.clock)
    if not clock_ok or not finite(started) then return reject('CAREER_COUNTER_CLOCK') end
    local function elapsed()
        local now = self.clock()
        if not finite(now) or now < started then error('CAREER_COUNTER_CLOCK', 0) end
        return now - started
    end
    local function check_time()
        if elapsed() >= self.seconds then error('CAREER_COUNTER_TIME_BUDGET', 0) end
    end
    local function get(at, size)
        if not address(at) or not integer(size, 64) or size == 0 or not address(at + size - 1) then
            error('CAREER_COUNTER_READ_ADDRESS', 0)
        end
        if d.reads >= self.max_reads or d.bytes + size > self.max_bytes then
            error('CAREER_COUNTER_READ_BUDGET', 0)
        end
        check_time()
        d.reads, d.bytes = d.reads + 1, d.bytes + size
        local raw = world.view.read(at, size)
        if type(raw) ~= 'string' or #raw ~= size then error('CAREER_COUNTER_READ_FAILED', 0) end
        check_time()
        return raw
    end
    local function ptr(at, unaligned)
        local raw = get(at, 8)
        local low, high = b.u32(raw, 0), b.u32(raw, 4)
        if high > 32767 then error('CAREER_COUNTER_POINTER', 0) end
        local value = low + high * 4294967296
        if value ~= 0 and not (unaligned and address(value) or pointer(value)) then
            error('CAREER_COUNTER_POINTER', 0)
        end
        return value
    end
    local function identity()
        local context = ptr(world.game + M.source.state)
        if context == 0 or b.u32(get(context + M.source.state_offset, 4), 0) ~= 3 then
            error('CAREER_COUNTER_WAITING_FOR_SHIP', 0)
        end
        local user = ptr(world.game + M.source.local_user)
        if user == 0 then error('CAREER_COUNTER_LOCAL_USER_UNAVAILABLE', 0) end
        if b.hex(get(user + M.source.local_peer, 8):reverse()):upper() ~= local_peer then
            error('CAREER_COUNTER_LOCAL_PEER_CHANGED', 0)
        end
        local counters = ptr(world.game + M.source.counters)
        if counters == 0 then error('CAREER_COUNTER_UNAVAILABLE', 0) end
        return {game = world.game, state_context = context, local_user = user,
            local_peer = local_peer, counter_pointer = counters}
    end
    local function values(at)
        local kills, deaths = b.u32(get(at + M.source.kills, 4), 0),
            b.u32(get(at + M.source.deaths, 4), 0)
        if kills >= 2147483648 or deaths >= 2147483648 then
            error('CAREER_COUNTER_VALUE_RANGE', 0)
        end
        return kills, deaths
    end
    local ok, snapshot = pcall(function()
        local before = identity()
        if self.proven_game == nil then
            for _, pin in ipairs(M.pins) do
                if get(world.game + pin.rva, #pin.hex / 2) ~= b.unhex(pin.hex) then
                    error('CAREER_COUNTER_CODE_MISMATCH', 0)
                end
            end
            for _, name in ipairs(M.names) do
                local at = ptr(world.game + M.source.names + name.slot * 8, true)
                if at == 0 then error('CAREER_COUNTER_NAME_POINTER', 0) end
                local raw = get(at, 64)
                local nul = raw:find('\0', 1, true)
                if not nul or raw:sub(1, nul - 1) ~= name.text then
                    error('CAREER_COUNTER_NAME_MISMATCH', 0)
                end
            end
        end
        local kills, deaths = values(before.counter_pointer)
        local after = identity()
        local new_kills, new_deaths = values(after.counter_pointer)
        if not same(before, after) then error('CAREER_COUNTER_IDENTITY_CHANGED', 0) end
        if kills ~= new_kills or deaths ~= new_deaths then error('CAREER_COUNTER_VALUES_CHANGED', 0) end
        check_time()
        return {kills = new_kills, deaths = new_deaths, local_peer = local_peer,
            status = 'native_career_counters', source = 'personal_career_native_counters',
            identity = after, atomic = false, server_ready = false, backend_ready = false,
            backend_refresh_verified = false, page_required = false}
    end)
    local final_ok, seconds = pcall(elapsed)
    if not final_ok then ok, snapshot = false, 'CAREER_COUNTER_CLOCK'
    elseif seconds >= self.seconds then ok, snapshot = false, 'CAREER_COUNTER_TIME_BUDGET' end
    d.elapsed_ms = final_ok and seconds * 1000 or 0
    d.reads_peak, d.bytes_peak = math.max(d.reads_peak, d.reads), math.max(d.bytes_peak, d.bytes)
    if not ok then return reject(type(snapshot) == 'string' and snapshot or 'CAREER_COUNTER_READ_FAILED') end
    self.proven_game, self.proven_view, self.proven_read = world.game, world.view, world.view.read
    d.ready, d.source_cached, d.reason = true, true, snapshot.status
    return snapshot, snapshot.status
end

return M
