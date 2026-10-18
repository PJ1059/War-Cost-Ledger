-- Actual built addon -> real visible-page reader -> real sync/accept/persist/
-- flush/retention paths. Reuse the frozen Career-row memory and Runtime fixture
-- from the existing integration test; no built module body is replaced.
-- Arguments: built addon, Runtime root, existing addon-Career test,
-- native reader test, native reader source, frozen Career-row fixture.
local addon,runtime,fixture,reader_test,reader_source,rows=assert(arg[1]),assert(arg[2]),
    assert(arg[3]),assert(arg[4]),assert(arg[5]),assert(arg[6])
local file=assert(io.open(fixture,'rb'))
local source=file:read('*a'):gsub('\r\n','\n');file:close()
local marker='local addon=dofile(addon_path)'
local start=assert(source:find(marker,1,true),'existing Career fixture boundary missing')
assert(not source:find(marker,start+#marker,true),'ambiguous Career fixture boundary')
local scenario=[=[
local epoch=200000*3600+123
os.time=function()return epoch end
saved.mission_sequence=7
saved.last_mission={sequence=7,status='ended',kills=10,deaths=2,
    ribbons={melee=3},mission_medals={air_expert=true}}
-- Match the already-saved anchor exactly. A later successful page sample must
-- take the production sync's unchanged-value branch, not its accepted callback.
saved.career_kd.source='personal_career_visible_page'
saved.career_kd.local_peer=f.peer
saved.career_kd.synced_at='2026-10-13T00:00:00Z'
m:alpha(0)
local addon=dofile(addon_path)
local function ticks(n)for _=1,n do frame(.1)end end
local function key_writes(key)
    local n=0;for _,value in ipairs(writes)do if value==key then n=n+1 end end;return n
end
local function same(a,b)
    if type(a)~=type(b)then return false end
    if type(a)~='table'then return a==b end
    for key,value in pairs(a)do if not same(value,b[key])then return false end end
    for key in pairs(b)do if a[key]==nil then return false end end
    return true
end
local checkpoint_key='career_kd_checkpoints_v1'
ticks(60)
assert(addon.state.history_kills==351849 and addon.state.history_deaths==4633)
assert(addon.state.history_reason=='CAREER_BASELINE_PLUS_OBSERVED_DELTAS')
assert(addon.career_sync_status().status=='waiting_page')
assert(#addon.career_checkpoint_snapshot().buckets==0,
    'a valid old baseline is not evidence of a current-login sample')
assert(saved[checkpoint_key] and #saved[checkpoint_key].buckets==0,
    'initial batched migration can save an empty checkpoint store only')
local writes_before=key_writes(checkpoint_key)
m:alpha(1);ticks(22)
assert(addon.career_sync_status().status=='synced')
assert(key_writes('career_kd')==0,'this explicitly exercises synced-but-unchanged page values')
local points=addon.career_checkpoint_snapshot().buckets
assert(#points==1 and points[1].first.at==epoch and points[1].last.at==epoch)
assert(points[1].first.kills==351849 and points[1].first.deaths==4633)
ticks(60)
assert(key_writes(checkpoint_key)==writes_before+1,'new point reaches the actual batched flush')
assert(same(saved[checkpoint_key],addon.career_checkpoint_snapshot()))
local stable_writes=key_writes(checkpoint_key)
epoch=epoch+30;ticks(120)
assert(key_writes(checkpoint_key)==stable_writes,'unchanged values within the same hour cause no checkpoint saves')
assert(addon.career_checkpoint_snapshot().buckets[1].last.at==epoch-30,
    'polling does not retimestamp an unchanged observation')

local before_restart=addon.career_checkpoint_snapshot()
local summary_before=addon.career_period_summary()
assert(#addon.mission_history_snapshot().entries==1)
local before_save=saves
assert(addon.delete_mission_history==nil,'there is no public deletion API')
assert(#addon.mission_history_snapshot().entries==1 and saves==before_save)
assert(same(addon.career_checkpoint_snapshot(),before_restart))
assert(same(saved[checkpoint_key],before_restart) and key_writes(checkpoint_key)==stable_writes,
    'viewing history does not mutate independent career checkpoints')
assert(addon.career_period_summary().current.kd==summary_before.current.kd)

-- Restart in a later hour with the page closed. Old points survive, but the
-- login-specific confirmation gate must reset before a new point is accepted.
epoch=epoch+7200;m:alpha(0);rawset(_G,'HD2WarCostLedgerV1',nil)
addon=dofile(addon_path);ticks(60)
assert(same(addon.career_checkpoint_snapshot(),before_restart),'restart retains exact observed points')
assert(#addon.mission_history_snapshot().entries==1,'history stays preserved')
local restart_writes=key_writes(checkpoint_key)
m:alpha(1);ticks(22)
points=addon.career_checkpoint_snapshot().buckets
assert(addon.career_sync_status().status=='synced' and #points==2)
assert(points[1].first.at==before_restart.buckets[1].first.at and points[2].first.at==epoch)
assert(key_writes('career_kd')==0,'equal native totals are sufficient confirmation after restart too')
ticks(60)
assert(key_writes(checkpoint_key)==restart_writes+1 and same(saved[checkpoint_key],addon.career_checkpoint_snapshot()))
assert(m.writes==0,'the frozen native reader fixture never writes memory')
print('PASS actual built career checkpoints: no current-login point before native page confirmation; synced unchanged totals establish a point; batched flush without same-hour save churn; no delete API; restart retains matches/points and re-requires confirmation. Real native reader and sync logic; frozen memory only, no built-source replacement.')
]=]
arg={addon,runtime,reader_test,reader_source,rows}
assert(loadstring(source:sub(1,start-1)..scenario,'@addon-career-summary-integration'))()
