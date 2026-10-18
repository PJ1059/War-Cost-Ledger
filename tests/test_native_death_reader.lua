-- Fixed owned memory only, actual Runtime domain and byte decoding; no game IO.
local source,runtime=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,1,function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua')) end
end)
local b=require('hd2runtime/core/bytes');local N=require('hd2runtime/domains/event_natives')
local create=dofile(source);local H,WI,E,A,I=N.health,N.wielder,N.engine,N.playerAvatars,N.injury
local U32=4294967296
local function u32(n)return b.encode(n,'u32')end
local function ptr(n)return u32(n%U32)..u32(math.floor(n/U32))end
local function type_bytes(v)return b.unhex(v):reverse()end
local AVATAR,OWNER=0x400011,0x400012
local VICTIM_TYPE,ENEMY_TYPE='4D1C334D294DFA97','0123456789ABCDEF'
local LOCAL,OTHER='0123456789ABCDEF','FEDCBA9876543210'
local PERSONA_PIN='4c8b0d0f2ec601418bc7418b91906301004d8b8198b3000085d2741d498d89986301000f1f004c39010f842f010000ffc04883c1203bc272ed'
local function memory()
    local m={data={},reads=0,bytes=0,writes=0,game=0x180000000,exe=0x140000000,next=0x300000000}
    function m:put(at,raw)for i=1,#raw do self.data[at+i-1]=raw:byte(i)end end
    function m:alloc()self.next=self.next+0x10000;return self.next end
    function m:hash(at,key,index,cap)
        cap=cap or 16;local buckets=self:alloc()
        self:put(at,ptr(buckets)..u32(cap)..u32(U32-1)..u32(1));self:put(buckets,string.rep('\255',cap*8))
        self:put(buckets+key%cap*8,u32(key)..u32(index));return buckets
    end
    m.manager,m.records,m.descriptors,m.descriptor=m:alloc(),m:alloc(),m:alloc(),m:alloc()
    m:put(m.game+H.global,ptr(m.manager));m:put(m.manager+H.header,string.rep('\0',H.headerSize))
    m:put(m.manager+H.capacity,u32(16));m:put(m.manager+H.live,u32(1))
    m:hash(m.manager+H.buckets,AVATAR,0)
    m:put(m.manager+H.descriptors,ptr(m.descriptors));m:put(m.manager+H.records,ptr(m.records))
    m:put(m.descriptors,ptr(m.descriptor))
    m:put(m.descriptor,type_bytes(VICTIM_TYPE)..u32(AVATAR)..u32(9)..u32(10)..u32(1))
    function m:health(life,owner,creditor)
        self:put(self.records,string.rep('\0',H.stride));self:put(self.records+H.record.life,u32(life))
        self:put(self.records+H.record.health,b.encode(life>=2 and 0 or 80,'i32'))
        self:put(self.records+H.record.lastOwner,u32(owner or OWNER))
        self:put(self.records+H.record.lastCreditor,type_bytes(creditor or OTHER))
    end
    m:health(2)
    function m:cause(kind,element,life,owned)
        self.ext=self.ext or self:alloc()
        self:put(self.manager+H.extArray,ptr(self.ext))
        self:put(self.ext,string.rep('\0',H.extStride))
        self:put(self.ext,u32(kind));self:put(self.ext+4,u32(element));self:put(self.ext+12,u32(life))
        self:put(self.descriptor+H.descriptor.flags,u32(owned==false and 0 or 1))
        for _,pin in ipairs({{0x925E38,'f6411401'},{0x925E42,'488b8360100000'},
            {0x925E49,'486bfe1c'},{0x925E58,'448974070c'},
            {0x925E99,'89040f'},{0x925EC9,'89440f04'}})do self:put(self.game+pin[1],b.unhex(pin[2]))end
    end
    function m:queue(rows,count)
        self.damage_system=self.damage_system or self:alloc()
        self:put(self.game+I.system,ptr(self.damage_system))
        count=count or #rows;self:put(self.damage_system+I.count,u32(count))
        for index,row in ipairs(rows)do
            local raw=string.rep('\0',112);local at=self.damage_system+0x1120+(index-1)*112
            self:put(at,raw);self:put(at,u32(row.target or AVATAR))
            self:put(at+4,u32(row.kind or 4));self:put(at+8,u32(row.element or 0))
            self:put(at+16,u32(row.dealer or 19));self:put(at+20,u32(row.owner or 18))
            self:put(at+24,type_bytes(row.creditor or LOCAL));self:put(at+32,u32(row.key or 650))
            self:put(at+44,u32(row.damage==nil and 100 or row.damage))
        end
        for _,pin in ipairs({
            {0x129EF04,'4c8b052de01d02'},{0x129EF12,'3d00100000'},
            {0x129EF37,'486bc070'},{0x129EF43,'420f11840020110000'},
            {0x129EF8F,'41898020112000'},{0x12A6F17,'8b8120112000'},
            {0x12A6F51,'488db92c110000'},{0x12A6FA8,'4883c770'},
            {0x12A8205,'418b16'},{0x12A8241,'458b4e08'},
            {0x12A8245,'458b4604'},{0x12A82C4,'498b4618'},
            {0x12A82D1,'418b4614'},{0x12A82D9,'418b4610'},
            {0x12A81DC,'418b762c'},
            {0xFD9BA4,'4c8b1ded234902'},{0xFD9BB1,'81faff7f0000'},
            {0xFD9BC9,'458b93d02ef200'},{0xFD9BF9,'498bbbc82ef200'},
            {0xFD9C4C,'488d0440'},{0xFD9C50,'488d80e4651e00'},
        })do self:put(self.game+pin[1],b.unhex(pin[2]))end
    end
    m.generations,m.generation_bytes,m.entities=m:alloc(),m:alloc(),m:alloc()
    m:put(m.exe+E.entities,ptr(m.generations));m:put(m.generations+E.generationSize,u32(32))
    m:put(m.generations+E.generations,ptr(m.generation_bytes));m:put(m.generation_bytes,string.rep('\1',32))
    m:put(m.game+WI.entities,ptr(m.entities));m:hash(m.entities+WI.entityMap,OWNER,0)
    m:put(m.entities+WI.descriptors,type_bytes(ENEMY_TYPE)..u32(OWNER)..u32(11)..u32(12)..u32(0))
    m.network_buckets=m:hash(m.entities+A.mapSlots,18,0)
    function m:network(goid,entity,kind,index)
        self:put(self.network_buckets+goid%16*8,u32(goid)..u32(index))
        local header=self.entities+WI.entityMap
        local data=self.data;local raw={};for offset=0,7 do raw[#raw+1]=string.char(data[header+offset])end
        local buckets=b.u32(table.concat(raw),0)+b.u32(table.concat(raw),4)*U32
        self:put(buckets+entity%16*8,u32(entity)..u32(index))
        self:put(self.entities+WI.descriptors+index*WI.descriptorStride,
            type_bytes(kind)..u32(entity)..u32(11)..u32(goid)..u32(0))
    end
    function m:position(x,y,z)
        self.units,self.unit_generations,self.unit_objects=self:alloc(),self:alloc(),self:alloc()
        self.unit_object,self.unit_vtable,self.unit_poses=self:alloc(),self:alloc(),self:alloc()
        self:put(self.exe+E.units,ptr(self.units));self:put(self.units+E.unitCount,u32(32))
        self:put(self.units+E.unitGenerations,ptr(self.unit_generations))
        self:put(self.units+E.unitObjects,ptr(self.unit_objects))
        self:put(self.unit_generations,string.rep('\0',32));self:put(self.unit_objects+9*8,ptr(self.unit_object))
        self:put(self.unit_object,ptr(self.unit_vtable));self:put(self.unit_object+E.unitId,u32(9))
        self:put(self.unit_vtable+0xE8,ptr(self.exe+E.sceneGraphMethod))
        self:put(self.exe+E.sceneGraphMethod,b.unhex(E.sceneGraphMethodBytes))
        self:put(self.unit_object+E.sceneGraphOffset+E.poses,ptr(self.unit_poses))
        self:put(self.unit_poses+E.translation,b.encode(x,'f32')..b.encode(y,'f32')..b.encode(z,'f32'))
    end
    for _,pin in ipairs(N.pins)do if pin.module=='game'then m:put(m.game+pin.rva,b.unhex(pin.hex))end end
    m:put(m.game+0x1819FDA,b.unhex(PERSONA_PIN))
    m.roster,m.user=m:alloc(),m:alloc()
    m:put(m.game+0x347CED8,ptr(m.roster));m:put(m.game+0x347CEF0,ptr(m.user))
    for i=0,3 do m:put(m.roster+i*0xC0,string.rep('\0',72))end
    local function name(peer,label)return type_bytes(peer)..label..string.rep('\0',64-#label)end
    m:put(m.roster,name(LOCAL,'本人'));m:put(m.roster+0xC0,name(OTHER,'队友甲'))
    m:put(m.user+0x16390,u32(2))
    m:put(m.user+0x16398,type_bytes(LOCAL)..string.rep('\0',12)..u32(2)..string.rep('\0',8)
        ..type_bytes(OTHER)..string.rep('\0',12)..u32(0)..string.rep('\0',8))
    local view={}
    function view.read(at,size)
        m.reads,m.bytes=m.reads+1,m.bytes+size
        if m.fault then local v=m.fault(at,size);if v~=nil then return v~=false and v or nil end end
        local out={};for i=0,size-1 do if m.data[at+i]==nil then return nil end;out[#out+1]=string.char(m.data[at+i])end
        return table.concat(out)
    end
    function view.write()m.writes=m.writes+1;error('write attempted')end
    m.world={game=m.game,exe=m.exe,view=view};m.reader=create({clock=function()return 0 end})
    m.players={{peer=LOCAL,avatar=AVATAR,slot=0,['local']=true},{peer=OTHER,avatar=OWNER,slot=1,['local']=false}}
    return m
end
local cases=0
local function check(fn)fn();cases=cases+1 end
check(function()
    local m=memory();local out,why=m.reader:read(m.world,AVATAR);assert(out,why)
    assert(out.life==2 and out.health==0 and out.last_owner==OWNER and out.last_creditor==OTHER)
    assert(out.victim_type==VICTIM_TYPE and out.last_owner_type==ENEMY_TYPE and not out.native_fatal_event_proven)
    assert(m.reader.diagnostics.reads<=96 and m.reader.diagnostics.bytes<=4096 and m.writes==0)
    print('native death Health: '..m.reader.diagnostics.reads..' reads / '..m.reader.diagnostics.bytes..' bytes')
end)
check(function()
    local m=memory();local out,why=m.reader:players(m.world,m.players);assert(out,why)
    assert(out[1].name=='本人' and out[1].persona_index==2 and out[1].slot==1 and out[1].slot_index==0)
    assert(out[2].name=='队友甲' and out[2].persona_index==0 and out[2].slot==2 and out[2].slot_index==1)
    assert(out[2].peer_id==OTHER and not out[2].callsign and not out[2].steam_id and not out[2].psn_id)
    assert(m.reader.diagnostics.bytes<=4096 and m.writes==0)
    print('native death roster: '..m.reader.diagnostics.reads..' reads / '..m.reader.diagnostics.bytes..' bytes')
    m.players[1].slot,m.players[2].slot=1,0
    out=assert(m.reader:players(m.world,m.players));assert(out[2].name=='队友甲' and out[2].persona_index==0 and out[2].slot==1 and out[2].slot_index==0)
end)
check(function()
    local m=memory();m:put(m.descriptor+H.descriptor.entity,u32(AVATAR+1))
    assert(select(2,m.reader:read(m.world,AVATAR))=='DEATH_DESCRIPTOR_IDENTITY')
end)
check(function()
    local m=memory();m:put(m.game+0x923C20,string.rep('\0',4))
    assert(select(2,m.reader:read(m.world,AVATAR))=='DEATH_CODE_PIN')
end)
check(function()
    local m=memory();local n=0
    m.fault=function(at,size)if at==m.records and size==H.stride then n=n+1;if n==2 then m:health(2,OWNER,LOCAL)end end end
    assert(select(2,m.reader:read(m.world,AVATAR))=='DEATH_HEALTH_CHANGED')
end)
check(function()
    local m=memory();local n=0
    m.fault=function(at)if at==m.roster+0xC0 then n=n+1;if n==2 then m:put(m.roster+0xC0,type_bytes(OTHER)..'换名'..string.rep('\0',58))end end end
    assert(select(2,m.reader:players(m.world,m.players))=='DEATH_ROSTER_CHANGED')
end)
check(function()
    local m=memory();m:put(m.manager+H.hashCapacity,u32(32768))
    assert(select(2,m.reader:read(m.world,AVATAR))=='DEATH_HEALTH_CAPACITY')
end)
check(function()
    local m=memory();m:put(m.generation_bytes+OWNER%4194304,'\2')
    local out=assert(m.reader:read(m.world,AVATAR));assert(not out.last_owner_type and out.last_creditor==OTHER)
end)
check(function()
    local m=memory();m:put(m.roster+8,'\255'..string.rep('\0',63))
    local out=assert(m.reader:players(m.world,m.players));assert(not out[1].name and out[2].name=='队友甲')
end)
check(function()
    local m=memory();local now=0
    m.reader=create({clock=function()now=now+.0011;return now end})
    assert(select(2,m.reader:read(m.world,AVATAR))=='DEATH_TIME_BUDGET')
end)
check(function()
    for _,element in ipairs({1,5})do
        local m=memory();m:cause(2,element,2)
        local out=assert(m.reader:read(m.world,AVATAR));local cause=assert(out.damage_cause)
        assert(cause.kind==2 and cause.element==element and cause.life==2 and cause.owned and cause.current)
        assert(cause.source=='native_health_extension' and not out.native_fatal_event_proven)
        assert(m.reader.diagnostics.reads<=96 and m.reader.diagnostics.bytes<=4096 and m.writes==0)
    end
end)
check(function()
    for _,case in ipairs({{1,2,true},{2,1,true},{2,2,false}})do
        local m=memory();m:health(case[1]);m:cause(2,1,case[2],case[3])
        local out=assert(m.reader:read(m.world,AVATAR));assert(not out.damage_cause)
    end
end)
check(function()
    local m=memory();m:cause(2,1,2);m:put(m.game+0x925EC9,string.rep('\0',4))
    local out=assert(m.reader:read(m.world,AVATAR));assert(not out.damage_cause and out.cause_reason=='DEATH_CAUSE_CODE_PIN')
    assert(out.last_creditor==OTHER,'optional cause failure cannot discard known owner/creditor')
end)
check(function()
    local m=memory();m:cause(2,1,2);local n=0
    m.fault=function(at)if at==m.ext then n=n+1;if n==2 then m:put(m.ext+4,u32(5))end end end
    local out=assert(m.reader:read(m.world,AVATAR));assert(not out.damage_cause and out.cause_reason=='DEATH_CAUSE_CHANGED')
end)
check(function()
    local m=memory();m:queue({{kind=5,dealer=18}});m:network(18,OWNER,ENEMY_TYPE,0)
    local out,why=m.reader:damage_events(m.world,AVATAR);assert(out,why)
    assert(out.queue_count==1 and out.scanned==1 and #out.events==1)
    local row=out.events[1];assert(row.target==AVATAR and row.kind==5 and row.damage==100 and row.creditor==LOCAL)
    assert(row.dealer_goid==18 and row.dealer_entity==OWNER and row.owner_entity==OWNER)
    assert(row.dealer_type==ENEMY_TYPE and #row.token==112 and out.token==row.token)
    assert(not row.damage_info_id and not row.projectile_id and not row.native_fatal_event_proven)
    assert(m.reader.diagnostics.reads<=96 and m.reader.diagnostics.bytes<=4096 and m.writes==0)
    print('native death queue: '..m.reader.diagnostics.reads..' reads / '..m.reader.diagnostics.bytes..' bytes')
end)
check(function()
    local m=memory();local weapon=0x400013;local weapon_type='AABBCCDDEEFF0011'
    m:queue({{kind=4}});m:network(18,AVATAR,VICTIM_TYPE,1);m:network(19,weapon,weapon_type,2)
    local out=assert(m.reader:damage_events(m.world,AVATAR));local row=assert(out.events[1])
    assert(row.kind==4 and row.dealer_entity==weapon and row.dealer_type==weapon_type)
    assert(row.owner_entity==AVATAR and row.owner_type==VICTIM_TYPE,'GOIDs must resolve independently of full entity IDs')
end)
check(function()
    local m=memory();m:queue({{target=OWNER},{kind=2,element=5,dealer=32767,owner=32767}})
    local out=assert(m.reader:damage_events(m.world,AVATAR));assert(#out.events==1 and out.events[1].element==5)
    assert(not out.events[1].dealer_entity and not out.events[1].owner_entity)
end)
check(function()
    local m=memory();m:queue({{kind=4,dealer=18}});m:network(18,OWNER,ENEMY_TYPE,0)
    m:put(m.generation_bytes+OWNER%4194304,'\2')
    local out=assert(m.reader:damage_events(m.world,AVATAR));assert(#out.events==1 and not out.events[1].dealer_entity)
end)
check(function()
    local m=memory();m:queue({{}});m:put(m.game+0x129EF43,string.rep('\0',9))
    assert(select(2,m.reader:damage_events(m.world,AVATAR))=='DEATH_QUEUE_CODE_PIN')
end)
check(function()
    local m=memory();m:queue({{kind=8}});m:put(m.game+0xFD9BA4,string.rep('\0',7))
    local out=assert(m.reader:damage_events(m.world,AVATAR));assert(out.events[1].kind==8 and out.source_reason=='DEATH_NETWORK_CODE_PIN')
end)
check(function()
    local m=memory();m:queue({{}});local count=0
    m.fault=function(at)if at==m.damage_system+I.count then count=count+1;if count==2 then m:put(at,u32(0))end end end
    assert(select(2,m.reader:damage_events(m.world,AVATAR))=='DEATH_QUEUE_CHANGED')
end)
check(function()
    local m=memory();m:queue({{}});local count=0
    m.fault=function(at)if at==m.damage_system+0x1120 then count=count+1;if count==2 then m:put(at+4,u32(8))end end end
    assert(select(2,m.reader:damage_events(m.world,AVATAR))=='DEATH_QUEUE_CHANGED')
end)
check(function()
    local m=memory();local rows={};for index=1,48 do rows[index]={target=OWNER}end
    rows[41]={kind=9,dealer=32767,owner=32767};m:queue(rows)
    for index=1,3 do local out=assert(m.reader:damage_events(m.world,AVATAR));assert(out.scanned==24 and #out.events==0)end
    local out=assert(m.reader:damage_events(m.world,AVATAR));assert(out.scanned==24 and out.events[1].kind==9)
    assert(m.reader.diagnostics.reads<=96 and m.reader.diagnostics.bytes<=4096)
end)
check(function()
    local m=memory();local rows={};for index=1,24 do rows[index]={kind=4,damage=index,dealer=32767,owner=32767}end
    m:queue(rows);local out=assert(m.reader:damage_events(m.world,AVATAR));assert(out.scanned==24 and #out.events==4)
    assert(out.events[1].damage==21 and out.events[4].damage==24 and #out.token==448)
    assert(m.reader.diagnostics.bytes<=4096)
end)
check(function()
    local m=memory();m:queue({{kind=10},{damage=0},{kind=9,dealer=32767,owner=32767}})
    local out=assert(m.reader:damage_events(m.world,AVATAR));assert(#out.events==1 and out.events[1].kind==9)
    m:queue({});out=assert(m.reader:damage_events(m.world,AVATAR));assert(out.queue_count==0 and #out.events==0 and out.token=='')
end)
check(function()
    local m=memory();m:queue({},4097)
    assert(select(2,m.reader:damage_events(m.world,AVATAR))=='DEATH_QUEUE_CAPACITY')
end)
check(function()
    local m=memory();m:position(12.5,-42,1.25);m:cause(4,0,2)
    local out,why=m.reader:read(m.world,AVATAR);assert(out,why)
    assert(out.position.x==12.5 and out.position.y==-42 and out.position.z==1.25)
    assert(out.damage_cause.kind==4 and m.reader.diagnostics.bytes<=4096 and m.reader.diagnostics.reads<=96)
end)
check(function()
    for _,fault in ipairs({'generation','identity','method','invalid_position'})do
        local m=memory();m:position(1,2,3)
        if fault=='generation'then m:put(m.unit_generations+9,'\1')
        elseif fault=='identity'then m:put(m.unit_object+E.unitId,u32(10))
        elseif fault=='method'then m:put(m.exe+E.sceneGraphMethod,string.rep('\0',5))
        else m:put(m.unit_poses+E.translation,b.encode(100001,'f32'))end
        local out=assert(m.reader:read(m.world,AVATAR));assert(not out.position and out.last_creditor==OTHER)
    end
end)
check(function()
    local m=memory();m:queue({{kind=4}});local clock=0
    m.reader=create({clock=function()return clock end})
    m.fault=function(at)if at==m.game+0xFD9BA4 then clock=.003 end end
    local out=assert(m.reader:damage_events(m.world,AVATAR))
    assert(out.events[1].kind==4 and out.source_reason=='DEATH_TIME_BUDGET','optional enrichment budget cannot erase the stable mechanism')
end)
check(function()
    local m=memory();m:cause(4,0,2)
    m.fault=function(at)if at==m.game+WI.entities then return false end end
    local out=assert(m.reader:read(m.world,AVATAR))
    assert(out.damage_cause.kind==4 and out.last_owner==OWNER and not out.last_owner_type)
    assert(out.owner_reason=='DEATH_READ_FAILED','an unavailable actor type cannot discard the persisted cause')
end)
print('PASS: '..cases..' native death owned-memory tests; actual Runtime layout, identities, names/persona, races, budget; no game calls/writes')
