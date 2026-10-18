-- Synthetic old-player archive. No game process, account or store access.
local cfg=assert(_BENCH)
local ffi=require('ffi')
ffi.cdef[[int QueryPerformanceCounter(int64_t *); int QueryPerformanceFrequency(int64_t *);]]
local ticks,frequency=ffi.new('int64_t[1]'),ffi.new('int64_t[1]')
assert(ffi.C.QueryPerformanceFrequency(frequency)~=0)
local function clock()ffi.C.QueryPerformanceCounter(ticks);return tonumber(ticks[0])/tonumber(frequency[0])end
local DAY=86400
local now=200*DAY+12345
local saved={version=1,entries={},death_records={}}
local history={revision=1,entries={}}
local icons={}
for n=1,24 do icons[n]={kind=n<=12 and'ribbon'or'medal',key='award'..n}end
for n=1,500 do
    local at=now-(n-1)*28800-100
    local entry={sequence=n,status='ended',ended_at=at,kills=640,deaths=80,weapons={},enemies={},
        weapons_observed=true,enemies_observed=true}
    local historical={sequence=n,status='ended',ended_at=at,kills=640,deaths=80,ribbons={},medals={},
        patriotic_bill={version=1,total_cents=2000,entries={}}}
    for k=1,64 do
        local id=string.format('%016X',k)
        entry.weapons[id]={id='weapon'..k,name='武器 '..k,kills=10,category='support',weapon_type='测试分类'}
        entry.enemies[id]={id='enemy'..k,name='敌人 '..k,kills=10,faction='bugs',size='轻型'}
    end
    for k=1,24 do historical[k<=12 and'ribbons'or'medals']['award'..k]=n end
    for k=1,20 do historical.patriotic_bill.entries[k]={key='bill'..k,name='费用 '..k,amount_cents=100}end
    saved.entries[n]=entry;history.entries[n]=historical
    for k=1,80 do
        saved.death_records[#saved.death_records+1]={id=n..':'..k,source_id=tostring(k),sequence=n,
            occurred_at=at-k,category='enemy',actor_name='敌人 '..k%40,weapon_name='武器 '..k%16,
            damage_kind='爆炸',confidence='inferred',evidence={death_observed='dead_state'}}
    end
end
local combat=dofile(cfg.combat)({saved=saved,clock=function()return now end})
local summary=dofile(cfg.summary)({icons=icons})
local state={history_reason='CAREER_BASELINE_PLUS_OBSERVED_DELTAS',history_kills=320000,history_deaths=40000}
local rows={}
local function measure(name,iterations,fn)
    collectgarbage('collect')
    local samples={};local total=0
    for n=1,iterations do local start=clock();fn(n);local elapsed=(clock()-start)*1000;samples[n]=elapsed;total=total+elapsed end
    table.sort(samples)
    rows[#rows+1]=string.format('{"name":%q,"iterations":%d,"mean_ms":%.9g,"p95_ms":%.9g,"max_ms":%.9g}',
        name,iterations,total/iterations,samples[math.ceil(iterations*.95)],samples[#samples])
end
measure('weapons_all_cold',1,function()assert(combat:query('weapons',{}).totals.kills==320000)end)
measure('weapons_all_hot',30,function()assert(combat:query('weapons',{}).totals.kills==320000)end)
measure('weapons_all_cross_second',15,function()now=now+1;assert(combat:query('weapons',{}).totals.kills==320000)end)
measure('deaths_all_cold',1,function()assert(combat:query('deaths',{mode='recent'}).totals.recorded_deaths==40000)end)
measure('deaths_all_hot',30,function()assert(combat:query('deaths',{mode='recent'}).totals.recorded_deaths==40000)end)
measure('deaths_all_cross_second',15,function()now=now+1;assert(combat:query('deaths',{mode='recent'}).totals.recorded_deaths==40000)end)
measure('weapons_day_cold',1,function()assert(combat:query('weapons',{period='24h'}).totals.kills==1920)end)
measure('weapons_day_cross_second',15,function()now=now+1;assert(combat:query('weapons',{period='24h'}).totals.kills==1920)end)
for n=1,8 do combat:query('deaths',{sequence=n,mode='recent'})end
measure('match_page_hot',30,function(n)assert(combat:query('deaths',{sequence=n%8+1,mode='recent'}).totals.recorded_deaths==80)end)
measure('summary_cold',1,function()assert(summary:summarize(history.entries,state,now,history.revision).all.kills==320000)end)
measure('summary_cross_second',30,function()now=now+1;assert(summary:summarize(history.entries,state,now,history.revision).all.kills==320000)end)
measure('legacy_crush_cold',1,function()assert(combat:legacy_crush_summary(history).total==0)end)
measure('legacy_crush_hot',30,function()assert(combat:legacy_crush_summary(history).total==0)end)
return '{"matches":500,"death_records":40000,"source_rows":64000,"saved_bill_lines":10000,"cases":['..table.concat(rows,',')..']}'
