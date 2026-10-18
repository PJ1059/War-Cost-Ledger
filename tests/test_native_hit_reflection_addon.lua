-- Real built controller/session/decoder/HUD; the batch comes from the new
-- owned native producer, not a Lua-constructed branch-2 record.
-- Native installation/transport boundaries are injected; Game is not opened.
local addon_path,runtime,root,fixture_path=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local fixture=assert(loadfile(fixture_path))()
assert(fixture.origin=='owned_reflection_producer_commit_and_drain')
assert(type(fixture.peer)=='string'and#fixture.peer==16 and fixture.epoch_sequence>=1)
local f=assert(io.open(root..'/tests/test_addon_native_hit_copy.lua','rb'))
local setup=f:read('*a'):gsub('\r\n','\n');f:close()
setup=setup:sub(1,assert(setup:find('local function record(sequence,result)',1,true))-1)
setup=setup:gsub("local VERSION = '0%.4%.24'","local VERSION = '0.4.27'")
setup=setup:gsub("local PEER='1234567890ABCDEF'",function()return "local PEER='"..fixture.peer.."'"end)
setup=setup:gsub('mission_sequence=0',function()return 'mission_sequence='..(fixture.epoch_sequence-1)end)
setup=setup:gsub('state.sequence==1',function()return 'state.sequence=='..fixture.epoch_sequence end)
local gate='assert(image.base==GAME and image.size==0x4744000)'
local first,last=assert(setup:find(gate,1,true))
setup=setup:sub(1,first-1)..gate..[[
    assert(profile.revision=='copy_pending_reflection_observer_v1')
    assert(profile.reflection_writeback_source_verified==true)
    assert(profile.ordinary_physical_FIFO_publish==false)
    assert(#profile.entries==21 and#profile.sites==8)
    assert(profile.sites[8].name=='reflection_writeback'and profile.sites[8].rva==0x13AE6BC)
]]..setup:sub(last+1)
local fixture_source=string.format("local proof=assert(loadfile(%q))()\n",fixture_path)
local scenario=[[
local f=assert(io.open(proof.records_path,'rb'));local records=f:read('*a');f:close()
assert(#records==proof.record_count*96 and#records<=64*96)
c.batches[#c.batches+1]=records;advance(1)
for name,n in pairs(proof.counts)do
    assert(state.ribbons['hit_'..name]==n,'native-produced ribbon count:'..name)
end
assert(c.addon.native_hit_status().current.accepted==proof.record_count)
local function find(items,key)
    for _,item in ipairs(items)do if item.key==key then return item end end
end
local awards=c.addon.award_notifications
local view=awards:snapshot(c.clock,true,false)
local reflected=assert(find(view.items,'hit_ricochet'),'genuine reflection appears at side')
assert(reflected.count==proof.counts.ricochet)
c.batches[#c.batches+1]=records;advance(1)
assert(c.addon.native_hit_status().current.accepted==proof.record_count)
assert(c.consumer.decoder.stale==proof.record_count)
advance(21)
view=awards:snapshot(c.clock,true,false)
assert(not find(view.items,'hit_ricochet'),'two idle seconds collect side reflection')
view=awards:snapshot(c.clock,true,true)
reflected=assert(find(view.ribbons,'hit_ricochet'),'map exposes collected ribbon')
assert(reflected.count==proof.counts.ricochet)
assert(c.starts==1 and c.packages==1 and#c.controller.native.prepared.observer_sites==8)
c.controller:stop('OWNED_REFLECTION_DONE')
assert(c.controller:status().restored and c.slot==GAME+0x4EE6C0)
print('PASS actual built0.4.27: native-produced reflection and three AP classes through real decoder/ribbons, duplicate reject, 2-second collection and eight-site lifecycle; Game absent, native installation boundary injected, Windows adapter load attempts blocked:'..windows_requests)
]]
assert(loadstring(fixture_source..setup..scenario,'@owned-native-produced-reflection-addon'))()
