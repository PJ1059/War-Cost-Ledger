local create=dofile(assert(arg[1]))
local layout=create()
local stats={kills='240',shots='1145',bill_text='130564.38$',kd_text='240/0［75.96↑］'}
local function item(id,kind,count,name,hit)
    return {id=id,kind=kind,count=count,total=count,name=name or id,side_icon=hit==true}
end
local function awards()
    return {ribbons={},medals={},hits={},items={},revision=1}
end
local function near(a,b) assert(math.abs(a-b)<.001,tostring(a)..' != '..tostring(b)) end
local view=awards()
view.items={item('H04','ribbon',7,nil,true),item('R01','ribbon',8),item('M01','medal',1,'民主收割机')}
view.deadline=3
local plan=layout:build(stats,view,false,600,nil,1,1)
assert(#plan.metrics==4 and plan.metrics[1].id=='U01' and plan.metrics[4].id=='U04')
local skull_center=plan.metrics[1].icon_x+plan.metrics[1].icon_width/2
assert(plan.metrics[1].icon_width==26 and plan.metrics[1].icon_height==29)
for index=2,4 do
    local metric=plan.metrics[index]
    near(metric.icon_width,10.5);near(metric.icon_height,10.5)
    near(metric.icon_x+metric.icon_width/2,skull_center)
end
assert(plan.metrics[4].text=='240/0[75.96]' and plan.metrics[2].text=='130564.38$')
assert(plan.metrics[4].history_trend==1 and plan.metrics[4].trend.id=='I01')
assert(plan.metrics[4].text_body=='240/0[75.96' and plan.metrics[4].text_suffix==']')
assert(plan.side.hits[1].count_text=='x7' and plan.side.medals[1].count_text=='x1')
assert(plan.side.hits[1].y<plan.side.ribbons[1].y and plan.side.ribbons[1].y<plan.side.medals[1].y)
for _,kind in ipairs({'hits','ribbons','medals'}) do
    local box=plan.side[kind][1]
    near(box.x+box.width,600);near(box.count_x,600)
end
assert(plan.side.ribbons[1].count_y>=plan.side.ribbons[1].icon_y+20)
local medal=plan.side.medals[1]
assert(medal.name_lines[1]=='民主收割机' and medal.name_y>=medal.icon_y+medal.icon_height)
near(medal.name_x,600)
assert(layout:build(stats,view,false,600,nil,1.9,1)==plan,'idle reuses its geometry')
for _,case in ipairs({
    {text='11/0［75.96↓］',trend=-1,id='I02'},
    {text='75.96［75.96］',trend=0},
    {text='11/0[75.96]',trend=-1,id='I02'},
}) do
    local p=create():build({kd_text=case.text,history_trend=case.trend},awards(),false,600,nil,0,1)
    local kd=p.metrics[4]
    assert(not kd.text:find('[［］↑↓]'))
    assert((kd.trend and kd.trend.id)==case.id)
    if kd.trend then
        assert(kd.trend.width==8 and kd.trend.height==4)
        assert(kd.body_text_x<kd.trend.x and kd.trend.x+8<=kd.suffix_text_x-8)
    else assert(kd.text_body==nil and kd.text_suffix==nil) end
end
view=awards();view.deadline=4
for n=1,6 do view.items[#view.items+1]=item('M0'..n,'medal',1,'血管中全是自由的香气') end
local narrow=layout:build(stats,view,false,336,nil,2,1)
assert(#narrow.side.medals==6 and #narrow.side.medals[1].name_lines==2)
assert(narrow.side.medals[4].y>narrow.side.medals[1].y,'named medals wrap to a second row')
for _,box in ipairs(narrow.glyphs) do
    assert(box.x>=0 and box.x+box.width<=narrow.width)
    assert(box.y+box.height<=narrow.height)
end
local wide=layout:build(stats,view,false,600,nil,2.1,1)
near(wide.side_height,narrow.side_height)
view=awards();view.medals={item('M01','medal',1,'民主收割机')}
local folded=layout:build(stats,view,false,600,nil,4,1)
assert(folded.side_height==0 and #folded.side.medals==0 and #folded.collected.medals==1)
view.hits={item('H02','ribbon',1,nil,true),item('H03','ribbon',0,nil,true),item('H04','ribbon',50,nil,true)}
view.ribbons={item('R01','ribbon',7),view.hits[1]}
assert(#layout:build(stats,view,false,600,nil,4,1).collected.hits==0,'always ribbons do not reveal TAB-only details')
local mapped=layout:build(stats,view,true,600,nil,4,1)
assert(#mapped.collected.hits==2 and #mapped.collected.ribbons==1)
assert(mapped.collected.hits[1].y>mapped.collected.medals[1].y)
assert(mapped.collected.hits[1].count_text=='1')
local charges={items={{id='stim',name='治疗针',text='治疗针 -2500.00MC',amount_text='-2500.00MC'}},deadline=7}
view.items={item('H02','ribbon',1,nil,true)};view.deadline=7
local charged=layout:build(stats,view,true,600,charges,5,1)
assert(#charged.charges==1 and charged.charges[1].text=='治疗针 -2500.00MC')
assert(charged.charges[1].y>=charged.side.hits[1].y+charged.side.hits[1].height+6)
assert(charged.height>=charged.charges[1].y+charged.charges[1].height)
collectgarbage('collect');collectgarbage('stop')
local before=collectgarbage('count')
for _=1,10000 do assert(layout:build(stats,view,true,600,charges,5.5,1)==charged) end
local growth=collectgarbage('count')-before;collectgarbage('restart')
assert(growth<16,'idle layout allocated '..growth..' KiB')
print('PASS: four icon metrics, shared right edge, distinct notice rows, names/wrapping, peak height/reclaim, TAB-only positive hit totals, charge reservation and 10000 retained layouts.')
