-- Built observer/recording path; only native memory and Runtime event transport
-- are replaced. Native byte decoding is covered by test_native_death_reader.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'));local source=input:read('*a'):gsub('\r\n','\n');input:close()
local boundary=assert(source:find('state=dofile(path).state',1,true))
local scenario=[=[
local callbacks={}
local factory=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local api=factory();api.events={on=function(kind,callback)callbacks[kind]=callback;return true end};return api
end
local function up(fn,key)
    for i=1,200 do local name,value=debug.getupvalue(fn,i);if not name then break end;if name==key then return value end end
end
local module=dofile(path);state=module.state
local detail=assert(up(module.career_combat_query,'combat_detail'))
local reader=assert(up(detail.observer.sample_damage,'reader'))
local LOCAL,OTHER='0000000000000011','0000000000000022'
local ROCKET,FRV='26E40437EA275296','2D85BFE3D8717FE5'
local queue,raws={},{}
local samples=0
function reader:damage_events(_,target)
    samples=samples+1;local events={};for _,row in ipairs(queue)do if row.target==target then events[#events+1]=copy(row)end end
    return{events=events,token=#events>0 and tostring(events[1].kind)..tostring(events[1].dealer_type)or''}
end
function reader:read(_,target)return copy(raws[target]),'DEATH_AVATAR_UNMAPPED'end
function reader:players(_,rows)
    local out={};for _,p in ipairs(rows)do out[#out+1]={peer_id=p.peer,avatar_id=p.avatar,
        slot_index=p['local']and 0 or 1,name=p['local']and'本人'or'队友'}end;return out
end
local function tick(n,dt)for _=1,n or 1 do clock=clock+100000;frame(dt or .1)end end
tick(2)
local function died(target,peer,pos,local_player)
    callbacks.player_died({local_player=local_player,peer=peer,avatar_id=target,
        observed='dead_state',frame=clock,position=pos})
end
local origin={x=0,y=0,z=0}
queue={{target=42,kind=4,element=0,damage=300,owner_entity=42,dealer_type=ROCKET,creditor=LOCAL}}
local before=samples;tick(1,.02)
assert(samples>before,'damage queue must be sampled before the 10 Hz observation gate')
queue={};died(42,LOCAL,origin,true)
stats.totals[DEATHS]=1;tick(14)
local records=module.combat_records_snapshot().death_records
assert(#records==1 and records[1].category=='self'and records[1].damage_kind=='爆炸')
assert(records[1].weapon_name=='RL-77 空爆火箭弹发射器'and records[1].evidence.weapon_type_hash==ROCKET,
    'actual built source names must reach saved self weapon death after body loss')

-- Separate actual local death without a source; another player's real vehicle
-- explosion provides the spatial witness. It must not add a local death.
avatar=43;tick(2);died(43,LOCAL,origin,true)
raws[88]={avatar_id=88,victim_type='4D1C334D294DFA97',life=2,last_owner=700,
    last_owner_type=FRV,last_creditor='0000000000000000',
    damage_cause={kind=4,element=0,life=2,owned=true,current=true,source='native_health_extension'}}
died(88,OTHER,{x=3,y=0,z=0},false)
stats.totals[DEATHS]=2;tick(14)
records=module.combat_records_snapshot().death_records
assert(#records==2 and records[2].evidence.nearby_death_inferred==true)
assert(records[2].weapon_name=='M-104 炽热型快速侦察载具'and records[2].damage_kind=='爆炸')
assert(records[2].evidence.nearby_death_distance==3 and records[2].confidence=='inferred')
assert(records[2].evidence.damage_kind_proven==false and records[2].evidence.weapon_source_proven==false)
local rank=module.career_combat_query('deaths',{period='all'})
assert(#rank.rows==2 and rank.rows[1].name~='自身','self weapon and vehicle mechanism must remain distinguishable')
active=false;tick(3)
assert(saved.combat_records_v1 and #saved.combat_records_v1.death_records==2)
local old=saved.combat_records_v1
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);tick(2)
records=module.combat_records_snapshot().death_records
assert(#records==2 and records[2].evidence.nearby_death_inferred and records[2].evidence.nearby_death_distance==3)
assert(records[1].weapon_name==old.death_records[1].weapon_name and state.kills==0 and state.total_cents==0,
    'death attribution survives reload without affecting kills or billing')
print('PASS built death causes: per-frame cache -> Runtime event -> self rocket explosion/body loss + nearby vehicle witness -> distinct career/save/reload; no remote death count, kills or fees')
]=]
arg={addon,runtime}
assert(loadstring(source:sub(1,boundary-1)..scenario,'@built-death-causes-061'))()
