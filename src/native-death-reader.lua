-- Independent, bounded read-only Health attribution and contemporaneous roster.
-- Runtime 0.30.3 layouts; no third-party DeathSourceNotice code or native calls.
local b=require('hd2runtime/core/bytes')
local N=require('hd2runtime/domains/event_natives')
local H,WI,E,A,I=N.health,N.wielder,N.engine,N.playerAvatars,N.injury
local SHA='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
local U32=4294967296
local ROSTER,USER=0x347CED8,0x347CEF0
local PERSONA_COUNT,PERSONA_ROWS=0x16390,0x16398
local PINS={
    {0x4A441A,'4c8b156722e802'},
    {0x923C20,'49894738'}, {0x923C34,'45897930'},
    {0x924F3E,'894844'}, {0x924F48,'48894850'},
    {0x9270F2,'83bc019c01000002'},
}
-- Captured matching-build cause setter, SHA c58fc32a...a6365ec;
-- see docs/fire-gas-source-research-0.4.51.md. These are independent of
-- the public Runtime's maxHealth-only extFields declaration.
local CAUSE_PINS={
    {0x925E38,'f6411401'},{0x925E42,'488b8360100000'},
    {0x925E49,'486bfe1c'},{0x925E58,'448974070c'},
    {0x925E99,'89040f'},{0x925EC9,'89440f04'},
}
-- Independent Runtime research_event_combat.py: queue 0 is copied damage
-- requests, not an applied-hit/fatal callback. +0x10/+0x14 contain GOIDs.
local QUEUE_PINS={
    {0x129EF04,'4c8b052de01d02'},{0x129EF12,'3d00100000'},
    {0x129EF37,'486bc070'},{0x129EF43,'420f11840020110000'},
    {0x129EF8F,'41898020112000'},{0x12A6F17,'8b8120112000'},
    {0x12A6F51,'488db92c110000'},{0x12A6FA8,'4883c770'},
    {0x12A8205,'418b16'},{0x12A8241,'458b4e08'},
    {0x12A8245,'458b4604'},{0x12A82C4,'498b4618'},
    {0x12A82D1,'418b4614'},{0x12A82D9,'418b4610'},
    {0x12A81DC,'418b762c'},
}
local NETWORK_PINS={
    {0xFD9BA4,'4c8b1ded234902'},{0xFD9BB1,'81faff7f0000'},
    {0xFD9BC9,'458b93d02ef200'},{0xFD9BF9,'498bbbc82ef200'},
    {0xFD9C4C,'488d0440'},{0xFD9C50,'488d80e4651e00'},
}
local PERSONA_PIN={0x1819FDA,'4c8b0d0f2ec601418bc7418b91906301004d8b8198b3000085d2741d498d89986301000f1f004c39010f842f010000ffc04883c1203bc272ed'}
local function integer(v,max) return type(v)=='number' and v>=0 and v<=max and v%1==0 end
local function address(v) return integer(v,140737488355327) and v>=65536 end
local function peer(v)
    return type(v)=='string' and #v==16 and not v:find('[^%x]') and v~='0000000000000000' and v:upper() or nil
end
local function hex(raw,at) return string.format('%08X%08X',b.u32(raw,at+4),b.u32(raw,at)) end
local function pow2(n)
    if not integer(n,1048576) or n==0 then return false end
    while n>1 and n%2==0 do n=n/2 end
    return n==1
end
local function utf8_name(raw)
    local ending=raw:find('\0',1,true)
    if not ending or ending==1 then return nil end
    local value=raw:sub(1,ending-1)
    if value:find('[%z\1-\31\127]') then return nil end
    local i=1
    while i<=#value do
        local c=value:byte(i);local n=c<128 and 0 or c>=194 and c<=223 and 1 or c>=224 and c<=239 and 2
            or c>=240 and c<=244 and 3 or nil
        if not n or i+n>#value then return nil end
        for j=1,n do local d=value:byte(i+j);if d<128 or d>191 then return nil end end
        local second=value:byte(i+1)
        if n==2 and (c==224 and second<160 or c==237 and second>=160)
            or n==3 and (c==240 and second<144 or c==244 and second>=144) then return nil end
        i=i+n+1
    end
    return value
end
return function(options)
    options=options or {}
    local api={diagnostics={ready=false,reason='NOT_READ',reads=0,bytes=0,reads_peak=0,bytes_peak=0,
        max_reads=96,max_bytes=4096,soft_budget_ms=2}}
    local clock=options.clock or os.clock
    local d=api.diagnostics
    local world,started,proven_key,persona_key,cause_key,cause_ready,cause_reason,queue_key,network_key
    local queue_cursor=0
    local function get(at,size)
        if not address(at) or not integer(size,512) or size==0 or not address(at+size-1) then error('DEATH_READ_ADDRESS',0) end
        if d.reads>=96 or d.bytes+size>4096 then error('DEATH_READ_BUDGET',0) end
        if clock()-started>=.002 then error('DEATH_TIME_BUDGET',0) end
        d.reads,d.bytes=d.reads+1,d.bytes+size
        local raw=world.view.read(at,size)
        if type(raw)~='string' or #raw~=size then error('DEATH_READ_FAILED',0) end
        return raw
    end
    local function ptr(at)
        local raw=get(at,8);local value=b.u32(raw,0)+b.u32(raw,4)*U32
        if value==0 then return nil end
        if not address(value) or value%8~=0 then error('DEATH_POINTER',0) end
        return value
    end
    local function mul32(a,c)
        return (a*(c%65536)+((a*math.floor(c/65536))%65536)*65536)%U32
    end
    local function hash(at,key,max_index)
        local raw=get(at,20);local cap,empty,factor=b.u32(raw,8),b.u32(raw,12),b.u32(raw,16)
        local buckets=b.u32(raw,0)+b.u32(raw,4)*U32
        if not pow2(cap) or not address(buckets) then error('DEATH_HASH_HEADER',0) end
        for probe=0,math.min(cap,32)-1 do
            local row_at=buckets+((mul32(key,factor)+probe)%cap)*8
            local row=get(row_at,8);local found,index=b.u32(row,0),b.u32(row,4)
            if found==key or found==empty then
                if get(at,20)~=raw or get(row_at,8)~=row then error('DEATH_HASH_CHANGED',0) end
                if found==empty or index==U32-1 then return nil end
                if index>=max_index then error('DEATH_HASH_INDEX',0) end
                return index
            end
        end
        error('DEATH_HASH_PROBE_LIMIT',0)
    end
    local function owner_type(entity)
        if not integer(entity,U32-1) or entity==0 then return nil end
        local generations=ptr(world.exe+E.entities)
        local limit=generations and b.u32(get(generations+E.generationSize,4),0)
        local bytes=generations and ptr(generations+E.generations)
        if not limit or not bytes or entity%4194304>=limit then return nil end
        local generation=get(bytes+entity%4194304,1):byte()
        if generation~=math.floor(entity/4194304)%256 then return nil end
        local manager=ptr(world.game+WI.entities)
        local index=manager and hash(manager+WI.entityMap,entity,1048576)
        if not index then return nil end
        local at=manager+WI.descriptors+index*WI.descriptorStride
        local raw=get(at,WI.descriptorStride)
        if b.u32(raw,WI.descriptorEntity)~=entity or get(at,WI.descriptorStride)~=raw then return nil end
        if ptr(world.game+WI.entities)~=manager then error('DEATH_OWNER_CHANGED',0) end
        return hex(raw,0)
    end
    local function network_source(goid)
        if not integer(goid,U32-1) or goid==32767 or goid==U32-1 then return nil end
        local manager=ptr(world.game+A.entities)
        local index=manager and hash(manager+A.mapSlots,goid,1048576)
        if not index then return nil end
        -- entityBase points at descriptor.entity, eight bytes after its type.
        local at=manager+A.entityBase-8+index*A.entityStride
        local raw=get(at,WI.descriptorStride)
        local entity=b.u32(raw,WI.descriptorEntity)
        if b.u32(raw,16)~=goid or get(at,WI.descriptorStride)~=raw
            or ptr(world.game+A.entities)~=manager then error('DEATH_NETWORK_CHANGED',0) end
        -- The entity map independently checks the complete generation, same
        -- descriptor identity and resource type; a GOID is never used as an ID.
        local kind=owner_type(entity)
        if kind~=hex(raw,0) then return nil end
        return entity,kind
    end
    local function unit_position(unit)
        -- Reviewed Runtime engine identity chain, not a guessed Transform row.
        if not integer(unit,U32-1) or unit==0 or E.sceneGraphOffset~=96 or E.poses~=40 or E.translation~=48 then return nil end
        local registry=ptr(world.exe+E.units)
        local count=registry and b.u32(get(registry+E.unitCount,4),0)
        local generations=registry and ptr(registry+E.unitGenerations)
        local objects=registry and ptr(registry+E.unitObjects)
        local index,generation=unit%4194304,math.floor(unit/4194304)%256
        if not count or count>1048576 or not generations or not objects or index>=count then return nil end
        if get(generations+index,1):byte()~=generation then return nil end
        local object=ptr(objects+index*8)
        if not object or b.u32(get(object+E.unitId,4),0)~=unit then return nil end
        local vtable=ptr(object);local method=vtable and ptr(vtable+0xE8)
        if method~=world.exe+E.sceneGraphMethod or get(method,#E.sceneGraphMethodBytes/2)~=b.unhex(E.sceneGraphMethodBytes)then return nil end
        local poses=ptr(object+E.sceneGraphOffset+E.poses)
        if not poses then return nil end
        local raw=get(poses+E.translation,12)
        local result={x=b.value(raw,0,'f32'),y=b.value(raw,4,'f32'),z=b.value(raw,8,'f32')}
        for _,value in pairs(result)do if value~=value or math.abs(value)>100000 then return nil end end
        if get(generations+index,1):byte()~=generation or ptr(objects+index*8)~=object
            or b.u32(get(object+E.unitId,4),0)~=unit or ptr(object+E.sceneGraphOffset+E.poses)~=poses
            or ptr(world.exe+E.units)~=registry then return nil end
        return result
    end
    local function run(current,work)
        d.ready,d.reads,d.bytes=false,0,0
        if N.source.gameDllSha256~=SHA or H.stride~=440 or H.record.lastOwner~=48
            or H.record.lastCreditor~=56 or H.record.life~=412 then
            d.reason='DEATH_BUILD_PROFILE';return nil,d.reason
        end
        if type(current)~='table' or not address(current.game) or not address(current.exe)
            or type(current.view)~='table' or type(current.view.read)~='function' then
            d.reason='DEATH_WORLD_UNAVAILABLE';return nil,d.reason
        end
        world,started=current,clock()
        local key=tostring(world.game)..':'..tostring(world.exe)..':'..tostring(world.view)..':'..tostring(world.view.read)
        local ok,result=pcall(function()
            if proven_key~=key then
                for _,pin in ipairs(PINS) do if get(world.game+pin[1],#pin[2]/2)~=b.unhex(pin[2]) then error('DEATH_CODE_PIN',0) end end
                proven_key=key
            end
            return work(key)
        end)
        d.reads_peak,d.bytes_peak=math.max(d.reads_peak,d.reads),math.max(d.bytes_peak,d.bytes)
        d.elapsed_ms=math.max(0,(clock()-started)*1000)
        if not ok then d.reason=tostring(result);return nil,d.reason end
        d.ready,d.reason=true,nil;return result
    end
    function api:reset()
        proven_key,persona_key,cause_key,queue_key,network_key=nil,nil,nil,nil,nil
        queue_cursor=0;d.ready=false
    end
    function api:damage_events(current,avatar)
        d.queue_scanned,d.queue_events=0,0
        if not integer(avatar,U32-1) or avatar==0 then d.reason='DEATH_AVATAR_UNAVAILABLE';return nil,d.reason end
        return run(current,function(key)
            if I.system~=0x347CF38 or I.count~=0x201120 or I.capacity~=4096
                or A.entities~=WI.entities or A.mapSlots~=0xF22EC8
                or A.entityBase~=0xF32F20 or A.entityStride~=24 then error('DEATH_QUEUE_PROFILE',0) end
            if queue_key~=key then
                for _,pin in ipairs(QUEUE_PINS)do
                    if get(world.game+pin[1],#pin[2]/2)~=b.unhex(pin[2])then error('DEATH_QUEUE_CODE_PIN',0)end
                end
                queue_key=key
            end
            local system=ptr(world.game+I.system)
            if not system then error('DEATH_QUEUE_UNAVAILABLE',0)end
            local count_raw=get(system+I.count,4);local count=b.u32(count_raw,0)
            if count>I.capacity then error('DEATH_QUEUE_CAPACITY',0)end
            local out={events={},queue_count=count,scanned=0,token='',source='native_damage_queue'}
            if count==0 then queue_cursor=0;return out end
            local selected={}
            local function inspect(raw,index)
                out.scanned=out.scanned+1
                local kind,element,amount=b.u32(raw,4),b.u32(raw,8),b.u32(raw,44)
                if b.u32(raw,0)==avatar and kind<=9 and amount>0 then
                    selected[#selected+1]={raw=raw,index=index,kind=kind,element=element,damage=amount}
                end
            end
            -- Observe the front that the game drains first, plus a rolling
            -- window when the queue is busy. No unbounded 4096-row scan/frame.
            local front=math.min(count,16)
            for start=0,front-1,4 do
                local length=math.min(4,front-start)
                local raw=get(system+0x1120+start*112,length*112)
                for offset=0,length-1 do inspect(raw:sub(offset*112+1,(offset+1)*112),start+offset)end
            end
            if count>16 then
                local remaining=count-16
                for offset=0,math.min(8,remaining)-1 do
                    local index=16+(queue_cursor+offset)%remaining
                    inspect(get(system+0x1120+index*112,112),index)
                end
                queue_cursor=(queue_cursor+8)%remaining
            else queue_cursor=0 end
            table.sort(selected,function(a,c)return a.index<c.index end)
            while #selected>4 do table.remove(selected,1)end
            -- Recheck only retained local rows and the queue identity/count.
            -- A compaction or concurrent rewrite rejects this snapshot.
            for _,row in ipairs(selected)do
                if get(system+0x1120+row.index*112,112)~=row.raw then error('DEATH_QUEUE_CHANGED',0)end
            end
            if get(system+I.count,4)~=count_raw or ptr(world.game+I.system)~=system then error('DEATH_QUEUE_CHANGED',0)end
            local tokens={}
            for _,row in ipairs(selected)do
                local raw=row.raw
                local item={target=avatar,kind=row.kind,element=row.element,damage=row.damage,
                    dealer_goid=b.u32(raw,16),owner_goid=b.u32(raw,20),creditor=peer(hex(raw,24)),
                    token=raw,source='native_damage_queue',native_fatal_event_proven=false}
                out.events[#out.events+1]=item;tokens[#tokens+1]=raw
            end
            out.token=table.concat(tokens)
            -- Resource enrichment is optional: budget/removed entities must
            -- not discard an already stable explosion/fall/element request.
            local ok,why=pcall(function()
                if #out.events==0 then return end
                if network_key~=key then
                    for _,pin in ipairs(NETWORK_PINS)do
                        if get(world.game+pin[1],#pin[2]/2)~=b.unhex(pin[2])then error('DEATH_NETWORK_CODE_PIN',0)end
                    end
                    network_key=key
                end
                local known={}
                for index=#out.events,1,-1 do
                    local row=out.events[index]
                    for _,prefix in ipairs({'dealer','owner'})do
                        local goid=row[prefix..'_goid'];local value=known[goid]
                        if value==nil then
                            local entity,kind=network_source(goid)
                            value=entity and {entity,kind}or false;known[goid]=value
                        end
                        if value then row[prefix..'_entity'],row[prefix..'_type']=value[1],value[2]end
                    end
                end
            end)
            if not ok then out.source_reason=tostring(why)end
            d.queue_scanned=out.scanned;d.queue_events=#out.events
            return out
        end)
    end
    function api:read(current,avatar)
        if not integer(avatar,U32-1) or avatar==0 then d.reason='DEATH_AVATAR_UNAVAILABLE';return nil,d.reason end
        return run(current,function(key)
            local manager=ptr(world.game+H.global)
            if not manager then error('DEATH_HEALTH_UNAVAILABLE',0) end
            local header=get(manager+H.header,H.headerSize)
            local live,cap=b.u32(header,H.live-H.header),b.u32(header,H.capacity-H.header)
            local hash_cap=b.u32(header,H.hashCapacity-H.header)
            if cap==0 or cap>H.maxRecords or live>cap or not pow2(hash_cap) or hash_cap>16384 then error('DEATH_HEALTH_CAPACITY',0) end
            local index=hash(manager+H.buckets,avatar,live)
            if not index then error('DEATH_AVATAR_UNMAPPED',0) end
            local descriptors,records=ptr(manager+H.descriptors),ptr(manager+H.records)
            local descriptor=descriptors and ptr(descriptors+index*8)
            if not descriptor or not records then error('DEATH_HEALTH_UNAVAILABLE',0) end
            local who=get(descriptor,H.descriptor.size)
            if b.u32(who,H.descriptor.entity)~=avatar then error('DEATH_DESCRIPTOR_IDENTITY',0) end
            local row=records+index*H.stride
            local raw=get(row,H.stride)
            local R=H.record
            local out={avatar_id=avatar,victim_type=hex(who,0),life=b.u32(raw,R.life),
                health=b.value(raw,R.health,'i32'),last_owner=b.u32(raw,R.lastOwner),last_creditor=hex(raw,R.lastCreditor),
                down_owner=b.u32(raw,R.downOwner),down_creditor=hex(raw,R.downCreditor),
                native_fatal_event_proven=false,source='native_health_last_owner_creditor'}
            if out.life==2 and b.u32(who,H.descriptor.flags)%2==1 and H.extStride==28 and H.extArray==0x1060 then
                -- Optional cause enrichment may fail without losing the
                -- already usable owner/creditor snapshot.
                local ok,cause=pcall(function()
                    if cause_key~=key then
                        cause_key,cause_ready,cause_reason=key,false,nil
                        for _,pin in ipairs(CAUSE_PINS)do
                            if get(world.game+pin[1],#pin[2]/2)~=b.unhex(pin[2])then
                                cause_reason='DEATH_CAUSE_CODE_PIN';return nil
                            end
                        end
                        cause_ready=true
                    end
                    if not cause_ready then return nil end
                    local ext=ptr(manager+H.extArray)
                    if not ext then cause_reason='DEATH_CAUSE_EXT_UNAVAILABLE';return nil end
                    local at=ext+index*H.extStride
                    local value=get(at,H.extStride)
                    if value~=get(at,H.extStride)then cause_reason='DEATH_CAUSE_CHANGED';return nil end
                    if b.u32(value,12)~=out.life then cause_reason='DEATH_CAUSE_LIFE_MISMATCH';return nil end
                    return {kind=b.u32(value,0),element=b.u32(value,4),life=b.u32(value,12)}
                end)
                if ok and cause then
                    out.damage_cause={kind=cause.kind,element=cause.element,life=cause.life,
                        owned=true,current=true,source='native_health_extension'}
                    cause_reason=nil
                elseif not ok then cause_reason=tostring(cause) end
                out.cause_reason=cause_reason
            end
            local final=get(row,H.stride)
            for _,field in ipairs({'life','health','lastOwner','lastCreditor','downOwner','downCreditor'}) do
                local offset=R[field];local size=field:find('Creditor') and 8 or 4
                if raw:sub(offset+1,offset+size)~=final:sub(offset+1,offset+size) then error('DEATH_HEALTH_CHANGED',0) end
            end
            if get(descriptor,H.descriptor.size)~=who or ptr(descriptors+index*8)~=descriptor
                or get(manager+H.header,H.headerSize)~=header or ptr(world.game+H.global)~=manager then
                error('DEATH_HEALTH_CHANGED',0)
            end
            -- A destroyed source or long entity-map probe cannot erase the
            -- already stable victim/cause fields. Actor names are enrichment.
            local ok,why=pcall(function()
                out.last_owner_type=owner_type(out.last_owner)
                if out.down_owner~=out.last_owner then out.down_owner_type=owner_type(out.down_owner)
                else out.down_owner_type=out.last_owner_type end
            end)
            if not ok then out.owner_reason=tostring(why)end
            local ok,position=pcall(unit_position,b.u32(who,H.descriptor.unit))
            if ok then out.position=position else out.position_reason=tostring(position)end
            return out
        end)
    end
    function api:players(current,list)
        if type(list)~='table' or #list>4 then d.reason='DEATH_PLAYER_LIST';return nil,d.reason end
        return run(current,function(key)
            if persona_key~=key then
                if get(world.game+PERSONA_PIN[1],#PERSONA_PIN[2]/2)~=b.unhex(PERSONA_PIN[2]) then error('DEATH_PERSONA_PIN',0) end
                persona_key=key
            end
            local roster,user=ptr(world.game+ROSTER),ptr(world.game+USER)
            if not roster or not user then error('DEATH_ROSTER_UNAVAILABLE',0) end
            local raw,by_peer={},{}
            for i=0,3 do
                raw[i+1]=get(roster+i*0xC0,72)
                local who=peer(hex(raw[i+1],0))
                if who then
                    if by_peer[who] then error('DEATH_DUPLICATE_ROSTER_PEER',0) end
                    by_peer[who]={name=utf8_name(raw[i+1]:sub(9)),peer_id=who}
                end
            end
            local count_raw=get(user+PERSONA_COUNT,4);local count=b.u32(count_raw,0)
            if count>4 then error('DEATH_PERSONA_COUNT',0) end
            local persona=count>0 and get(user+PERSONA_ROWS,count*32) or ''
            local persona_seen={}
            for i=0,count-1 do
                local who=peer(hex(persona,i*32));local index=b.u32(persona,i*32+20)
                if who and by_peer[who] and index<4 then
                    if persona_seen[who] then error('DEATH_DUPLICATE_PERSONA_PEER',0) end
                    persona_seen[who]=true;by_peer[who].persona_index=index
                end
            end
            local out,seen={},{}
            for _,player in ipairs(list) do
                local who=peer(player.peer or player.peer_id)
                if who then
                    if seen[who] then error('DEATH_DUPLICATE_PLAYER_PEER',0) end
                    seen[who]=true
                    local row=by_peer[who] or {peer_id=who}
                    row.slot_index=integer(player.slot,3) and player.slot or nil
                    row.slot=row.slot_index and row.slot_index+1 or nil
                    row.avatar_id=integer(player.avatar,U32-1) and player.avatar or nil
                    row.local_player=player['local']==true
                    row.identity_scope='session_peer_not_permanent_account'
                    row.identity_source='contemporaneous_native_roster'
                    out[#out+1]=row
                end
            end
            for i=0,3 do if get(roster+i*0xC0,72)~=raw[i+1] then error('DEATH_ROSTER_CHANGED',0) end end
            if get(user+PERSONA_COUNT,4)~=count_raw or count>0 and get(user+PERSONA_ROWS,count*32)~=persona
                or ptr(world.game+ROSTER)~=roster or ptr(world.game+USER)~=user then error('DEATH_ROSTER_CHANGED',0) end
            return out
        end)
    end
    return api
end
