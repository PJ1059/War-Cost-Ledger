-- Reuse complete actual-reader scenarios; intercept only the presentation API
-- to verify fuel and discarded magazines emit exactly the existing debit.
local input=assert(io.open(assert(arg[4]),'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local replacement=[[
local module=dofile(addon); local state=module.state
local charges=assert(module.charge_notifications)
local original_emit=charges.emit
local emitted,emits,last_name=0,0,nil
function charges:emit(key,name,amount,now)
    emitted=emitted+amount;emits=emits+1;last_name=name
    return original_emit(self,key,name,amount,now)
end
]]
local at=assert(source:find('local module=dofile(addon); local state=module.state',1,true))
local suffix=at+#'local module=dofile(addon); local state=module.state'
source=source:sub(1,at-1)..replacement..source:sub(suffix)
local needle='frame(0.1); checks=checks+1'
local begin=assert(source:find(needle,1,true))
local validation=[[
local before=state.total_cents
local old_sequence=state.sequence
emitted=0
frame(0.1); checks=checks+1
if old_sequence==state.sequence then
    assert(emitted==state.total_cents-before,'every actual debit must emit exactly once at check '..checks)
else assert(emitted==state.total_cents,'new mission cannot replay old fees') end
]]
source=source:sub(1,begin-1)..validation..source:sub(begin+#needle)
source=source..[[
assert(emits>0 and last_name:find('燃料'))
print('PASS: built real-reader fuel consumption and discarded-magazine scenarios emit precisely existing debits; refills, duplicate polls, unavailable readings and zero-new-SHOTS reloads remain correct.')
]]
assert(loadstring(source,'@charge-discard-integration'))()
