-- Actual built entry: real host/controller/link/decoder/session/ledger.
-- Only native installation APIs/package loader and transport are replaced.
-- No Windows API, captured instruction or Game process/memory is touched.
local addon_path,runtime,root=assert(arg[1]),assert(arg[2]),assert(arg[3])
local windows_requests=0
package.preload['hd2runtime/runtime/windows_ffi']=function()
    windows_requests=windows_requests+1
    error('OWNED_WINDOWS_API_BOUNDARY',0)
end
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local JSON=require('hd2runtime/runtime/mod_store')
local native=require('hd2runtime/domains/event_natives')
local S,K,H=native.stats.keys.projectiles_fired,native.stats.keys.dealt_kills,native.stats.keys.projectiles_hit
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local v=f:read('*a');f:close();return v end
local f=assert(io.open(addon_path,'rb'));local built=f:read('*a'):gsub('\r\n','\n');f:close()
assert(built:find("local VERSION = '0.4.24'",1,true),'actual built0.4.24')
local P=assert(loadfile(root..'/dist/native-six-code-copy-probe-owned-20261013/native-code-copy-profile.lua'))()
local old_sha=assert(built:match('local PLUGIN_FRAME_PROBE_SOURCE_SHA = "([%x]+)"'))
local patched=built
local function replace_literal(before,after)
    local a,c=assert(patched:find(before,1,true))
    assert(not patched:find(before,c+1,true),'unique native boundary anchor')
    patched=patched:sub(1,a-1)..after..patched:sub(c+1)
end
local function replace_module(start,finish,replacement)
    local a=assert(patched:find(start,1,true),'native loader start')
    local c=assert(patched:find(finish,a,true),'native loader end')
    patched=patched:sub(1,a-1)..replacement..patched:sub(c)
end
replace_module('-- Consume a lifetime-owned native bridge supplied by the verified installer.',
    '\n    end)()\n    hit_package=(function()',"return assert(rawget(_G,'HD2OwnedTransport'))")
replace_module('-- Prepare private native pages; never writes a game instruction or pauses a thread.',
    '\n    end)()\n    local copy_link=(function()',"return assert(rawget(_G,'HD2OwnedPackage'))")
replace_literal('code=load_code_copy_controller(),package=hit_package',
    'code=HD2OwnedInstallBoundary(load_code_copy_controller()),package=hit_package')

local function clone(v)if type(v)~='table'then return v end;local x={};for k,a in pairs(v)do x[k]=clone(a)end;return x end
local function qword(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local function wire(s)return(s:gsub('..',function(pair)return string.char(tonumber(pair,16))end)):reverse()end
local c={clock=0,game_state=3,slot=0x180000000+0x4EE6C0,owned=0x190000000,
    code_news=0,starts=0,allocations=0,registers=0,cas_calls=0,packages=0,
    configure_calls=0,attach_calls=0,pause_calls=0,resume_calls=0,stats_reads=0,
    batches={},writes={},saves=0,logs={},saved={probe_enabled=false,native_hit_copy_auto_install=true,
        ui_settings={auto_ui_probe=false,career_page_sync=false},mission_sequence=0}}
local GAME,EXE,CTX=0x180000000,0x140000000,0x240000000
local SLOT=GAME+0x37CEB10+0x68
local PEER='1234567890ABCDEF'
local sources,metadata={},{}
for i,r in ipairs(P.regions)do sources[i]=b.unhex(r.hex)end
for i,r in ipairs(P.source_metadata)do metadata[i]=b.unhex(r.hex)end
local header=file('dist/hit-contact-registration-source-20261013/game-pe-header.bin')
local export=file('dist/game-plugin-export-source-20261013/original-export.bin')
local getter=file('dist/hit-game-plugin-entry-window-live-20261013-v1/plugin-entry-window.bin'):sub(1,173)
local STORES={{0x58,0x4EE160},{0x68,0x4EE6C0},{0x80,0x4EE710},{0x88,0x4EE750},
    {0x90,0x4EE7E0},{0xA0,0x4EE7F0},{0xB8,0x4EE9D0},{0xC0,0x4EEAB0},
    {0x98,0x4EE690},{0x18,0x4EE6A0},{0x20,0x4EE6B0}}
local io_adapter={mode='live',address=function(v)return v end,
    module=function(name)return name==nil and EXE or name=='game.dll'and GAME or nil end,
    module_hash=function(handle)
        return handle==GAME and'2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
            or'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
    end,pid=function()return 12345 end,system_info=function()return 4096,0x7FFFFFFFFFFF,65536 end,
    precise_time=function()return c.clock end}
function io_adapter.query(at)
    if at>=c.owned and at<c.owned+P.allocation_bytes then
        return{base=at<c.owned+P.code_page_bytes and c.owned or c.owned+P.code_page_bytes,
            size=at<c.owned+P.code_page_bytes and P.code_page_bytes or P.allocation_bytes-P.code_page_bytes,
            state=0x1000,type=0x20000,allocation_base=c.owned,
            protect=at<c.owned+P.code_page_bytes and c.RX and 0x20 or 4}
    end
    if at>=GAME and at<GAME+0x4744000 then
        local rva=at-GAME
        return{base=GAME,size=0x4744000,state=0x1000,type=0x1000000,allocation_base=GAME,
            protect=at==SLOT and 4 or rva>=0x1000 and rva<0x2111000 and 0x20 or 2}
    end
    return nil
end
function io_adapter.read(at,n)
    local rva=at-GAME
    if rva==0 and n==4096 then return header end
    if rva==0x39D4000 and n==74 then return export end
    if rva==0x4EEAD0 and n==173 then return getter end
    if at==SLOT and n==8 then return qword(c.slot)end
    if rva==0x37CEB10 and n==200 then
        local raw=string.rep('\0',200)
        for _,s in ipairs(STORES)do
            local value=qword(s[1]==0x68 and c.slot or GAME+s[2])
            raw=raw:sub(1,s[1])..value..raw:sub(s[1]+9)
        end
        return raw
    end
    for i,r in ipairs(P.regions)do
        local off=rva-r.rva
        if off>=0 and off+n<=r.length then return sources[i]:sub(off+1,off+n)end
    end
    for i,r in ipairs(P.source_metadata)do if rva==r.rva and n==r.length then return metadata[i]end end
    return nil -- Other optional live readers see an unavailable fake address.
end
function io_adapter.allocate(req)
    assert(req.size==P.allocation_bytes and req.lowest<=c.owned and c.owned+req.size-1<=req.highest)
    c.allocations=c.allocations+1;return{base=c.owned,injected_owned=true}
end
function io_adapter.write(at,raw)assert(at>=c.owned and at+#raw<=c.owned+P.allocation_bytes);c.writes[at]=raw end
function io_adapter.register(at,count,base)
    assert(at==c.owned+P.table_offset and count==28 and base==GAME);c.registers=c.registers+1;return true
end
function io_adapter.protect(at,n,mode)assert(at==c.owned and n==P.code_page_bytes and mode==0x20);c.RX=true;return true end
function io_adapter.flush(at,n)assert(c.RX and at==c.owned and n==P.code_page_bytes);return true end
function io_adapter.cas(_,at,replacement,expected)
    assert(at==SLOT and c.RX);c.cas_calls=c.cas_calls+1
    local old=c.slot;if old==expected then c.slot=replacement end;return old
end
function io_adapter.counter()return 0 end
local view={slot=function()return{}end,
    pointer=function(at)if at==SLOT then return c.slot elseif at==GAME+0x3326340 then return CTX end end,
    u32=function(at)if at==CTX+0xAC21C then return c.game_state end end}
c.world={game=GAME,exe=EXE,runtime=io_adapter,view=view}
rawset(_G,'HD2OwnedInstallBoundary',function(real)
    return{new=function(options)
        c.code_news=c.code_news+1;options.adapter=io_adapter;options.clock=function()return c.clock end
        local controller=real.new(options)
        local start=controller.start
        function controller:start(world,game)c.starts=c.starts+1;return start(self,world,game)end
        c.controller=controller;return controller
    end}
end)
rawset(_G,'HD2OwnedPackage',{prepare=function(image,profile)
    assert(image.base==GAME and image.size==0x4744000)
    assert(c.controller:status().reads==28 and c.cas_calls==0 and c.registers==0)
    c.packages=c.packages+1
    local handle={abi=1,stride=96,native_certified=false,code_base=0x190020000,
        code_size=65536,addresses={},lifetime={functions_registered=true}}
    for i,entry in ipairs(profile.entries)do handle.addresses[entry.name]=handle.code_base+(i-1)*2048 end
    c.handle=handle;return handle
end})
local transport={}
function transport.configure(handle,peer,epoch,enabled)
    assert(handle==c.handle and handle.native_certified and enabled==true)
    assert(c.addon.state.mission and c.addon.state.stats_baseline~=nil,'real mission stats baseline before configure')
    c.configure_calls=c.configure_calls+1;c.peer,c.epoch=peer,epoch;c.enabled=true;return true
end
function transport.pause(handle,peer,epoch)assert(handle==c.handle and peer==c.peer and epoch==c.epoch);c.pause_calls=c.pause_calls+1;c.enabled=false;return true end
function transport.resume(handle,peer,epoch)assert(handle==c.handle and peer==c.peer and epoch==c.epoch);c.resume_calls=c.resume_calls+1;c.enabled=true;return true end
function transport.attach(handle,options)
    assert(handle==c.handle and handle.native_certified and options.peer==c.peer and options.epoch==c.epoch)
    c.attach_calls=c.attach_calls+1
    local decoder=options.decoder.new({peer=options.peer,epoch=options.epoch,
        accept=options.accept,observe_record=options.observe_record})
    local consumer={decoder=decoder,records=0,ready=true}
    function consumer:step(now)
        assert(self.ready);local raw=table.remove(c.batches,1)or'';assert(#raw%96==0 and#raw<=64*96)
        local ok,why=decoder:consume(raw,now,{abi=1,stride=96,connector_proven=true,
            epoch=c.epoch,count=#raw/96,dropped='0000000000000000'})
        if ok then self.records=self.records+#raw/96 end;return ok,why
    end
    function consumer:detach()self.ready=false end
    c.consumer=consumer;return consumer
end
rawset(_G,'HD2OwnedTransport',transport)
local frame,bindings
local store={get=function(_,k,v)if c.saved[k]==nil then return clone(v)end;return clone(c.saved[k])end,
    set=function(_,k,v)
        if k=='native_hit_copy_evidence'and c.evidence_error then c.evidence_error=false;error('OWNED_EVIDENCE_STORE_ERROR',0)end
        c.saved[k]=clone(v)
    end,save=function()c.saves=c.saves+1;return true end}
local mod={store=function()return store end,log=function(_,s)c.logs[#c.logs+1]=s end,
    bind=function(_,id,value)bindings=bindings or{};bindings[id]=value end,on_frame=function(_,fn)frame=fn end}
package.preload['mods/skyeshade/hd2runtime']=function()return{mod=function()return mod end,
    ui={overlay=function()return{draw=function()end,show=function()end,hide=function()end}end}}end
local stats={totals={[S]=0,[K]=0,[H]=0},sources={}}
package.preload['hd2runtime/runtime/event_world']=function()return{
    open=function()return c.world end,
    game_state=function()return{state=c.game_state,mission=c.game_state==4,host=true}end,
    entity_state=function()return nil end,
    players=function()return{{['local']=true,entity=42,peer=PEER}}end,
    stat_breakdown=function(_,_,requested)
        local wanted=false;for _,key in ipairs(requested)do if key==H then wanted=true end end
        assert(wanted);c.stats_reads=c.stats_reads+1;return stats
    end}end
package.preload['hd2runtime/runtime/beacon_redirect']=function()return{prove=function()return false end,clock=function()return 0 end,beacons=function()return{}end}end
package.preload['hd2runtime/runtime/stratagem_loadout']=function()return{prove=function()return false end,id_of=function()return nil end}end
JSON.open=function(owner)
    return{get=function(_,k,default)
        if owner:sub(-19)=='/plugin_frame_probe'then return{source_sha=old_sha,phase='stopped'}end
        return clone(default)
    end,set=function()end,save=function()return true end}
end
os.clock=function()return c.clock end
rawset(_G,'HD2WarCostLedgerV1',nil);rawset(_G,'ModOptionsMenu',nil)
c.addon=assert(loadstring(patched,'@actual-built-native-hit-copy-owned'))()
assert(frame and c.packages==0 and c.starts==0,'import cannot install')
local state=c.addon.state
local function advance(n)for _=1,n do c.clock=c.clock+.1;frame(.1)end end
advance(23)
assert(c.starts==1 and c.code_news==1 and c.packages==1 and c.allocations==1 and c.cas_calls==1)
assert(c.controller:status().reads==57 and c.controller:status().bytes==70878 and c.handle.native_certified)
assert(c.configure_calls==0,'ship cannot configure a mission')
advance(5);assert(c.starts==1 and c.configure_calls==0)
c.game_state=4;advance(1)
assert(state.mission and state.sequence==1 and state.stats_baseline and c.configure_calls==1 and c.attach_calls==1)
assert(c.addon.native_hit_status().ready)
local function record(sequence,result)
    local raw=string.rep('\0',96)
    local function put(offset,value)raw=raw:sub(1,offset)..value..raw:sub(offset+#value+1)end
    put(0,qword(sequence));put(8,wire(c.epoch));put(16,wire(PEER))
    put(44,b.encode(100,'u32'));put(48,b.encode(200,'u32'));put(52,b.encode(300,'u32'))
    put(60,b.encode(result=='ricochet'and 2 or result=='unknown'and 99 or 1,'u32'))
    for offset,value in pairs({[64]=3,[68]=2,[72]=1,[76]=10,[92]=result=='blocked'and-.25 or result=='penetration'and.5 or 2})do
        put(offset,b.encode(value,'f32'))
    end
    put(80,b.encode(1,'u32'));put(84,b.encode(1,'u32'));put(88,b.encode(0x1FF,'u32'))
    return raw
end
local kinds={'ricochet','blocked','penetration','full_penetration'}
local first={};for i,name in ipairs(kinds)do first[i]=record(i,name)end
c.batches[#c.batches+1]=table.concat(first);advance(1)
for _,name in ipairs(kinds)do assert(state.ribbons['hit_'..name]==1,'real four-class ribbon:'..name)end
assert(c.addon.native_hit_status().current.accepted==4)
c.batches[#c.batches+1]=table.concat(first)..record(5,'unknown');advance(1)
for _,name in ipairs(kinds)do assert(state.ribbons['hit_'..name]==1)end
local facts=c.addon.native_hit_status().current
assert(facts.accepted==4 and facts.stale==4 and facts.unclassified==1)
bindings['war_cost_ledger.toggle_hud'].on_press()
local more={};local sequence=5
for _=1,5 do for _,name in ipairs(kinds)do sequence=sequence+1;more[#more+1]=record(sequence,name)end end
c.batches[#c.batches+1]=table.concat(more);advance(1)
for _,name in ipairs(kinds)do assert(state.ribbons['hit_'..name]==6,'F8 hidden does not stop native classification')end
assert(c.saved.hud_enabled==false and c.addon.native_hit_status().current.accepted==24)
local evidence=assert(c.saved.native_hit_copy_evidence)
assert(#evidence.records==16 and evidence.limit==16)
for _,name in ipairs(kinds)do assert(evidence.counts[name]==4,'four raw evidence per class')end
for _,row in ipairs(evidence.records)do assert(#row.raw_hex==192 and not row.raw_hex:find('[^%x]'))end
advance(2);assert(c.starts==1 and c.configure_calls==1)
c.game_state=3;advance(1)
assert(not state.mission and c.pause_calls==1 and c.addon.native_hit_status().previous.accepted==24)
c.game_state=4;advance(1)
assert(state.sequence==2 and c.configure_calls==2 and c.attach_calls==2 and c.starts==1)
c.evidence_error=true;local second={};for i,name in ipairs(kinds)do second[i]=record(i,name)end
c.batches[#c.batches+1]=table.concat(second);advance(1)
for _,name in ipairs(kinds)do assert(state.ribbons['hit_'..name]==1,'observer failure cannot block real counting')end
assert(c.addon.native_hit_status().current.accepted==4 and c.consumer.decoder.observer_reason=='OWNED_EVIDENCE_STORE_ERROR')
assert(c.saved.native_hit_copy_evidence.epoch~=c.epoch and#c.saved.native_hit_copy_evidence.records==16)
assert(c.starts==1 and c.packages==1 and c.cas_calls==1)
c.controller:stop('OWNED_TEST_DONE');assert(c.controller:status().restored and c.slot==GAME+0x4EE6C0)
print('PASS actual built0.4.24 native-hit-copy 1 focused group: Ship install once, real baseline/session/four ribbons, duplicate+unknown reject, F8 count, evidence4/class16total, observer-error count; Game_accessed=false Windows_API_called=false captured_code_executed=false')
