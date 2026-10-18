-- Read the existing, local-player stat snapshot. No extra native reads.
-- projectiles_hit counts projectiles, not victims, pellets fired or damage ticks.
-- Source allowlist comes from the SDK's actual Projectile weapon branches.
return function(allowed, key)
    local api = {total = 0, added = 0, ready = false, reason = 'WAITING_FOR_STATS',
        policy = 'local_projectile_stat_known_projectile_weapons', sources = {}}
    local prior, entity, native_total
    local function count(n)
        return type(n) == 'number' and n >= 0 and n <= 2147483647 and n % 1 == 0
    end
    function api:reset()
        self.total, self.added, self.ready, self.reason, self.sources = 0, 0, false, 'WAITING_FOR_STATS', {}
        prior, entity, native_total = nil, nil, nil
    end
    function api:sample(snapshot, player_entity)
        self.added = 0
        if type(snapshot) ~= 'table' or type(snapshot.totals) ~= 'table'
            or not count(snapshot.totals[key]) or type(snapshot.sources) ~= 'table'
            or not count(player_entity) then
            self.ready, self.reason = false, 'HIT_STATS_UNAVAILABLE'; return nil
        end
        local values, n, sum = {}, 0, 0
        for source, stats in pairs(snapshot.sources) do
            n = n + 1
            if n > 64 or type(stats) ~= 'table' or not count(stats[key] or 0) then
                self.ready, self.reason = false, 'HIT_STATS_INVALID'; return nil
            end
            if allowed[source] then values[source] = stats[key] or 0; sum = sum + values[source] end
        end
        if sum > snapshot.totals[key] then
            self.ready, self.reason = false, 'HIT_STATS_INCONSISTENT'; return nil
        end
        local first = prior == nil
        local rebase = first or entity ~= player_entity or snapshot.totals[key] < native_total
        if rebase then
            -- Late observation shows native totals but never announces old hits.
            if first then self.total, self.sources = sum, values end
            prior = values
        else
            local deltas, added = {}, 0
            for source, value in pairs(values) do
                local before = prior[source] or 0
                if value > before then
                    deltas[source] = value - before
                    added = added + deltas[source]
                end
                -- A missing/reused source block cannot replay an earlier count.
            end
            if added > snapshot.totals[key] - native_total then
                -- A source-table redistribution is not a new projectile contact.
                prior, entity, native_total = values, player_entity, snapshot.totals[key]
                self.ready, self.reason = false, 'HIT_SOURCE_REBASE'; return nil
            end
            self.added = added
            for source, delta in pairs(deltas) do
                self.sources[source] = (self.sources[source] or 0) + delta
                prior[source] = values[source]
            end
            self.total = self.total + self.added
        end
        entity, native_total = player_entity, snapshot.totals[key]
        self.ready, self.reason = true, nil
        return self.total, self.added, first
    end
    return api
end
