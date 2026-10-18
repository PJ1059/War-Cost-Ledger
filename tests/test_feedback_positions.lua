-- All independent settings retain cumulative totals and leave ribbons on the right.
local create=dofile(assert(arg[1]))
local stats={kills='3',shots='12',bill_text='1.20MC',kd_text='3/0[75.94]'}
local hit={id='H04',kind='ribbon',count=2,total=19,name='击穿',side_icon=true}
local ribbon={id='R02',kind='ribbon',count=1,total=3,name='反重'}
local medal={id='M01',kind='medal',count=1,total=1,name='民主收割机'}
local total_hit={id='H04',kind='ribbon',count=19,total=19,name='击穿',side_icon=true}
local awards={items={hit,ribbon,medal},hits={total_hit},ribbons={ribbon},medals={medal},revision=1,deadline=5}
local charges={items={{id='grenade',name='毒气榴弹',text='毒气榴弹 -180.00MC',amount_text='-180.00MC'}},deadline=5}
local cases=0
for _,hits in ipairs({'right','center','hidden'})do
 for _,fees in ipairs({'right','center','hidden'})do
  local layout=create()
  local positions={hit_position=hits,charge_position=fees}
  local p=layout:build(stats,awards,false,600,charges,1,1,positions)
  assert(#p.side.hits==(hits=='right' and 1 or 0),'right hit setting ignored')
  assert(#p.center_hits==(hits=='center' and 1 or 0),'central hit setting ignored')
  assert(#p.charges==(fees=='right' and 1 or 0),'right fee setting ignored')
  assert(#p.center_charges==(fees=='center' and 1 or 0),'central fee setting ignored')
  assert(#p.side.ribbons==1 and #p.side.medals==1,'position settings moved earned ribbons/medals')
  if fees=='center' and hits=='center' then
   assert(p.center_charges[1].y>=p.center_hit_height+6,'central hit and fee overlap')
  end
  local total=layout:build(stats,awards,true,600,charges,1.1,1,positions)
  assert(#total.collected.hits==1 and total.collected.hits[1].count_text=='19','hiding feedback erased TAB totals')
  cases=cases+1
 end
end
print('PASS: '..cases..' independent hit/fee position combinations, retained right ribbons and TAB totals.')
