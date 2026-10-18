local source,runtime,fixture_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,1,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local M=dofile(source)
local fixture=dofile(fixture_path)
local PEER='0102030405060708'
local function pointer(n)return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')end
local function memory()
    local m={records={},reads={},writes=0,local_user=0x300000000}
    for _,r in ipairs(fixture.records)do m.records[#m.records+1]={r[1],b.unhex(r[2])}end
    m.records[#m.records+1]={fixture.game+M.source.local_user,pointer(m.local_user)}
    m.records[#m.records+1]={m.local_user+M.source.local_peer,b.unhex(PEER):reverse()}
    function m:patch(at,raw)
        local n=0
        for _,r in ipairs(self.records)do
            if at>=r[1] and at+#raw<=r[1]+#r[2]then
                local offset=at-r[1];r[2]=r[2]:sub(1,offset)..raw..r[2]:sub(offset+#raw+1);n=n+1
            end
        end
        assert(n>0,'patch must remain in fixture')
    end
    m.world={game=fixture.game,runtime={mode='live',write=function()m.writes=m.writes+1;error('no writes')end},view={}}
    m.world.view.read=function(at,n)
        m.reads[#m.reads+1]={at,n}
        if m.on_read then m.on_read(at,n)end
        for _,r in ipairs(m.records)do if at>=r[1] and at+n<=r[1]+#r[2]then return r[2]:sub(at-r[1]+1,at-r[1]+n)end end
        error(string.format('outside owned header fixture %x / %d',at,n))
    end
    return m
end
if HD2_CAREER_PANEL_FIXTURE_ONLY then return {memory=memory,fixture=fixture,M=M,b=b,peer=PEER,pointer=pointer}end
local function reader()return M.new({clock=function()return 0 end})end
local m,r=memory(),reader()
local g,why=r:read(m.world,PEER)
assert(g,why)
assert(g.parent==fixture.controller+0x4DAF8 and g.gui_context==fixture.gui_context)
assert(g.position[1]==732 and g.position[2]==-237 and g.width==420 and g.height==747)
assert(g.root.width==1920 and g.root.height==1080 and g.root.sx==1)
assert(r.diagnostics.reads<=48 and r.diagnostics.bytes<8192 and m.writes==0)
for _,read in ipairs(m.reads)do assert(read[1]~=fixture.controller+0x4E6D0,'must never follow statistic rows')end
local first=r.diagnostics.reads
assert(r:read(m.world,PEER));assert(r.diagnostics.reads==first-4,'code pins cached by world identity')
for _,failure in ipairs({'hidden','foreign_peer','parent','context','rotation','rebuild','nonship','budget'})do
    m,r=memory(),reader()
    if failure=='hidden'then m:patch(fixture.controller+M.source.panel+M.source.alpha,b.encode(0,'f32'))end
    if failure=='foreign_peer'then m:patch(m.local_user+M.source.local_peer,b.unhex('0807060504030202'))end
    if failure=='parent'then m:patch(fixture.controller+M.source.root+0xF0,pointer(fixture.controller+0xA8))end
    if failure=='context'then m:patch(fixture.controller+M.source.name+0xF8,pointer(fixture.gui_context+8))end
    if failure=='rotation'then m:patch(fixture.controller+M.source.root+0x68,b.encode(.5,'f32'))end
    if failure=='nonship'then m:patch(fixture.state_context+M.source.state_offset,b.encode(4,'u32'))end
    if failure=='rebuild'then
        local seen=0;m.on_read=function(at)
            if at==fixture.controller+M.source.root then seen=seen+1
                if seen==2 then m:patch(at+0x94,b.encode(2,'f32'))end end
        end
    end
    if failure=='budget'then local t=0;r.clock=function()t=t+.001;return t end end
    local result,reason=r:read(m.world,PEER)
    assert(not result and type(reason)=='string',failure..' must hide')
    assert(m.writes==0)
end
print('PASS: actual Career parent fixture, x732/y237/420x747, bounded double identity, no statistic rows, pin cache, hide on page/peer/parent/context/matrix/rebuild/time failure.')
