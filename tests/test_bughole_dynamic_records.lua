-- Replay real descriptor and 12-byte destruction records across the user's
-- single ordinary-hole closure. Native memory is replaced by owned bytes.
local observer_module=dofile(assert(arg[1]))
local native_module=dofile(assert(arg[2]))
local fixture=dofile(assert(arg[3]))
local function eq(a,b,label)assert(a==b,(label or'')..': '..tostring(a)..' ~= '..tostring(b))end
local function unhex(hex)return(hex:gsub('..',function(x)return string.char(tonumber(x,16))end))end
local function u32(raw,offset)
    local a,b,c,d=raw:byte(offset+1,offset+4)
    return a+b*256+c*65536+d*16777216
end
eq(#fixture.records,11);eq(fixture.expected_closures,1)
local game,manager,destruction=0x180000000,0x20000000,0x30000000
local pins={}
for _,group in ipairs({native_module.pins,native_module.record_pins,native_module.record_bound_pins or{}})do
    for _,pin in ipairs(group)do pins[pin[1]]=pin[2]end
end
local by_index,by_pointer={},{}
for i,row in ipairs(fixture.records)do
    assert(row.record_index>=0x17000 and row.record_index<0x17C00)
    by_index[row.record_index]=row;by_pointer[0x40000000+i*24]=row
end
local closed=false
local view={slot=function()return{}end,
    proves=function(at,hex)eq(pins[at-game],hex,'actual native pin');return true end,
    pointer=function(at)
        if at==game+0x3326550 then return manager end
        eq(at,game+0x346D528);return destruction
    end,
    u32=function(at)eq(at,manager+12);return #fixture.records end,
    read=function(at,size)
        local row=assert(by_pointer[at],'only captured descriptor addresses are readable')
        eq(size,24);return unhex(row.descriptor_hex)
    end,
    fill=function(block,at,length)
        if at==manager+0x4030 then
            eq(length,#fixture.records*8)
            return{ptr=function(_,offset)return 0x40000000+(offset/8+1)*24 end}
        end
        if at==manager+0x6030 then
            eq(length,#fixture.records*4)
            return{i32=function(_,offset)return fixture.records[offset/4+1].record_index end}
        end
        local first=(at-destruction-0xC5F78)/12
        assert(first%1==0 and first>=0x17000 and first+length/12<=0x17C00)
        local function record(offset)
            local row=assert(by_index[first+math.floor(offset/12)],'only captured record indices are readable')
            return unhex(closed and row.after_hex or row.before_hex),offset%12
        end
        return{u32=function(_,offset)local raw,o=record(offset);return u32(raw,o)end,
            u8=function(_,offset)local raw,o=record(offset);return raw:byte(o+1)end}
    end,
}
local world={game=game,view=view}
local adapter=native_module.create({source={gameDllSha256=native_module.game_sha256}})
local observer=observer_module.new({world_api=adapter})
eq(#assert(observer:step(world,1,1)),0,'captured open-hole baseline')
eq(observer.diagnostics.known_holes,11,'all actual dynamic holes must be discovered')
closed=true
local rows=assert(observer:step(world,1.25,1))
eq(#rows,1,'the same actual single closure must report once')
eq(rows[1].record_index,0x17026);eq(rows[1].unit,4194819)
eq(rows[1].resource,'8901F188DB366B4B');eq(rows[1].stage,1)
eq(rows[1].creditor_verified,false,'record discovery is not killer identity')
eq(#assert(observer:step(world,1.5,1)),0,'same captured closed record must not replay')
eq(native_module.max_records,0x17C00,'both real caller bounds')
eq(adapter.destruction_records(world,{world=destruction},0x17C00,0x17C00,{}),nil,'native capacity remains bounded')
print('real dynamic ordinary-hole replay: 11 native descriptors at 0x17026..0x17030; exactly one observed 0->1 closure PASS')
