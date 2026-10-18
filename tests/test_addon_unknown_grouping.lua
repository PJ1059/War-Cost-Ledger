-- Built addon: display-only unknown grouping must preserve source records.
-- Optional fifth argument is a de-identified real-account store fixture.
local addon,runtime,fixture,root=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local seed=arg[5] and dofile(arg[5]) or nil
local input=assert(io.open(fixture,'rb'));local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
if type(seed)=='table'then saved=copy(seed)end
local original=copy(saved.combat_records_v1 or{version=1,entries={},death_records={}})
saved.combat_records_v1=copy(original)
local rows=saved.combat_records_v1
local W1,W2,E1,E2='1111000011110000','2222000022220000','3333000033330000','4444000044440000'
local NAMED='5555000055550000'
local function row(id,name,kills,extra)
 local out={id=id,name=name,kills=kills,known=false,category='unknown',faction='unknown',size='未知体型'}
 for k,v in pairs(extra or{})do out[k]=v end;return out
end
rows.entries[#rows.entries+1]={sequence=900001,status='ended',kills=1000,deaths=11,
 weapons_observed=true,enemies_observed=true,
 weapons={['968211C0033DCE64']=row('968211C0033DCE64','old rifle',1),
  ['B056F8FC74ABA02D']=row('B056F8FC74ABA02D','old exact label',2),
  [NAMED]=row(NAMED,'已存可用来源',4),[W1]=row(W1,W1,5),[W2]=row(W2,'未知武器来源',7),
  unknown=row('unknown','未记录的旧击杀',11)},
 enemies={['D1E990BAF22D5A52']=row('D1E990BAF22D5A52','old predator',3),
  RawNamedEnemy=row('RawNamedEnemy','已存可用敌人',4),[E1]=row(E1,E1,6),[E2]=row(E2,'未知敌人',8),
  unknown=row('unknown','未记录的旧击杀',13)}}
rows.entries[#rows.entries+1]={sequence=900002,status='ended',legacy=true,kills=20,deaths=9,weapons={},enemies={}}
rows.entries[#rows.entries+1]={sequence=900003,status='ended',kills=0,deaths=5,ended_at=1000,weapons={},enemies={}}
rows.entries[#rows.entries+1]={sequence=900004,status='ended',kills=0,ended_at=1001,weapons={},enemies={}}
local function death(id,category,actor)
 rows.death_records[#rows.death_records+1]={id='900001:'..id,source_id=id,sequence=900001,
  occurred_at=1792040400+#rows.death_records,category=category,actor_name=actor,confidence='unknown'}
end
death('known-enemy','enemy','掠食追踪虫');death('known-environment','environment','火焰')
death('known-name-with-unknown-category','unknown','已知环境名称')
death('unknown-source','unknown','未知来源');death('unknown-raw-hash','unknown',W1)
for index=1,3 do rows.death_records[#rows.death_records+1]={id='900004:cross-'..index,source_id='cross-'..index,
 sequence=900004,occurred_at=1001,category='enemy',actor_name='跨局验证敌人',confidence='unknown'}end
local module=dofile(path);state=module.state
local function query(view,sequence,more)
 local filters={period='all',sequence=sequence}
 for k,v in pairs(more or{})do filters[k]=v end
 return module.career_combat_query(view,filters)
end
local function grouped(result,name,field,total)
 local found,count,sum,last=nil,0,0,false
 for index,value in ipairs(result.rows)do
  sum=sum+(value[field]or 0)
  if value.name==name then
   found,count,last=value,count+1,index==#result.rows
  else
   assert(not last,'a known row cannot follow the unknown group')
   assert(value.name~='未记录的旧击杀'and value.name~='未知武器来源'and value.name~='未知敌人',
    'legacy placeholders must merge into the single display group')
  end
 end
 assert(count==1 and last,'one '..name..' group is last even when it is the largest count')
 if total then assert(sum==total,'display grouping cannot lose or invent totals')end
 return found
end
local weapons=query('weapons',900001)
local enemies=query('enemies',900001)
local wu=grouped(weapons,'未知','kills',1000);local eu=grouped(enemies,'未知','kills',1000)
assert(wu.kills==993 and eu.kills==993,'raw hashes/placeholders/native gaps share one unknown bucket')
local seen={};for _,value in ipairs(weapons.rows)do seen[value.name]=value end
assert(seen['AR-23 解放者']and seen['AR-23 解放者'].kills==1)
assert(seen['激光炮装甲兵（废案）']and seen['激光炮装甲兵（废案）'].kills==2,
 'a precisely named resource remains useful although its weapon category is unknown')
assert(seen['已存可用来源']and seen['已存可用来源'].kills==4,
 'an actual saved display name survives absent category metadata')
seen={};for _,value in ipairs(enemies.rows)do seen[value.name]=value end
assert(seen['掠食追踪虫']and seen['掠食追踪虫'].kills==3)
assert(seen['已存可用敌人']and seen['已存可用敌人'].kills==4,
 'a named enemy remains visible when its size is unknown')
grouped(query('weapons',900001,{sort='name'}),'未知','kills',1000)
grouped(query('enemies',900001,{sort='name'}),'未知','kills',1000)
assert(grouped(query('weapons',900002),'未知','kills',20).kills==20)
assert(grouped(query('enemies',900002),'未知','kills',20).kills==20)
local deaths=query('deaths',900001)
assert(grouped(deaths,'未知死因','count',11).count==8,
 'two unknown source records plus six missing causes become one last death-rank group')
assert(grouped(query('deaths',900002),'未知死因','count',9).count==9)
local cross=query('deaths',nil,{period='24h',now=1002})
assert(grouped(cross,'未知死因','count',8).count==5 and cross.totals.deaths==8,
 'B three real records without native totals cannot offset A five never-recorded deaths')
local recent=query('deaths',900001,{mode='recent'})
assert(#recent.rows==4 and recent.rows[1].actor_name=='已知环境名称'and recent.rows[2].actor_name=='火焰'
 and recent.rows[3].actor_name=='掠食追踪虫','known recent records preserve their original timestamp order')
local recent_unknown=recent.rows[#recent.rows]
assert(recent_unknown.unknown_group==true and recent_unknown.name=='未知死因'
 and #recent_unknown.records==2 and recent_unknown.unrecorded_count==6,
 'recent mode groups two real unknown records and six missing causes once at the bottom')
local old_recent=query('deaths',900002,{mode='recent'}).rows[1]
assert(old_recent.unknown_group==true and #old_recent.records==0 and old_recent.unrecorded_count==9,
 'a missing old cause is a count summary, never a fabricated timestamped death event')
local snap=module.combat_records_snapshot();local raw
for _,entry in ipairs(snap.entries)do if entry.sequence==900001 then raw=entry end end
assert(raw.weapons[W1].kills==5 and raw.weapons[W2].kills==7 and raw.enemies[E1].kills==6 and raw.enemies[E2].kills==8,
 'the raw complete hashes survive display-only aggregation')
local stored_deaths=0;for _,record in ipairs(snap.death_records)do if record.sequence==900001 then stored_deaths=stored_deaths+1 end end
assert(stored_deaths==5,'recent/rank grouping cannot replace or add raw death records')
-- Later exact directories can recover old names from those raw hashes.
local create=dofile(review_root..'/src/combat-records.lua')
local later=create({saved=snap,weapon_catalog={[W1]={id='later-source',name='后续确认来源',category='unknown'}},
 enemy_catalog={[E1]={key='LaterEnemy',name_zh='后续确认敌人',class='未知体型',kill=true}}})
local function find(result,name)for _,value in ipairs(result.rows)do if value.name==name then return value end end end
assert(find(later:query('weapons',{sequence=900001}),'后续确认来源').kills==5)
assert(find(later:query('enemies',{sequence=900001}),'后续确认敌人').kills==6)
-- The real history view uses exactly this filtered query rather than another
-- ranking implementation. Its expanded single-match order is the same.
local layout=dofile(review_root..'/src/career-panel-model.lua')({},nil,dofile(review_root..'/src/career-combat-panel-model.lua'))
local history={entries={{sequence=900001,status='ended',kills=1000,deaths=11,ribbons={},medals={}}}}
local function history_plan(scroll)
 return layout:layout({totals={}},{width=420,height=747,view='history',page_visible=true,personal=true,
  history=history,expanded_sequence=900001,scroll=scroll,
  combat_query=function(view,filters)
   assert(filters.sequence==900001 and filters.period=='all')
   return module.career_combat_query(view,filters)
  end})
end
local plan=history_plan(0);local names={weapons={},enemies={}}
for scroll=0,math.ceil(plan.max_scroll/16)do
 plan=history_plan(scroll*16)
 for _,label in ipairs(plan.header_texts)do
  for _,lane in ipairs({'weapons','enemies'})do
   local index=label.id:match('^match_'..lane..'_name(%d+)$')
   if index then names[lane][tonumber(index)]=label.text end
  end
 end
end
for _,lane in ipairs({'weapons','enemies'})do
 local seen_unknown=0;local last=0
 for index,name in pairs(names[lane])do last=math.max(last,index);if name=='未知'then seen_unknown=seen_unknown+1 end end
 assert(seen_unknown==1 and names[lane][last]=='未知','expanded history consumes the same grouped last unknown for '..lane)
end
-- A supplied real account is checked per saved mission and in aggregate.
for _,view in ipairs({'weapons','enemies'})do
 for _,entry in ipairs(original.entries)do
  local expected=0;for _,value in pairs(entry[view]or{})do expected=expected+(value.kills or 0)end
  expected=math.max(expected,entry.kills or 0)
  local result=query(view,entry.sequence);local sum=0;local unknown=0
  for index,value in ipairs(result.rows)do
   sum=sum+value.kills
   if value.name=='未知'then unknown=unknown+1;assert(index==#result.rows)end
  end
  assert(unknown<=1 and sum==expected,'real saved single-match total or unknown ordering changed')
 end
end
if #original.entries>0 then
 local by_sequence={};for _,record in ipairs(original.death_records)do by_sequence[record.sequence]=(by_sequence[record.sequence]or 0)+1 end
 local expected_total=0
 for _,entry in ipairs(original.entries)do
  expected_total=expected_total+math.max(entry.deaths or 0,by_sequence[entry.sequence]or 0)
  by_sequence[entry.sequence]=nil
 end
 for _,n in pairs(by_sequence)do expected_total=expected_total+n end
 local original_only=create({saved=original})
 local result=original_only:query('deaths',{});local sum=0;local unknown=0
 for index,value in ipairs(result.rows)do sum=sum+value.count;if value.name=='未知死因'then unknown=unknown+1;assert(index==#result.rows)end end
 assert(sum==expected_total and unknown<=1,'real saved death rank retains each match missing causes once without cross-match cancellation')
 local expected_gaps=expected_total-#original.death_records
 assert(result.totals.deaths==expected_total and result.totals.unrecorded_deaths==expected_gaps,
  'real account total and missing summary must use the same per-sequence evidence')
 if expected_gaps>0 then assert(unknown==1 and result.rows[#result.rows].unrecorded_count==expected_gaps)end
 print('PASS real saved death accounting: '..expected_total..' displayed = '..#original.death_records..' actual records + '..expected_gaps..' per-match missing.')
end
print('PASS: built unknown grouping and last order, legacy gaps, named resources with unknown category/size, preserved raw hashes and future exact naming, real history single-match path and optional de-identified saved-account totals.')
]]
arg={addon,runtime}
assert(loadstring('local review_root,seed=...\n'..source:sub(1,start-1)..scenario,'@addon-unknown-grouping'))(root,seed)
