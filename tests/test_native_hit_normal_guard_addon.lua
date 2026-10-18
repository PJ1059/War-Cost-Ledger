-- Actual candidate entry and seven-site linker; only existing native/transport
-- boundaries are injected. Reuse old SETUP without rerunning its old scenarios.
local addon_path,runtime,root=assert(arg[1]),assert(arg[2]),assert(arg[3])
local f=assert(io.open(root..'/tests/test_addon_native_hit_copy.lua','rb'))
local setup=f:read('*a'):gsub('\r\n','\n');f:close()
setup=setup:sub(1,assert(setup:find("local kinds={'ricochet'",1,true))-1)
setup=setup:gsub("local VERSION = '0%.4%.24'","local VERSION = '0.4.26'")
local gate='assert(image.base==GAME and image.size==0x4744000)'
local first,last=assert(setup:find(gate,1,true))
setup=setup:sub(1,first-1)..gate..[[
    assert(profile.revision=='copy_pending_normal_result_guard_v1')
    assert(profile.ricochet_producer_verified==false and profile.ordinary_physical_FIFO_publish==false)
    assert(#profile.entries==20 and#profile.sites==7)
]]..setup:sub(last+1)
local marker="rawset(_G,'HD2OwnedTransport',transport)"
local at=assert(setup:find(marker,1,true))
setup=setup:sub(1,at-1)..[[
c.diagnostic_reads=0
function transport.diagnostic_snapshot(handle,peer,epoch)
    assert(handle==c.handle and peer==c.peer and epoch==c.epoch)
    c.diagnostic_reads=c.diagnostic_reads+1
    return{revision=1,peer=peer,epoch=epoch,alt_seen='0000000000000001',true_seen='0000000000000001',
        claimed=1,committed_mask=1,records={{slot=0,tag=4,raw_hex=string.rep('AB',96)}}}
end
]]..setup:sub(at)
local scenario=[[
local results={'blocked','penetration','full_penetration'}
local raw={};for i,name in ipairs(results)do raw[i]=record(i,name)end
c.batches[#c.batches+1]=table.concat(raw);advance(11)
for _,name in ipairs(results)do assert(state.ribbons['hit_'..name]==1,'normal ribbon:'..name)end
assert(state.ribbons.hit_ricochet==0,'a speed-processing diagnostic cannot award ricochet')
assert(c.addon.native_hit_status().current.accepted==3)
local evidence=assert(c.saved.native_hit_tail_diagnostic)
assert(evidence.version=='0.4.26'and evidence.profile_revision=='copy_pending_normal_result_guard_v1')
assert(evidence.claimed==1 and evidence.records[1].tag==4)
c.batches[#c.batches+1]=table.concat(raw)..record(4,'unknown');advance(1)
assert(c.addon.native_hit_status().current.accepted==3)
assert(c.consumer.decoder.stale==3 and c.consumer.decoder.unclassified==1)
for _,name in ipairs(results)do assert(state.ribbons['hit_'..name]==1)end
assert(state.ribbons.hit_ricochet==0)
advance(11) -- Let the legitimate duplicate/unknown snapshot finish its save.
local saves=c.saves;advance(11);assert(c.saves==saves,'unchanged diagnostic is not saved again')
c.controller:stop('OWNED_NORMAL_GUARD_DONE');assert(c.controller:status().restored)
print('PASS actual built0.4.26: normal/AP three ribbons, diagnostic isolation, exact profile, duplicate/unknown handling, unchanged-save and seven-site lifecycle; Game and captured-code execution absent, Windows adapter load attempts blocked:'..windows_requests)
]]
assert(loadstring(setup..scenario,'@owned-actual-normal-result-guard'))()
