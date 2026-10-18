-- Read-only subset of HD2Runtime 0.31.3's destruction descriptor API for the
-- installed 0.30.3 Runtime. Source: SkyeShade/HD2Runtime runtime/event_world.lua
-- (destructibles/destructible_descriptor/bug_hole_kind) and domains/event_natives.lua,
-- frozen in dist/career-stats-source-audit/upstream. Uses Runtime's proven world
-- and ReadProcessMemory-backed view; never dereferences a Lua FFI game pointer.
-- Descriptor ownership means network authority, NOT who closed the hole.
local M={}
M.game_sha256='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
M.pins={
    {0x526646,'488b1d03ffdf02'}, -- manager global
    {0x526691,'ff430c'}, -- instance count
    {0x5266f0,'4f8994c130400000'}, -- descriptor pointers +0x4030
    {0x88330b,'418984b630600000'}, -- destruction record indices +0x6030
    {0x8835cb,'8b500c'}, -- descriptor unit
    {0x88384c,'8b5008'}, -- descriptor entity
    {0x13e1b64,'4c8b1dbdb90802'}, -- destruction world global
}
-- The stage getter/writer pins are separate so the older diagnostic-only
-- descriptor consumer keeps exactly its previous API and proof contract.
M.record_pins={
    {0x13e1bdf,'488d0449'},
    {0x13e1be3,'410fb684837f5f0c00'},
    {0x13e2037,'41884707'},
    {0x13e2161,'8b9c96785f0c00'},
}
-- Both the local enqueue caller and network handler accept records below
-- 0x17C00. 0x17000 is only the static packed-stage split inside enqueue.
-- Real ordinary holes captured on 2026-10-16 use 0x17026..0x17030.
M.record_bound_pins={
    {0x13E1512,'4181f8007c0100'},
    {0xBBA67E,'4181f8007c0100'},
}
M.record_stride=12
M.max_records=0x17C00
local holes={
    ['095686275A113614']='shrieker',['0DF874E208040D2F']='base',
    ['36CC8EAD2BB18D78']='hiveguard',['3A2CEF12ED32A088']='bile_titan',
    ['4776A1CF3F19A13B']='stalker',['7E4C6B45BCC45C3F']='warrior_captive',
    ['8901F188DB366B4B']='scavenger',['8C31B749759CBD61']='warrior',
    ['97DD3178E9F0AB70']='prowler',['9B58C95349D051F9']='spitter',
    ['9D8632A79C2D9789']='warrior_tutorial',['B6A181ADCF547AEB']='warrior_ceiling',
    ['BC2AF8548C6D5E06']='hunter',['D666AA61D804D311']='scavenger_captive',
    ['F78BF0FF5C62140D']='boomer',
}
local function u32(raw,at)
    local a,b,c,d=raw:byte(at+1,at+4)
    return d and a+b*256+c*65536+d*16777216 or nil
end
function M.create(native_schema)
    native_schema=native_schema or require('hd2runtime/domains/event_natives')
    local api,proven,records_proven={},nil,nil
    local function prove(world)
        if (native_schema.source or{}).gameDllSha256~=M.game_sha256 then return nil,'DESTRUCTION_BUILD_MISMATCH'end
        if not world or type(world.view)~='table'or type(world.view.proves)~='function'then
            return nil,'DESTRUCTION_VERIFIED_WORLD_REQUIRED'
        end
        if proven==world then return true end
        for _,p in ipairs(M.pins)do
            if not world.view.proves(world.game+p[1],p[2])then
                return nil,'DESTRUCTION_PIN_'..string.format('%X',p[1])
            end
        end
        proven=world
        return true
    end
    function api.destructibles(world,pointer_block,index_block)
        local ok,why=prove(world);if not ok then return nil,why end
        local manager=world.view.pointer(world.game+0x3326550)
        local destruction=world.view.pointer(world.game+0x346D528)
        if not manager or not destruction then return nil,'DESTRUCTION_MANAGER_UNREADABLE'end
        local count=world.view.u32(manager+12)
        if type(count)~='number'or count%1~=0 or count<0 or count>1024 then return nil,'DESTRUCTION_COUNT'end
        local list={count=count,world=destruction}
        if count==0 then return list end
        list.pointers=world.view.fill(pointer_block,manager+0x4030,count*8)
        list.indices=world.view.fill(index_block,manager+0x6030,count*4)
        if not list.pointers or not list.indices then return nil,'DESTRUCTION_ARRAYS_UNREADABLE'end
        return list
    end
    function api.destructible_descriptor(world,pointer)
        local ok,why=prove(world);if not ok then return nil,why end
        local raw=pointer and world.view.read(pointer,24)
        if type(raw)~='string'or#raw~=24 then return nil,'DESTRUCTION_DESCRIPTOR_UNREADABLE'end
        return {resource=string.format('%08X%08X',u32(raw,4),u32(raw,0)),
            entity=u32(raw,8),unit=u32(raw,12)}
    end
    function api.destruction_records(world,list,first,last,block)
        local ok,why=prove(world);if not ok then return nil,why end
        if records_proven~=world then
            for _,p in ipairs(M.record_pins)do
                if not world.view.proves(world.game+p[1],p[2])then return nil,'DESTRUCTION_RECORD_PIN'end
            end
            for _,p in ipairs(M.record_bound_pins)do
                if not world.view.proves(world.game+p[1],p[2])then return nil,'DESTRUCTION_RECORD_BOUND_PIN'end
            end
            records_proven=world
        end
        if type(list)~='table'or type(list.world)~='number'
            or type(first)~='number'or first%1~=0 or first<0
            or type(last)~='number'or last%1~=0 or last<first or last>=M.max_records
            or last-first+1>4096 then
            return nil,'DESTRUCTION_RECORD_RANGE'
        end
        return world.view.fill(block,list.world+0xC5F78+first*12,(last-first+1)*12)
    end
    function api.destruction_record(records,offset)
        if not records or type(offset)~='number'or offset<0 or offset%12~=0 then return nil end
        local unit,stage,flags=records:u32(offset),records:u8(offset+7),records:u8(offset+8)
        if type(unit)~='number'or type(stage)~='number'or type(flags)~='number'then return nil end
        return unit,stage,flags%2==1
    end
    -- This is the official unit-position path including level units (Titan
    -- holes). Validate generations, object unit and the scene-graph method;
    -- the position is the hole's own root, never a player/explosion fallback.
    function api.unit_position(world,unit,level)
        local ok,why=prove(world);if not ok then return nil,why end
        if type(unit)~='number'or unit%1~=0 or unit<=0 or unit>=4294967296
            or type(world.exe)~='number'then return nil,'DESTRUCTION_UNIT'end
        local E=native_schema.engine
        if type(E)~='table'then return nil,'DESTRUCTION_ENGINE_SCHEMA'end
        local index,generation=unit%4194304,math.floor(unit/4194304)%256
        local registry=world.view.pointer(world.exe+E.units)
        if not registry then return nil end
        local count=world.view.u32(registry+E.unitCount)
        local generations=world.view.pointer(registry+E.unitGenerations)
        local objects=world.view.pointer(registry+E.unitObjects)
        if not count or not generations or not objects or index>=count then return nil end
        local current=world.view.read(generations+index,1)
        if not current or current:byte()~=generation then return nil end
        local object=world.view.pointer(objects+index*8)
        if not object or world.view.u32(object+E.unitId)~=unit then return nil end
        local vtable=world.view.pointer(object)
        local method=vtable and world.view.pointer(vtable+0xE8)
        local scene_offset
        if level and vtable==world.exe+23556320 and method==world.exe+2927696
            and world.view.proves(method,'488d4148c3')then scene_offset=72
        elseif method==world.exe+E.sceneGraphMethod and world.view.proves(method,E.sceneGraphMethodBytes)then
            scene_offset=E.sceneGraphOffset
        else return nil end
        local poses=world.view.pointer(object+scene_offset+E.poses)
        local raw=poses and world.view.read(poses+E.translation,12)
        if type(raw)~='string'or#raw~=12 then return nil end
        local bytes=require('hd2runtime/core/bytes')
        local x,y,z=bytes.value(raw,0,'f32'),bytes.value(raw,4,'f32'),bytes.value(raw,8,'f32')
        if x~=x or y~=y or z~=z or math.abs(x)>100000 or math.abs(y)>100000 or math.abs(z)>100000 then return nil end
        return {x=x,y=y,z=z}
    end
    function api.bug_hole_kind(resource)return holes[resource]end
    return api
end
return M
