-- Current personal Career's two observed integer rows, read-only and Ship-only.
-- Type4/high32=0/low<2^31 is the real-page verified subset; no generic enum guess.
local b = require('hd2runtime/core/bytes')
local profile = require('hd2runtime/schemas/current')
local bit = require('bit')
local M = {source = {
    exe_sha = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    fixture_sha = '6dc84d63eddee2136e1572fbaa7b6c5ccf8900bd213e21acbf71b25551e2b9fc',
    state = 0x3326340, state_offset = 705052,
    dispatch = 0x3326E68, count = 5740, rows = 5744,
    local_user = 0x347CEF0, local_peer = 0xB398,
    panel = 0x4DC08, list = 0x9B8, track_alpha = 195256 + 84,
    tag = 0xA40, value = 0x1390,
}, pins = {
    {rva = 0x143C950, hex = '40534883ec20488bd94881c110010000'},
    {rva = 0x143A1BA, hex = '440fb69958010000'},
    {rva = 0x143A1E3, hex = '4c8d0440423954c108'},
    {rva = 0x143A212, hex = 'c744242401000000'},
}}
local Reader = {}; Reader.__index = Reader
local LIMIT_READS, LIMIT_BYTES, LIMIT_SECONDS = 64, 8192, .002
local FIELDS = {'game', 'state_context', 'dispatch', 'controller', 'list', 'gui_context',
    'local_user', 'local_peer'}
local function integer(v, max)
    return type(v) == 'number' and v >= 0 and v <= max and v % 1 == 0
end
local function address(v)
    return integer(v, 140737488355327) and v >= 65536
end
local function pointer(v) return address(v) and v % 8 == 0 end
local function kind(raw) return bit.band(bit.rshift(b.u32(raw, 0), 18), 15) end
local function links(raw) return raw:sub(225, 256) end
local function same_identity(a, c)
    if not a or not c then return false end
    for _, field in ipairs(FIELDS) do if a[field] ~= c[field] then return false end end
    return true
end
local function peer_hex(raw) return b.hex(raw:reverse()):upper() end

function M.new(options)
    options = options or {}
    local reads, bytes, seconds = options.max_reads or LIMIT_READS,
        options.max_bytes or LIMIT_BYTES, options.seconds or LIMIT_SECONDS
    assert(integer(reads, LIMIT_READS) and reads > 0, 'invalid read limit')
    assert(integer(bytes, LIMIT_BYTES) and bytes > 0, 'invalid byte limit')
    assert(type(seconds) == 'number' and seconds > 0 and seconds <= LIMIT_SECONDS, 'invalid time limit')
    return setmetatable({clock = options.clock or os.clock, max_reads = reads,
        max_bytes = bytes, seconds = seconds, visible_only = options.visible_only == true,
        diagnostics = {ready = false, reason = 'NOT_READ',
            bytes = 0, reads = 0, bytes_peak = 0, reads_peak = 0, ui_cache_loaded = false,
            server_ready = false, backend_ready = false}}, Reader)
end

function Reader:reset()
    self.loaded_identity, self.proven_game, self.proven_view = nil, nil, nil
    self.diagnostics.ui_cache_loaded = false
end

function Reader:read(world, local_peer)
    local d = self.diagnostics
    d.ready, d.bytes, d.reads, d.elapsed_ms = false, 0, 0, 0
    local function reject(reason) d.reason = reason; return nil, reason end
    if profile.exe_sha ~= M.source.exe_sha or profile.dll_sha ~= M.source.dll_sha then
        self:reset(); return reject('CAREER_BUILD_MISMATCH')
    end
    if type(world) ~= 'table' or not pointer(world.game) or world.game % 4096 ~= 0
        or type(world.view) ~= 'table' or type(world.view.read) ~= 'function'
        or type(world.runtime) ~= 'table' or world.runtime.mode ~= 'live' then
        self:reset(); return reject('CAREER_WORLD_UNAVAILABLE')
    end
    if type(local_peer) ~= 'string' or #local_peer ~= 16 or local_peer:find('[^%x]')
        or local_peer == '0000000000000000' then
        self:reset(); return reject('CAREER_LOCAL_PEER_UNAVAILABLE')
    end
    local_peer = local_peer:upper()
    if self.proven_game ~= world.game or self.proven_view ~= world.view then self:reset() end
    local started = self.clock()
    local function get(at, size)
        if not address(at) or not integer(size, 4096) or size == 0 or not address(at + size - 1) then
            error('CAREER_READ_ADDRESS', 0)
        end
        if d.reads >= self.max_reads or d.bytes + size > self.max_bytes then error('CAREER_READ_BUDGET', 0) end
        if self.clock() - started >= self.seconds then error('CAREER_TIME_BUDGET', 0) end
        d.reads, d.bytes = d.reads + 1, d.bytes + size
        local raw = world.view.read(at, size)
        if type(raw) ~= 'string' or #raw ~= size then error('CAREER_READ_FAILED', 0) end
        return raw
    end
    local function ptr(at)
        local raw = get(at, 8)
        local low, high = b.u32(raw, 0), b.u32(raw, 4)
        if high > 32767 then error('CAREER_POINTER', 0) end
        local value = low + high * 4294967296
        if value ~= 0 and not pointer(value) then error('CAREER_POINTER', 0) end
        return value
    end
    local function locate()
        local state_context = ptr(world.game + M.source.state)
        if state_context == 0 then error('CAREER_WAITING_FOR_SHIP', 0) end
        if b.u32(get(state_context + M.source.state_offset, 4), 0) ~= 3 then
            error('CAREER_WAITING_FOR_SHIP', 0)
        end
        local dispatch = ptr(world.game + M.source.dispatch)
        if dispatch == 0 then error('CAREER_CONTROLLER_UNAVAILABLE', 0) end
        local count = b.u32(get(dispatch + M.source.count, 4), 0)
        if count < 1 or count > 64 then error('CAREER_REGISTRY_BOUNDS', 0) end
        local entries = get(dispatch + M.source.rows, count * 16)
        local selected
        for index = 0, count - 1 do
            if b.u32(entries, index * 16 + 8) == 224 then
                local controller = b.pointer(entries, index * 16)
                if not pointer(controller) then error('CAREER_CONTROLLER_POINTER', 0) end
                local panel = controller + M.source.panel
                local alpha = b.value(get(panel + M.source.track_alpha, 4), 0, 'f32')
                if alpha < 0 or alpha > 1.001 then error('CAREER_ALPHA', 0) end
                local list = panel + M.source.list
                local header = get(list, 256)
                local context = b.pointer(header, 0xF8)
                if kind(header) ~= 1 or not pointer(context) then error('CAREER_LIST_IDENTITY', 0) end
                if selected then error('CAREER_AMBIGUOUS_CONTROLLER', 0) end
                selected = {game = world.game, state_context = state_context, dispatch = dispatch,
                    controller = controller, list = list, gui_context = context,
                    header = header, alpha = alpha, page_visible = alpha > .95}
            end
        end
        if not selected then error('CAREER_CONTROLLER_UNAVAILABLE', 0) end
        return selected
    end
    local function local_user()
        local at = ptr(world.game + M.source.local_user)
        if at == 0 then error('CAREER_LOCAL_USER_UNAVAILABLE', 0) end
        local raw = get(at + M.source.local_peer, 8)
        if peer_hex(raw) ~= local_peer then error('CAREER_LOCAL_PEER_CHANGED', 0) end
        return at
    end
    local function widget(at, parent, context, expected_kind)
        local raw = get(at, 256)
        if kind(raw) ~= expected_kind or b.pointer(raw, 0xF0) ~= parent
            or b.pointer(raw, 0xF8) ~= context then error('CAREER_WIDGET_IDENTITY', 0) end
        return raw
    end
    local function descriptor(at, key, is_value)
        local raw = get(at + 272, 345)
        if b.u32(raw, 0) ~= key or raw:byte(345) ~= (is_value and 1 or 0) then
            error('CAREER_LABEL_BINDING', 0)
        end
        if not is_value then return key end
        -- A deliberate supported subset from the actual user-visible page:
        -- count key, exact type4, zero upper32 and nonnegative signed32 range.
        local value = b.u32(raw, 16)
        if b.u32(raw, 8) ~= 0xAB2A7B35 or b.u32(raw, 12) ~= 4
            or b.u32(raw, 20) ~= 0 or value >= 2147483648 then error('CAREER_VALUE_FORMAT', 0) end
        return value
    end
    local function rows(owner)
        local first = b.pointer(owner.header, 0xE0)
        if not pointer(first) then error('CAREER_FIRST_ROW', 0) end
        local path, seen = {first}, {[first] = true}
        for index = 2, 9 do
            local next_row = ptr(path[index - 1] + 0xE8)
            if next_row == 0 or seen[next_row] then error('CAREER_ROW_CHAIN', 0) end
            path[index], seen[next_row] = next_row, true
        end
        local result = {path = path, headers = {}}
        for _, record in ipairs({{index = 1, key = 0xF68F08B2, name = 'kills'},
                                 {index = 9, key = 0x32C9CF0D, name = 'deaths'}}) do
            local row = path[record.index]
            result.headers[#result.headers + 1] = widget(row, owner.list, owner.gui_context, 1)
            local tag, value = row + M.source.tag, row + M.source.value
            result.headers[#result.headers + 1] = widget(tag, row, owner.gui_context, 7)
            result.headers[#result.headers + 1] = widget(value, row, owner.gui_context, 7)
            descriptor(tag, record.key, false)
            result[record.name] = descriptor(value, 0x2BAA24A7, true)
        end
        return result
    end
    local ok, snapshot = pcall(function()
        local before = locate()
        before.local_user, before.local_peer = local_user(), local_peer
        if self.visible_only and not before.page_visible then error('CAREER_PAGE_NOT_VISIBLE', 0) end
        if self.loaded_identity and not same_identity(self.loaded_identity, before) then
            self.loaded_identity, d.ui_cache_loaded = nil, false
        end
        if not before.page_visible and not self.loaded_identity then error('CAREER_UI_CACHE_NOT_ESTABLISHED', 0) end
        if self.proven_game ~= world.game or self.proven_view ~= world.view then
            for _, pin in ipairs(M.pins) do
                if get(world.game + pin.rva, #pin.hex / 2) ~= b.unhex(pin.hex) then error('CAREER_CODE_MISMATCH', 0) end
            end
            self.proven_game, self.proven_view = world.game, world.view
        end
        local old_rows = rows(before)
        local after = locate()
        after.local_user, after.local_peer = local_user(), local_peer
        if not same_identity(before, after) or links(before.header) ~= links(after.header)
            or before.page_visible ~= after.page_visible then error('CAREER_PAGE_CHANGED', 0) end
        local new_rows = rows(after)
        for index, at in ipairs(old_rows.path) do
            if at ~= new_rows.path[index] then error('CAREER_ROW_CHAIN_CHANGED', 0) end
        end
        for index, raw in ipairs(old_rows.headers) do
            if kind(raw) ~= kind(new_rows.headers[index]) or links(raw) ~= links(new_rows.headers[index]) then
                error('CAREER_ROW_REBUILT', 0)
            end
        end
        if old_rows.kills ~= new_rows.kills or old_rows.deaths ~= new_rows.deaths then error('CAREER_VALUE_CHANGED', 0) end
        if after.page_visible then self.loaded_identity = after; d.ui_cache_loaded = true end
        return {kills = new_rows.kills, deaths = new_rows.deaths, local_peer = local_peer,
            status = after.page_visible and 'page_visible' or 'ui_cache_observed',
            page_visible = after.page_visible, ui_cache_loaded = self.loaded_identity ~= nil,
            ui_cache_refresh_verified = false, server_ready = false, backend_ready = false,
            source = 'personal_career_native_rows_type4_positive32', identity = after,
            observed_type = 4, generic_numeric_enum_verified = false, atomic = false}
    end)
    d.elapsed_ms = (self.clock() - started) * 1000
    d.bytes_peak, d.reads_peak = math.max(d.bytes_peak, d.bytes), math.max(d.reads_peak, d.reads)
    if not ok then
        if snapshot == 'CAREER_LOCAL_PEER_CHANGED' or snapshot == 'CAREER_LOCAL_USER_UNAVAILABLE' then
            self.loaded_identity, d.ui_cache_loaded = nil, false
        end
        return reject(type(snapshot) == 'string' and snapshot or 'CAREER_READ_FAILED')
    end
    d.ready, d.reason = true, snapshot.status
    return snapshot, snapshot.status
end

return M
