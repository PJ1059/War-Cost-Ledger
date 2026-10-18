-- Mission lifecycle only. The caller supplies one already-certified native
-- handle and calls tick from its existing 10 Hz stats observation block.
-- There is no loader, hook installation, game read, HUD toggle or allocation of
-- native pages here. accept(contact, time, session) keeps final old-epoch data
-- attributable to its original mission even after the caller changes missions.
local M={max_batch=64}
local ZERO='0000000000000000'
local function exact(s)
    return type(s)=='string' and #s==16 and not s:find('[^%x]') and s~=ZERO
end
local function clock(n)return type(n)=='number' and n==n and n>=0 and n<math.huge end
function M.epoch(sequence)
    if exact(sequence) then return sequence:upper() end
    if type(sequence)~='number' or sequence<1 or sequence>9007199254740991
        or sequence%1~=0 then return nil,'MISSION_SEQUENCE_INVALID' end
    local hi=math.floor(sequence/4294967296)
    return string.format('%08X%08X',hi,sequence-hi*4294967296)
end

function M.new(options)
    assert(type(options)=='table' and type(options.connector)=='table'
        and type(options.connector.configure)=='function' and type(options.connector.attach)=='function'
        and type(options.decoder)=='table' and type(options.decoder.new)=='function'
        and type(options.accept)=='function','hit session needs connector, decoder and a sink')
    local connector=options.connector
    local api={ready=false,status='waiting_handle',current=nil,last=nil}
    local handle,last_time,drained=nil,0,false
    local function changed(s)
        if options.changed then pcall(options.changed,s,api) end
    end
    local function state(s,status,reason)
        local different=s.status~=status or s.reason~=reason
        s.status,s.reason=status,reason
        api.status,api.reason,api.ready=status,reason,status=='active'
        s.ready=api.ready
        if different then
            changed(s)
            if reason and options.log then pcall(options.log,'Native hit session: '..reason) end
        end
    end
    local function partial(s,reason)
        if not s.partial then s.partial=true;s.coverage_reason=reason;changed(s) end
        if s.consumer and s.consumer.decoder then s.consumer.decoder.partial=true end
    end
    local function control(name,s,enabled)
        local ok,result,why
        if type(connector[name])~='function' then return nil,'NATIVE_'..name:upper()..'_UNAVAILABLE' end
        if name=='configure' then
            ok,result,why=pcall(connector.configure,handle,s.peer,s.epoch,enabled)
        else ok,result,why=pcall(connector[name],handle,s.peer,s.epoch) end
        if not ok then return nil,'NATIVE_'..name:upper()..'_FAILED' end
        if result~=true then return nil,why or ('NATIVE_'..name:upper()..'_BUSY') end
        return true
    end
    local function step(s,now)
        if drained or not s.consumer then return nil,'NO_CONSUMER' end
        drained=true
        local before=s.consumer.records or 0
        local ok,result,why=pcall(s.consumer.step,s.consumer,now)
        if not ok or result~=true then
            partial(s,why or 'NATIVE_DRAIN_FAILED')
            s.failure=why or 'NATIVE_DRAIN_FAILED'
            return nil,s.failure
        end
        s.records=s.consumer.records or before
        local decoder=s.consumer.decoder
        if decoder then
            if decoder.partial then partial(s,'NATIVE_COVERAGE_GAP') end
            s.unclassified,s.stale=decoder.unclassified or 0,decoder.stale or 0
        end
        return s.records-before
    end
    local function finish(s,status,reason)
        if s.consumer then pcall(s.consumer.detach,s.consumer) end
        s.closed=true
        state(s,status,reason)
        api.last,api.current=s,nil
    end
    local function request_stop(s,mode,reason)
        -- A busy configure has not applied this session's identity to the
        -- native bridge. Pausing that new identity would be rejected forever.
        if mode=='close' and not s.configured then finish(s,'ended');return end
        s.stop_mode=mode
        if mode=='pause' then partial(s,reason) end
        state(s,'stopping',reason)
    end
    local function stop(s,now)
        if not s.stopped then
            -- pause must disable and prove native quiescence without changing
            -- the FIFO, identities, rows or counters. configure(false) resets
            -- the FIFO and is deliberately never a lifecycle substitute.
            local ok,why=control('pause',s)
            if not ok then partial(s,why);state(s,'stopping',why);return false end
            s.stopped=true
            state(s,'draining',s.stop_mode=='pause' and s.coverage_reason or nil)
        end
        if s.consumer and not s.failure then
            local count,why=step(s,now)
            if count==nil then s.failure=why end
            if count and count>=M.max_batch then return false end
        end
        if s.failure then finish(s,'failed',s.failure)
        elseif s.stop_mode=='pause' then state(s,'paused',s.coverage_reason)
        else finish(s,'ended') end
        return true
    end
    local function attach(s)
        local ok,consumer,why=pcall(connector.attach,handle,{peer=s.peer,epoch=s.epoch,
            observe_record=options.observe_record,
            decoder=options.decoder,accept=function(contact,now)
                local accepted,result=pcall(options.accept,contact,now,s)
                if not accepted then partial(s,'HIT_SINK_FAILED');return false end
                if result==false then return false end
                s.accepted=s.accepted+(contact.count or 1)
                changed(s)
                return true
            end})
        if not ok or type(consumer)~='table' or type(consumer.step)~='function' then
            s.failure=why or 'NATIVE_ATTACH_FAILED'
            partial(s,s.failure)
            request_stop(s,'close',s.failure)
            return false
        end
        s.consumer=consumer
        return true
    end
    function api:set_handle(value)
        if type(value)~='table' or value.native_certified~=true then
            return nil,'NATIVE_HANDLE_NOT_CERTIFIED'
        end
        if handle and handle~=value then return nil,'NATIVE_HANDLE_ALREADY_BOUND' end
        handle=value
        if not self.current then self.status,self.reason='waiting_baseline',nil end
        return true
    end
    function api:tick(now,observation)
        if not clock(now) or now<last_time then return nil,'INVALID_CLOCK' end
        if type(observation)~='table' then return nil,'OBSERVATION_INVALID' end
        last_time,drained=now,false
        if not handle then self.ready=false;self.status='waiting_handle';return true end
        local epoch=M.epoch(observation.sequence)
        local peer=exact(observation.peer) and observation.peer:upper() or nil
        local available=observation.world==true and observation.mission~=nil
        local eligible=available and observation.mission==true and epoch and peer
        local s=self.current
        if s then
            local ended=available and observation.mission==false
            local different=available and observation.mission==true and epoch and peer
                and (s.epoch~=epoch or s.peer~=peer)
            if ended or different then
                if s.status~='stopping' and s.status~='draining' then request_stop(s,'close')
                else s.stop_mode='close' end
            elseif not eligible and s.status=='configuring' then
                -- No successful configure or attachment exists yet. Leave
                -- this one pending session in place until identity returns.
                partial(s,not available and 'WORLD_UNAVAILABLE' or 'LOCAL_IDENTITY_UNAVAILABLE')
                state(s,'configuring',s.coverage_reason)
                return true
            elseif not eligible and s.status~='stopping' and s.status~='draining' and s.status~='paused' then
                request_stop(s,'pause',not available and 'WORLD_UNAVAILABLE' or 'LOCAL_IDENTITY_UNAVAILABLE')
            end
            if s.status=='stopping' or s.status=='draining' then
                if not stop(s,now) then return true end
                s=self.current
            end
            if s and s.status=='paused' then
                if not eligible then return true end
                local ok,why=control('resume',s)
                if not ok then state(s,'paused',why);return true end
                s.stopped,s.stop_mode=false,nil
                state(s,'active')
            end
            if s and s.status=='active' then
                if not drained then
                    local count,why=step(s,now)
                    if count==nil then request_stop(s,'close',why) end
                end
                return true
            end
        end
        if not self.current then
            -- A failed identity gets one attach attempt. Retry only after a
            -- genuine peer/mission change; busy control retries allocate none.
            if self.last and self.last.status=='failed' and eligible
                and self.last.epoch==epoch and self.last.peer==peer then return true end
            if not eligible or observation.baseline~=true then
                self.ready=false
                self.status=available and observation.mission==false and 'ended' or 'waiting_baseline'
                return true
            end
            s={sequence=observation.sequence,peer=peer,epoch=epoch,accepted=0,records=0,
                unclassified=0,stale=0,partial=false,ready=false,configured=false}
            self.current=s
            state(s,'configuring')
        else s=self.current end
        if s.status=='configuring' then
            if not eligible then return true end
            if type(connector.pause)~='function' or type(connector.resume)~='function' then
                partial(s,'NATIVE_LIFECYCLE_CONTROL_UNAVAILABLE')
                state(s,'configuring','NATIVE_LIFECYCLE_CONTROL_UNAVAILABLE')
                return true
            end
            local ok,why=control('configure',s,true)
            if not ok then partial(s,why);state(s,'configuring',why);return true end
            s.configured=true
            if not attach(s) then stop(s,now);return true end
            state(s,'active')
            if not drained then
                local count,reason=step(s,now)
                if count==nil then request_stop(s,'close',reason) end
            end
        end
        return true
    end
    return api
end
return M
