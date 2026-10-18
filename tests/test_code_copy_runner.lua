local create=dofile(assert(arg[1]))
local function fixture(mode)
    local f={starts=0,ticks=0,stops=0,loads=0,saves=0,logs={}}
    local p={d={phase='idle',reason='NOT_STARTED',counter=0,payload_ready=false}}
    function p:status()return self.d end
    function p:start(_,game)
        assert(game.state==3 and game.mission==false)
        f.starts=f.starts+1
        if mode=='start_error' then error('START_FAILURE') end
        self.d={phase='running',reason='WINDOW_RUNNING',counter=0};return self.d
    end
    function p:tick()
        f.ticks=f.ticks+1
        if mode=='tick_error' then error('TICK_FAILURE') end
        return self:stop('WINDOW_ENDED')
    end
    function p:stop(reason)
        f.stops=f.stops+1
        local pending=mode=='cleanup' and f.stops<3
        self.d={phase='stopped',reason=reason,counter=7,restored=not pending,
            cleanup_required=pending};return self.d
    end
    f.runner=create({source_sha='fixture',version='fixture',load=function()
        f.loads=f.loads+1;return {new=function()return p end}
    end,persist=function(value)f.saves=f.saves+1;f.saved=value end,
        log=function(s)f.logs[#f.logs+1]=s end})
    return f
end
local world,ship,mission={}, {state=3,mission=false}, {state=4,mission=true}
local tests=0
local function test(fn)fn();tests=tests+1 end
test(function()
    local f=fixture();assert(not f.runner:active() and f.loads==0)
    f.runner:step(10,world,ship);assert(f.loads==0)
    assert(f.runner:request(10));f.runner:step(14.9,world,ship);assert(f.loads==0)
    f.runner:step(15,world,mission);assert(f.loads==0)
    f.runner:step(15,world,ship);assert(f.starts==1 and f.saves==0)
    f.runner:step(17,world,ship);assert(f.saved.restored and f.saved.source_sha=='fixture' and f.saves==1)
    assert(not f.runner:active());f.runner:step(18,world,ship)
    assert(f.ticks==1 and f.saves==1 and not f.runner:request(20))
end)
test(function()
    local f=fixture();f.runner:request(0);f.runner:cancel('CANCEL')
    f.runner:step(10,world,ship);assert(f.loads==0 and not f.runner:active())
end)
test(function()
    local f=fixture();f.runner:request(0);f.runner:step(36,nil,nil)
    assert(f.loads==0 and f.saves==1 and f.saved.reason=='COPY_SHIP_WAIT_EXPIRED')
end)
test(function()
    local f=fixture();f.runner:request(0);f.runner:step(5,world,ship)
    f.runner:step(5.1,nil,nil);assert(f.stops==1 and f.saved.reason=='WORLD_UNAVAILABLE' and f.saved.restored)
end)
test(function()
    local f=fixture('cleanup');f.runner:request(0);f.runner:step(5,world,ship)
    f.runner:step(7,world,ship);assert(f.runner:active() and f.saves==0)
    f.runner:step(7.1,nil,nil);assert(f.stops==2 and f.saves==0)
    f.runner:step(7.2,nil,nil);assert(f.stops==3 and f.saved.restored and f.saves==1 and not f.runner:active())
end)
for _,mode in ipairs({'start_error','tick_error'})do test(function()
    local f=fixture(mode);f.runner:request(0);f.runner:step(5,world,ship)
    if mode=='tick_error'then f.runner:step(7,world,ship)end
    assert(f.stops==1 and f.saved.restored and f.saves==1 and not f.runner:active())
end)end
test(function()
    local f=fixture();assert(not f.runner:request(0/0));assert(not f.runner:request(math.huge))
    assert(f.loads==0 and f.saves==0)
end)
print('PASS explicit code-copy runner: '..tests..' cases; Ship-only queue, no startup, one run, cancellation, error cleanup and independent terminal save.')
