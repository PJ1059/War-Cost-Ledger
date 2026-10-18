-- Actual Runtime readers + owned memory fixture; never opens the game process.
local runtime_root = assert(arg[2], 'Runtime source root required')
table.insert(package.loaders, 1, function(name)
    if name:sub(1, 11) ~= 'hd2runtime/' then return '\nnot a Runtime module' end
    local path = runtime_root .. '/' .. name:sub(12) .. '.lua'
    local fn, why = loadfile(path)
    return fn or ('\n' .. tostring(why))
end)
local b = require('hd2runtime/core/bytes')
local N = require('hd2runtime/domains/event_natives')
local D = require('hd2runtime/domains/pelican')
local world_api = require('hd2runtime/runtime/event_world')
local native_view = require('hd2runtime/runtime/native_view')
local factory = assert(loadfile(arg[1]))()
local WI, E = N.wielder, N.engine
local MG, MC, AM, MT = D.turretWeapon.magazine, D.gatling.magazineCopy, D.ammo, D.gatling.magazineTypes
local TORCHER = '4FB0F8C02F55C82B'
local U32 = 4294967296
local function u32(n) return b.encode(n, 'u32') end
local function ptr(n) return u32(n % U32) .. u32(math.floor(n / U32)) end
local function type_bytes(hex) return b.unhex(hex):reverse() end
local function patch(raw, at, bytes)
    return raw:sub(1, at) .. bytes .. raw:sub(at + #bytes + 1)
end
local function text(path)
    local file = assert(io.open(runtime_root .. '/' .. path, 'rb'))
    local result = file:read('*a'); file:close()
    return result:gsub('\r\n', '\n')
end
local function extract(source, start)
    local at = assert(source:find(start, 1, true), start)
    local finish = assert(source:find('\nend\n', at, true))
    return source:sub(at, finish + 4)
end
-- Compile just the actual read-only functions; avoid all development native
-- write modules and pelican_weapon's global jit.off side effect.
local env = setmetatable({b = b, world_module = world_api, SP = D.spawn}, {__index = _G})
local index_fn = assert(loadstring(extract(text('runtime/pelicans.lua'), 'local function index_of(')
    .. '\nreturn index_of'))
setfenv(index_fn, env)
env.pelicans = {index_of = index_fn()}
local type_fn = assert(loadstring(extract(text('runtime/pelican_gatling.lua'), 'local function type_record(')
    .. '\nreturn type_record'))
setfenv(type_fn, env)
env.gatling = {type_record = type_fn()}
env.M, env.TW, env.MC, env.AM, env.G = {}, D.turretWeapon, MC, AM, D.gatling
env.map_at = function(at) return {keys = at, capacity = at + 8, empty = at + 12, multiplier = at + 16} end
env.CHIN = D.gatling.chinTurretResource
local real_ammo = assert(loadstring(extract(text('runtime/pelican_weapon.lua'), 'local function magazine_state(')
    .. '\n' .. extract(text('runtime/pelican_weapon.lua'), 'function M.ammo_state(')
    .. '\nreturn M.ammo_state'))
setfenv(real_ammo, env)
real_ammo = real_ammo()

local function memory(copy, resource)
    resource = resource or TORCHER
    local m = {regions = {}, reads = {}, view_reads = 0, writes = 0, fault = nil,
        game = 0x140000000, exe = 0x180000000, avatar = 17,
        entity = 0x400002, other = 0x400003, keys_next = 0x310000000}
    local held_manager, held_slots = 0x210000000, 0x211000000
    local entities, generation_manager, generations = 0x220000000, 0x221000000, 0x222000000
    local magazine, records, entries, copies = 0x240000000, 0x241000000, 0x242000000, 0x243000000
    local component_world, type_table = entities, 0x270000000 -- same actual global as WI.entities.
    local weapon, weapon_records = 0x280000000, 0x281000000
    m.weapon, m.weapon_records, m.resource = weapon, weapon_records, resource
    m.held_slots, m.generation_bytes, m.entity_manager = held_slots, generations, entities
    m.magazine, m.records, m.entries, m.copies, m.type_table = magazine, records, entries, copies, type_table
    function m:put(at, raw) self.regions[at] = raw end
    function m:hash(manager, at, entity, index, cap, collisions)
        cap = cap or 8
        local keys = self.keys_next; self.keys_next = keys + 0x100000
        local raw = (u32(U32 - 1) .. u32(U32 - 1)):rep(cap)
        local first = entity % cap
        for probe = 0, (collisions or 0) - 1 do
            raw = patch(raw, ((first + probe) % cap) * 8, u32(20000 + probe) .. u32(0))
        end
        if index ~= nil then raw = patch(raw, ((first + (collisions or 0)) % cap) * 8, u32(entity) .. u32(index)) end
        self:put(manager + at, ptr(keys) .. u32(cap) .. u32(U32 - 1) .. u32(1))
        self:put(keys, raw)
        return keys
    end
    m:put(m.game + WI.wielder, ptr(held_manager))
    m:put(m.game + WI.inventory, ptr(0)) -- optional selection absent; slot0 still proven.
    m:hash(held_manager, WI.wielderHash, m.avatar, 0)
    m:put(held_manager + WI.slots, ptr(held_slots))
    m:put(held_slots, u32(m.entity))
    m:put(m.exe + E.entities, ptr(generation_manager))
    m:put(generation_manager + E.generationSize, u32(4))
    m:put(generation_manager + E.generations, ptr(generations))
    m:put(generations, string.char(0, 0, 1, 1))
    m:put(m.game + WI.entities, ptr(entities))
    m:hash(entities, WI.entityMap, m.entity, 0)
    m:put(entities + WI.descriptors, type_bytes(resource) .. u32(m.entity) .. u32(29) .. u32(40) .. u32(1))
    m:put(m.game + D.turretWeapon.weapon.global, ptr(weapon))
    m:hash(weapon, D.turretWeapon.weapon.map, m.entity, 0)
    m:put(weapon + D.turretWeapon.weapon.records, ptr(weapon_records))
    m:put(weapon_records, u32(128) .. string.rep('\0', 36))
    m:put(m.game + MG.global, ptr(magazine))
    m:put(magazine + MC.count, u32(copy and 3 or 0))
    m:put(magazine + MC.capacity, u32(16))
    m:hash(magazine, MG.map, m.entity, 1)
    m:hash(magazine, MC.map, m.entity, copy and 2 or nil)
    m:put(magazine + MG.records, ptr(records))
    m:put(magazine + AM.entries, ptr(entries))
    m:put(magazine + MC.records, ptr(copies))
    m:put(records + MG.stride, u32(60) .. u32(0) .. u32(1) .. u32(0))
    m:put(entries + AM.entryStride, u32(3) .. u32(60) .. string.char(0, 0, 0, 0))
    local definition = patch(string.rep('\0', MC.stride), AM.capacity, u32(copy and 3000 or 100))
    m:put(copies + 2 * MC.stride, definition)
    m:put(m.game + D.spawn.world, ptr(component_world))
    m:put(component_world + MT.offset, ptr(type_table))
    local lo, hi = tonumber(resource:sub(9), 16), tonumber(resource:sub(1, 8), 16)
    m.type_slot = ((hi % MT.slots) * (U32 % MT.slots) + lo % MT.slots) % MT.slots
    m:put(type_table, string.rep('\0', MT.records))
    m.regions[type_table] = patch(m.regions[type_table], m.type_slot * 16, type_bytes(resource) .. u32(0) .. u32(0))
    m:put(type_table + MT.records, patch(string.rep('\0', MT.stride), AM.capacity, u32(100)))
    local adapter = {}
    function adapter.read(at, size)
        m.reads[#m.reads + 1] = {at, size}
        if m.fault then
            local changed = m.fault(at, size, #m.reads)
            if changed ~= nil then return changed ~= false and changed or nil end
        end
        for base, raw in pairs(m.regions) do
            if at >= base and at + size <= base + #raw then return raw:sub(at - base + 1, at - base + size) end
        end
        return nil
    end
    function adapter.write() m.writes = m.writes + 1; error('a write was attempted') end
    m.view = native_view.new(adapter)
    m.world = {game = m.game, exe = m.exe, view = m.view}
    m.player = {['local'] = true, avatar = m.avatar, entity = 10, peer = 'FEDCBA9876543210'}
    function m:reader(options, resources)
        options = options or {}; options.clock = options.clock or function() return 0 end
        return factory(world_api, options, resources)
    end
    return m
end
-- The built-addon test reuses exactly this memory layout, without executing the
-- assertions below. Its caller temporarily sets this flag and supplies arg[1:2].
if rawget(_G, 'HD2_CONSUMABLE_FIXTURE_ONLY') then
    return {memory = memory, world_api = world_api, real_ammo = real_ammo,
        reader_factory = factory, TORCHER = TORCHER, N = N, D = D,
        u32 = u32, ptr = ptr, patch = patch}
end
local passed = 0
local function test(name, fn)
    fn(); passed = passed + 1
end
local function total(m)
    local amount = 0; for _, r in ipairs(m.reads) do amount = amount + r[2] end; return amount
end
local state_fields = {'rounds', 'working', 'spares', 'capacity', 'from', 'chambered', 'chamber_empty'}
test('actual Runtime equipped/ammo_state equivalence: type and private mod capacity', function()
    for _, copy in ipairs({false, true}) do
        local m = memory(copy)
        local expected_held = world_api.equipped(m.world, m.avatar)
        local expected = real_ammo(m.world, m.entity, TORCHER)
        m.reads = {}
        local reader = m:reader()
        local actual, why = reader:read(m.world, m.player)
        assert(actual, tostring(why) .. ' last=' .. string.format('%X/%d', m.reads[#m.reads][1], m.reads[#m.reads][2]))
        assert(actual.entity == expected_held.entity and actual.resource == expected_held.type)
        for _, key in ipairs(state_fields) do assert(actual.state[key] == expected[key], key) end
        assert(actual.state.capacity == (copy and 3000 or 100)) -- accepts other MOD's live capacity.
        assert(reader.diagnostics.operations == #m.reads)
        assert(reader.diagnostics.bytes == total(m))
        assert(reader.diagnostics.operations <= 48 and total(m) <= 4096 and m.writes == 0)
        print('normal ' .. (copy and 'copy' or 'type') .. ': ' .. #m.reads .. ' operations, ' .. total(m) .. ' bytes')
    end
end)
test('generic magazine allowlist: same actual ammo reader, type/private capacity and chamber fields', function()
    for _, resource in ipairs({'1122334455667788', '8877665544332211'}) do
        for _, copy in ipairs({false, true}) do
            local m = memory(copy, resource)
            local expected = real_ammo(m.world, m.entity, resource)
            m.reads = {}
            local reader = m:reader(nil, {[resource] = {inventory_mode = 'magazine'}})
            local got, why = reader:read(m.world, m.player)
            assert(got, why)
            assert(got.resource == resource and got.reserve_mode == 'magazine' and got.weapon_flags == 128)
            for _, key in ipairs(state_fields) do assert(got.state[key] == expected[key], key) end
            assert(got.state.chambered == 1 and got.state.chamber_empty == 0)
            assert(#m.reads == (copy and 42 or 44) and reader.diagnostics.bytes == total(m) and m.writes == 0)
        end
    end
end)
test('unproven / round / heat policies reject before ammo', function()
    local resource = '1122334455667788'
    for _, policy in ipairs({true, {}, {inventory_mode = 'rounds'}, {inventory_mode = 'heat'}}) do
        local m = memory(false, resource)
        local got, why = m:reader(nil, {[resource] = policy}):read(m.world, m.player)
        assert(not got and why == 'UNSUPPORTED_WEAPON')
    end
    for _, flags in ipairs({0, 256, 512, 384, 640, 896}) do
        local m = memory(false, resource)
        m.regions[m.weapon_records] = patch(m.regions[m.weapon_records], 0, u32(flags))
        local got, why = m:reader(nil, {[resource] = {inventory_mode = 'magazine'}}):read(m.world, m.player)
        assert(not got and why == 'UNSUPPORTED_RESERVE_MODE')
    end
end)
test('missing / nonlocal rejects before first read', function()
    for _, player in ipairs({{}, {['local'] = false, avatar = 17}, {['local'] = true, avatar = 0}}) do
        local m = memory(); local reader = m:reader()
        assert(reader:read(m.world, player) == nil and #m.reads == 0)
    end
    local m = memory(); assert(m:reader():read(m.world, nil) == nil and #m.reads == 0)
end)
test('unsupported held type', function()
    local m = memory()
    m.regions[m.entity_manager + WI.descriptors] = patch(m.regions[m.entity_manager + WI.descriptors], 0, type_bytes('1122334455667788'))
    local value, why = m:reader():read(m.world, m.player)
    assert(not value and why == 'UNSUPPORTED_WEAPON')
end)
test('generation invalid before snapshot', function()
    local m = memory(); m:put(m.generation_bytes, string.char(0, 0, 0, 1))
    local value, why = m:reader():read(m.world, m.player)
    assert(not value and why == 'HELD_GENERATION')
end)
test('same type switch during snapshot rejects different entity', function()
    local m = memory(); local n = 0
    m:hash(m.entity_manager, WI.entityMap, m.other, 0)
    -- first lookup needs both weapon ids in the same proven hash.
    local header = m.regions[m.entity_manager + WI.entityMap]
    local key_at = b.pointer(header, 0)
    m.regions[key_at] = patch(m.regions[key_at], (m.entity % 8) * 8, u32(m.entity) .. u32(0))
    m.fault = function(at, size)
        if at == m.held_slots then
            n = n + 1
            if n == 2 then
                m.regions[m.entity_manager + WI.descriptors] = patch(m.regions[m.entity_manager + WI.descriptors], 8, u32(m.other))
                return u32(m.other)
            end
        end
    end
    local value, why = m:reader():read(m.world, m.player)
    assert(not value and why == 'HELD_CHANGED')
end)
test('same entity generation or resource changes after ammo', function()
    for _, kind in ipairs({'generation', 'type'}) do
        local m = memory(); local n = 0
        m.fault = function(at, size)
            if at == m.held_slots then
                n = n + 1
                if n == 2 then
                    if kind == 'generation' then m:put(m.generation_bytes, string.char(0, 0, 2, 1))
                    else m.regions[m.entity_manager + WI.descriptors] = patch(m.regions[m.entity_manager + WI.descriptors], 0, type_bytes('1122334455667788')) end
                end
            end
        end
        local value = m:reader():read(m.world, m.player)
        assert(value == nil)
    end
end)
test('moving working fuel retains identity for observer; invalid fuel never becomes zero', function()
    local m = memory(); m.regions[m.records + MG.stride] = patch(m.regions[m.records + MG.stride], 0, u32(59))
    local got, why = m:reader():read(m.world, m.player)
    assert(got and got.entity == m.entity and got.state.working == 59 and got.state.rounds == 60 and why == 'WORKING_UNSETTLED')
    m = memory(); m.regions[m.records + MG.stride] = patch(m.regions[m.records + MG.stride], 0, u32(U32 - 1))
    got, why = m:reader():read(m.world, m.player)
    assert(not got and why == 'AMMO_INCONSISTENT')
    local m = memory(); m.regions[m.type_table + MT.records] = patch(m.regions[m.type_table + MT.records], AM.capacity, u32(0))
    assert(m:reader():read(m.world, m.player) == nil)
end)
test('first read failure and short read are missing, no invented stock', function()
    for _, fail in ipairs({false, 'x'}) do
        local m = memory(); m.fault = function() return fail end
        local got, why = m:reader():read(m.world, m.player)
        assert(not got and why == 'READ_FAILED' and #m.reads == 1)
    end
end)
test('collision lookup stops at operation budget', function()
    local m = memory()
    m:hash(m.magazine, MG.map, m.entity, 1, 128, 100)
    local reader = m:reader()
    local value, why = reader:read(m.world, m.player)
    assert(not value and why == 'OPERATION_BUDGET')
    assert(#m.reads == 48 and reader.diagnostics.operations == 48 and m.writes == 0)
end)
test('type hash collision also has global operation bound', function()
    local m = memory()
    m.regions[m.type_table] = (type_bytes('1122334455667788') .. u32(0) .. u32(0)):rep(MT.slots)
    local got, why = m:reader():read(m.world, m.player)
    assert(not got and why == 'OPERATION_BUDGET' and #m.reads == 48)
end)
test('actual Runtime held hash lookup has the same global bound', function()
    local m = memory()
    local manager = b.pointer(m.regions[m.game + WI.wielder], 0)
    m:hash(manager, WI.wielderHash, m.avatar, 0, 128, 100)
    local value, why = m:reader():read(m.world, m.player)
    assert(not value and why == 'OPERATION_BUDGET' and #m.reads == 48)
end)
test('byte budget rejects a read before adapter call', function()
    local m = memory(); local reader = m:reader({max_bytes = 8})
    local got, why = reader:read(m.world, m.player)
    assert(not got and why == 'BYTE_BUDGET' and #m.reads == 1 and total(m) == 8)
end)
test('soft time budget checked before first read', function()
    local m = memory(); local step = 0
    local reader = m:reader({clock = function() step = step + 1; return step * 0.002 end})
    local got, why = reader:read(m.world, m.player)
    assert(not got and why == 'TIME_BUDGET' and #m.reads == 0)
end)
test('soft time budget checked during lookup before next read', function()
    local m = memory(); local step = 0
    local reader = m:reader({clock = function() step = step + 1; return step * 0.0001 end})
    local value, why = reader:read(m.world, m.player)
    assert(not value and why == 'TIME_BUDGET' and #m.reads > 0 and #m.reads < 48)
end)
test('read failure resets ready and subsequent valid sample reuses blocks', function()
    local m = memory(); local reader = m:reader()
    assert(reader:read(m.world, m.player))
    m.fault = function() return false end
    assert(reader:read(m.world, m.player) == nil and not reader.diagnostics.ready)
    m.fault = nil; assert(reader:read(m.world, m.player) and reader.diagnostics.ready)
    local old_ops, old_bytes = reader.diagnostics.operations_peak, reader.diagnostics.read_peak
    for _ = 1, 100 do assert(reader:read(m.world, m.player)) end
    assert(reader.diagnostics.operations_peak == old_ops and reader.diagnostics.read_peak == old_bytes)
    assert(m.writes == 0)
end)
print('consumable reader: ' .. passed .. ' tests passed; actual Runtime read-only functions, no game I/O')
