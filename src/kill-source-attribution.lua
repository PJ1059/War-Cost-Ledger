-- Independent adapter for HD2Runtime's documented player_kill_credited event.
-- Sources describe a local-player stat batch, never the weapon of one victim.
-- Does not alter bills, weapon totals, enemy classification or ribbon counts.
return function(names)
    names = names or {}
    local api = {policy = 'runtime_source_stat_batch_no_victim_pairing', latest = nil,
        diagnostics = {ready = false, batches = 0, kills = 0, reason = 'WAITING_FOR_CREDIT'}}
    local function count(value)
        return type(value) == 'number' and value >= 0 and value <= 2147483647 and value % 1 == 0
    end
    local function type_id(value)
        if type(value) == 'string' and #value == 16 and not value:find('[^%x]') then return value:upper() end
    end
    local function label(kind, raw)
        local entry = kind and names[kind]
        if type(entry) == 'table' then
            return entry.name_zh or entry.name or raw or kind
        end
        return raw or kind or '未知来源'
    end
    function api:reset()
        self.latest = nil
        self.diagnostics = {ready = false, batches = 0, kills = 0, reason = 'WAITING_FOR_CREDIT'}
    end
    function api:observe(event)
        local function reject(reason)
            self.diagnostics.ready, self.diagnostics.reason = false, reason
            return nil, reason
        end
        if type(event) ~= 'table' or event.local_player ~= true then return reject('NOT_LOCAL_CREDIT') end
        if not count(event.kills) or event.kills == 0 then return reject('INVALID_KILL_GROWTH') end
        if event.total ~= nil and (not count(event.total) or event.total < event.kills) then
            return reject('INVALID_KILL_TOTAL')
        end
        if event.sources ~= nil and type(event.sources) ~= 'table' then return reject('INVALID_SOURCE_LIST') end
        if event.unattributed ~= nil and not count(event.unattributed) then return reject('INVALID_UNATTRIBUTED') end
        local sources, by_type, total, known = {}, {}, 0, 0
        for index, source in ipairs(event.sources or {}) do
            if index > 64 or type(source) ~= 'table' or not count(source.kills) then
                return reject('INVALID_SOURCE_COUNTS')
            end
            total = total + source.kills
            if source.kills > 0 then
                local kind = type_id(source.type)
                if kind then
                    local row = by_type[kind]
                    if not row then
                        row = {type = kind, name = label(kind, source.name), kills = 0}
                        sources[#sources + 1], by_type[kind] = row, row
                    end
                    row.kills = row.kills + source.kills
                    known = known + source.kills
                end
            end
        end
        if total + (event.unattributed or 0) > event.kills then return reject('INCONSISTENT_SOURCE_COUNTS') end
        table.sort(sources, function(a, b) return a.kills > b.kills or (a.kills == b.kills and a.type < b.type) end)
        local unknown = event.kills - known
        local status = known == 0 and 'unknown_source'
            or (#sources == 1 and unknown == 0 and 'single_source' or 'mixed_sources')
        local batch = {mission = event.mission, frame = event.frame, time = event.time,
            kills = event.kills, total = event.total, sources = sources,
            known_kills = known, unknown_kills = unknown,
            unattributed = event.unattributed, status = status, per_victim = false,
            label = status == 'single_source' and sources[1].name
                or (status == 'mixed_sources' and '混合来源' or '未知来源')}
        self.latest = batch
        local diag = self.diagnostics
        diag.ready, diag.reason, diag.status = true, nil, status
        diag.batches, diag.kills = diag.batches + 1, diag.kills + event.kills
        return batch
    end
    -- The Runtime id makes this one registration idempotent. The caller owns
    -- mission reset and may inspect latest without copying any BFV mod state.
    function api:subscribe(events, owner, on_batch)
        if type(events) ~= 'table' or type(events.on) ~= 'function' then return nil, 'RUNTIME_EVENTS_UNAVAILABLE' end
        local subscription = events.on('player_kill_credited', function(event)
            local batch = self:observe(event)
            if batch and on_batch then on_batch(batch) end
        end, {id = 'ledger_source_credit', owner = owner, scope = 'session'})
        self.subscription = subscription
        return subscription
    end
    return api
end
