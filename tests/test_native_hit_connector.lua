-- Native pointers refer to pages in this very test process, retained by Python.
local root,sdk,description=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.preload['hd2runtime/core/bytes']=function()return dofile(sdk..'/core/bytes.lua')end
package.preload['hd2runtime/runtime/windows_ffi']=function()return dofile(sdk..'/runtime/windows_ffi.lua')end
local spec=dofile(description)
local connector=dofile(root..'/src/native-hit-connector.lua')
local decoder=dofile(root..'/src/native-hit-feedback.lua')
local model=dofile(root..'/src/hit-feedback.lua')()
local options={peer=spec.peer,epoch=spec.epoch,decoder=decoder,accept=function(c,t)return model:accept(c,t)end}
local uncertified={abi=1,stride=96,bridge=spec.bridge,consumer=spec.consumer,capacity=8,lifetime={}}
assert(connector.attach(uncertified,options)==nil)
spec.native_certified=true;spec.lifetime={owned_fixture=true}
local c=assert(connector.attach(spec,options))
assert(c:step(-1)==nil and c:step(math.huge)==nil and c.drains==0,
    'invalid clock must not drain the native queue')
assert(c:step(10))
assert(c.records==4 and c.decoder.accepted==4 and c.decoder.unclassified==0)
for _,key in ipairs({'blocked','penetration','full_penetration','ricochet'})do assert(model.cumulative[key]==1)end
assert(c:step(10.1) and c.records==4 and c.drains==2,'empty native drain replayed records')
assert(c:step(9)==nil and c.drains==2,'a rewound clock must not consume native records')
assert(model:visible(12,false,true)==nil and model:visible(12,true,true).total==4)
c:detach();assert(c:step(12.1)==nil and c.drains==2)
local wrong={peer=spec.peer,epoch='0000000000000008',decoder=decoder,accept=options.accept}
assert(connector.attach(spec,wrong)==nil)
print('PASS real game LuaJIT FFI calls owned native drain -> four classes; one preallocated 64-record buffer')
print('PASS empty queue no replay, exact u64 peer/epoch, invalid handle rejection, detach and two-second fold')
