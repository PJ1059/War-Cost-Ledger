-- Real Runtime bytes/schema with owned memory; no live process or UI writes.
local M=assert(loadfile(arg[1]))()
local C=assert(loadfile(arg[2]))()
local b=require('hd2runtime/core/bytes')
local U32=4294967296
local LOCAL,OTHER='0102030405060708','1112131415161718'
local function u32(n)return b.encode(n,'u32')end
local function ptr(n)return u32(n%U32)..u32(math.floor(n/U32))end
local function memory()
    local m={records={},game=0x180000000,hud=0x300000000,state=0x310000000,user=0x320000000,
        roster=0x330000000,gui=0x340000000,names=0x350000000,writes=0,reads=0,bytes=0,read_log={}}
    function m:put(at,raw)
        for _,r in ipairs(self.records)do
            if at>=r[1]and at+#raw<=r[1]+#r[2]then
                local n=at-r[1];r[2]=r[2]:sub(1,n)..raw..r[2]:sub(n+#raw+1);return
            end
        end
        self.records[#self.records+1]={at,raw}
    end
    function m:read(at,n)
        self.reads,self.bytes=self.reads+1,self.bytes+n
        self.read_log[#self.read_log+1]={at,n}
        if self.fault then local v=self.fault(at,n);if v~=nil then return v~=false and v or nil end end
        for _,r in ipairs(self.records)do if at>=r[1]and at+n<=r[1]+#r[2]then return r[2]:sub(at-r[1]+1,at-r[1]+n)end end
        return nil
    end
    function m:player(i,who,label)
        self:put(self.roster+i*0xC0,b.unhex(who):reverse()..label..string.rep('\0',64-#label))
    end
    m.chat=m.hud+M.source.chat
    m:put(m.game+M.source.state,ptr(m.state));m:put(m.state+M.source.state_offset,u32(4))
    m:put(m.game+M.source.hud,ptr(m.hud));m:put(m.game+M.source.user,ptr(m.user))
    m:put(m.user+M.source.local_peer,b.unhex(LOCAL):reverse())
    m:put(m.game+M.source.roster,ptr(m.roster))
    for i=0,3 do m:put(m.roster+i*0xC0,string.rep('\0',72))end
    m:player(0,LOCAL,'本人');m:player(1,OTHER,'队友')
    for _,pin in ipairs(M.pins)do m:put(m.game+pin[1],b.unhex(pin[2]))end
    local function header(kind,parent,context,child,nxt)
        return u32(kind*262144)..string.rep('\0',220)..ptr(child or 0)..ptr(nxt or 0)..ptr(parent)..ptr(context)
    end
    m:put(m.chat,header(1,0x360000000,m.gui))
    for i=0,63 do
        local at=m.chat+M.source.row+i*M.source.stride
        local raw=header(1,m.chat+0x330,m.gui,at+0x110,i<63 and at+M.source.stride or 0)
            ..string.rep('\0',16)..header(8,at,m.gui)..string.rep('\0',16)
            ..u32(0x14DCC78A)..string.rep('\0',341)
        assert(#raw==889);m:put(at,raw)
    end
    function m:notice(i,label,target,template,options)
        options=options or{}
        local at=self.chat+M.source.row+i*M.source.stride+0x220
        local name_at=self.names+i*0x100+(options.unaligned and 3 or 0)
        self:put(name_at,label..string.rep('\0',64-#label))
        local namearg=u32(M.source.name_key)..u32(options.name_type or 1)..ptr(name_at)..string.rep('\0',8)
        local discovery=u32(M.source.discovery_key)..u32(options.discovery_type or 10)..ptr(0)..ptr(target or 0x101166A22E)
        local args=options.swap and(discovery..namearg)or(namearg..discovery)
        local count=options.count or 2
        if count==3 then args=args..u32(0x12345678)..u32(4)..string.rep('\0',16)end
        self:put(at,u32(template or 0x92871A58)..u32(0)..args..string.rep('\0',336-#args)..string.char(count))
        return at,name_at
    end
    local view={}
    function view.read(at,n)return m:read(at,n)end
    function view.write()m.writes=m.writes+1;error('must not write')end
    m.world={game=m.game,runtime={mode='live'},view=view}
    m.reader=M.new({clock=function()return 0 end})
    return m
end
local function sweep(m,players)
    local out,why
    for i=1,16 do
        out,why=m.reader:step(m.world,players)
        assert(m.reader.diagnostics.bytes<=8192 and m.reader.diagnostics.reads<=80)
        if i<16 then assert(not out and why=='RECON_SCANNING',why)end
    end
    assert(out and out.complete and why=='RECON_SWEEP_COMPLETE',why)
    assert(m.writes==0)
    return out
end
local cases=0
local function test(fn)fn();cases=cases+1 end
test(function()
    local m=memory();local at,name_at=m:notice(0,'本人',0x101166A22E,nil,{unaligned=true})
    m:notice(63,'队友',0x101166A22F,0xCD539459,{swap=true,count=3})
    local out=sweep(m)
    assert(#out.rows==2 and out.local_peer==LOCAL)
    assert(out.rows[1].local_player and out.rows[1].peer==LOCAL and out.rows[1].name=='本人')
    assert(not out.rows[2].local_player and out.rows[2].peer==OTHER)
    assert(out.rows[1].signature~=out.rows[2].signature)
    assert(m.reader.diagnostics.bytes_peak<7000)
    for _,read in ipairs(m.read_log)do assert(read[1]~=0x101166A22E)end-- Locale key, never a pointer.
    print('native recon peak: '..m.reader.diagnostics.reads_peak..' reads / '..m.reader.diagnostics.bytes_peak..' bytes per step')
end)
test(function()
    -- Exactly the declared 56B from the saved real native discovery descriptor
    -- (20261013-v2, SHA09b8e0...), with owned NAME storage at its captured
    -- unaligned pointer. Unused descriptor capacity is not claimed as evidence.
    local m=memory()
    local prefix=b.unhex('581a87920000000011771f34010000002cce5f01100000000000000010000000817b23380a00000000000000000000002ea2661110000000')
    m:put(m.chat+M.source.row+0x220,prefix..string.rep('\0',344-#prefix)..'\2')
    m:put(0x10015FCE2C,'本人'..string.rep('\0',64-#'本人'))
    local out=sweep(m)
    assert(#out.rows==1 and out.rows[1].name=='本人'and out.rows[1].local_player)
    assert(out.rows[1].signature:find('2ea2661110000000',1,true))
    assert(out.rows[1].discovery_key==0x1166A22E and out.rows[1].discovery_kind==nil)
end)
test(function()
    -- Native type10 tail low32 is the locale key. The upper32 differs across
    -- the two real samples and must never be part of an address/locale identity.
    local m=memory();local core=C.new();local ctx={mission=true,sequence=31}
    assert(core:update(sweep(m),ctx)==0)
    m:notice(0,'本人',16*U32+0xDD55D46A)
    m:notice(1,'本人',0x01F261DE,0xCD539459)
    m:notice(2,'本人',16*U32+0x1166A22E)
    m:notice(3,'本人',0x12345678)
    local out=sweep(m)
    assert(out.rows[1].discovery_kind=='point_of_interest'and out.rows[2].discovery_kind=='point_of_interest')
    assert(out.rows[3].discovery_key==0x1166A22E and out.rows[3].discovery_kind==nil)
    assert(out.rows[4].discovery_key==0x12345678 and out.rows[4].discovery_kind==nil)
    assert(core:update(out,ctx)==2,'POI must be excluded without blocking actual/unknown target keys')
    assert(core:update(sweep(m),ctx)==0)
    assert(m.reader.diagnostics.poi_rows==2)
    assert(m.reader.diagnostics.reads_peak<=80 and m.reader.diagnostics.bytes_peak<=8192)
    for _,r in ipairs(m.read_log)do
        assert(r[1]~=16*U32+0xDD55D46A and r[1]~=0x12345678 and r[1]~=0x1166A22E)
    end
end)
test(function()
    assert(M.discovery_kind(0x01F261DE)=='point_of_interest')
    assert(M.discovery_kind(0xD5BD7333)=='point_of_interest')
    assert(M.discovery_kind(0xDD55D46A)=='point_of_interest')
    assert(M.discovery_kind(0x1166A22E)==nil)
    assert(M.discovery_kind(0x12345678)==nil)
end)
test(function()
    local m=memory();local core=C.new();local ctx={mission=true,sequence=31}
    m:notice(0,'本人',0x101166A22E);assert(core:update(sweep(m),ctx)==0)
    m:notice(1,'本人',0x101166A22F);assert(core:update(sweep(m),ctx)==1)
    assert(core:update(sweep(m),ctx)==0)
    m:notice(2,'队友',0x101166A230);core:update(sweep(m),ctx);assert(core:update(sweep(m),ctx)==0)
    assert(core:update(sweep(m),ctx)==0)
end)
test(function()
    local m=memory();local core=C.new();local ctx={mission=true,sequence=31}
    local at,name_at=m:notice(0,'本人',0x101166A22E)
    m:put(name_at,string.rep('X',64))-- Old notification NAME temporarily unavailable.
    assert(core:update(sweep(m),ctx)==0)
    m:put(name_at,'本人'..string.rep('\0',64-#'本人'))
    assert(core:update(sweep(m),ctx)==0)-- Resolving the old binding does not replay it.
    local descriptor=m:read(at,345)
    m:put(m.chat+M.source.row+63*M.source.stride+0x220,descriptor)
    m:put(at,u32(0x14DCC78A)..string.rep('\0',341))
    assert(core:update(sweep(m),ctx)==0)-- Same native descriptor moving slots stays one event.
end)
test(function()
    local m=memory();local core=C.new();local ctx={mission=true,sequence=31}
    for i=0,3 do m:notice(i,'本人',0x101166A22E+i,0xCD539459,{count=3})end
    assert(core:update(sweep(m),ctx)==0)
    assert(m.reader.diagnostics.reads_peak<=80 and m.reader.diagnostics.bytes_peak<=8192)
    m:notice(0,'本人',0x101166A22E,0x92871A58)
    assert(core:update(sweep(m),ctx)==0)-- Color-template change is still the same native NAME/DISCOVERY binding.
    print('native recon all-discovery peak: '..m.reader.diagnostics.reads_peak..' reads / '..m.reader.diagnostics.bytes_peak..' bytes per step')
end)
test(function()
    local m=memory();m:notice(0,'本人',123,0x14DCC78A)-- Player chat imitation/non-discovery template.
    m:notice(1,'本人',124,nil,{name_type=10})
    m:notice(2,'本人',125,nil,{discovery_type=1})
    m:notice(3,'本人',126,nil,{count=4})
    assert(#sweep(m).rows==0)
end)
test(function()
    local m=memory();m:notice(0,'本人',123);m:player(1,OTHER,'本人')
    local out=sweep(m);assert(#out.rows==1 and not out.rows[1].local_player)
    assert(out.rows[1].reason=='AMBIGUOUS_ROSTER_NAME')
end)
test(function()
    local m=memory();m:notice(0,'本人',123)
    local players={{peer=LOCAL,name='本人',['local']=true},{peer=OTHER,name='队友'}}
    local out=sweep(m,players);assert(out.rows[1].local_player)
    for _,r in ipairs(m.records)do if r[1]==m.game+M.source.roster then r[2]='bad'end end
    assert(sweep(m,players).rows[1].local_player)-- Supplied roster avoids native roster IO.
end)
test(function()
    local m=memory();m:notice(0,'不存在的人',123)
    local out=sweep(m);assert(not out.rows[1].local_player and out.rows[1].reason=='NAME_NOT_IN_CURRENT_ROSTER')
    m=memory();local at,name_at=m:notice(0,'本人',123);m:put(name_at,string.rep('X',64))
    out=sweep(m);assert(not out.rows[1].local_player and out.rows[1].reason=='NAME_UNREADABLE')
end)
test(function()
    local m=memory();local at,name_at=m:notice(0,'本人',123);local reads=0
    m.fault=function(p)
        if p==name_at then reads=reads+1;if reads==2 then return string.rep('X',64)end end
    end
    local out,why=m.reader:step(m.world);assert(not out and why=='RECON_DESCRIPTOR_CHANGED',why)
    m.fault=nil;assert(sweep(m).rows[1].local_player)
end)
test(function()
    local m=memory();m:notice(0,'本人',123);local reads=0
    m.fault=function(p)
        if p==m.roster then reads=reads+1;if reads==2 then return string.rep('\0',72)end end
    end
    local out,why=m.reader:step(m.world);assert(not out and why=='RECON_ROSTER_CHANGED',why)
end)
test(function()
    local m=memory();m:notice(0,'本人',123);local r=m.reader
    assert(select(2,r:step(m.world))=='RECON_SCANNING')
    m:put(m.state+M.source.state_offset,u32(3))
    assert(select(2,r:step(m.world))=='RECON_NOT_IN_MISSION')
    m:put(m.state+M.source.state_offset,u32(4));assert(sweep(m).rows[1].local_player)
    r:reset();assert(select(2,r:step(m.world))=='RECON_SCANNING')
end)
test(function()
    local m=memory();m:put(m.game+M.pins[1][1],string.rep('\0',#M.pins[1][2]/2))
    assert(select(2,m.reader:step(m.world))=='RECON_CODE_PIN')
    m=memory();m:put(m.chat+M.source.row+0xF8,ptr(m.gui+8))
    assert(select(2,m.reader:step(m.world))=='RECON_ROW_IDENTITY')
    m=memory();m.fault=function(p,n)if p==m.chat then return ''end end
    assert(select(2,m.reader:step(m.world))=='RECON_READ_FAILED')
end)
test(function()
    local m=memory();local n=0
    m.reader=M.new({clock=function()n=n+1;return n>=5 and .002 or 0 end})
    assert(select(2,m.reader:step(m.world))=='RECON_TIME_BUDGET')
    assert(m.reader.diagnostics.reads<=3)
end)
print('native recon reader: '..cases..' cases passed')
