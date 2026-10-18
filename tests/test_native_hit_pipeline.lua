-- The binary was drained by owned native x64 code, not encoded in Lua.
package.preload['hd2runtime/core/bytes']=function() return dofile(assert(arg[3])..'/core/bytes.lua') end
local decoder=dofile(assert(arg[1]))
local model=dofile(assert(arg[2]))()
local file=assert(io.open(assert(arg[4]),'rb'))
local raw=file:read('*a');file:close()
local api=decoder.new({peer='FEDCBA9876543210',epoch='0000000000000007',
    accept=function(c,t) return model:accept(c,t) end})
-- Explicit fixture approval. No game connector provides this metadata yet.
local fixture={abi=1,stride=96,count=8,epoch='0000000000000007',
    dropped='0000000000000001',connector_proven=true}
assert(api:consume(raw,1,fixture))
assert(api.accepted==5 and api.unclassified==3 and api.partial==true)
assert(api.last_sequence=='0000000000000008')
assert(model.cumulative.total==5 and model.cumulative.blocked==2)
assert(model.cumulative.penetration==1 and model.cumulative.full_penetration==1)
assert(model.cumulative.ricochet==1 and model.recent.blocked==2)
print('PASS actual owned x64 bytes decode into four classes with one category counter')
assert(model:visible(2.999,false,true)~=nil)
assert(model:visible(3,false,true)==nil)
assert(model:visible(3,true,true).blocked==2)
print('PASS idle two seconds collects; map retains cumulative counts')
assert(api:consume(raw,4,fixture))
assert(api.accepted==5 and api.stale==8 and model.cumulative.total==5)
print('PASS duplicate native drain bytes never replay rewards')
assert(model:visible(4,true,false)==nil and model.cumulative.total==5)
print('PASS hiding the HUD preserves totals')
