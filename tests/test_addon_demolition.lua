-- Built entry with real stage reader, matcher, menu and persistence; only the
-- native memory boundary and Runtime event delivery use owned fixtures.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local file=assert(io.open(fixture,'rb'));local source=file:read('*a'):gsub('\r\n','\n');file:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local callbacks={}
local hd2_factory=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
 local hd2=hd2_factory()
 hd2.events={on=function(name,fn)
  callbacks[name]=fn
  return {state='active',active=function()return true end}
 end}
 return hd2
end
local E=native.engine
local manager,destruction,descriptor=0x60000000,0x61000000,0x62000000
local registry,generations,objects,object,poses,vtable=0x63000000,0x64000000,0x65000000,0x66000000,0x67000000,0x68000000
world.exe=0x10000000
local stage,records_ready,positions_ready=0,true,true
local old_pointer,old_u32,old_fill,old_read=view.pointer,view.u32,view.fill,view.read
view.proves=function()return true end
view.pointer=function(at)
 local pointers={
  [world.game+0x3326550]=manager,[world.game+0x346D528]=destruction,
  [world.exe+E.units]=registry,[registry+E.unitGenerations]=generations,
  [registry+E.unitObjects]=objects,[objects+901*8]=object,
  [object]=vtable,[vtable+0xE8]=world.exe+E.sceneGraphMethod,
  [object+E.sceneGraphOffset+E.poses]=poses,
 }
 return pointers[at] or old_pointer(at)
end
view.u32=function(at)
 if at==manager+12 then return 1 end
 if at==registry+E.unitCount then return 4096 end
 if at==object+E.unitId then return 901 end
 return old_u32(at)
end
view.fill=function(slot,at,length)
 if at==manager+0x4030 then assert(length==8);return {ptr=function()return descriptor end} end
 if at==manager+0x6030 then assert(length==4);return {i32=function()return 0x17026 end} end
 if at==destruction+0xC5F78+0x17026*12 then
  assert(length==12)
  if not records_ready then return nil end
  return {u32=function(_,offset)assert(offset==0);return 901 end,
   u8=function(_,offset)if offset==7 then return stage end;assert(offset==8);return 1 end}
 end
 return old_fill(slot,at,length)
end
view.read=function(at,size)
 if at==descriptor then
  assert(size==24)
  return b.encode(0x08040D2F,'u32')..b.encode(0x0DF874E2,'u32')..b.encode(501,'u32')
   ..b.encode(901,'u32')..string.rep('\0',8)
 end
 if at==generations+901 then assert(size==1);return '\0'end
 if at==poses+E.translation then
  assert(size==12);if not positions_ready then return nil end;return string.rep('\0',12)
 end
 return old_read(at,size)
end
local api=dofile(path);state=api.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function explosion(owner,name)
 assert(callbacks.explosion,'explosion not subscribed')
 local event={name=name or 'Grenade Frag',position={x=0,y=0,z=0},local_player=owner=='local'}
 if owner=='local' then event.creditor_peer='0000000000000011';event.player={peer=event.creditor_peer}
 elseif owner=='other' then event.creditor_peer='0000000000000022';event.player={peer=event.creditor_peer} end
 callbacks.explosion(event)
end
local function restart()
 active=false;tick(2);stage=0;records_ready=true;positions_ready=true;active=true;tick(4)
 assert(state.ribbons.demolition==0)
end
tick(4)
assert(api.demolition_status().subscribed and api.demolition_status().reader.ready)
assert(api.demolition_status().reader.known_holes==1,'actual ordinary-hole dynamic index was discarded')
explosion('local','throwable/g6_frag/detonation');positions_ready=false;stage=1
for _=1,4 do tick();if state.ribbons.demolition>0 then break end end
assert(state.ribbons.demolition==1,'one local closure did not award R04')
assert(api.demolition_status().reader.cached_positions==1,
 'closing-unit position must come from its live observation when native position is gone')
assert(state.demolition_inferred==1 and #state.demolition_evidence==1)
assert(state.demolition_evidence[1].confidence=='inferred' and state.kills==0 and state.total_cents==0,
 'inferred closure altered kill count or bill')
tick(30);assert(state.ribbons.demolition==1,'same closed hole replayed')
local final_status=api.demolition_status()
local final_polls=final_status.reader.polls
assert(final_polls>0 and final_status.reader.closures==1 and final_status.attribution.awarded==1)
assert(final_status.reader.resource_samples[1]=='0DF874E208040D2F')
local external_status=api.demolition_status()
external_status.reader.resource_samples[1]='caller-owned-change'
external_status.attribution.awarded=999
assert(api.demolition_status().reader.resource_samples[1]=='0DF874E208040D2F',
 'status resources expose mutable reader data')
assert(api.demolition_status().attribution.awarded==1,'status exposes mutable attribution data')
active=false;tick(2)
assert(saved.last_mission.ribbons.demolition==1 and saved.career_awards_v1,'ship return lost ribbon')
assert(api.demolition_status().reader.polls==0,'ship return did not reset the active observer')
assert(final_status.reader.polls==final_polls and final_status.reader.closures==1
 and final_status.reader.resource_samples[1]=='0DF874E208040D2F'
 and final_status.attribution.awarded==1,'mission reset mutated an earlier status snapshot')
assert(saved.last_mission.demolition_status.reader.polls==final_polls
 and saved.last_mission.demolition_status.reader.closures==1
 and saved.last_mission.demolition_status.attribution.awarded==1,
 'mission end saved the reset diagnostic instead of the final sampled state')
assert(saved.bughole_diagnostic_v1.reader.polls==final_polls
 and saved.bughole_diagnostic_v1.reader.known_holes==1
 and saved.bughole_diagnostic_v1.attribution.awarded==1,
 'mission end did not force-save the final demolition diagnostic')
local found=false
for _,entry in ipairs(api.mission_history_snapshot().entries)do
 if entry.sequence==state.sequence then assert(entry.ribbons.demolition==1);found=true end
end
assert(found,'mission history did not retain inferred ribbon')
restart();explosion('local','throwable/g6_frag/detonation');explosion('other','throwable/g6_frag/detonation');stage=1;tick(28)
assert(state.ribbons.demolition==1,'teammate competition wrongly vetoed local coverage')
assert(state.demolition_evidence[1].evidence.conflict_count==1,'competitor was omitted from inferred evidence')
restart();explosion('local','throwable/g6_frag/detonation');explosion('unknown','unmapped');stage=1;tick(28)
assert(state.ribbons.demolition==1,'unknown competitor wrongly vetoed local coverage')
restart();explosion('local','unmapped');stage=1;tick(28)
assert(state.ribbons.demolition==1,'unknown local radius did not use BFV 9m fallback')
assert(state.demolition_evidence[1].evidence.selected_explosion.radius==9)
restart();explosion('local','P-34 Breacher');stage=1;tick(4)
assert(state.ribbons.demolition==1,'SDK demolition=0 filter still discarded a valid local blast')
restart();explosion('other','throwable/g6_frag/detonation');stage=1;tick(28)
assert(state.ribbons.demolition==0,'teammate-only explosion became local credit')
restart();stage=1;tick(4);active=false;tick(2);explosion('local','throwable/g6_frag/detonation');tick(40)
assert(state.ribbons.demolition==0,'unsettled closure was forced on ship return')
restart();explosion('local','throwable/g6_frag/detonation');records_ready=false;tick(4);stage=1;records_ready=true;tick(28)
assert(state.ribbons.demolition==0,'read gap replayed closure')
restart();stage=1;tick(4);explosion('local','throwable/g6_frag/detonation')
destruction=destruction+0x100000;tick(28)
assert(state.ribbons.demolition==0,'destruction-world replacement retained old pending credit')
restart();stage=1;tick(4);explosion('local','throwable/g6_frag/detonation')
clock=clock+3000000;frame(3);tick(28)
assert(state.ribbons.demolition==0,'long sampling gap retained stale attribution window')
print('PASS built demolition: dynamic 0x17026 stage/live-position cache + explosion subscription -> immediate inferred R04, teammate/unknown evidence, 9m fallback, once-only, immutable status snapshots/final diagnostic persistence, gap/return reset and career history; no kill/bill changes.')
]]
local body=source:sub(1,start-1)..scenario
local run=assert(loadstring(body,'=built_demolition'))
local previous=arg;arg={addon,runtime,fixture};run();arg=previous
