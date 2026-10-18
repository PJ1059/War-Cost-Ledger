-- One-shot, explicitly enabled score-table research. No polling of files in normal gameplay.
local function create(mod, store, load_reader)
    local M = {}
    function M:poll() end
    if store:get('probe_enabled', false) ~= true then return M end
    local folder = os.getenv('LOCALAPPDATA')
    if not folder then mod:log('统计探针：LOCALAPPDATA 不可用。'); return M end
    folder = folder .. '\\HD2Runtime\\mod_data\\'
    local request_path = folder .. 'ledger_probe_request.json'
    local json = require('hd2runtime/runtime/mod_store')
    local function u32(value)
        return string.char(value % 256, math.floor(value / 256) % 256,
            math.floor(value / 65536) % 256, math.floor(value / 16777216) % 256)
    end
    local elapsed, reader, block = 0, nil, nil
    mod:log('小型统计探针已启用：只有 capture 命令会采集，不执行完整内存快照。')
    function M:poll(world, players, game, dt)
        elapsed = elapsed + dt
        if elapsed + 1e-9 < 1 then return end
        elapsed = math.max(0, elapsed - math.floor(elapsed + 1e-9))
        local file = io.open(request_path, 'rb')
        if not file then return end
        local text = file:read(1025); file:close()
        if not text or #text > 1024 then os.remove(request_path); return end
        local ok, request = pcall(json.decode, text)
        if not ok or type(request) ~= 'table' or type(request.id) ~= 'string'
            or not request.id:match('^%x+$') or #request.id ~= 32
            or type(request.label) ~= 'string' or #request.label > 160
            or (request.format ~= nil and request.format ~= 'json' and request.format ~= 'binary') then
            os.remove(request_path); return
        end
        local stem = folder .. 'ledger_probe_' .. request.id
        for _, extension in ipairs({'.json', '.bin'}) do
            local existing = io.open(stem .. extension, 'rb')
            if existing then existing:close(); os.remove(request_path); return end
        end
        local binary = request.format == 'binary'
        local player
        for _, item in ipairs(players) do if item['local'] == true then player = item; break end end
        local result = {version = '0.3.3', id = request.id, label = request.label,
            time = os.time(), mission = game.mission == true, build = 25480438}
        local captured, reason
        if player and player.entity then
            reader = reader or load_reader()
            if binary then captured, reason = reader.raw(world, player.entity)
            else
                block = block or world.view.slot()
                captured, reason = reader.snapshot(world, player.entity, block)
            end
            result.player_entity = player.entity
        else reason = 'local player unavailable' end
        result.error = reason
        if captured and binary then
            result.capacity, result.empty, result.score_index = captured.capacity, captured.empty, captured.score_index
            result.game_state, result.game_mode, result.host = game.state, game.mode, game.host
            result.player_lifecycle = player.lifecycle
            -- One-shot context only: no continuous avatar/position sampling.
            local api_ok, api = pcall(require, 'hd2runtime/runtime/event_world')
            if api_ok and type(api.players) == 'function' and type(api.unit_position) == 'function' then
                local players_ok, with_avatars = pcall(api.players, world, true)
                if players_ok and type(with_avatars) == 'table' then
                    for _, item in ipairs(with_avatars) do
                        if item['local'] == true and item.entity == player.entity then
                            result.avatar = item.avatar
                            if item.lifecycle ~= nil then result.player_lifecycle = item.lifecycle end
                            if item.avatar then
                                local position_ok, position = pcall(api.unit_position, world, item.avatar)
                                if position_ok then result.position = position end
                            end
                            break
                        end
                    end
                end
            end
        else result.stats = captured end
        local code = {'', ''}
        if captured and request.include_code == true then
            if binary then result.code_ranges = {} else result.code = {} end
            -- Existing research's score summary and telemetry functions; no game writes or hooks.
            for index, range in ipairs({{0x630130, 0x7C0}, {0xBF9810, 0x50E}}) do
                local bytes = world.view.read(world.game + range[1], range[2])
                if type(bytes) ~= 'string' or #bytes ~= range[2] then bytes = nil end
                if binary then
                    code[index] = bytes or ''
                    result.code_ranges[index] = {rva = range[1], size = range[2],
                        error = not bytes and 'unreadable' or nil}
                else
                    result.code[#result.code + 1] = {rva = range[1], size = range[2],
                        hex = bytes and bytes:gsub('.', function(c) return string.format('%02X', c:byte()) end)
                            or nil, error = not bytes and 'unreadable' or nil}
                end
            end
        end
        local encoded = json.encode(result)
        local parts, size, target = {encoded}, #encoded, stem .. '.json'
        if captured and binary then
            target = stem .. '.bin'
            parts = {encoded, captured.main_bytes, captured.sources_bytes, code[1], code[2]}
            local header = 'HD2STAT1'
            size = 28
            for _, part in ipairs(parts) do header = header .. u32(#part); size = size + #part end
            table.insert(parts, 1, header)
        end
        if size > 1048576 then mod:log('统计探针：结果超过 1 MiB，未保存。'); os.remove(request_path); return end
        local pending = target .. '.tmp'
        local output = io.open(pending, 'wb')
        if not output then mod:log('统计探针：结果文件无法打开。'); os.remove(request_path); return end
        local written, failure = true, nil
        for _, part in ipairs(parts) do
            written, failure = output:write(part)
            if not written then break end
        end
        local closed, close_failure = output:close()
        failure = failure or close_failure
        local renamed = written and closed and os.rename(pending, target)
        if renamed then
            os.remove(request_path)
            mod:log('统计探针已保存 ' .. request.label .. '：' .. target
                .. (captured and '' or '；读取失败：' .. tostring(reason)))
        else mod:log('统计探针保存失败：' .. tostring(failure)); os.remove(request_path) end
    end
    return M
end
return create
