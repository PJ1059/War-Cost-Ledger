-- Frozen dispatch evidence and synthetic addresses; no Game reads or calls.
local runtime,root,observer_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local s=f:read('*a');f:close();return s end
local P=dofile(root..'/src/native-code-copy-profile.lua')
local text=file('src/native-code-copy-probe.lua'):gsub('__NATIVE_CODE_COPY_PROFILE__',function()
    return '(function()\n'..file('src/native-code-copy-profile.lua')..'\nend)()'
end)
local copy=assert(loadstring(text))()
local link=dofile(root..'/src/native-hit-copy-link.lua')
local function fixture()
    local pr=dofile(observer_path)
    local h={code_base=0x190020000,code_size=65536,addresses={},lifetime={functions_registered=true}}
    local offset=0
    for _,e in ipairs(pr.entries)do
        offset=math.floor((offset+15)/16)*16;h.addresses[e.name]=h.code_base+offset
        offset=offset+#e.code_hex/2
    end
    assert(offset<=65536)
    local src={};for i,r in ipairs(P.regions)do src[i]=b.unhex(r.hex)end
    return copy.prepare(0x180000000,0x190000000),pr,h,src
end
local plan,profile,handle,source=fixture()
local before={};for i,r in ipairs(plan.regions)do before[i]=r end
link.link(plan,profile,handle,source,P.regions)
assert(#plan.observer_sites==9 and #profile.sites==8)
for _,s in ipairs(plan.observer_sites)do
    local r=s.name=='demolition_dispatch'and 2
        or (s.name=='physical_success'or s.name=='physical_alt_tail')and 6
        or (s.name=='default_delta'or s.name=='custom_curve')and 4 or 3
    local offset=s.copy_pc-plan.layout[r]
    local raw=plan.regions[r]
    local disp=b.u32(raw,offset+1);if disp>=2147483648 then disp=disp-4294967296 end
    assert(raw:byte(offset+1)==232 and s.copy_pc+5+disp==s.target)
    plan.regions[r]=raw:sub(1,offset)..before[r]:sub(offset+1,offset+s.length)..raw:sub(offset+s.length+1)
end
for i,r in ipairs(plan.regions)do assert(r==before[i],'exactly nine call sites change')end
plan,profile,handle,source=fixture()
local original=table.concat(plan.regions)
local offset=0xAB5FFE-P.regions[2].rva
source[2]=source[2]:sub(1,offset)..'\0'..source[2]:sub(offset+2)
assert(not pcall(link.link,plan,profile,handle,source,P.regions))
assert(table.concat(plan.regions)==original,'late dispatch PIN failure leaves all hit sites unchanged')
local function probe(change)
    local p=copy.new()
    p.game_base=0x180000000
    local reads=0
    p.io={query=function(at)
        return {base=p.game_base,size=0x4744000,state=0x1000,type=0x1000000,
            protect=0x20,allocation_base=p.game_base}
    end,read=function(at,n)
        reads=reads+1
        for _,range in ipairs(profile.demolition_source)do
            if at==p.game_base+range.rva then
                local raw=b.unhex(range.hex);assert(#raw==n)
                if change and reads==6 then return raw:sub(1,-2)..string.char((raw:byte(-1)+1)%256)end
                return raw
            end
        end
        error('unlisted read')
    end}
    return p
end
local p=probe(false);p:_observer_source(profile);p:_observer_source(profile)
assert(p.d.demolition_source_reads==6 and p.d.demolition_source_bytes==3216)
assert(not pcall(p._observer_source,p,profile),'third read violates finite contract')
p=probe(true);p:_observer_source(profile)
local ok=pcall(p._observer_source,p,profile)
assert(not ok,'post-copy metadata mismatch cannot publish')
print('PASS demolition source/link: unchanged six regions/28 RF, nine exact private CALLs, atomic late rejection, two bounded source checks')
