-- Private read-only Lua export inventory. No engine calls, objects or metatables.
-- Only names/types leave collect(); a listed name does not prove its contract.
local M={}
local REQUESTED={'root','PhysicsWorld','Actor','World','Unit','ScriptWorld','Application'}
local TOTAL,PER_MODULE,NAME_BYTES,BUDGET_MS=1024,256,96,2
local function finite(v)return type(v)=='number'and v==v and v~=math.huge and v~=-math.huge end
local function valid_name(name)
    return #name>0 and #name<=NAME_BYTES and not name:find('[^ -~]')
end
local function by_name(a,b)return a.name<b.name end

-- opts.clock is a trusted diagnostic clock in seconds (default os.clock).
-- opts.budget_ms may lower, but cannot raise, the fixed 2ms soft limit.
function M.collect(root,opts)
    if type(opts)~='table'then opts={}end
    local clock=rawget(opts,'clock')
    if type(clock)~='function'then
        local os_table=rawget(_G,'os')
        clock=type(os_table)=='table'and rawget(os_table,'clock')or nil
    end
    local budget=rawget(opts,'budget_ms')
    if not finite(budget)then budget=BUDGET_MS end
    budget=math.max(0,math.min(BUDGET_MS,budget))
    local out={version=1,complete=false,reason='COMPLETE',elapsed_ms=0,
        total_entries=0,total_scanned=0,modules={},
        limits={total_entries=TOTAL,per_module_entries=PER_MODULE,name_bytes=NAME_BYTES,
            budget_ms=budget,soft_time_limit=true}}
    local started,stop,first_issue
    if type(clock)~='function'then stop='CLOCK_UNAVAILABLE'
    else
        local ok,value=pcall(clock)
        if ok and finite(value)then started=value else stop='CLOCK_INVALID'end
    end
    local function time_check()
        if stop then return false end
        local ok,value=pcall(clock)
        if not ok or not finite(value)or value<started then stop='CLOCK_INVALID';return false end
        out.elapsed_ms=(value-started)*1000
        if out.elapsed_ms>=budget then stop='TIME_LIMIT';return false end
        return true
    end
    for _,name in ipairs(REQUESTED)do
        local row={name=name,type='unobserved',status='not_scanned',reason='NOT_SCANNED',
            entries={},scanned=0,skipped_non_string=0,skipped_invalid_name=0}
        out.modules[#out.modules+1]=row
        if type(root)~='table'then
            row.type=type(root);row.status='unsupported';row.reason='UNSUPPORTED_ROOT'
        elseif time_check()then
            local module=name=='root'and root or rawget(root,name)
            row.type=type(module)
            if row.type~='table'then
                row.status='unsupported';row.reason='UNSUPPORTED_TYPE'
            else
                row.status='complete';row.reason='COMPLETE'
                local previous
                while true do
                    if not time_check()then row.status='partial';row.reason=stop;break end
                    if out.total_scanned>=TOTAL then
                        stop='TOTAL_LIMIT';row.status='partial';row.reason=stop;break
                    end
                    if row.scanned>=PER_MODULE then
                        row.status='partial';row.reason='MODULE_LIMIT';break
                    end
                    local key,value=next(module,previous)
                    if key==nil then break end
                    previous=key;row.scanned=row.scanned+1;out.total_scanned=out.total_scanned+1
                    if type(key)~='string'then row.skipped_non_string=row.skipped_non_string+1
                    elseif not valid_name(key)then row.skipped_invalid_name=row.skipped_invalid_name+1
                    else
                        row.entries[#row.entries+1]={name=key,type=type(value)}
                        out.total_entries=out.total_entries+1
                    end
                end
                if row.status=='complete'and(row.skipped_non_string>0 or row.skipped_invalid_name>0)then
                    row.status='partial';row.reason='FILTERED_KEYS'
                end
                table.sort(row.entries,by_name)
            end
        else row.reason=stop end
        if row.status~='complete'and not first_issue then first_issue=row.reason end
    end
    -- Final clock sample is a soft duration measurement, not another engine operation.
    if not stop and started then time_check()end
    table.sort(out.modules,by_name)
    out.reason=stop or first_issue or'COMPLETE'
    out.complete=out.reason=='COMPLETE'
    return out
end
return M
