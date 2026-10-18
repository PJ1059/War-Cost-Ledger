-- Read-only local held consumable stock. Caller schedules at 10 Hz and owns life/mission resets.
-- Fields follow Runtime 0.30.3 event_world.equipped and pelican_weapon.ammo_state.
-- Only read-only domains are loaded; no Pelican developer/write modules are required.
local b = require('hd2runtime/core/bytes')
local N = require('hd2runtime/domains/event_natives')
local D = require('hd2runtime/domains/pelican')
local WI, MG, MC, AM, MT = N.wielder, D.turretWeapon.magazine,
    D.gatling.magazineCopy, D.ammo, D.gatling.magazineTypes
local WEAPON = D.turretWeapon.weapon
local EQUIPMENT=require('hd2runtime/domains/player_equipment')
local INVENTORY,DEPOSIT=EQUIPMENT.inventory,EQUIPMENT.deposit
local CREMATOR='78A8185F63A70795'
local CREMATOR_PACK='43EB1C3C1A1860E0'
local PACK_PINS={
    {rva=5455706,hex='488b1d8726df02488bf9448b430c443b4328720c488bcbe8dadb3400448b430c443b03720c488bcbe8c9dd3400448b430c418bc033d2488d0cc500000000488b434848891401488b433848893c01488d4b208b5708e8dcb71f01ff430c'},
    {rva=5456206,hex='e8bde5fcff4c8b7424488b480485c979028b088bc3488d14c500000000488b4750890c02488b47508b0c02'},
}
local HEAT={global=0x3326D48,map=40,count=20,descriptors=64,states=88,stride=12,reserve=0,pins={
    {rva=7616912,hex='0fbae2090f837e0000004c8b15a733be02418b5230458b4238440fafc38d6aff85d274334d8b4a28458b5a340f1f40008bc5428d0c064823c8418b04c9413bc3740c3bc3740cffc63bf272e4eb093bc37505418b7cc904498b4a408bc7488b0cc1e8faa7dcfff30f104060e828559c014c8b742440f30f2cf08bc6488b5c24504883c4205f5e5dc3'},
    {rva=7619111,hex='468b0cc1410fbae1090f83870000004c8b1d0b2bbe02458b4b30418b7b380faffa458d71ff4585c97452498b7328418b6b340f1f8000000000418bce448d043b4c23c1428b0cc64e8d14c63bcd74253bca7425ffc3413bd972df8bc8498b43584c8d0449428b1c80e83c1f030003c3e958ffffff3bca7504418b42048bc8498b43584c8d0449428b1c80e81a1f030003c3e936ffffff'},
    {rva=7757689,hex='e8c2c0ffff8bcb41b9010000004c8d0449488b4f5842890481488b4f58428b14818916488b5424608b024803c0c744c5008b9164ec44894cc504488974c5084883c604ff02488b475842c744800400000000488b4758428b4c8004890e'},
}}
local TORCHER, U32 = '4FB0F8C02F55C82B', 4294967296
local GAME_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
-- The two-component paired backpack path alone allows 64 operations; other
-- held-stock paths keep 48. All share the same bytes and pre-read time limits.
local LIMIT_OPS, LIMIT_BYTES, LIMIT_SECONDS = 48, 4096, 0.001

local function integer(n, maximum)
    return type(n) == 'number' and n >= 0 and n <= maximum and n % 1 == 0
end
local function address(n)
    return integer(n, 140737488355327) and n >= 65536
end

-- factory(world_api [, {clock, max_operations, max_bytes, seconds}, supported_resources]); test options
-- can lower hard limits only. Missing/failed readings return nil, never empty fuel.
return function(world_api, options, supported_resources)
    world_api = world_api or require('hd2runtime/runtime/event_world')
    options = options or {}
    supported_resources = supported_resources or {[TORCHER] = true}
    assert(type(supported_resources) == 'table', 'invalid supported resources')
    local max_ops = options.max_operations or LIMIT_OPS
    local max_bytes = options.max_bytes or LIMIT_BYTES
    local seconds = options.seconds or LIMIT_SECONDS
    assert(integer(max_ops, LIMIT_OPS) and max_ops > 0, 'invalid operation limit')
    assert(integer(max_bytes, LIMIT_BYTES) and max_bytes > 0, 'invalid byte limit')
    assert(type(seconds) == 'number' and seconds > 0 and seconds <= LIMIT_SECONDS, 'invalid time limit')
    local clock = options.clock or os.clock
    local diagnostics = {ready = false, reason = 'NOT_READ', bytes = 0, operations = 0,
        read_peak = 0, operations_peak = 0, elapsed_ms = 0,
        max_operations = max_ops, max_bytes = max_bytes, soft_budget_ms = seconds * 1000}
    local api = {diagnostics = diagnostics, resource = TORCHER}
    local original, proxy, slots, started, operations, bytes, heat_proven, pack_proven, read_limit

    local function charge(size)
        if not integer(size, LIMIT_BYTES) or size == 0 then error('INVALID_READ_SIZE', 0) end
        if operations + 1 > (read_limit or max_ops) then error('OPERATION_BUDGET', 0) end
        if bytes + size > max_bytes then error('BYTE_BUDGET', 0) end
        -- A soft bound checked BEFORE each native read; an individual slow read
        -- cannot be preempted and is not an FPS guarantee.
        if clock() - started >= seconds then error('TIME_BUDGET', 0) end
        operations, bytes = operations + 1, bytes + size
    end
    local function read(at, size)
        if not address(at) or not address(at + size - 1) then error('INVALID_READ_ADDRESS', 0) end
        charge(size)
        local raw = original.read(at, size)
        if type(raw) ~= 'string' or #raw ~= size then error('READ_FAILED', 0) end
        return raw
    end
    local function pointer(at)
        local raw = read(at, 8)
        local lo, hi = b.u32(raw, 0), b.u32(raw, 4)
        local value = lo + hi * U32
        if hi > 32767 or not address(value) then return nil end
        return value
    end
    local function fill(block, at, size)
        if not address(at) or not address(at + size - 1) then error('INVALID_READ_ADDRESS', 0) end
        charge(size)
        if not original.fill(block, at, size) then error('READ_FAILED', 0) end
        return block
    end
    local view = {read = read, pointer = pointer, u32 = function(at) return b.u32(read(at, 4), 0) end,
        fill = fill}
    -- No inherited read, prove, runtime or write-capable adapter is exposed.
    -- slots carry reusable bytes/buffers; no address survives a read() call.
    local function prepare(world)
        if original ~= world.view then
            original, slots = world.view, {}
            for _, name in ipairs({'header', 'bucket', 'record', 'entry', 'capacity', 'type_key'}) do
                slots[name] = original.slot()
            end
        end
        proxy = proxy or {view = view}
        proxy.game, proxy.exe = world.game, world.exe
    end
    local function block(name, at, size)
        return fill(slots[name], at, size)
    end
    -- The component's proven key/index hash; budget interrupts collisions before
    -- the upstream maximum of 4096 probes can be reached.
    local function index_of(manager, map, entity)
        local header = block('header', manager + map, 20)
        local keys, cap = header:ptr(0), header:u32(8)
        local empty, multiplier = header:u32(12), header:u32(16)
        if not keys or cap == 0 or cap > 1048576 then error('AMMO_HASH_INVALID', 0) end
        local start = world_api.mul32(entity, multiplier)
        for probe = 0, math.min(cap, 4096) - 1 do
            local entry = block('bucket', keys + ((start + probe) % cap) * 8, 8)
            local key = entry:u32(0)
            if key == entity then
                local index = entry:u32(4)
                if index ~= U32 - 1 then return index end
                return nil
            end
            if key == empty then return nil end
        end
    end
    local function held(avatar)
        local manager = pointer(proxy.game + WI.wielder)
        if not manager then error('HELD_UNREADABLE', 0) end
        local index = world_api.hash_value(proxy, manager + WI.wielderHash, avatar)
        if not index or index >= 65536 then error('HELD_UNREADABLE', 0) end
        local list = pointer(manager + WI.slots)
        if not list then error('HELD_UNREADABLE', 0) end
        local entity = view.u32(list + index * WI.stride)
        if entity == 0 or entity == avatar then error('NO_HELD_WEAPON', 0) end
        if world_api.entity_exists(proxy, entity) ~= true then error('HELD_GENERATION', 0) end
        local resource = world_api.entity_type(proxy, entity)
        local policy = resource and supported_resources[resource]
        local mode
        if resource == TORCHER and policy then mode = 'fuel'
        elseif type(policy)=='table' and policy.inventory_mode=='fuel' then
            mode=policy.inventory_storage=='paired_deposit' and resource==CREMATOR and 'backpack_fuel' or 'fuel'
        elseif type(policy) == 'table' and policy.inventory_mode == 'magazine' then mode = 'magazine'
        elseif type(policy) == 'table' and policy.inventory_mode == 'heatsink' then mode = 'heatsink' end
        if not mode then error('UNSUPPORTED_WEAPON', 0) end
        return entity, resource, mode
    end
    local function type_capacity(resource)
        local cworld = pointer(proxy.game + D.spawn.world)
        local tab = cworld and pointer(cworld + MT.offset)
        if not tab then error('MAGAZINE_TYPE_UNREADABLE', 0) end
        local lo, hi = tonumber(resource:sub(9), 16), tonumber(resource:sub(1, 8), 16)
        local start = ((hi % MT.slots) * (U32 % MT.slots) + lo % MT.slots) % MT.slots
        for probe = 0, MT.slots - 1 do
            local key = block('type_key', tab + ((start + probe) % MT.slots) * 16, 16)
            if key:u32(0) == lo and key:u32(4) == hi then
                return block('capacity', tab + MT.records + key:u32(8) * MT.stride + AM.capacity, 4):u32(0)
            end
            if key:u32(0) == 0 and key:u32(4) == 0 then break end
        end
        error('MAGAZINE_TYPE_UNREADABLE', 0)
    end
    local function magazine_flags(entity)
        local manager = pointer(proxy.game + WEAPON.global)
        if not manager then error('WEAPON_UNREADABLE', 0) end
        local index = index_of(manager, WEAPON.map, entity)
        local records = index and pointer(manager + WEAPON.records)
        if not records then error('WEAPON_UNREADABLE', 0) end
        local flags = view.u32(records + index * WEAPON.stride + WEAPON.flags)
        if math.floor(flags / WEAPON.magazine) % 2 ~= 1
            or math.floor(flags / WEAPON.rounds) % 2 ~= 0
            or math.floor(flags / WEAPON.heat) % 2 ~= 0 then error('UNSUPPORTED_RESERVE_MODE', 0) end
        return flags
    end
    local function ammo(entity, resource)
        local manager = pointer(proxy.game + MG.global)
        if not manager then error('MAGAZINE_UNREADABLE', 0) end
        local ri = index_of(manager, MG.map, entity)
        if not ri then error('MAGAZINE_UNREADABLE', 0) end
        local records, entries = pointer(manager + MG.records), pointer(manager + AM.entries)
        if not records or not entries then error('MAGAZINE_UNREADABLE', 0) end
        local ci = index_of(manager, MC.map, entity)
        local cap, from
        if ci then
            local copies = pointer(manager + MC.records)
            if not copies then error('MAGAZINE_COPY_UNREADABLE', 0) end
            cap, from = block('capacity', copies + ci * MC.stride + AM.capacity, 4):u32(0), 'copy'
        else
            cap, from = type_capacity(resource), 'type'
        end
        local record = block('record', records + ri * MG.stride, MG.stride)
        local entry = block('entry', entries + ri * AM.entryStride, AM.entryStride)
        local rounds, working = entry:i32(AM.entryRounds), record:i32(MG.rounds)
        if cap == 0 or rounds < 0 or rounds > cap or working < 0 or working > cap then error('AMMO_INCONSISTENT', 0) end
        return {rounds = rounds, working = working, spares = entry:u32(AM.entrySpares),
            chambered = record:u32(MG.chambered), chamber_empty = entry:u8(AM.entryChamberEmpty),
            capacity = cap, from = from}
    end
    local function heatsinks(entity,resource)
        local key=tostring(proxy.game)..':'..tostring(proxy.exe)
        if heat_proven~=key then
            for _,pin in ipairs(HEAT.pins)do
                if read(proxy.game+pin.rva,#pin.hex/2)~=b.unhex(pin.hex)then error('HEAT_CODE_PIN_CHANGED',0)end
            end
            heat_proven=key
        end
        local manager=pointer(proxy.game+HEAT.global)
        if not manager then error('HEAT_UNREADABLE',0)end
        local index=index_of(manager,HEAT.map,entity)
        -- Component rows can be sparse across owned/network partitions.
        if not index or index>=4096 then error('HEAT_UNREADABLE',0)end
        local descriptors,states=pointer(manager+HEAT.descriptors),pointer(manager+HEAT.states)
        if not descriptors or not states then error('HEAT_UNREADABLE',0)end
        local descriptor=pointer(descriptors+index*8)
        if not descriptor then error('HEAT_UNREADABLE',0)end
        local who=read(descriptor,24)
        if b.u32(who,8)~=entity or b.u32(who,20)%2~=1
            or string.format('%08X%08X',b.u32(who,4),b.u32(who,0))~=resource then error('HEAT_OWNERSHIP',0)end
        local at=states+index*HEAT.stride
        -- The heat gauge changes during firing/cooling; reserve is a separate
        -- integer and only native replacement consumes it. Never price gauge loss.
        local reserve_raw=read(at+HEAT.reserve,4);local reserve=b.u32(reserve_raw,0)
        if reserve>10000 then error('HEAT_INVALID_RESERVE',0)end
        if read(at+HEAT.reserve,4)~=reserve_raw or read(descriptor,24)~=who
            or pointer(descriptors+index*8)~=descriptor or pointer(manager+HEAT.states)~=states
            or pointer(manager+HEAT.descriptors)~=descriptors
            or pointer(proxy.game+HEAT.global)~=manager then error('HEAT_CHANGED',0)end
        return {spares=reserve,from='heat'}
    end
    local function backpack_fuel(avatar)
        local key=tostring(proxy.game)..':'..tostring(proxy.exe)
        if pack_proven~=key then
            for _,pin in ipairs(PACK_PINS)do
                if read(proxy.game+pin.rva,#pin.hex/2)~=b.unhex(pin.hex)then error('PACK_CODE_PIN_CHANGED',0)end
            end
            pack_proven=key
        end
        local inventory=pointer(proxy.game+INVENTORY.global)
        if not inventory then error('PACK_INVENTORY_UNREADABLE',0)end
        local ii=index_of(inventory,INVENTORY.hash,avatar)
        if not ii or ii>=4096 then error('PACK_INVENTORY_UNREADABLE',0)end
        local ids,rows=pointer(inventory+INVENTORY.descriptors),pointer(inventory+INVENTORY.records)
        local id=ids and pointer(ids+ii*8)
        if not id or not rows then error('PACK_INVENTORY_UNREADABLE',0)end
        local who=read(id,24)
        if b.u32(who,8)~=avatar or b.u32(who,20)%2~=1 then error('PACK_INVENTORY_OWNERSHIP',0)end
        local pack_at=rows+ii*INVENTORY.stride+INVENTORY.slots.backpack
        local pack_raw=read(pack_at,4);local pack=b.u32(pack_raw,0)
        if pack==0 or pack==avatar then error('PACK_NOT_EQUIPPED',0)end
        local manager=pointer(proxy.game+DEPOSIT.global)
        local di=manager and index_of(manager,DEPOSIT.hash,pack)
        if not di or di>=4096 then error('PACK_DEPOSIT_UNREADABLE',0)end
        local descs,states=pointer(manager+DEPOSIT.descriptors),pointer(manager+DEPOSIT.live)
        local desc=descs and pointer(descs+di*8)
        if not desc or not states then error('PACK_DEPOSIT_UNREADABLE',0)end
        local identity=read(desc,24)
        if b.u32(identity,8)~=pack or string.format('%08X%08X',b.u32(identity,4),b.u32(identity,0))~=CREMATOR_PACK then
            error('PACK_DEPOSIT_TYPE',0)
        end
        local at=states+di*DEPOSIT.liveStride+DEPOSIT.amount
        local raw=read(at,4);local remaining=b.u32(raw,0)
        if remaining>10000 then error('PACK_INVALID_REMAINING',0)end
        if read(at,4)~=raw or read(pack_at,4)~=pack_raw or read(id,24)~=who
            or read(desc,24)~=identity or pointer(descs+di*8)~=desc
            or pointer(manager+DEPOSIT.live)~=states or pointer(manager+DEPOSIT.descriptors)~=descs
            or pointer(proxy.game+DEPOSIT.global)~=manager
            or pointer(inventory+INVENTORY.records)~=rows or pointer(inventory+INVENTORY.descriptors)~=ids
            or pointer(proxy.game+INVENTORY.global)~=inventory then error('PACK_CHANGED',0)end
        return {remaining=remaining,pack_entity=pack,from='backpack'}
    end
    function api:read(world, player)
        diagnostics.ready = false
        diagnostics.bytes, diagnostics.operations, diagnostics.elapsed_ms = 0, 0, 0
        if type(player) ~= 'table' or player['local'] ~= true
            or not integer(player.avatar, U32 - 1) or player.avatar == 0 then
            diagnostics.reason = 'NOT_LOCAL_AVATAR'; return nil, diagnostics.reason
        end
        if type(world) ~= 'table' or not address(world.game) or not address(world.exe)
            or type(world.view) ~= 'table' or type(world.view.slot) ~= 'function'
            or type(world.view.fill) ~= 'function' or type(world.view.read) ~= 'function' then
            diagnostics.reason = 'WORLD_UNAVAILABLE'; return nil, diagnostics.reason
        end
        if N.source.gameDllSha256 ~= GAME_SHA or D.source.gameDllSha256 ~= GAME_SHA
            or EQUIPMENT.source.gameDllSha256~=GAME_SHA then
            diagnostics.reason = 'BUILD_PROFILE_MISMATCH'; return nil, diagnostics.reason
        end
        operations, bytes, started = 0, 0, clock();read_limit=max_ops;diagnostics.max_operations=max_ops
        local ok, result = pcall(function()
            prepare(world)
            local entity, resource, mode = held(player.avatar)
            if mode=='backpack_fuel' then read_limit=options.max_operations or 64 end
            diagnostics.max_operations=read_limit
            local flags = mode == 'magazine' and magazine_flags(entity) or nil
            local state = mode == 'heatsink' and heatsinks(entity,resource)
                or mode == 'backpack_fuel' and backpack_fuel(player.avatar) or ammo(entity, resource)
            local after, after_type, after_mode = held(player.avatar)
            if after ~= entity or after_type ~= resource or after_mode ~= mode then error('HELD_CHANGED', 0) end
            return {entity = entity, resource = resource, reserve_mode = mode, weapon_flags = flags, state = state}
        end)
        diagnostics.bytes, diagnostics.operations = bytes, operations
        diagnostics.elapsed_ms = math.max(0, (clock() - started) * 1000)
        diagnostics.read_peak = math.max(diagnostics.read_peak, bytes)
        diagnostics.operations_peak = math.max(diagnostics.operations_peak, operations)
        if not ok then diagnostics.reason = tostring(result); return nil, diagnostics.reason end
        diagnostics.ready = true
        diagnostics.reason = (result.reserve_mode=='heatsink' or result.reserve_mode=='backpack_fuel') and 'READY'
            or result.state.working == result.state.rounds and 'READY' or 'WORKING_UNSETTLED'
        -- Return identity even while the game's working copy is settling; the
        -- pure observer decides whether to retain its baseline or charge.
        return result, diagnostics.reason
    end
    return api
end
