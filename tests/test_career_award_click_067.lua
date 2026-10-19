-- Real model/feed input, including fast clicks queued between 10 Hz native samples.
local make=dofile(assert(arg[1]))
local make_model=dofile(assert(arg[2]))
local icons=dofile(assert(arg[3]))({},function()return true end).icons
local function fixture()
    local g={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,
        alpha_address=0x50000,local_peer='0000000000000011',position={732,-237},width=420,height=747,
        root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
    local mouse={x=10,y=10,w=1920,h=1080,left=false}
    local now=0
    local records={totals={ribbons={air=3},medals={democracy_harvester=2}}}
    local history={revision=1,limit=500,entries={}}
    for i=1,20 do history.entries[i]={sequence=21-i,status='ended',kills=21-i,deaths=1,
        ended_at=200000-i*60,ribbons={air=i},medals={}} end
    history.entries[1].medals.democracy_harvester=1
    local api=make({model=make_model(icons),records=function()return records end,
        history=function()return history end,mouse=function()return mouse end,
        format_time=function()return '2026-10-19 12:00' end,
        gui_resolution=function()return 1920,1080 end,
        reader=function()return {read=function()return g end}end})
    local f={history=history}
    function f:step(dt)
        now=now+(dt or .1)
        api:step(now,{}, {state=3,mission=false},{{['local']=true,peer='0000000000000011'}})
        return self:plan()
    end
    function f:plan()return assert(api:snapshot()).model end
    function f:item(kind)
        for _,item in ipairs(self:plan().items)do if item.kind==kind then return item end end
        error('missing '..kind)
    end
    function f:input(item,left,dt)
        mouse={x=item and g.position[1]+item.x+4 or 10,
            y=item and -g.position[2]+item.y+item.height/2 or 10,w=1920,h=1080,left=left}
        now=now+(dt or .016);api:sample_input(now)
    end
    function f:press(item)self:input(item,false);self:input(item,true);self:input(item,false)end
    f:step()
    return f
end

-- The clicked ribbon owns #1, even when the latest pointer hovers a medal owning #20.
local f=fixture()
local ribbon,medal=f:item('ribbon'),f:item('medal')
assert(ribbon.sequence==1 and medal.sequence==20)
f:press(ribbon);f:press(ribbon);f:input(medal,false)
local plan=f:step()
assert(plan.view=='history' and plan.expanded_sequence==1,
    'queued double-click used the latest hovered award instead of the clicked ribbon')

-- Moving away before the native sample must not erase a valid medal double-click.
f=fixture();medal=f:item('medal')
f:press(medal);f:press(medal);f:input(nil,false)
plan=f:step()
assert(plan.view=='history' and plan.expanded_sequence==20,
    'queued medal double-click must not depend on a currently visible tooltip')

f=fixture();f:press(f:item('ribbon'));plan=f:step()
assert(plan.view=='collection','one click must not navigate')

f=fixture();ribbon=f:item('ribbon')
f:press(ribbon);f:step();f:step(.41);f:press(ribbon);plan=f:step()
assert(plan.view=='collection','separate clicks outside 400 ms must not navigate')

f=fixture();f:press(f:item('ribbon'));f:press(f:item('medal'));plan=f:step()
assert(plan.view=='collection','clicking two different awards is not a double-click')

-- A refreshed history changes the validated award destination. Drop the old
-- queued presses instead of silently sending them to the newly indexed match.
f=fixture();ribbon=f:item('ribbon');f:press(ribbon);f:press(ribbon)
f.history.entries[1].ribbons.air=100
f.history.revision=f.history.revision+1
plan=f:step()
assert(plan.view=='collection','stale queued destination must not navigate after history changes')
print('PASS: fast queued award double-clicks use the clicked destination after cursor movement; single/slow/mixed/stale clicks do not navigate.')
