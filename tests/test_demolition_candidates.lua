local module=dofile(arg[1])
local function eq(a,b,label)assert(a==b,(label or'')..': '..tostring(a)..' ~= '..tostring(b))end
local function put(raw,at,value,bytes)
    local chars={};for i=1,bytes do chars[i]=string.char(value%256);value=math.floor(value/256)end
    return raw:sub(1,at)..table.concat(chars)..raw:sub(at+bytes+1)
end
local function row(seq,unit,peer_hi)
    local raw=string.rep('\0',128)
    for _,x in ipairs({{0,0x100000,8},{8,0xFFFFFFFF,4},{12,peer_hi or 0x76543210,4},
        {0x28,7,4},{0x40,0xFFFFFFFF,4},{0x44,peer_hi or 0x76543210,4},
        {0x50,unit or 901,4},{0x58,1,1},{0x5c,unit or 901,4},
        {0x63,1,1},{0x64,3,1},{0x68,seq or 1,4}})do raw=put(raw,x[1],x[2],x[3])end
    return raw
end
local raw=row()
local decoded=assert(module.decode(raw))
eq(decoded.world,0x100000);eq(decoded.record_index,7);eq(decoded.stage_transition,true)
eq(decoded.local_peer,'76543210FFFFFFFF');eq(decoded.source_peer_candidate,'76543210FFFFFFFF')
eq(decoded.creditor_verified,false);eq(decoded.ribbon_eligible,false)
eq(module.decode(raw:sub(2)),nil)
eq(module.decode(put(raw,0x28,0x17000,4)),nil)
for _,change in ipairs({{0x50,0,4},{0x5c,902,4},{0x57,1,1},{0x58,0,1},
    {0x63,0,1},{0x64,0,1},{0x48,1,1}})do
    eq(assert(module.decode(put(raw,change[1],change[2],change[3]))).stage_transition,false,'transition gate')
end

local descriptors,lookup_count,world_pointer={},0,0x100000
for i=1,40 do descriptors[i]={resource=i==1 and'HOLE'or'DECORATION',unit=900+i,entity=500+i}end
local world={game=0x180000000,view={slot=function()return{}end}}
local source={
    destructibles=function()
        return {world=world_pointer,count=#descriptors,
            pointers={ptr=function(_,at)return at/8+1 end},
            indices={i32=function(_,at)return at/4+7 end}}
    end,
    destructible_descriptor=function(_,p)lookup_count=lookup_count+1;return descriptors[p]end,
    bug_hole_kind=function(resource)return resource=='HOLE'and'warrior'or nil end,
}
local emitted={}
local observer=module.new({world_api=source,emit=function(r)emitted[#emitted+1]=r end})
assert(observer:refresh(world,1));eq(lookup_count,32,'descriptor cap')
eq(observer.diagnostics.descriptor_count,40);eq(observer.diagnostics.cached_descriptors,32)
eq(observer.diagnostics.known_holes,1);eq(observer.diagnostics.pending_descriptors,8)
eq(observer.diagnostics.incomplete,true)
assert(observer:refresh(world,1.1));eq(lookup_count,32,'4 Hz throttle')
assert(observer:refresh(world,1.25));eq(lookup_count,40,'finish current descriptors')
eq(observer.diagnostics.cached_descriptors,40);eq(observer.diagnostics.pending_descriptors,0)
eq(observer.diagnostics.incomplete,false);eq(observer.diagnostics.known_holes,1,'existing hole survives refresh')
local event=assert(observer:accept(raw,0x100000,'76543210FFFFFFFF'))
eq(event.target_verified,true);eq(event.target_kind,'warrior');eq(event.candidate_matches_local,true)
eq(event.ribbon_eligible,false,'candidate is never a personal award')
eq(#emitted,1)
eq(observer:accept(raw,0x100000,'76543210FFFFFFFF'),nil,'dedupe')
eq(observer:accept(row(2),0x100000,'76543211FFFFFFFF'),nil,'full peer differs despite same low bits')
local unknown=assert(observer:accept(row(2,902),0x100000,'76543210FFFFFFFF'))
eq(unknown.target_verified,false,'record/unit mismatch')
eq(observer.diagnostics.unit_mismatch,1)

-- A descriptor slot and index reused by a new world must not keep its kind.
world_pointer=0x200000;descriptors[1]={resource='DECORATION',unit=901,entity=501}
assert(observer:refresh(world,1.5));eq(observer:accept(raw,0x100000,'76543210FFFFFFFF'),nil)
local fresh=assert(observer:accept(put(raw,0,0x200000,8),0x200000,'76543210FFFFFFFF'))
eq(fresh.target_verified,false,'new-world type invalidates cache')
for i=2,8 do assert(observer:accept(put(row(i),0,0x200000,8),0x200000,'76543210FFFFFFFF'))end
eq(observer:accept(put(row(9),0,0x200000,8),0x200000,'76543210FFFFFFFF'),nil,'bounded unknown receipts')
-- Unknown scenery must never consume the reserved 32 hole receipts.
observer:reset();world_pointer=0x100000;descriptors[1]={resource='HOLE',unit=901,entity=501}
assert(observer:refresh(world,2))
for i=1,8 do assert(observer:accept(row(i,902),0x100000,'76543210FFFFFFFF'))end
eq(observer:accept(row(9,902),0x100000,'76543210FFFFFFFF'),nil,'unknown cap')
for i=10,41 do assert(observer:accept(row(i),0x100000,'76543210FFFFFFFF'))end
eq(observer:accept(row(42),0x100000,'76543210FFFFFFFF'),nil,'hole cap')
eq(observer.diagnostics.samples,40);eq(observer.diagnostics.holes,32);eq(observer.diagnostics.unknown,8)
-- A failed refresh keeps its status when the next frame is throttled.
local original_list=source.destructibles
source.destructibles=function()return nil,'PIN_FAILED'end
local ok,why=observer:refresh(world,3)
eq(ok,nil);eq(why,'PIN_FAILED');eq(observer.diagnostics.ready,false);eq(observer.diagnostics.world,nil)
ok,why=observer:refresh(world,3.1);eq(ok,nil);eq(why,'PIN_FAILED','throttled failure remains failed')
source.destructibles=original_list
assert(observer:refresh(world,3.25));eq(observer.diagnostics.ready,true);eq(observer.diagnostics.reason,nil)
source.destructibles=function()error('fixture adapter failure')end
eq(pcall(observer.refresh,observer,world,4),false)
ok,why=observer:refresh(world,4.1);eq(ok,nil);eq(why,'DESTRUCTION_REFRESH_INCOMPLETE')
source.destructibles=original_list
observer:reset();eq(observer.diagnostics.world,nil);eq(observer.diagnostics.ready,false)
eq(observer.diagnostics.receipts_seen,0);eq(observer.diagnostics.known_holes,0)

-- A late descriptor is not silently reclassified: summary exposes the exact
-- missing-target window until its slot is visited in the next bounded poll.
descriptors[1]={resource='DECORATION',unit=901,entity=501}
descriptors[40]={resource='HOLE',unit=940,entity=540}
assert(observer:refresh(world,5))
eq(observer.diagnostics.pending_descriptors,8);eq(observer.diagnostics.known_holes,0)
local late=put(row(100,940),0x28,46,4)
eq(assert(observer:accept(late,0x100000,'76543210FFFFFFFF')).target_verified,false)
eq(observer.diagnostics.target_missing,1)
assert(observer:refresh(world,5.25))
eq(observer.diagnostics.known_holes,1);eq(observer.diagnostics.pending_descriptors,0)
local _,duplicate_reason=observer:accept(late,0x100000,'76543210FFFFFFFF')
eq(duplicate_reason,'RECEIPT_DUPLICATE','no retrospective promotion of saved unknown row')
eq(assert(observer:accept(put(late,0x68,101,4),0x100000,'76543210FFFFFFFF')).target_verified,true)
print('demolition diagnostics: transitions/full peer/target linkage/cache lifecycle/bounds PASS')
