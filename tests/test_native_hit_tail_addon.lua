-- Reuse only the existing built-entry SETUP, not its old test scenarios.
-- Native APIs/transport are injected; actual addon/host/link/session run.
local addon_path,runtime,root=assert(arg[1]),assert(arg[2]),assert(arg[3])
local f=assert(io.open(root..'/tests/test_addon_native_hit_copy.lua','rb'))
local setup=f:read('*a'):gsub('\r\n','\n');f:close()
setup=setup:sub(1,assert(setup:find("local kinds={'ricochet'",1,true))-1)
setup=setup:gsub("local VERSION = '0%.4%.24'","local VERSION = '0.4.25'")
local marker="rawset(_G,'HD2OwnedTransport',transport)"
local at=assert(setup:find(marker,1,true))
setup=setup:sub(1,at-1)..[[
c.diagnostic_reads=0
function transport.diagnostic_snapshot(handle,peer,epoch)
    assert(handle==c.handle and peer==c.peer and epoch==c.epoch)
    c.diagnostic_reads=c.diagnostic_reads+1
    if c.diagnostic_error then c.diagnostic_error=false;error('OWNED_DIAG_READ_FAILED')end
    return{revision=1,peer=peer,epoch=epoch,alt_seen='0000000000000001',true_seen='0000000000000000',
        claimed=1,committed_mask=1,records={{slot=0,tag=3,raw_hex=string.rep('AB',96)}}}
end
]]..setup:sub(at)
local scenario=[[
advance(11)
local evidence=assert(c.saved.native_hit_tail_diagnostic)
assert(evidence.version=='0.4.25'and evidence.profile_revision=='copy_pending_tail_diagnostic_v1')
assert(evidence.peer==PEER and evidence.epoch==c.epoch and#evidence.records==1 and evidence.records[1].tag==3)
assert(c.addon.native_hit_status().current.accepted==0,'diagnostic cannot add ordinary contacts')
assert(state.ribbons.hit_ricochet==0 and state.ribbons.hit_blocked==0,'diagnostic cannot award ribbons')
local saves=c.saves;local reads=c.diagnostic_reads
advance(5);assert(c.diagnostic_reads<=reads+1,'maximum one diagnostic read per second')
assert(c.saves==saves,'unchanged diagnostic does not flush again')
c.diagnostic_error=true
c.batches[#c.batches+1]=record(1,'blocked')
advance(11)
assert(state.ribbons.hit_blocked==1 and c.addon.native_hit_status().current.accepted==1,'read failure cannot block hit counting')
c.game_state=3;advance(1)
c.game_state=4;advance(11)
assert(state.sequence==2 and c.saved.native_hit_tail_diagnostic.epoch==c.epoch,'fresh epoch replaces diagnostic')
assert(state.ribbons.hit_ricochet==0 and state.ribbons.hit_blocked==0)
c.controller:stop('OWNED_TAIL_ADDON_DONE')
assert(c.controller:status().restored)
print('PASS actual built0.4.25 diagnostic integration: store/scope/1Hz/no repeated save/error isolation/epoch reset; no Game, Windows API or native execution')
]]
assert(loadstring(setup..scenario,'@owned-actual-tail-diagnostic'))()
