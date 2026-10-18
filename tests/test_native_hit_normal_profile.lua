-- The input was produced by actual owned native AP/default/final/qualifier/FIFO.
-- It is a controlled contact fixture; no gameplay connection is implied.
package.preload['hd2runtime/core/bytes']=function()return dofile(assert(arg[3])..'/core/bytes.lua')end
local decoder=dofile(assert(arg[1]))
local model=dofile(assert(arg[2]))()
local file=assert(io.open(assert(arg[4]),'rb'))
local raw=file:read('*a');file:close()
assert(#raw==288)
local api=decoder.new({peer='FEDCBA9876543210',epoch='0000000000000001',
    accept=function(c,t)return model:accept(c,t)end})
for i,delta in ipairs({-1,0,1})do
    local record=assert(decoder.decode(raw,(i-1)*96))
    assert(record.source==1002 and record.target==1001 and record.flags==511)
    assert(record.delta==delta and record.effects==0)
end
local fixture={abi=1,stride=96,count=3,epoch='0000000000000001',
    dropped='0000000000000000',connector_proven=true}
assert(api:consume(raw,10,fixture))
assert(api.accepted==3 and api.unclassified==0 and not api.partial)
assert(model.cumulative.blocked==1 and model.cumulative.penetration==1)
assert(model.cumulative.full_penetration==1 and model.cumulative.total==3)
assert(model:visible(11.99,false,true)~=nil)
assert(model:visible(12,false,true)==nil)
assert(model:visible(12,true,true).total==3)
assert(api:consume(raw,13,fixture))
assert(api.accepted==3 and api.stale==3 and model.cumulative.total==3)
print('PASS native AP/default/final/source/qualifier records -> Lua three classes -> two-second collection')
print('PASS own u64 identity, cumulative map counts, duplicate record rejection')
