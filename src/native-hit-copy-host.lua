-- Install the observation copy once on the ship. The existing mission session
-- controls the recorder gate, identity and bounded draining independently.
local M={}
function M.new(options)
    assert(type(options)=='table'and type(options.code)=='table'and type(options.code.new)=='function'
        and type(options.package)=='table'and type(options.package.prepare)=='function'
        and type(options.link)=='table'and type(options.link.link)=='function'
        and type(options.profile)=='table','HIT_COPY_HOST_OPTIONS')
    local controller,attempted,ship_since,result,reported
    local api={phase='waiting_ship',reason='WAITING_SHIP'}
    local function record(value)
        result=value;api.phase,api.reason=value.phase,value.reason
        if reported or value.phase=='running' or value.cleanup_required then return end
        reported=true
        if options.log then options.log('命中副本装载停止：'..tostring(value.reason))end
    end
    function api:handle()
        return controller and controller:observer_handle() or nil
    end
    function api:status()
        return result or {phase=api.phase,reason=api.reason,installed=false}
    end
    function api:tick(now,world,game)
        assert(type(now)=='number'and now==now and now>=0 and now<math.huge,'HIT_COPY_HOST_CLOCK')
        if controller then
            local current=controller:status()
            if current.cleanup_required then record(controller:stop('CLEANUP_RETRY'))
            elseif world and game then record(controller:tick(world,game))end
            -- Missing world pauses the mission session. It does not discard
            -- the reusable dispatch copy during a loading transition.
            return self:status()
        end
        if attempted then return self:status()end
        if not world or not game or game.state~=3 or game.mission~=false then
            ship_since=nil;return self:status()
        end
        if not ship_since then ship_since=now;return self:status()end
        if now-ship_since<2 then return self:status()end
        attempted=true
        local ok,value=pcall(function()
            controller=options.code.new({continuous=true,
                observer_factory=function(image)
                    return options.profile,options.package.prepare(image,options.profile)
                end,observer_link=options.link.link})
            return controller:start(world,game)
        end)
        if not ok then
            if controller then
                local stopped,why=pcall(controller.stop,controller,'HOST_START_ERROR')
                if stopped and why.cleanup_required then record(why);return self:status()end
            end
            value={phase='failed',reason=tostring(value),installed=false}
        end
        record(value)
        if value.phase=='running'and options.log then
            options.log('命中副本已装载；等待任务与本人统计基线。')
        end
        return self:status()
    end
    return api
end
return M
