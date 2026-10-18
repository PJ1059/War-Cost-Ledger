local create=dofile(assert(arg[1]))
local icons={{id='R01',key='air',kind='ribbon'},{id='R10',key='recon',kind='ribbon'},
    {id='M01',key='democracy_harvester',kind='medal'}, {id='M06',key='fragrant',kind='medal'}}
local function total(api,group,key) return api:snapshot().totals[group][key] end
local function state(sequence,air,medal)
    return {sequence=sequence,mission=true,ribbons={air=air},mission_medals={democracy_harvester=medal}}
end
local api=create({icons=icons})
assert(not api:observe({sequence=0,ribbons={air=99}}))
local s=state(1,5,true)
local changed,reason,earned=api:observe(s)
assert(changed and reason=='baseline' and earned==0)
assert(total(api,'ribbons','air')==0 and total(api,'medals','democracy_harvester')==0,
    'first positive sample must not reconstruct history')
s.ribbons.air=7
changed,reason,earned=api:observe(s)
assert(changed and earned==2 and total(api,'ribbons','air')==2)
assert(not api:observe(s),'same frame must not recount')
s.ribbons.recon=1
assert(api:observe(s) and total(api,'ribbons','recon')==1,'missing at mission baseline means no award yet')
s.ribbons.air=2
assert(not api:observe(s),'same mission rollback cannot lower the high water mark')
s.ribbons.air=8
assert(api:observe(s) and total(api,'ribbons','air')==3)
s.ribbons.air=nil
assert(not api:observe(s),'a partial state cannot reset the previous count')
s.ribbons.air=9
assert(api:observe(s) and total(api,'ribbons','air')==4)
s.mission_medals.democracy_harvester=false
api:observe(s)
s.mission_medals.democracy_harvester=true
assert(not api:observe(s),'same mission boolean medal is never counted twice')
local second=state(2,0,false)
assert(api:observe(second))
second.ribbons.air=3
second.mission_medals.democracy_harvester=true
assert(api:observe(second))
assert(total(api,'ribbons','air')==7 and total(api,'medals','democracy_harvester')==1)
second.mission=false;second.status='ended'
second.ribbons.air=4
assert(api:observe(second) and total(api,'ribbons','air')==8,'final mission snapshot is still observed')
assert(not api:observe(s),'an older mission cannot replay')
local saved=api:snapshot()
saved.totals.ribbons.air=888
assert(total(api,'ribbons','air')==8,'the persisted copy cannot mutate the live accumulator')
local restarted=create({icons=icons,saved=api:snapshot(),legacy={last_mission=second,
    combat_history={medals={democracy_harvester=true}}}})
assert(not restarted:observe(second))
assert(total(restarted,'ribbons','air')==8 and total(restarted,'medals','democracy_harvester')==1,
    'restart and repeated legacy input must not count again')
second.mission=true;second.status=nil;second.ribbons.air=6
assert(restarted:observe(second) and total(restarted,'ribbons','air')==10)
local third=state(3,0,false)
restarted:observe(third)
third.mission_medals.democracy_harvester=true
restarted:observe(third)
assert(total(restarted,'medals','democracy_harvester')==2,'next mission may earn the medal again')
local legacy={last_mission={sequence=24,status='ended',ribbons={air=6,recon=2},
    mission_medals={democracy_harvester=true}},
    combat_history={kills=100000,deaths=20,medals={democracy_harvester=true,fragrant=true}},
    fire_history={kills=200000}}
local migrated=create({icons=icons,legacy=legacy})
assert(total(migrated,'ribbons','air')==6 and total(migrated,'ribbons','recon')==2)
assert(total(migrated,'medals','democracy_harvester')==1 and total(migrated,'medals','fragrant')==1,
    'legacy unlock and last mission true may describe the same medal')
assert(not migrated:observe(legacy.last_mission),'migrated last mission also installs the checkpoint')
legacy.last_mission.ribbons.air=7
assert(migrated:observe(legacy.last_mission) and total(migrated,'ribbons','air')==7)
local no_history=create({icons=icons,legacy={combat_history={kills=999999},fire_history={kills=999999}}})
assert(total(no_history,'ribbons','air')==0 and total(no_history,'medals','fragrant')==0,
    'kills never invent historical ribbons or medals')
local unlock=create({icons=icons,legacy={last_mission={sequence=25,status='ended',
    medals={fragrant=true},mission_medals={},ribbons={}}}})
assert(total(unlock,'medals','fragrant')==1,'an explicit old unlock proves at least one acquisition')
local invalid=create({icons=icons,legacy={last_mission={sequence=9,status='ended',
    ribbons={air=-1,recon=0/0},mission_medals={democracy_harvester=-1}}}})
assert(total(invalid,'ribbons','air')==0 and total(invalid,'ribbons','recon')==0)
assert(total(invalid,'medals','democracy_harvester')==0)
assert(not pcall(create,{icons=icons,saved={version=2,totals={}}}),
    'unknown saved version must not silently re-import legacy')
print('PASS: first baseline, actual growth, absent keys, rollback, partial states, mission end, sequence dedupe, same-mission medal, restart, conservative one-time migration and no kill inference.')

-- Version-1 bool checkpoints upgrade in place without replay; subsequent
-- numeric acquisitions count their exact difference and survive a reload.
local repeated=create({icons=icons,saved={version=1,totals={ribbons={},medals={democracy_harvester=4}},
    checkpoint={sequence=70,ribbons={},medals={democracy_harvester=true}}}})
local current=state(70,nil,1)
assert(not repeated:observe(current))
assert(total(repeated,'medals','democracy_harvester')==4)
current.mission_medals.democracy_harvester=3
assert(repeated:observe(current) and total(repeated,'medals','democracy_harvester')==6)
local checkpoint=repeated:snapshot()
assert(checkpoint.checkpoint.medals.democracy_harvester==3)
repeated=create({icons=icons,saved=checkpoint})
assert(not repeated:observe(current))
for _,v in ipairs({true,1,2,-1,math.huge,0/0})do
    current.mission_medals.democracy_harvester=v
    assert(not repeated:observe(current),'partial/old/invalid reads cannot repeat a numeric medal')
end
current.mission_medals.democracy_harvester=4
assert(repeated:observe(current) and total(repeated,'medals','democracy_harvester')==7)
local migrated_counts=create({icons=icons,legacy={last_mission={sequence=71,status='ended',ribbons={},
    medals={democracy_harvester=true},mission_medals={democracy_harvester=3}},
    combat_history={medals={democracy_harvester=true}}}})
assert(total(migrated_counts,'medals','democracy_harvester')==3)
assert(not migrated_counts:observe({sequence=71,status='ended',ribbons={},mission_medals={democracy_harvester=3}}))
local crush_icons={{id='R12',key='crush',kind='ribbon'}}
local old_crush=create({icons=crush_icons,saved={version=1,totals={ribbons={},medals={}},
    checkpoint={sequence=31,ribbons={},medals={}}}})
assert(not old_crush:observe({sequence=31,status='ended',ribbons={},mission_medals={}}))
assert(total(old_crush,'ribbons','crush')==0,'a new definition cannot manufacture a stored legacy acquisition')
local crush_state={sequence=32,mission=true,ribbons={crush=0},mission_medals={}}
old_crush:observe(crush_state);crush_state.ribbons.crush=3;assert(old_crush:observe(crush_state))
assert(total(old_crush,'ribbons','crush')==3)
local restored_crush=create({icons=crush_icons,saved=old_crush:snapshot()})
assert(not restored_crush:observe(crush_state)and total(restored_crush,'ribbons','crush')==3)
print('PASS: repeatable numeric medals, legacy bool checkpoint, exact differences, restart and max-only legacy import.')
