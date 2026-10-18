-- Reuse the frozen three-region injected adapter, with three focused six-region
-- cases. No native APIs or Game access; installed code is never loaded here.
local root=assert(arg[3])
local f=assert(io.open(root..'/tests/test_native_code_copy_probe.lua','rb'))
local test=f:read('*a');f:close()
local function replace(before,after,expected)
    local out,pos,count={},1,0
    while true do
        local a,c=test:find(before,pos,true)
        if not a then out[#out+1]=test:sub(pos);break end
        out[#out+1]=test:sub(pos,a-1);out[#out+1]=after;pos=c+1;count=count+1
    end
    assert(count==expected,'six-region fixture anchor: '..before)
    test=table.concat(out)
end
replace('src/native-code-copy-profile.lua','dist/native-six-code-copy-probe-owned-20261013/native-code-copy-profile.lua',2)
replace('dist/native-code-copy-probe-owned-20261013/python-reference/',
        'dist/native-six-code-copy-probe-owned-20261013/python-reference/',3)
replace('req.size==0xB000','req.size==0xD000',1)
replace('count==19','count==28',1)
replace('n==0x9000','n==0xB000',2)
replace('r.bytes==64904 and r.reads==39','r.bytes==70878 and r.reads==57',1)
replace('r.retained_pages==11','r.retained_pages==13',1)
replace("r.name=='contact'and offset==8192","r.name=='ap'and offset==0",1)
replace('f.allocations==1 and i==3',"f.allocations==1 and r.name=='physical_UW180'",1)
replace('f.writes[P.regions[1].offset]..f.writes[P.regions[2].offset]..f.writes[P.regions[3].offset]',
    '(function()local rows={}for i,r in ipairs(P.regions)do rows[i]=f.writes[r.offset]end return table.concat(rows)end)()',1)
replace("local cases={'normal','full_code','metadata_post','fingerprint','mission','register','flush','install_race','cas_error','cleanup_retry','foreign_restore','counter_restore'}",
        "local cases={'normal','full_code','metadata_post'}",1)
replace('19RF/16chain/GS mapping','28RF/22chain/GS mapping',1)
replace('PASS native-code-copy-probe ','PASS native-six-code-copy-probe ',1)
assert(loadstring(test,'=owned_six_code_copy_probe'))()
