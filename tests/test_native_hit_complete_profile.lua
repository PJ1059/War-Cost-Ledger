-- Four records from owned native normal/physical paths, not Lua-built records.
package.preload['hd2runtime/core/bytes']=function()return dofile(assert(arg[3])..'/core/bytes.lua')end
local decoder=dofile(assert(arg[1]))
local model=dofile(assert(arg[2]))()
local file=assert(io.open(assert(arg[4]),'rb'))
local raw=file:read('*a');file:close();assert(#raw==384)
local api=decoder.new({peer='FEDCBA9876543210',epoch='0000000000000001',
    accept=function(c,t)return model:accept(c,t)end})
local expected={'blocked','penetration','full_penetration','ricochet'}
for i,result in ipairs(expected)do
    local record=assert(decoder.decode(raw,(i-1)*96))
    assert(record.source==1002 and record.target==1001)
    assert(record.branch==(i==4 and 2 or 1) and record.flags==(i==4 and 323 or 511))
    assert(decoder.classify(record,'FEDCBA9876543210','0000000000000001').result==result)
end
local fixture={abi=1,stride=96,count=4,epoch='0000000000000001',
    dropped='0000000000000000',connector_proven=true}
assert(api:consume(raw,10,fixture))
assert(api.accepted==4 and api.unclassified==0 and not api.partial)
assert(model.cumulative.total==4)
for _,key in ipairs(expected)do assert(model.cumulative[key]==1 and model.recent[key]==1)end
assert(model:visible(11.99,false,true)~=nil and model:visible(12,false,true)==nil)
assert(model:visible(12,true,true).total==4)
assert(api:consume(raw,13,fixture))
assert(api.accepted==4 and api.stale==4 and model.cumulative.total==4)
print('PASS owned native normal/true physical -> four Lua classes -> one counter per class')
print('PASS two-second collection, map totals and duplicate rejection')
