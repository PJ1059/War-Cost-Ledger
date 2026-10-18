-- The actual addon observation helpers + actual candidate/descriptor modules.
-- Only world IO, normal-hit session and already-tested native drain boundaries
-- are fixtures; no Game process or native function is called.
local root=assert(arg[1])
local function read(path)local f=assert(io.open(root..'/'..path,'rb'));local s=f:read('*a');f:close();return s end
local addon=read('src/addon.lua')
local first=assert(addon:find('local function observe_demolition_interface(',1,true))
local last=assert(addon:find('local function flush(',first,true))
local helpers=addon:sub(first,last-1)
local candidates=dofile(root..'/src/demolition-candidates.lua')
local worldmodule=dofile(root..'/src/demolition-world.lua')
local function eq(a,b,label)assert(a==b,(label or'')..': '..tostring(a)..' ~= '..tostring(b))end
local function clone(v)if type(v)~='table'then return v end;local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out end
local function put(raw,at,value,size)
    local chars={};for i=1,size do chars[i]=string.char(value%256);value=math.floor(value/256)end
    return raw:sub(1,at)..table.concat(chars)..raw:sub(at+size+1)
end
local PEER='F1234567FFFFFFFF'
local function wire(hex)return(hex:gsub('..',function(pair)return string.char(tonumber(pair,16))end)):reverse()end
local gamebase,destruction=0x180000000,0x200000
local function row(sequence,unit,other)
    local r=string.rep('\0',128)
    for _,x in ipairs({{0,destruction,8},{0x28,7,4},{0x50,unit or 901,4},
        {0x58,1,1},{0x5c,unit or 901,4},{0x63,1,1},{0x64,3,1},{0x68,sequence,4}})do
        r=put(r,x[1],x[2],x[3])
    end
    r=r:sub(1,8)..wire(PEER)..r:sub(17)
    r=r:sub(1,0x40)..wire(other and'01234567FFFFFFFF'or PEER)..r:sub(0x49)
    return r
end
local manager,descriptor=0x100000,0x300000
local descriptor_bytes=string.rep('\0',24)
for _,x in ipairs({{0,0x759CBD61},{4,0x8C31B749},{8,501},{12,901}})do
    descriptor_bytes=put(descriptor_bytes,x[1],x[2],4)
end
local unavailable,throws=false,false
local view={slot=function()return{}end,proves=function()return true end}
function view.pointer(at)
    if throws then error('fixture descriptor adapter failure')end
    if unavailable then return nil end
    if at==gamebase+0x3326550 then return manager end
    eq(at,gamebase+0x346D528);return destruction
end
function view.u32(at)eq(at,manager+12);return 1 end
function view.fill(_,at,size)
    if at==manager+0x4030 then eq(size,8);return{ptr=function()return descriptor end}end
    eq(at,manager+0x6030);eq(size,4);return{i32=function()return 7 end}
end
function view.read(at,size)eq(at,descriptor);eq(size,24);return descriptor_bytes end
local world={game=gamebase,view=view}
local saved,pending,main_calls,tail_calls,normal_hits={}, {},0,0,0
local store_writes,persist_calls=0,0
local header={dropped=0,rejected=0,sequence=12,batches=10,scanned=1}
local snapshot_throw=false
local state={sequence=1,stats_baseline={},ribbons={demolition=7,hit_blocked=0},kills=41,total_cents=900}
local handle={}
local session={}
function session:set_handle(h)eq(h,handle);return true end
function session:tick(_,obs)
    main_calls=main_calls+1
    if obs.mission then self.current={sequence=obs.sequence,peer=PEER,epoch=string.format('%016X',obs.sequence)}
    else self.last=self.current or self.last;self.current=nil end
    state.ribbons.hit_blocked=state.ribbons.hit_blocked+normal_hits;normal_hits=0
    return true
end
local connector={}
function connector.demolition_snapshot(h,peer,epoch)
    eq(h,handle);eq(peer,PEER)
    if snapshot_throw then error('fixture drain failure')end
    local records=pending;pending={}
    return{epoch=epoch,peer=peer,records=records,dropped=header.dropped,rejected=header.rejected,
        sequence=header.sequence,batches=header.batches,scanned=header.scanned}
end
function connector.diagnostic_snapshot()
    tail_calls=tail_calls+1;return nil,'NO_TAIL_DIAGNOSTIC'
end
local env=setmetatable({state=state,hud_time=0,hit_session=session,hit_connector=connector,
    hit_copy_host={handle=function()return handle end,tick=function()return{phase='running'}end},
    demolition_candidates=candidates.new({world_api=worldmodule.create({source={gameDllSha256=worldmodule.game_sha256}})}),
    demolition_next_at=0,hit_tail_diag_next_at=0,VERSION='fixture',CODE_COPY_PROBE_SOURCE_SHA='fixture',
    store={set=function(_,key,value)saved[key]=clone(value);store_writes=store_writes+1 end},
    persist=function()persist_calls=persist_calls+1 end}, {__index=_G})
local compiled=assert(loadstring(helpers..'\nreturn observe_hit_interface','@addon-demolition-observation'))
setfenv(compiled,env);local observe=compiled()
local mission=true
local function tick(dt)
    env.hud_time=env.hud_time+(dt or 1.1)
    header.batches=header.batches+1 -- Native empty frames also advance this heartbeat.
    observe(world,{state=mission and 4 or 3,mission=mission},{{['local']=true,peer=PEER}})
end
pending={row(1)};normal_hits=2;tick()
local evidence=assert(saved.native_demolition_diagnostic)
eq(#evidence.records,1);eq(evidence.records[1].target_kind,'warrior')
eq(evidence.records[1].candidate_matches_local,true);eq(evidence.records[1].ribbon_eligible,false)
eq(#evidence.records[1].raw_hex,256);eq(state.ribbons.hit_blocked,2)
eq(state.ribbons.demolition,7);eq(state.kills,41);eq(state.total_cents,900)
tick();eq(#saved.native_demolition_diagnostic.records,1,'empty drain does not duplicate')
local before_idle=store_writes;tick()
eq(store_writes,before_idle,'same state and native heartbeat alone do not write')
pending={row(1),row(2,nil,true)};tick()
eq(#saved.native_demolition_diagnostic.records,2,'dedupe and different full peer')
eq(saved.native_demolition_diagnostic.records[2].candidate_matches_local,false)

for i=3,12 do pending[#pending+1]=row(i,902)end;tick()
eq(#saved.native_demolition_diagnostic.unknown_records,8,'unknown limit')
-- The old addon saved only when a row was added; after eight unknowns the
-- following real counters were silently lost even though draining continued.
local before_full=store_writes
pending={row(99,902)};header.sequence=99;header.dropped=4;header.rejected=1;normal_hits=1;tick()
evidence=saved.native_demolition_diagnostic
eq(#evidence.unknown_records,8);eq(evidence.sequence,99,'full unknown budget still saves latest header')
eq(evidence.dropped,4);eq(evidence.rejected,1);eq(store_writes,before_full+1)
eq(evidence.candidate_summary.unknown_limit,3,'bounded summary records discarded unknown rows')
eq(evidence.candidate_summary.descriptor_count,1);eq(evidence.candidate_summary.known_holes,1)
eq(evidence.candidate_summary.incomplete,false);eq(state.ribbons.hit_blocked,3)
local before_header=store_writes
header.sequence=100;header.dropped=5;header.rejected=2;tick()
evidence=saved.native_demolition_diagnostic
eq(evidence.sequence,100,'empty drain with changed header persists')
eq(evidence.dropped,5);eq(evidence.rejected,2);eq(evidence.batches,header.batches)
eq(store_writes,before_header+1)
local before_repeat=store_writes;tick()
eq(store_writes,before_repeat,'unchanged empty drain is not written again')
for i=13,42 do pending[#pending+1]=row(i)end;tick()
for i=43,52 do pending[#pending+1]=row(i)end;tick()
eq(#saved.native_demolition_diagnostic.records,32,'reserved hole budget')

-- Descriptors disappearing or throwing cannot consume another normal-hit tick
-- or suppress the tail step; successful empty drains cannot mask target errors.
unavailable=true;normal_hits=3;tick()
eq(state.demolition_diagnostic_reason,'DESTRUCTION_MANAGER_UNREADABLE')
eq(saved.native_demolition_diagnostic.candidate_summary.ready,false)
eq(saved.native_demolition_diagnostic.candidate_summary.reason,'DESTRUCTION_MANAGER_UNREADABLE')
eq(state.ribbons.hit_blocked,6)
throws=true;local before=tail_calls;normal_hits=4;tick()
assert(state.demolition_diagnostic_reason:find('DEMOLITION_OBSERVER_FAILED:',1,true))
eq(state.ribbons.hit_blocked,10);eq(tail_calls,before+1,'tail survives descriptor exception')
throws=false;unavailable=false;snapshot_throw=true;normal_hits=1;tick()
eq(state.demolition_diagnostic_reason,'DEMOLITION_DIAGNOSTIC_READ_FAILED')
eq(state.ribbons.hit_blocked,11)
snapshot_throw=false;tick();eq(state.demolition_diagnostic_reason,nil)

mission=false;tick();eq(session.current,nil)
state.sequence=2;mission=true;pending={row(1)};tick()
evidence=saved.native_demolition_diagnostic
eq(evidence.epoch,'0000000000000002');eq(#evidence.records,1);eq(#evidence.unknown_records,0)
eq(env.demolition_candidates.diagnostics.samples,1,'new mission clears limit and dedupe')
eq(state.ribbons.demolition,7);eq(state.kills,41);eq(state.total_cents,900)
eq(persist_calls,store_writes,'one batched dirty signal per changed evidence write')
print('PASS addon demolition observation: real helpers/adapter/candidates, 32+8 bounds, current headers after cap/empty drain, unchanged idle suppression, bounded target summary, full-peer evidence, no awards, exception isolation, normal-hit continuity, next-mission reset ('..main_calls..' ticks)')
