-- Real game LuaJIT and Runtime bytes decoder, with simulated native controls.
-- These fixtures own their Lua FIFO. No game process, pages or hooks are used.
local root,sdk=assert(arg[1]),assert(arg[2])
package.preload['hd2runtime/core/bytes']=function()return dofile(sdk..'/core/bytes.lua')end
local bytes=require('hd2runtime/core/bytes')
local decoder=dofile(root..'/src/native-hit-feedback.lua')
local sessions=dofile(root..'/src/native-hit-session.lua')
local PEER,OTHER='FEDCBA9876543210','FEDCBA9876543211'
local ZERO='0000000000000000'
local tests=0
local function check(name,fn)
    local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));tests=tests+1;print('PASS '..name)
end
local function q(s)
    return bytes.encode(tonumber(s:sub(9,16),16),'u32')..bytes.encode(tonumber(s:sub(1,8),16),'u32')
end
local function u(n)return bytes.encode(n,'u32')end
local function f(n)return bytes.encode(n,'f32')end
local function fixture()
    local h={native_certified=true}
    local x={handle=h,queue={},configs=0,pauses=0,resumes=0,attaches=0,steps=0,
        enabled=false,sequence=0,configure_busy=0,pause_busy=0,resume_busy=0,accepted={},changes=0}
    local c={}
    function c.configure(handle,peer,epoch,enabled)
        assert(handle==h and enabled==true,'only initial/new-epoch enable config is allowed')
        x.configs=x.configs+1;x.enabled=false
        if x.configure_throw then error('simulated native configure failure')end
        if x.configure_busy>0 then x.configure_busy=x.configure_busy-1;return false end
        x.queue={};x.peer,x.epoch=peer,epoch;x.enabled=true
        return true
    end
    function c.pause(handle,peer,epoch)
        assert(handle==h);x.pauses=x.pauses+1;x.enabled=false
        if peer~=x.peer or epoch~=x.epoch then return nil,'BRIDGE_IDENTITY_MISMATCH' end
        if x.pause_busy>0 then x.pause_busy=x.pause_busy-1;return false end
        if x.pause_throw then error('simulated native pause failure')end
        return true
    end
    function c.resume(handle,peer,epoch)
        assert(handle==h and peer==x.peer and epoch==x.epoch)
        x.resumes=x.resumes+1
        if x.resume_busy>0 then x.resume_busy=x.resume_busy-1;return false end
        x.enabled=true;return true
    end
    function c.attach(handle,options)
        assert(handle==h and options.peer==x.peer and options.epoch==x.epoch)
        x.attaches=x.attaches+1
        if x.attach_failure then return nil,'BRIDGE_IDENTITY_MISMATCH' end
        local d=options.decoder.new(options)
        local consumer={decoder=d,records=0,ready=true}
        function consumer:step(now)
            x.steps=x.steps+1
            if x.drain_failure then return nil,'BRIDGE_DRAIN_INVALID' end
            assert(self.ready and options.peer==x.peer and options.epoch==x.epoch)
            local n=math.min(#x.queue,64);local batch={}
            for i=1,n do batch[i]=table.remove(x.queue,1)end
            local ok,why=d:consume(table.concat(batch),now,{abi=1,stride=96,connector_proven=true,
                epoch=options.epoch,count=n,dropped=x.dropped or ZERO})
            if ok then self.records=self.records+n end
            assert(n<=64);x.last_batch=n
            return ok,why
        end
        function consumer:detach()self.ready=false;x.detached=(x.detached or 0)+1 end
        return consumer
    end
    x.connector=c
    x.session=sessions.new({connector=c,decoder=decoder,accept=function(contact,now,s)
        if x.sink_throw then error('simulated sink failure')end
        x.accepted[#x.accepted+1]={sequence=s.sequence,peer=s.peer,result=contact.result,time=now}
        return true
    end,changed=function()x.changes=x.changes+1 end})
    function x:tick(now,changes)
        local observation={world=true,mission=true,sequence=7,peer=PEER,baseline=true}
        for key,value in pairs(changes or {})do observation[key]=value end
        local before=self.steps
        assert(self.session:tick(now,observation))
        assert(self.steps-before<=1,'each 10 Hz tick has at most one bounded FIFO drain')
        return self.session.current,self.session.last
    end
    function x:bind()assert(self.session:set_handle(h))end
    function x:publish(branch,delta,extra)
        assert(self.enabled,'simulated native producer must be enabled')
        self.sequence=self.sequence+1
        local seq=string.format('%016X',self.sequence)
        local raw=q(seq)..q(self.epoch)..q(self.peer)..q(ZERO)..u(0)..u(0)..u(1)..u(123)..u(42)..u(99)
            ..u(0)..u(branch or 1)..f(4)..f(3)..f(1)..f(0)..u(0)..u(1)
            ..u(branch==2 and 323 or 511)..f(delta or 1)
        assert(#raw==96)
        self.queue[#self.queue+1]=raw
        if extra then self.queue[#self.queue+1]=raw end
        return raw
    end
    return x
end

check('exact mission epochs preserve high bits and reject rounded u64 numbers',function()
    assert(sessions.epoch(7)=='0000000000000007')
    assert(sessions.epoch(4294967297)=='0000000100000001')
    assert(sessions.epoch(9007199254740991)=='001FFFFFFFFFFFFF')
    assert(sessions.epoch('fedcba9876543210')=='FEDCBA9876543210')
    for _,bad in ipairs({0,-1,1.1,9007199254740992,math.huge,ZERO,'bad'})do assert(sessions.epoch(bad)==nil)end
end)
check('certified handle plus true initial stats baseline plus exact peer gate activation',function()
    local x=fixture();x:tick(0);assert(x.configs==0 and x.attaches==0)
    assert(x.session:set_handle({native_certified=false})==nil)
    x:bind();x:tick(.1,{baseline=false});x:tick(.2,{peer=ZERO});x:tick(.3,{mission=false})
    assert(x.configs==0 and not x.session.ready)
    local s=x:tick(.4);assert(s.epoch=='0000000000000007' and x.configs==1 and x.attaches==1)
    assert(x.session.ready and s.ready and x.enabled)
    assert(x.session:set_handle({native_certified=true})==nil,'existing lifetime handle must not be replaced')
end)
check('busy configuration retries existing session once per next tick with no attach allocation',function()
    local x=fixture();x:bind();x.configure_busy=2
    local s=x:tick(0);assert(s.status=='configuring' and s.partial and not x.session.ready)
    assert(x.attaches==0 and not x.enabled)
    x:tick(.1);assert(x.session.current==s and x.attaches==0 and x.configs==2)
    x:tick(.2);assert(x.session.current==s and x.attaches==1 and x.session.ready and x.configs==3)
end)
check('never-configured pending session ends without pausing unapplied native identity',function()
    local x=fixture();x:bind();x.peer,x.epoch=OTHER,'0000000000000006';x.configure_busy=2
    local pending=x:tick(0);assert(not pending.configured and not pending.consumer)
    local current,last=x:tick(.1,{mission=false})
    assert(not current and last==pending and last.closed and last.status=='ended')
    assert(x.pauses==0 and x.steps==0 and x.attaches==0 and x.configs==1)
    assert(x.peer==OTHER and x.epoch=='0000000000000006' and not x.session.ready)
    x:tick(.2,{mission=false});assert(not x.session.current and x.pauses==0)
end)
check('never-configured mission or peer change abandons pending identity and can configure next session',function()
    for _,change in ipairs({{sequence=8},{peer=OTHER}})do
        local x=fixture();x:bind();x.peer,x.epoch=PEER,'0000000000000006';x.configure_busy=1
        local pending=x:tick(0);assert(not pending.configured and not pending.consumer)
        local current,last=x:tick(.1,change)
        assert(current~=pending and current.configured and last==pending and last.closed)
        assert(last.status=='ended' and x.pauses==0 and x.configs==2 and x.attaches==1)
        assert(current.epoch==sessions.epoch(change.sequence or 7) and current.peer==(change.peer or PEER))
        assert(x.session.ready)
    end
end)
check('pending baseline cannot activate while world or peer is unavailable',function()
    local x=fixture();x:bind();x.configure_busy=1;local s=x:tick(0)
    x:tick(.1,{world=false});x:tick(.2,{peer=ZERO})
    assert(x.configs==1 and x.attaches==0 and s==x.session.current and not x.session.ready)
    x:tick(.3);assert(x.configs==2 and x.attaches==1 and x.session.ready)
end)
check('missing lifecycle controls reject enable and retry after controls become available',function()
    local x=fixture();x:bind();local pause=x.connector.pause;x.connector.pause=nil
    local s=x:tick(0);assert(s.partial and not s.ready and s.reason=='NATIVE_LIFECYCLE_CONTROL_UNAVAILABLE')
    x:tick(.1);assert(x.configs==0 and x.attaches==0 and x.session.current==s)
    x.connector.pause=pause;x:tick(.2);assert(x.configs==1 and x.attaches==1 and x.session.ready)
end)
check('real decoder classifies four branches independently of F8 display and later stats gaps',function()
    local x=fixture();x:bind();x:tick(0)
    x:publish(1,-1);x:publish(1,0);x:publish(1,1);x:publish(2)
    local s=x:tick(.1,{hud_enabled=false,baseline=false})
    assert(s.accepted==4 and s.records==4 and #x.accepted==4)
    for i,key in ipairs({'blocked','penetration','full_penetration','ricochet'})do assert(x.accepted[i].result==key)end
    x:tick(.2,{hud_enabled=true});assert(s.accepted==4 and x.attaches==1 and x.configs==1)
end)
check('world gap pauses and drains 64 plus 64 plus 2 without reconfigure or new decoder',function()
    local x=fixture();x:bind();local s=x:tick(0);local consumer=s.consumer
    for _=1,130 do x:publish()end
    x:tick(.1,{world=false});assert(not x.enabled and not x.session.ready and s.accepted==64 and s.status=='draining')
    x:tick(.2,{world=false});assert(s.accepted==128 and s.status=='draining')
    x:tick(.3,{world=false});assert(s.accepted==130 and s.status=='paused' and s.partial)
    local steps=x.steps;x:tick(.4,{world=false});assert(x.steps==steps and x.pauses==1)
    x:tick(.5);assert(x.session.current==s and s.consumer==consumer and x.resumes==1)
    assert(x.configs==1 and x.attaches==1 and s.accepted==130 and x.session.ready)
    x:publish(2);x:tick(.6);assert(s.accepted==131 and s.consumer.decoder.last_sequence=='0000000000000083')
end)
check('same mission returning early drains old queued tail before resume without replay',function()
    local x=fixture();x:bind();local s=x:tick(0)
    for _=1,66 do x:publish()end
    x:tick(.1,{world=false});assert(s.accepted==64 and x.resumes==0)
    x:tick(.2);assert(s.accepted==66 and x.resumes==1 and x.configs==1 and x.attaches==1)
    x:tick(.3);assert(s.accepted==66)
end)
check('mission switch retains old session attribution and empties FIFO before reset',function()
    local x=fixture();x:bind();local old=x:tick(0)
    for _=1,130 do x:publish()end
    x:tick(.1,{sequence=8});assert(x.session.current==old and old.accepted==64 and x.configs==1)
    x:tick(.2,{sequence=8});assert(old.accepted==128 and x.configs==1)
    local new,last=x:tick(.3,{sequence=8})
    assert(new~=old and last==old and last.status=='ended' and last.closed and last.accepted==130)
    assert(new.epoch=='0000000000000008' and new.accepted==0 and x.configs==2 and x.attaches==2)
    for _,event in ipairs(x.accepted)do assert(event.sequence==7)end
    x:publish(2);x:tick(.4,{sequence=8});assert(new.accepted==1 and x.accepted[131].sequence==8)
end)
check('peer change is exact above 2^53 and old peer tail never enters the new session',function()
    local x=fixture();x:bind();local old=x:tick(0);x:publish(1,-1)
    local new,last=x:tick(.1,{peer=OTHER})
    assert(last==old and last.peer==PEER and last.accepted==1 and new.peer==OTHER and new.accepted==0)
    assert(x.accepted[1].peer==PEER and x.configs==2 and x.attaches==2)
    x:publish(2);x:tick(.2,{peer=OTHER});assert(new.accepted==1 and x.accepted[2].peer==OTHER)
end)
check('exit mission waits for native active observers and saves tail before closing',function()
    local x=fixture();x:bind();local old=x:tick(0);x:publish();x.pause_busy=1
    x:tick(.1,{mission=false});assert(not x.enabled and not x.session.ready and old.status=='stopping')
    assert(old.partial and #x.queue==1 and old.accepted==0 and x.configs==1)
    local current,last=x:tick(.2,{mission=false})
    assert(not current and last==old and last.accepted==1 and last.status=='ended' and last.closed)
    assert(x.pauses==2 and x.configs==1 and x.attaches==1)
end)
check('native control errors keep old session paused and retry without reallocation',function()
    local x=fixture();x:bind();local old=x:tick(0);x:publish();x.pause_throw=true
    x:tick(.1,{world=false});assert(old.status=='stopping' and old.partial and not x.session.ready)
    x:tick(.2,{world=false});assert(x.attaches==1 and x.configs==1 and x.session.current==old)
    x.pause_throw=false;x:tick(.3,{world=false});assert(old.status=='paused' and old.accepted==1)
    x.resume_busy=1;x:tick(.4);assert(old.status=='paused' and not x.session.ready and not x.enabled)
    x:tick(.5);assert(x.session.ready and old.accepted==1 and x.attaches==1 and x.configs==1)
end)
check('invalid clock has no control or drain effects',function()
    local x=fixture();x:bind();x:tick(1);local controls,steps=x.configs+x.pauses+x.resumes,x.steps
    for _,now in ipairs({.9,-1,math.huge})do assert(x.session:tick(now,{})==nil)end
    assert(x.configs+x.pauses+x.resumes==controls and x.steps==steps and x.session.ready)
end)
check('attach failure stops producer and permits no repeated same-identity allocation',function()
    local x=fixture();x:bind();x.attach_failure=true;x:tick(0)
    assert(not x.enabled and not x.session.ready and not x.session.current)
    assert(x.session.last.status=='failed' and x.session.last.partial and x.attaches==1)
    for i=1,100 do x:tick(i*.1)end
    assert(x.attaches==1 and x.configs==1 and x.pauses==1)
    x.attach_failure=false;x:tick(11,{sequence=8});assert(x.attaches==2 and x.session.ready)
end)
check('decoder drops and duplicate sequences mark coverage while preserving counted records',function()
    local x=fixture();x:bind();local s=x:tick(0);x:publish(1,0,true);x.dropped='0000000000000001'
    x:tick(.1);assert(s.accepted==1 and s.records==2 and s.stale==1 and s.partial)
    x:tick(.2);assert(s.accepted==1 and s.stale==1)
end)
check('sink exception is isolated and never invents acceptance or erases other mission counts',function()
    local x=fixture();x:bind();local s=x:tick(0);x:publish();x:tick(.1);assert(s.accepted==1)
    x.sink_throw=true;x:publish();x:tick(.2)
    assert(s.accepted==1 and #x.accepted==1 and s.partial and x.session.ready)
    x.sink_throw=false;x:publish();x:tick(.3);assert(s.accepted==2 and #x.accepted==2)
end)
check('drain error becomes failed only after producer pause without resetting known counts',function()
    local x=fixture();x:bind();local s=x:tick(0);x:publish();x:tick(.1)
    x.drain_failure=true;x:tick(.2);assert(s.accepted==1 and s.status=='stopping' and not x.session.ready)
    x:tick(.3);assert(not x.enabled and x.session.last==s and s.status=='failed' and s.accepted==1)
    x:tick(.4);assert(x.attaches==1 and x.configs==1)
end)
print('Native hit session: '..tests..' checks passed; actual game LuaJIT + decoder, simulated native controls; game events/FPS unverified')
