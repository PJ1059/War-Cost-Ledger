local create=dofile(assert(arg[1]))
local icons={{kind='ribbon',key='air'},{kind='ribbon',key='recon'},
    {kind='medal',key='democracy_harvester'},{kind='medal',key='fragrant'}}
local HOUR,DAY=3600,86400
local function state(kills,deaths)
    return {history_kills=kills,history_deaths=deaths,history_reason='CAREER_BASELINE_PLUS_OBSERVED_DELTAS'}
end
local function entry(sequence,ended,kills,deaths,ribbons,medals)
    return {sequence=sequence,status='ended',ended_at=ended,kills=kills,deaths=deaths,
        ribbons=ribbons or {},medals=medals or {}}
end
local tests=0
local function check(name,fn)fn();tests=tests+1;print('PASS '..name)end
check('partial period plots begin at the first actual in-range checkpoint when the cutoff is unrecorded',function()
    local at=60*DAY+1234;local target=at-DAY
    local api=create({icons=icons})
    api:observe(state(100,10),target-5978)
    api:observe(state(120,10),target+11536)
    api:observe(state(130,10),at-100)
    local saved=api:snapshot()
    local result=api:summarize({},state(140,10),at)
    for index,row in ipairs(result.periods)do
        assert(row.career.baseline,'recorded checkpoints inside the selected period must keep its graph visible')
        assert(row.career.partial and row.career.reason=='available_partial')
        local expected=index==1 and target+11536 or target-5978
        assert(row.career.baseline.at==expected and row.career.series[1].at==expected)
        assert(row.career.series[#row.career.series].at==at and row.career.series[#row.career.series].kd==14)
        assert(row.career.baseline.at>row.career.target_at,'partial means the missing cutoff is not fabricated')
    end
    assert(api:snapshot().buckets[1].first.at==saved.buckets[1].first.at,'rendering never rewrites checkpoints')
    local future=create({icons=icons});future:observe(state(1,1),at+1)
    assert(not future:summarize({},state(140,10),at).periods[1].career.baseline,'future observations cannot fill a period')
end)
check('periods use only retained timestamped ended records including early ship returns',function()
    local at=60*DAY
    local entries={entry(1,at,7,0,{air=1},{fragrant=1}),
        entry(2,at-DAY,5,1,{air=2},{fragrant=1}),
        entry(3,at-DAY-1,3,2,{recon=1}),
        entry(4,at-7*DAY,2,0,{recon=2},{democracy_harvester=1}),
        entry(5,at-7*DAY-1,11,3,{air=4}),
        entry(6,at-30*DAY,1,1),entry(7,at-30*DAY-1,999,99),
        entry(8,nil,999,99),entry(9,at+1,999,99),entry(10,at,999,99)}
    entries[10].status='active'
    local api=create({icons=icons})
    local result=api:summarize(entries,state(1000,10),at)
    local a,b,c=unpack(result.periods)
    assert(a.key=='24h' and a.missions==2 and a.kills==12 and a.deaths==1)
    assert(a.ribbons.air==3 and a.medals.fragrant==2)
    assert(b.key=='7d' and b.missions==4 and b.kills==17 and b.deaths==3)
    assert(b.ribbons.recon==3 and b.medals.democracy_harvester==1)
    assert(c.key=='30d' and c.missions==6 and c.kills==29 and c.deaths==7)
    assert(a.unknown_time==1 and c.unknown_time==1)
    assert(a.career.delta==nil and a.career.reason=='baseline_unavailable')
    assert(result.current.kd==100,'comparison is total career KD, not the period K/D')
end)
check('unknown times and missing statistics are never converted to zero or inferred',function()
    local at=40*DAY
    local unknown=entry(1,nil,100,10);unknown.started_at=at-100
    local interrupted=entry(2,nil,40,2);interrupted.status='interrupted'
    local api=create({icons=icons})
    local result=api:summarize({unknown,interrupted,entry(3,at,nil,0),entry(4,at,5,nil)},nil,at)
    local row=result.periods[1]
    assert(row.unknown_time==2 and row.missions==2 and row.kills==nil and row.deaths==nil)
    assert(row.known_kills==5 and row.known_deaths==0 and row.missing_kills==1 and row.missing_deaths==1)
    assert(result.current==nil and row.career.reason=='career_unavailable')
end)
check('nearest checkpoint must precede target and be within one hour',function()
    local at=60*DAY+1234
    local target=at-DAY
    local api=create({icons=icons})
    assert(api:observe(state(100,10),target-3600))
    assert(api:observe(state(110,10),target-10))
    assert(api:observe(state(120,10),target+1))
    local row=api:summarize({},state(150,10),at).periods[1]
    assert(row.career.baseline.at==target-10 and row.career.baseline.kd==11)
    assert(row.career.gap_seconds==10 and row.career.delta==4 and row.career.current_kd==15)
    local exact=create({icons=icons});exact:observe(state(100,10),target-3600)
    assert(exact:summarize({},state(100,10),at).periods[1].career.delta==0)
    local old=create({icons=icons});old:observe(state(100,10),target-3601)
    local missing=old:summarize({},state(100,10),at).periods[1].career
    assert(missing.baseline==nil and missing.delta==nil and missing.reason=='baseline_too_old')
    local future=create({icons=icons});future:observe(state(100,10),target+1)
    local partial=future:summarize({},state(100,10),at).periods[1].career
    assert(partial.reason=='available_partial'and partial.baseline.at==target+1 and partial.partial)
end)
check('all three career comparisons use independent target checkpoints and zero death semantics',function()
    local at=60*DAY
    local api=create({icons=icons})
    api:observe(state(50,0),at-30*DAY)
    api:observe(state(100,10),at-7*DAY)
    api:observe(state(200,10),at-DAY)
    local a,b,c=unpack(api:summarize({},state(15,0),at).periods)
    assert(a.career.delta==-5 and b.career.delta==5 and c.career.delta==-35)
    assert(c.career.baseline.kd==50,'zero deaths use at least one in numeric comparison')
end)
check('same counts in one hour never churn revision at 10 Hz but the next hour records a point',function()
    local api=create({icons=icons});local s=state(100,10)
    assert(api:observe(s,100));local revision=api.revision
    for n=1,10000 do assert(not api:observe(s,100+n*.1))end
    assert(api.revision==revision and #api:snapshot().buckets==1)
    assert(api:observe(s,HOUR+100) and api.revision==revision+1)
    s.history_kills=101;assert(api:observe(s,HOUR+200))
    s.history_kills=102;assert(api:observe(s,HOUR+300))
    local last=api:snapshot().buckets[2]
    assert(last.first.at==HOUR+100 and last.first.kills==100)
    assert(last.last.at==HOUR+300 and last.last.kills==102)
    assert(not api:observe(state(200,10),HOUR+299),'clock rollback cannot reorder history')
end)
check('checkpoint state is independent of deleted mission history and survives restart',function()
    local at=60*DAY
    local api=create({icons=icons});api:observe(state(100,10),at-DAY)
    local records={entry(1,at,10,1,{air=2},{fragrant=1})}
    local before=api:summarize(records,state(110,11),at).periods[1]
    local saved=api:snapshot();local restarted=create({icons=icons,saved=saved})
    records={}
    local after=restarted:summarize(records,state(110,11),at).periods[1]
    assert(before.missions==1 and after.missions==0 and after.kills==0)
    assert(before.career.delta==after.career.delta and after.career.baseline.kills==100)
    saved.buckets[1].first.kills=999;saved.buckets[1].last.kills=999
    assert(restarted:snapshot().buckets[1].first.kills==100)
    local copy=restarted:snapshot();copy.buckets[1].last.kills=888
    assert(restarted:snapshot().buckets[1].last.kills==100)
end)
check('31 day first and last checkpoints remain bounded while retaining 30 day baselines',function()
    local api=create({icons=icons})
    for hour=1,1000 do
        api:observe(state(hour*2,1),hour*HOUR)
        api:observe(state(hour*2+1,1),hour*HOUR+30)
    end
    local snap=api:snapshot()
    assert(#snap.buckets==745 and #snap.buckets*2<=api.checkpoint_limit)
    assert(snap.buckets[1].hour==256 and snap.buckets[#snap.buckets].hour==1000)
    local row=api:summarize({},state(2001,1),1000*HOUR+30).periods[3]
    assert(row.career.baseline and row.career.gap_seconds==0)
    assert(row.career.baseline.at==280*HOUR+30)
end)
check('same second updates resolve to the latest actual point and never invent old data',function()
    local api=create({icons=icons})
    api:observe(state(100,10),100);api:observe(state(110,10),100)
    local bucket=api:snapshot().buckets[1]
    assert(bucket.first.kills==110 and bucket.last.kills==110)
    assert(api:summarize({},state(120,10),DAY+100).periods[1].career.delta==1)
    local partial=api:summarize({},state(120,10),DAY+99).periods[1].career
    assert(partial.partial and partial.baseline.at==100,'uses the actual next checkpoint rather than inventing the target at 99')
end)
check('invalid career or clock cannot mint checkpoints or display false comparisons',function()
    local api=create({icons=icons,clock=function()error('unavailable')end})
    assert(not api:observe(state(100,10)))
    assert(not api:observe({history_kills=100,history_deaths=10},100))
    assert(not api:observe(state(100,0/0),100) and not api:observe(state(-1,10),100))
    assert(not api:observe(state(100,10),-1) and not api:observe(state(100,10),math.huge))
    assert(#api:snapshot().buckets==0 and api.revision==0)
    assert(api:summarize({},state(100,10)).periods[1].career.reason=='clock_unavailable')
    assert(not pcall(create,{icons=icons,saved={version=2,buckets={}}}))
end)
check('summed counts preserve exact integers and report overflow instead of rounding',function()
    local api=create({icons=icons});local maximum=9007199254740991
    local row=api:summarize({entry(1,100,maximum,0,{air=maximum}),entry(2,100,1,1,{air=1})},nil,100).periods[1]
    assert(row.kills==nil and row.known_kills==nil and row.overflow.kills)
    assert(row.deaths==1 and row.ribbons.air==nil and row.overflow.ribbons.air)
end)
check('all includes preserved unknown-time and interrupted matches without inventing a career baseline',function()
    local api=create({icons=icons})
    local partial=entry(2,200,20,0,{recon=2});partial.status='interrupted'
    local result=api:summarize({entry(1,nil,10,1,{air=3}),partial},state(100,2),300)
    assert(result.all.missions==2 and result.all.kills==30 and result.all.deaths==1)
    assert(result.all.unknown_time==1 and result.all.ribbons.air==3 and result.all.ribbons.recon==2)
    assert(result.all.career.baseline==nil and result.all.career.series==nil)
    assert(result.periods[1].missions==1 and result.periods[1].kills==20)
end)
check('all baseline and bounded trend use only actual observations and preserve endpoints',function()
    local api=create({icons=icons})
    for hour=1,100 do api:observe(state(100+hour,2),hour*HOUR)end
    local current=state(220,2)
    local result=api:summarize({},current,101*HOUR)
    local all=result.all.career
    assert(all.baseline.at==HOUR and all.baseline.kd==50.5 and all.delta==59.5)
    assert(#all.series==24 and all.series[1].at==HOUR and all.series[24].at==101*HOUR)
    local previous=-1
    for _,p in ipairs(all.series)do
        assert(p.at>previous);previous=p.at
        assert(p.kd==(p.at==101*HOUR and 110 or (100+p.at/HOUR)/2),'no interpolated data')
    end
    local day=result.periods[1].career
    assert(day.baseline.at==77*HOUR and #day.series<=24 and day.series[1].at==77*HOUR)
    assert(result.periods[2].career.partial and result.periods[2].career.series[1].at==HOUR,
        'shorter retained history is drawn from its actual first point without inventing seven-day-old data')
end)
print('Career history summary tests passed: '..tests..' (pure period sums and independent bounded career checkpoints)')
check('patriotic bill all-time and period sums keep real zero separate from missing older bills',function()
    local now=60*DAY;local api=create({icons=icons})
    local a,b,c,d=entry(1,now,1,0),entry(2,now-DAY-1,2,0),entry(3,now,3,0),entry(4,now,4,0)
    a.patriotic_bill={version=1,total_cents=1200,entries={{key='ammo:a',name='AC-8 弹药',amount_cents=1200}}}
    b.patriotic_bill={version=1,total_cents=800,entries={{key='ammo:a',name='AC-8 弹药',amount_cents=800}}}
    c.patriotic_bill={version=1,total_cents=0,entries={}}
    local result=api:summarize({a,b,c,d},nil,now)
    local all=result.all.patriotic_bill;local day=result.periods[1].patriotic_bill
    assert(all.total_cents==2000 and all.recorded_missions==3 and all.missing_missions==1)
    assert(#all.entries==1 and all.entries[1].amount_cents==2000)
    assert(day.total_cents==1200 and day.recorded_missions==2 and day.missing_missions==1)
    all.entries[1].amount_cents=1;assert(a.patriotic_bill.entries[1].amount_cents==1200,'aggregate owns its own rows')
    assert(api:summarize({d},nil,now).all.patriotic_bill.recorded_missions==0)
end)
check('revision cache avoids rescans across seconds while preserving exact time and source ownership',function()
    local api=create({icons=icons});local now=60*DAY
    local raw=entry(1,now-100,3,1,{air=2})
    raw.patriotic_bill={version=1,total_cents=150,entries={{key='a',name='费用',amount_cents=150}}}
    local reads=0
    local proxy=setmetatable({},{__index=function(_,key)reads=reads+1;return raw[key]end})
    local entries={proxy};local current=state(100,10)
    local first=api:summarize(entries,current,now,1)
    assert(reads>0 and first.all.kills==3)
    reads=0
    first.all.patriotic_bill.entries[1].amount_cents=999
    local second=api:summarize(entries,current,now+1.25,1)
    assert(reads==0,'an unchanged retained archive is not scanned on each UI second')
    assert(second.as_of==now+1.25 and second.periods[1].from_at==now+1.25-DAY and second.all.to_at==now+1.25)
    assert(second.all.patriotic_bill.entries[1].amount_cents==150,'returned aggregates cannot mutate the cached source')
    raw.kills=4
    assert(api:summarize(entries,current,now+2,2).all.kills==4,'same-table revision update invalidates aggregates')
    raw.kills=5
    assert(api:summarize(entries,current,now+3).all.kills==5,'unversioned callers still observe in-place edits')
    raw.kills=6
    assert(api:summarize(entries,current,now+4).all.kills==6)
end)
check('cached periods enter and leave at exact timestamps, including rollback and reload',function()
    local api=create({icons=icons});local now=60*DAY
    local entries={entry(1,now-DAY,2,1),entry(2,now+.5,3,1)}
    assert(api:summarize(entries,nil,now,1).periods[1].kills==2)
    assert(api:summarize(entries,nil,now+.0001,1).periods[1].kills==0)
    assert(api:summarize(entries,nil,now+.5,1).periods[1].kills==3)
    assert(api:summarize(entries,nil,now,1).periods[1].kills==2,'clock rollback restores an expired row')
    for index,seconds in ipairs({DAY,7*DAY,30*DAY})do
        local timed={entry(1,now-seconds,9,1)}
        assert(api:summarize(timed,nil,now,index).periods[index].kills==9)
        assert(api:summarize(timed,nil,now+.01,index).periods[index].kills==0)
    end
    local restored=create({icons=icons,saved=api:snapshot()})
    assert(restored:summarize(entries,nil,now+.5,1).periods[1].kills==3)
end)
