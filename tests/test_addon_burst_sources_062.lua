-- Real addon ingestion: native KILLS and per-source counters need not arrive
-- in the same 10 Hz snapshot. All IO is the existing owned integration fixture.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local f=assert(io.open(fixture,'rb'));local text=f:read('*a'):gsub('\r\n','\n');f:close()
local boundary=assert(text:find('state=dofile(path).state',1,true))
local scenario=[[
local CANNON,MG='1FA1F596769225C2','439F9E65C18567DA'
local TITAN='9E2E17F2CCCCAFDD'
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor()
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TITAN,life=0,credit=0}
    actors[#actors+1]=a;return a
end
local function source(hash,n)
    local row=stats.sources[hash]or{[SHOTS]=0,[KILLS]=0};stats.sources[hash]=row
    row[KILLS]=row[KILLS]+n
end
local function dead(a)
    a.life,a.credit=2,0x11;stats.totals[KILLS]=stats.totals[KILLS]+1
end
local function notice()return (state.kill_source_notices.items or{})[1]end
local function clear()tick(60);assert(not notice(),'notice must expire')end
tick(12)
local a=actor();tick(3);dead(a);tick(2);source(CANNON,1);tick(3)
assert(notice()and notice().source_hash==CANNON,
    'a source counter arriving 200ms after the native kill must complete its pending target')
assert(state.kills==1 and state.weapon_stats[CANNON].kills==1)
local first=notice();tick(10)
assert(notice().at==first.at and notice().expires_at==first.expires_at,
    'source completion must retain the actual kill time and five-second expiry')
clear()
local b=actor();tick(3);source(MG,1);tick(2);dead(b);tick(3)
assert(notice()and notice().source_hash==MG,
    'a source counter arriving 200ms before the native kill must survive until its target')
assert(state.kills==2 and state.weapon_stats[MG].kills==1)
clear()
local c,d=actor(),actor();tick(3)
dead(c);source(CANNON,1);source(MG,1);tick(2);dead(d);tick(4)
assert(notice()and notice().source_hash==MG,
    'two source credits with a split native kill count must not discard both source rows')
assert(state.kills==4 and state.weapon_stats[CANNON].kills==2 and state.weapon_stats[MG].kills==2)
clear()
-- A delayed unmatched source is bounded to the same short pairing window.
source(CANNON,1);tick(10)
assert(not notice(),'source-only growth cannot manufacture a victim')
local e=actor();tick(3);dead(e);tick(10)
assert(notice()and notice().source_hash==nil,'an expired source cannot explain a later kill')
local query=module.career_combat_query('weapons',{sequence=state.sequence})
assert(state.kills==5 and query.totals.kills>=4,'pairing may not add native kills')
print('PASS built burst source ingestion: delayed/ahead/split counters, bounded expiry, no added kills or source-only victims.')
]]
arg={addon,runtime}
assert(loadstring(text:sub(1,boundary-1)..scenario,'@addon-burst-sources-062'))()
