local module=dofile(arg[1])
local upstream=dofile(arg[2])
local function eq(a,b,label)assert(a==b,(label or'')..': '..tostring(a)..' ~= '..tostring(b))end
local function bytes(n,size)
    local out={};for i=1,size do out[i]=string.char(n%256);n=math.floor(n/256)end
    return table.concat(out)
end
local count,unreadable,bad_pin=2,false,false
local calls={pins=0,read=0,fill=0,pointer=0}
local game,manager,world_pointer=0x180000000,0x100000,0x200000
local pins={};for _,p in ipairs(upstream.pins)do pins[p.rva]=p.hex end
for _,p in ipairs(module.pins)do eq(pins[p[1]],p[2],'exact upstream pin')end
local raw=bytes(0x759CBD61,4)..bytes(0x8C31B749,4)..bytes(701,4)..bytes(901,4)..bytes(1,4)..bytes(1,4)
local pointers,indices={},{}
local view={
    proves=function(at,pin)
        calls.pins=calls.pins+1;eq(pins[at-game],pin);return not bad_pin
    end,
    pointer=function(at)
        calls.pointer=calls.pointer+1
        if at==game+upstream.destruction.global then return manager end
        eq(at,game+upstream.destruction.world);return world_pointer
    end,
    u32=function(at)eq(at,manager+upstream.destruction.count);return count end,
    fill=function(block,at,length)
        calls.fill=calls.fill+1
        if at==manager+upstream.destruction.descriptors then eq(length,count*8);eq(block,pointers)
        else eq(at,manager+upstream.destruction.worldIndex);eq(length,count*4);eq(block,indices)end
        return not unreadable and block or nil
    end,
    read=function(at,size)calls.read=calls.read+1;eq(at,0x300000);eq(size,24);return not unreadable and raw or nil end,
}
local world={game=game,view=view}
-- Simulate installed 0.30.3 schema: no destruction entries or APIs are present.
local old_schema={source={gameDllSha256=upstream.source.gameDllSha256}}
local api=module.create(old_schema)
local list=assert(api.destructibles(world,pointers,indices))
eq(list.count,2);eq(list.world,world_pointer);eq(calls.pins,#module.pins);eq(calls.fill,2)
local d=assert(api.destructible_descriptor(world,0x300000))
eq(d.resource,'8C31B749759CBD61');eq(d.entity,701);eq(d.unit,901);eq(d.owned,nil,'no player attribution')
eq(calls.pins,#module.pins,'pins once per proven world')
for resource,kind in pairs(upstream.destruction.holes)do eq(api.bug_hole_kind(resource),kind,'official hole catalog')end
eq(api.bug_hole_kind('0000000000000000'),nil)
count=0;assert(api.destructibles(world,pointers,indices));eq(calls.fill,2,'empty skips arrays')
count=1025;eq(api.destructibles(world,pointers,indices),nil);eq(calls.fill,2,'bounded arrays')
count=2;unreadable=true;eq(api.destructibles(world,pointers,indices),nil)
eq(api.destructible_descriptor(world,0x300000),nil)
local previous_pins,previous_pointer=calls.pins,calls.pointer
eq(module.create({source={gameDllSha256='different'}}).destructibles(world,pointers,indices),nil)
eq(calls.pins,previous_pins);eq(calls.pointer,previous_pointer,'wrong build reads nothing')
bad_pin=true;eq(module.create(old_schema).destructibles(world,pointers,indices),nil)
eq(calls.pointer,previous_pointer,'wrong pin reads no live manager')
print('demolition world adapter: upstream parity/Runtime 0.30.3/bounds/unreadable/build pins PASS')
