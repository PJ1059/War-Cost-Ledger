-- Fixed native chat-HUD rows, read-only and incremental. Offsets/descriptors
-- are from the saved 2026-10-13 discovery and HUD-handler captures.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local bit=require('bit')
local M={source={
    exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    state=0x3326340,state_offset=705052,hud=0x346D538,chat=0x14498,
    roster=0x347CED8,user=0x347CEF0,local_peer=0xB398,
    row=0x4390,stride=0x3D8,count=64,child=0x110,descriptor=0x110,
    name_key=0x341F7711,discovery_key=0x38237B81,
},pins={
    {19869569,'488b3db0a51702498bf0488bda80bf35e32400000f84b80000004c8b1d369f180233c0'},
    {19869720,'488d8f98440100488bd0e849c45600'},
    {0x186042D,'488db75847000041be40000000'},
    {0x1860455,'488d8e38fcffff'},
    {0x18604C3,'4881c6d8030000'},
    {0x143C950,'40534883ec20488bd94881c110010000'},
    {0x143A1BA,'440fb69958010000'},
}}
local U32=4294967296
local KEYS={[0x92871A58]=true,[0xCD539459]=true}
-- The live type10 tail's low u32 is a locale key, not a pointer.
-- 0x1166A22E resolves exactly to Light Nest in the saved live discovery.
-- These three keys are Major/ordinary/Minor Place of Interest in all 15 locales.
local POI_KEYS={[0x01F261DE]=true,[0xD5BD7333]=true,[0xDD55D46A]=true}
function M.discovery_kind(key)
    return POI_KEYS[key]and'point_of_interest'or nil
end
local function integer(v,max)return type(v)=='number'and v>=0 and v<=max and v%1==0 end
local function address(v)return integer(v,140737488355327)and v>=65536 end
local function pointer(v)return address(v)and v%8==0 end
local function rawptr(raw,at)return b.u32(raw,at)+b.u32(raw,at+4)*U32 end
local function kind(raw,at)return bit.band(bit.rshift(b.u32(raw,at or 0),18),15)end
local function peer(raw)return b.hex(raw:reverse()):upper()end
local function name(raw)
    local ending=raw:find('\0',1,true)
    if not ending or ending==1 then return nil end
    local value=raw:sub(1,ending-1)
    if value:find('[%z\1-\31\127]')then return nil end
    local i=1
    while i<=#value do
        local c=value:byte(i);local n=c<128 and 0 or c>=194 and c<=223 and 1 or c>=224 and c<=239 and 2
            or c>=240 and c<=244 and 3 or nil
        if not n or i+n>#value then return nil end
        for j=1,n do local d=value:byte(i+j);if d<128 or d>191 then return nil end end
        local second=value:byte(i+1)
        if n==2 and(c==224 and second<160 or c==237 and second>=160)
            or n==3 and(c==240 and second<144 or c==244 and second>=144)then return nil end
        i=i+n+1
    end
    return value
end
function M.new(options)
    options=options or{}
    local api={diagnostics={ready=false,reason='NOT_READ',reads=0,bytes=0,reads_peak=0,bytes_peak=0,
        max_reads=80,max_bytes=8192,soft_budget_ms=2,rows_per_step=4}}
    local clock=options.clock or os.clock
    local proven,sweep,cursor=nil,nil,0
    function api:reset()sweep,cursor=nil,0;self.diagnostics.ready=false end
    function api:step(world,players)
        local d=self.diagnostics;d.ready,d.reads,d.bytes=false,0,0
        local function reject(why)self:reset();d.reason=why;return nil,why end
        if profile.exe_sha~=M.source.exe_sha or profile.dll_sha~=M.source.dll_sha then return reject('RECON_BUILD_MISMATCH')end
        if type(world)~='table'or not pointer(world.game)or type(world.view)~='table'
            or type(world.view.read)~='function'or type(world.runtime)~='table'or world.runtime.mode~='live'then
            return reject('RECON_WORLD_UNAVAILABLE')
        end
        local started=clock()
        local function get(at,size)
            if not address(at)or not integer(size,1024)or size==0 or not address(at+size-1)then error('RECON_READ_ADDRESS',0)end
            if d.reads>=80 or d.bytes+size>8192 then error('RECON_READ_BUDGET',0)end
            if clock()-started>=.002 then error('RECON_TIME_BUDGET',0)end
            d.reads,d.bytes=d.reads+1,d.bytes+size
            local ok,raw=pcall(world.view.read,at,size)
            if not ok or type(raw)~='string'or #raw~=size then error('RECON_READ_FAILED',0)end
            return raw
        end
        local function ptr(at)
            local value=rawptr(get(at,8),0)
            if not pointer(value)then error('RECON_POINTER',0)end
            return value
        end
        local ok,result,why=pcall(function()
            local world_key=tostring(world.game)..':'..tostring(world.view)..':'..tostring(world.view.read)
            if proven~=world_key then
                self:reset()
                for _,pin in ipairs(M.pins)do if get(world.game+pin[1],#pin[2]/2)~=b.unhex(pin[2])then error('RECON_CODE_PIN',0)end end
                proven=world_key
            end
            local state=ptr(world.game+M.source.state)
            if b.u32(get(state+M.source.state_offset,4),0)~=4 then error('RECON_NOT_IN_MISSION',0)end
            local hud=ptr(world.game+M.source.hud);local chat=hud+M.source.chat
            local root=get(chat,256)
            local gui=rawptr(root,0xF8)
            if kind(root)~=1 or not pointer(rawptr(root,0xF0))or not pointer(gui)then error('RECON_ROOT_IDENTITY',0)end
            local user=ptr(world.game+M.source.user);local local_raw=get(user+M.source.local_peer,8)
            if local_raw==string.rep('\0',8)then error('RECON_LOCAL_PEER',0)end
            local local_peer=peer(local_raw)
            local roster,raw_roster,people=nil,{},{}
            -- Reuse the caller's contemporaneous enriched roster when complete.
            local supplied=type(players)=='table'and #players>0 and #players<=4
            local seen,has_local={},false
            if supplied then
                for _,p in ipairs(players)do
                    local who=type(p)=='table'and(p.peer_id or p.peer)
                    local label=type(p)=='table'and p.name
                    if type(who)~='string'or #who~=16 or who:find('[^%x]')or who=='0000000000000000'
                        or type(label)~='string'or #label>63 or name(label..'\0')~=label or seen[who:upper()]then supplied=false;break end
                    who=who:upper();seen[who]=true;has_local=has_local or who==local_peer
                    people[#people+1]={peer=who,name=label,local_player=who==local_peer}
                end
                supplied=supplied and has_local
            end
            if not supplied then
                people={};roster=ptr(world.game+M.source.roster)
                for i=0,3 do
                    local raw=get(roster+i*0xC0,72);raw_roster[i+1]=raw
                    if raw:sub(1,8)~=string.rep('\0',8)then
                        local who=peer(raw:sub(1,8));people[#people+1]={peer=who,name=name(raw:sub(9)),local_player=who==local_peer}
                    end
                end
            end
            local roster_key={}
            for _,p in ipairs(people)do roster_key[#roster_key+1]=p.peer..':'..(p.name or'')end
            table.sort(roster_key);roster_key=table.concat(roster_key,'|')
            local identity=world_key..':'..tostring(chat)..':'..tostring(gui)..':'..local_peer
            if not sweep or sweep.identity~=identity or sweep.roster~=roster_key then
                sweep={identity=identity,roster=roster_key,local_peer=local_peer,rows={}};cursor=0
            end
            local batch={}
            for i=cursor,math.min(cursor+3,63)do
                local at=chat+M.source.row+i*M.source.stride
                local raw=get(at,889);local child=at+M.source.child
                local next_row=i<63 and at+M.source.stride or 0
                if kind(raw)~=1 or rawptr(raw,0xE0)~=child or rawptr(raw,0xE8)~=next_row
                    or rawptr(raw,0xF0)~=chat+0x330 or rawptr(raw,0xF8)~=gui
                    or kind(raw,0x110)~=8 or rawptr(raw,0x200)~=at or rawptr(raw,0x208)~=gui then
                    error('RECON_ROW_IDENTITY',0)
                end
                local descriptor=raw:sub(0x220+1,0x220+345)
                local template,count=b.u32(descriptor,0),descriptor:byte(345)
                if KEYS[template]and(count==2 or count==3)then
                    local names,discoveries,name_at,name_argument,discovery=0,0,nil,nil,nil
                    for j=0,count-1 do
                        local offset=8+j*24;local key,typ=b.u32(descriptor,offset),b.u32(descriptor,offset+4)
                        if key==M.source.name_key then
                            names=names+1
                            if typ==1 then name_at=rawptr(descriptor,offset+8);name_argument=descriptor:sub(offset+1,offset+24)end
                        end
                        if key==M.source.discovery_key then discoveries=discoveries+1;if typ==10 then discovery=descriptor:sub(offset+1,offset+24)end end
                    end
                    if names==1 and discoveries==1 and name_at and address(name_at)and discovery then
                        local got,value=pcall(get,name_at,64)
                        if not got and value~='RECON_READ_FAILED'then error(value,0)end
                        local label=got and name(value)or nil
                        -- Only the low u32 is the locale key; the upper u32
                        -- has uninitialised residue in the prior real sample.
                        local target_key=b.u32(discovery,16)
                        local row={index=i,system_discovery=true,template=template,name=label,
                            -- Keep opaque native target bytes, not just NAME.
                            -- Raw NAME binding also stays stable if its string
                            -- was temporarily unreadable/ambiguous last sweep.
                            signature=b.hex(name_argument)..':'..b.hex(discovery),
                            discovery_key=target_key,discovery_kind=M.discovery_kind(target_key),
                            local_player=false,reason='NAME_UNREADABLE'}
                        if label then
                            local match,n=nil,0
                            for _,p in ipairs(people)do if p.name==label then match,n=p,n+1 end end
                            row.reason=n==1 and'UNIQUE_CURRENT_ROSTER_NAME'or n==0 and'NAME_NOT_IN_CURRENT_ROSTER'or'AMBIGUOUS_ROSTER_NAME'
                            if n==1 then row.peer,row.local_player=match.peer,match.local_player end
                        end
                        if get(child+0x110,8+24*count)~=descriptor:sub(1,8+24*count)
                            or get(child+0x110+344,1)~=descriptor:sub(345,345)
                            or got and get(name_at,64)~=value then error('RECON_DESCRIPTOR_CHANGED',0)end
                        batch[#batch+1]=row
                    end
                end
                if get(at+0xE0,52)~=raw:sub(0xE0+1,0xE0+52)
                    or get(child+0xF0,16)~=raw:sub(0x200+1,0x210)then error('RECON_ROW_CHANGED',0)end
            end
            if roster then
                for i=0,3 do if get(roster+i*0xC0,72)~=raw_roster[i+1]then error('RECON_ROSTER_CHANGED',0)end end
                if ptr(world.game+M.source.roster)~=roster then error('RECON_ROSTER_CHANGED',0)end
            end
            local final_root=get(chat,256)
            if ptr(world.game+M.source.user)~=user or get(user+M.source.local_peer,8)~=local_raw
                or ptr(world.game+M.source.hud)~=hud or kind(final_root)~=1
                or final_root:sub(241,256)~=root:sub(241,256)
                or ptr(world.game+M.source.state)~=state or b.u32(get(state+M.source.state_offset,4),0)~=4 then
                error('RECON_CONTEXT_CHANGED',0)
            end
            for _,row in ipairs(batch)do sweep.rows[#sweep.rows+1]=row end
            cursor=cursor+4;d.rows_scanned=cursor
            if cursor<64 then return nil,'RECON_SCANNING'end
            local out=sweep;out.complete=true;out.source='native_system_discovery_chat_descriptor'
            d.poi_rows=0
            for _,row in ipairs(out.rows)do
                if row.discovery_kind=='point_of_interest'then d.poi_rows=d.poi_rows+1 end
                d.last_discovery_key=row.discovery_key
            end
            sweep,cursor=nil,0
            return out,'RECON_SWEEP_COMPLETE'
        end)
        d.elapsed_ms=math.max(0,(clock()-started)*1000)
        d.reads_peak,d.bytes_peak=math.max(d.reads_peak,d.reads),math.max(d.bytes_peak,d.bytes)
        if not ok then return reject(tostring(result))end
        d.ready,d.reason=result~=nil,why
        return result,why
    end
    return api
end
return M
