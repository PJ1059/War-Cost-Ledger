-- Only native system-discovery descriptors are accepted, never chat prose.
-- Compare complete sweeps by content/multiplicity. This is a notification
-- inference: the game's unique discovery event ID is not exposed.
local M = {}
local KEYS = {[0x92871A58]=true,[0xCD539459]=true}
function M.new()
    local api={diagnostics={ready=false,reason='WAITING_FOR_BASELINE',total=0}}
    local identity,sequence,counts=nil,nil,{}
    function api:reset()
        identity,sequence,counts=nil,nil,{}
        self.diagnostics={ready=false,reason='WAITING_FOR_BASELINE',total=0}
    end
    function api:update(snapshot,context)
        context=context or {}
        if context.mission~=true then self:reset();self.diagnostics.reason='NOT_IN_MISSION';return 0,self.diagnostics end
        if sequence~=context.sequence then self:reset();sequence=context.sequence end
        local d=self.diagnostics
        if type(snapshot)~='table' or snapshot.complete~=true or type(snapshot.identity)~='string'
            or type(snapshot.rows)~='table' or #snapshot.rows>64 then
            d.reason='WAITING_FOR_SWEEP';return 0,d
        end
        local current,local_rows={},{}
        for _,row in ipairs(snapshot.rows)do
            if type(row)=='table' and row.system_discovery==true and KEYS[row.template]
                and type(row.signature)=='string' and #row.signature>0 and #row.signature<=512 then
                local key=row.signature
                current[key]=(current[key] or 0)+1
                if row.discovery_kind~='point_of_interest' and row.local_player==true
                    and type(row.peer)=='string' and row.peer==snapshot.local_peer then
                    local_rows[key]=(local_rows[key] or 0)+1
                end
            end
        end
        if identity~=snapshot.identity then
            identity,counts=snapshot.identity,current
            d.ready,d.reason,d.rows,d.increment=true,'BASELINE_ESTABLISHED',#snapshot.rows,0
            return 0,d
        end
        local delta=0
        for key,after in pairs(current)do
            local before=counts[key] or 0
            if after>before then delta=delta+math.min(after-before,local_rows[key] or 0) end
        end
        -- Keep only the native 64-row window. Content that disappears and later
        -- reappears may count again, matching the explicitly accepted policy.
        counts=current
        d.ready,d.reason,d.rows,d.increment=true,delta>0 and 'LOCAL_DISCOVERY' or 'NO_NEW_LOCAL_DISCOVERY',#snapshot.rows,delta
        d.total=d.total+delta
        return delta,d
    end
    return api
end
return M
