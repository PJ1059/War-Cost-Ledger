-- Count only observed local-player KILLS growth for reviewed vehicle bodies.
-- Parent body is the user-approved crush rule; mounted weapons are excluded.
-- This is not a native collision-mechanism claim and performs no game reads.
local function count(v)
    return type(v)=='number' and v>=0 and v<=2147483647 and v%1==0
end
return function(allowed,key)
    assert(type(allowed)=='table' and type(key)=='number' and key>=0 and key<=4294967295
        and key%1==0,'vehicle ribbons need reviewed sources and native KILLS key')
    local hashes={}
    for hash,source in pairs(allowed)do
        assert(type(hash)=='string' and #hash==16 and not hash:find('[^%x]')
            and type(source)=='table' and source.kind=='vehicle_body'
            and source.known_player_call_in==true,'invalid reviewed vehicle body source')
        hashes[#hashes+1]=hash:upper()
    end
    local api={version=1,total=0,added=0,ready=false,reason='WAITING_FOR_STATS',
        policy='confirmed_player_vehicle_parent_source_kills_as_crush',sources={}}
    local prior,entity,native_total,needs_baseline={},nil,nil,true
    function api:reset()
        self.total,self.added,self.ready,self.reason,self.sources=0,0,false,'WAITING_FOR_STATS',{}
        prior,entity,native_total,needs_baseline={},nil,nil,true
    end
    function api:gap()
        self.added,self.ready,self.reason=0,false,'VEHICLE_KILL_STATS_UNAVAILABLE'
        needs_baseline=true
    end
    function api:sample(snapshot,player_entity)
        self.added=0
        local function reject(reason)
            self.ready,self.reason=false,reason
            needs_baseline=true
            return nil
        end
        if type(snapshot)~='table' or type(snapshot.totals)~='table' or not count(snapshot.totals[key])
            or type(snapshot.sources)~='table' or not count(player_entity) then
            return reject('VEHICLE_KILL_STATS_UNAVAILABLE')
        end
        local values,sum={},0
        for _,hash in ipairs(hashes)do
            local row=snapshot.sources[hash]
            if row~=nil then
                if type(row)~='table' or not count(row[key] or 0) then
                    return reject('VEHICLE_KILL_SOURCE_INVALID')
                end
                values[hash]=row[key] or 0;sum=sum+values[hash]
            end
        end
        local current=snapshot.totals[key]
        if sum>current then return reject('VEHICLE_KILL_SOURCES_EXCEED_TOTAL') end
        if needs_baseline or entity~=player_entity or native_total==nil or current<native_total then
            -- No backfill: an initial/late-join/recovered value is not an award.
            -- Keep previously earned ribbons across counter/player rebases.
            for hash,value in pairs(values)do prior[hash]=value end
            entity,native_total,needs_baseline=player_entity,current,false
            self.ready,self.reason=true,'VEHICLE_KILL_BASELINE'
            return self.total,0,true
        end
        local deltas,added={},0
        for hash,value in pairs(values)do
            local before=prior[hash] or 0
            if value>before then deltas[hash]=value-before;added=added+deltas[hash] end
            -- A source counter decrease starts a new segment at its observed
            -- value, never awards that value or erases previously earned counts.
        end
        if added>current-native_total then
            -- Table movement/reappearance without matching local native kills
            -- is a rebase, not another body-kill batch.
            for hash,value in pairs(values)do prior[hash]=value end
            entity,native_total=player_entity,current
            self.ready,self.reason=false,'VEHICLE_KILL_SOURCE_REBASE'
            return nil
        end
        for hash,value in pairs(values)do prior[hash]=value end
        for hash,delta in pairs(deltas)do self.sources[hash]=(self.sources[hash] or 0)+delta end
        self.total,self.added=self.total+added,added
        entity,native_total=player_entity,current
        self.ready,self.reason=true,nil
        return self.total,added,false
    end
    return api
end
