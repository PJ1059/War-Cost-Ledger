-- Pure injected adapter test: no Windows allocation/registration/CAS or Game entry call.
local source,runtime,root=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
    if name=='native-code-copy-profile'then return assert(loadfile(root..'/src/native-code-copy-profile.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local fp=require('hd2runtime/core/fingerprint')
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local x=f:read('*a');f:close();return x end
local P=require('native-code-copy-profile')
local text=file('src/native-code-copy-probe.lua')
local embedded,replacements=text:gsub('__NATIVE_CODE_COPY_PROFILE__',function()
    return '(function()\n'..file('src/native-code-copy-profile.lua')..'\nend)()'
end)
assert(replacements==1,'exact profile injection token')
local M=assert(loadstring(embedded,'=owned_code_copy_probe'))()
local function qword(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local header=file('dist/hit-contact-registration-source-20261013/game-pe-header.bin')
local export=file('dist/game-plugin-export-source-20261013/original-export.bin')
local getter=file('dist/hit-game-plugin-entry-window-live-20261013-v1/plugin-entry-window.bin'):sub(1,173)
local expected_code=file('dist/native-code-copy-probe-owned-20261013/python-reference/code.bin')
local expected_uw=file('dist/native-code-copy-probe-owned-20261013/python-reference/unwind.bin')
local expected_rf=file('dist/native-code-copy-probe-owned-20261013/python-reference/runtime-function-table.bin')
local code,metadata={},{}
for i,r in ipairs(P.regions)do code[i]=b.unhex(r.hex)end
for i,r in ipairs(P.source_metadata)do metadata[i]=b.unhex(r.hex)end
local STORES={{0x58,0x4EE160},{0x68,0x4EE6C0},{0x80,0x4EE710},{0x88,0x4EE750},
    {0x90,0x4EE7E0},{0xA0,0x4EE7F0},{0xB8,0x4EE9D0},{0xC0,0x4EEAB0},
    {0x98,0x4EE690},{0x18,0x4EE6A0},{0x20,0x4EE6B0}}
local function fixture(change)
    fp.reset()
    local game_base,exe_base,ctx,owned=0x180000000,0x140000000,0x240000000,0x190000000
    local original,slot=game_base+M.source.frame_rva,game_base+M.source.table_rva+0x68
    local f={change=change,time=10,state=3,slot=original,allocations=0,registers=0,protects=0,flushes=0,
        cas_calls=0,reads=0,hashes=0,bytes=0,queries=0,writes={},counter=0,pid=12345}
    local io={mode='live',address=function(x)return x end,
        module=function(n)return n==nil and exe_base or n=='game.dll'and game_base or nil end}
    function io.module_hash(handle)
        f.hashes=f.hashes+1;assert(handle==game_base or handle==exe_base)
        return change=='fingerprint'and handle==game_base and string.rep('0',64)
            or handle==game_base and M.source.dll_sha or M.source.exe_sha
    end
    function io.query(at)
        f.queries=f.queries+1
        if at>=owned and at<owned+P.allocation_bytes then
            assert(f.allocations==1,'no owned memory before allocation')
            local iscode=at<owned+P.code_page_bytes
            return{base=iscode and owned or owned+P.code_page_bytes,
                size=iscode and P.code_page_bytes or P.allocation_bytes-P.code_page_bytes,
                state=0x1000,type=0x20000,allocation_base=owned,protect=iscode and f.RX and 0x20 or 4}
        end
        assert(at>=game_base and at<game_base+M.source.game_size,'outside fixed fake Game image')
        local rva=at-game_base
        return{base=game_base,size=M.source.game_size,state=0x1000,type=0x1000000,allocation_base=game_base,
            protect=at==slot and(f.restore_denied and 2 or 4)or(rva>=0x1000 and rva<0x2111000)and 0x20 or 4}
    end
    function io.read(at,n)
        f.reads,f.bytes=f.reads+1,f.bytes+n
        local rva=at-game_base
        if rva==0 and n==4096 then return header end
        if rva==M.source.export_rva and n==74 then return export end
        if rva==M.source.getter_rva and n==173 then return getter end
        if at==slot and n==8 then return qword(f.slot)end
        if rva==M.source.table_rva and n==200 then
            local rows={};for i=1,200 do rows[i]='\0'end
            for _,r in ipairs(STORES)do
                local raw=qword(r[1]==0x68 and f.slot or game_base+r[2])
                for i=1,8 do rows[r[1]+i]=raw:sub(i,i)end
            end
            return table.concat(rows)
        end
        for i,r in ipairs(P.regions)do
            local offset=rva-r.rva
            if offset>=0 and offset+n<=r.length then
                local raw=code[i]:sub(offset+1,offset+n)
                if change=='full_code'and r.name=='contact'and offset==8192 then raw=raw:sub(1,-2)..string.char((raw:byte(-1)+1)%256)end
                return raw
            end
        end
        for i,r in ipairs(P.source_metadata)do
            if rva==r.rva and n==r.length then
                local raw=metadata[i]
                if change=='metadata_post'and f.allocations==1 and i==3 then raw=raw:sub(1,-2)..string.char((raw:byte(-1)+1)%256)end
                return raw
            end
        end
        error('outside complete named source fixture')
    end
    function io.pid()return f.pid end
    function io.system_info()return 4096,0x7FFFFFFFFFFF,65536 end
    function io.allocate(req)
        f.allocations=f.allocations+1
        assert(req.size==0xB000 and req.alignment==65536 and req.lowest>=game_base+M.source.game_size
            and req.highest<=game_base+0x7FFFFFFF and owned>=req.lowest and owned+req.size-1<=req.highest)
        return {base=owned,injected_owned=true}
    end
    function io.write(at,raw)
        assert(at>=owned and at+#raw<=owned+P.allocation_bytes,'no write reaches fake Game')
        f.writes[at-owned]=raw
    end
    function io.register(at,count,base)
        f.registers=f.registers+1;assert(at==owned+P.table_offset and count==19 and base==game_base)
        return change~='register'
    end
    function io.protect(at,n,mode)
        f.protects=f.protects+1;assert(at==owned and n==0x9000 and mode==0x20)
        f.RX=true;return true
    end
    function io.flush(at,n)f.flushes=f.flushes+1;assert(f.RX and at==owned and n==0x9000);return change~='flush'end
    function io.cas(p,at,replacement,expected)
        f.cas_calls=f.cas_calls+1;assert(f.RX and f.flushes==1 and at==slot)
        if change=='install_race'and f.cas_calls==1 then f.slot=game_base+0x1234 end
        local old=f.slot;if old==expected then f.slot=replacement end
        if change=='cas_error'and f.cas_calls==1 then error('OWNED_AFTER_CAS_ERROR',0)end
        return old
    end
    function io.counter()if f.counter_fail then error('OWNED_COUNTER_ERROR',0)end;return f.counter end
    local view={pointer=function(at)assert(at==game_base+M.source.state_rva);return ctx end,
        u32=function(at)assert(at==ctx+M.source.state_offset);return f.state end}
    f.world={runtime=io,view=view,game=game_base,exe=exe_base};f.game={state=3,mission=false}
    if change=='mission'then f.game.state,f.game.mission=4,true end
    f.probe=M.new({adapter=io,clock=function()return f.time end})
    assert(f.allocations==0 and f.reads==0 and f.hashes==0 and f.cas_calls==0,'new has no native/source activity')
    f.original,f.owned,f.slot_address=original,owned,slot
    return f
end
local count=0
local cases={'normal','full_code','metadata_post','fingerprint','mission','register','flush','install_race','cas_error','cleanup_retry','foreign_restore','counter_restore'}
if arg[4]then
    local selected=assert(arg[4]:match('([^/]+)$'),'owned selector')
    local found=false;for _,case in ipairs(cases)do if case==selected then found=true end end
    assert(found,'unknown owned selector');cases={selected}
end
for _,case in ipairs(cases)do
    local f=fixture(case);local r=f.probe:start(f.world,f.game)
    if case=='normal'or case=='cleanup_retry'or case=='foreign_restore'or case=='counter_restore'then
        assert(r.phase=='running',case..':'..tostring(r.reason))
        assert(r.full_source_verified_before and r.full_source_verified_after and r.registered and r.installed)
        assert(r.reads==f.reads and r.bytes==f.bytes and r.bytes==64904 and r.reads==39)
        assert(r.retained_pages==11 and r.allocation_calls==1 and f.allocations==1 and f.cas_calls==1)
        assert(f.writes[P.regions[1].offset]..f.writes[P.regions[2].offset]..f.writes[P.regions[3].offset]==expected_code,'Lua code relocation equals independent Python mapper')
        assert(f.writes[P.unwind_offset]==expected_uw and f.writes[P.table_offset]==expected_rf,'19RF/16chain/GS mapping')
        assert(#f.writes[P.wrapper_offset]==14 and#f.writes[P.cas_offset]==9)
        if case=='counter_restore'then
            f.counter_fail=true;r=f.probe:stop('DISABLED')
            assert(r.phase=='stopped'and r.restored and not r.cleanup_required and f.slot==f.original and f.cas_calls==2)
            assert(r.counter_reason=='OWNED_COUNTER_ERROR','diagnostic failure recorded without blocking restore')
        elseif case=='cleanup_retry'then
            f.restore_denied=true;r=f.probe:stop('CANCEL')
            assert(r.phase=='failed'and r.cleanup_required and f.slot==f.owned)
            f.restore_denied=false;r=f.probe:stop('RETRY');assert(r.restored and not r.cleanup_required and f.slot==f.original)
        elseif case=='foreign_restore'then
            f.slot=f.original+16;r=f.probe:stop('DISABLED')
            assert(r.third_party_preserved and not r.restored and f.slot==f.original+16)
        else
            f.counter=23;f.time=12.01;r=f.probe:tick(f.world,f.game)
            assert(r.phase=='stopped'and r.reason=='WINDOW_ENDED'and r.restored and r.counter==23 and f.slot==f.original)
        end
        local reads=f.reads;f.probe:tick(nil,nil);f.probe:stop('again');assert(f.reads==reads)
    else
        assert(r.phase=='failed',case..':'..tostring(r.reason));assert(not r.installed)
        if case=='full_code'then assert(f.allocations==0 and r.reason:find('FULL_CODE_CHANGED',1,true))end
        if case=='metadata_post'then assert(f.registers==1 and f.cas_calls==0 and r.reason:find('FULL_METADATA_CHANGED',1,true))end
        if case=='fingerprint'or case=='mission'then assert(f.reads==0 and f.allocations==0)end
        if case=='register'then assert(f.protects==0 and f.cas_calls==0)end
        if case=='flush'then assert(f.cas_calls==0)end
        if case=='install_race'then assert(f.slot==f.original-M.source.frame_rva+0x1234 and r.third_party_preserved)end
        if case=='cas_error'then assert(r.restored and not r.cleanup_required and f.slot==f.original and f.cas_calls==2)end
    end
    assert(not r.payload_ready and not r.classification_ready and not r.engine_dispatch_proven and not r.Game_or_exception_safety_proven)
    local reads,allocations,calls=f.reads,f.allocations,f.cas_calls
    local again=f.probe:start(f.world,f.game)
    assert(again.reason==r.reason and f.reads==reads and f.allocations==allocations and f.cas_calls==calls,'one shot across failures/stops')
    count=count+1
end
print('PASS native-code-copy-probe '..count..' injected owned cases; Game_accessed=false Windows_API_called=false RX_executed=false installed=false')
