local create=assert(loadfile(assert(arg[1])))()
local source_starts,prepared,linked,ticks,stops=0,0,0,0,0
local handle={native_certified=true}
local status={phase='running',reason='OBSERVATION_COPY_INSTALLED',installed=true}
local options
options={profile={},package={prepare=function()prepared=prepared+1;return handle end},
    link={link=function()linked=linked+1 end},code={new=function(config)
        assert(config.continuous and type(config.observer_factory)=='function'and type(config.observer_link)=='function')
        return {start=function(_,world,game)
                source_starts=source_starts+1;assert(game.state==3 and not game.mission)
                local profile,actual=config.observer_factory({});assert(actual==handle and profile==options.profile)
                config.observer_link();return status
            end,
            status=function()return status end,
            observer_handle=function()return status.installed and handle or nil end,
            tick=function(_,world,game)ticks=ticks+1;return status end,
            stop=function()stops=stops+1;status={phase='stopped',reason='CLEANUP_RETRY',installed=false};return status end}
    end}}
local host=create.new(options)
assert(source_starts==0 and prepared==0 and linked==0)
host:tick(0,{}, {state=4,mission=true});assert(source_starts==0)
host:tick(1,{}, {state=3,mission=false});host:tick(2.9,{}, {state=3,mission=false});assert(source_starts==0)
host:tick(3,{}, {state=3,mission=false});assert(source_starts==1 and prepared==1 and linked==1 and host:handle()==handle)
host:tick(4,nil,nil);assert(stops==0 and ticks==0 and host:handle()==handle,'loading gap keeps dispatch copy; session pauses recorder')
host:tick(5,{}, {state=4,mission=true});assert(source_starts==1 and ticks==1 and host:handle()==handle)
status={phase='failed',reason='RESTORE_PENDING',installed=true,cleanup_required=true}
host:tick(6,nil,nil);assert(stops==1 and host:handle()==nil)
host:tick(7,{}, {state=3,mission=false});assert(source_starts==1,'one installation attempt per process')
print('PASS native-hit-copy-host phase/baseline loading gap / cleanup retry; no Game access')
