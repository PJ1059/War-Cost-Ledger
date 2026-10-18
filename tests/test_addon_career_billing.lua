-- Actual built charge -> per-match bill -> period/lifetime sum -> restart.
-- Reuse the owned native-stat fixture; no production module is substituted.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local file=assert(io.open(fixture,'rb'));local source=file:read('*a'):gsub('\r\n','\n');file:close()
local marker='state=dofile(path).state'
local at=assert(source:find(marker,1,true),'existing integration boundary missing')
local scenario=[=[
saved.mission_sequence=7
saved.last_mission={sequence=7,status='ended',kills=10,deaths=0,total_cents=300,
    entries={{event='ammunition_fired',price_id='legacy',name='历史实际弹药费',amount_cents=300}},ribbons={},mission_medals={}}
saved.mission_history_v1={version=1,max_sequence=7,deleted={},entries={
    {sequence=7,status='ended',kills=10,deaths=0,ribbons={},medals={}},
    {sequence=6,status='ended',kills=5,deaths=1,ribbons={},medals={}}}}
saved.ui_settings={billing_enabled=true,auto_ui_probe=false,career_ship_sync=false}
local module=dofile(path);state=module.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function fire(amount)
    local kind='968211C0033DCE64'
    local row=stats.sources[kind]or{[SHOTS]=0,[KILLS]=0};stats.sources[kind]=row
    row[SHOTS]=row[SHOTS]+amount;stats.totals[SHOTS]=stats.totals[SHOTS]+amount;tick()
end
local function entry(seq)
    for _,row in ipairs(module.mission_history_snapshot().entries)do if row.sequence==seq then return row end end
    error('missing real mission '..seq)
end
assert(entry(7).patriotic_bill.total_cents==300 and entry(6).patriotic_bill==nil,
    'only the actual matching legacy bill is imported')
tick();assert(state.sequence==8 and state.billing_enabled==true)
fire(10);assert(state.total_cents==350 and entry(8).patriotic_bill.total_cents==350,
    'actual source ammunition charge reaches the matching history bill')
local shown=module.game_hud:native_model(.2,true,600)
assert(shown.stats.bill_visible and #shown.charges.items>0,'charged amount is visible before the toggle')
module.ui_settings:set('billing_enabled',false)
local hidden=module.game_hud:native_model(.2,true,600)
assert(hidden.stats.bill_visible==false and #hidden.charges.items==0,'same-frame cached HUD and fees hide immediately')
for _,metric in ipairs(hidden.layout.metrics)do assert(metric.key~='bill','disabled ledger leaves no bill metric')end
fire(1000);assert(state.total_cents==350 and entry(8).patriotic_bill.total_cents==350,
    'disabled shooting does not generate new history costs')
module.ui_settings:set('billing_enabled',true)
fire(1);assert(state.total_cents==385 and entry(8).patriotic_bill.total_cents==385,
    'reenabling starts from current counters without charging the disabled shots')
active=false;tick()
assert(saved.mission_history_v1.entries[1].patriotic_bill.total_cents==385)
local all=module.career_period_summary().all.patriotic_bill
assert(all.total_cents==685 and all.recorded_missions==2 and all.missing_missions==1,
    'all career bill sums exact recorded matches while preserving missing old amounts')
local previous=saved.mission_history_v1
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick()
all=module.career_period_summary().all.patriotic_bill
assert(all.total_cents==685 and all.recorded_missions==2 and all.missing_missions==1)
assert(previous.entries[1].patriotic_bill.total_cents==385,'later saves cannot mutate old bill snapshots')
print('PASS built patriotic billing: exact legacy import, actual native source charge/history/summary, disabled no-cost baseline, reenable without catch-up, missing old bills, persistence and restart without double counts.')
]=]
arg={addon,runtime}
assert(loadstring(source:sub(1,at-1)..scenario,'@addon-career-billing-integration'))()
