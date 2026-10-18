-- Actual built entry, real persistence path and native stat counters. Only
-- process/memory boundaries use the existing owned integration fixture.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'));local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
saved.mission_sequence=7
saved.last_mission={sequence=7,status='ended',kills=10,deaths=2,ribbons={},mission_medals={},
 weapon_stats={['968211C0033DCE64']={name='AR-23 解放者',kills=3}},
 unit_kills={Charger={name_zh='强袭虫',class='重型',faction='terminids',count=1}}}
local epoch=1792040400
os.time=function()return epoch end
local api=dofile(path);state=api.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function query(kind,more)
 local filter={period='all',mode='recent'};for k,v in pairs(more or {})do filter[k]=v end
 return api.career_combat_query(kind,filter)
end
local function total(kind)
 local n=0;for _,row in ipairs(query(kind).rows)do n=n+row.kills end;return n
end
assert(total('weapons')==10 and total('enemies')==10,'old total and available source detail must survive migration')
local old_deaths=query('deaths')
assert(#old_deaths.rows==1 and old_deaths.rows[1].unknown_group==true
 and old_deaths.rows[1].name=='未知死因' and old_deaths.rows[1].count==2
 and old_deaths.rows[1].unrecorded_count==2 and #old_deaths.rows[1].records==0
 and old_deaths.coverage.unrecorded_deaths==2,'old counts are one summary without fabricated events')
tick(2)
stats.sources['968211C0033DCE64']={[SHOTS]=10,[KILLS]=2};stats.totals[SHOTS]=10;stats.totals[KILLS]=2
tick(2)
local a={id=501,pointer=228256,kind='1A7FCDFF98C664B0',life=0,credit=0}
actors[1]=a;tick(4);a.life=2;a.credit=0x11;stats.totals[KILLS]=3;tick(4)
local sources=query('weapons')
assert(sources.totals.kills==13 and sources.totals.linked_kills==0,'weapon total or unknown associations changed')
local found=false
for _,row in ipairs(sources.rows)do
 if row.name=='AR-23 解放者' then found=true;assert(row.kills==5 and row.category=='primary')end
 for _,detail in ipairs(row.detail_rows)do assert(detail.known==false,'native batch is not a victim pair')end
end
assert(found and total('enemies')==13,'source classifications and separate enemy lane must be queryable')
-- The 1.1s settlement allows a later teammate event inside the 1s group window.
stats.totals[DEATHS]=1;health_life=2;tick(14)
local deaths=query('deaths')
assert(#deaths.rows==1 and deaths.rows[1].count==3 and #deaths.rows[1].records==1
 and deaths.rows[1].records[1].sequence==8,'new native death counter did not save one local record')
assert(deaths.rows[1].category=='unknown' and deaths.rows[1].records[1].weapon_name==nil,'unavailable native source was guessed')
tick(10);assert(query('deaths').rows[1].count==3 and #query('deaths').rows[1].records==1,'one death counter produced duplicates')
active=false;tick(2)
assert(saved.combat_records_v1 and saved.combat_records_v1.version==1,'combat records were not flushed on returning to ship')
local snap=api.combat_records_snapshot();assert(#snap.entries==2 and #snap.death_records==1)
local found_ended=false;for _,entry in ipairs(snap.entries)do if entry.sequence==8 then
 found_ended=entry.status=='ended';assert(entry.kills==3 and entry.deaths==1)
end end
assert(found_ended,'midway ship return must keep the match')
local revision=snap.version;tick(60)
assert(#api.combat_records_snapshot().death_records==1 and total('weapons')==13,'ship polling reimported records')
print('PASS: built migration, real source categories, independent enemy lane, native counter death once, unknown attribution and ship-return persistence.')
]]
local body=source:sub(1,start-1)..scenario
local run=assert(loadstring(body,'=built_combat_records'))
local previous=arg;arg={addon,runtime};run();arg=previous
