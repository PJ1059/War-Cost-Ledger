-- Explicit menu action -> one Ship-only code-copy diagnostic per process.
-- Native ownership/restoration stays in the injected controller; no native work here.
return function(options)
    local api={phase='idle',reason='NOT_REQUESTED'}
    local controller,result,queued_at,deadline,attempted,recorded
    local function snapshot()
        return result or {phase=api.phase,reason=api.reason,payload_ready=false,
            classification_ready=false,requested=queued_at~=nil}
    end
    local function finish(value)
        if type(value)~='table' then error('COPY_RUNNER_INVALID_STATUS') end
        result=value;api.phase,api.reason=value.phase,value.reason
        if value.cleanup_required or value.cleanup_failed then return end
        if value.phase~='stopped' and value.phase~='failed' and value.phase~='rejected' then return end
        if recorded then return end
        recorded=true
        value.source_sha=options.source_sha
        value.version=options.version
        value.captured_at=os.date('!%Y-%m-%dT%H:%M:%SZ')
        local ok,why=pcall(options.persist,value)
        if not ok then value.dump_error=tostring(why) end
        options.log(string.format('命中代码副本测试：%s，调用%d次，恢复%s；四类命中仍未验证。',
            tostring(value.reason),tonumber(value.counter)or 0,tostring(value.restored==true)))
    end
    local function stop(reason)
        queued_at,deadline=nil,nil
        if not controller then
            api.phase,api.reason='cancelled',reason
            return snapshot()
        end
        local ok,value=pcall(controller.stop,controller,reason)
        if not ok then
            value={phase='failed',reason=tostring(value),cleanup_required=true,
                cleanup_failed=true,payload_ready=false,classification_ready=false}
        end
        finish(value);return snapshot()
    end
    function api:status() return snapshot() end
    function api:active()
        return queued_at~=nil or (controller~=nil and not recorded)
            or (result and (result.cleanup_required or result.cleanup_failed)) or false
    end
    function api:request(now)
        if attempted or controller or queued_at then return false,'COPY_ALREADY_REQUESTED' end
        if type(now)~='number' or now~=now or now<0 or now==math.huge then return false,'COPY_CLOCK_INVALID' end
        queued_at,deadline=now+5,now+35
        api.phase,api.reason='queued','WAITING_SHIP'
        return true
    end
    function api:cancel(reason) return stop(reason or 'USER_CANCELLED') end
    function api:step(now,world,game)
        if result and (result.cleanup_required or result.cleanup_failed) then
            return stop('CLEANUP_RETRY')
        end
        if queued_at then
            if now>deadline then
                queued_at,deadline=nil,nil;attempted=true
                finish({phase='rejected',reason='COPY_SHIP_WAIT_EXPIRED',counter=0,
                    payload_ready=false,classification_ready=false});return snapshot()
            end
            if now<queued_at or not world or not game or game.state~=3 or game.mission~=false then return snapshot() end
            queued_at,deadline=nil,nil;attempted=true
            local ok,value=pcall(function()
                controller=options.load().new()
                return controller:start(world,game)
            end)
            if not ok then
                if controller then return stop('START_ERROR: '..tostring(value)) end
                value={phase='failed',reason=tostring(value),counter=0,
                    payload_ready=false,classification_ready=false}
            end
            finish(value);return snapshot()
        end
        if not controller or recorded then return snapshot() end
        if not world or not game then return stop('WORLD_UNAVAILABLE') end
        local ok,value=pcall(controller.tick,controller,world,game)
        if not ok then return stop('TICK_ERROR: '..tostring(value)) end
        finish(value);return snapshot()
    end
    return api
end
