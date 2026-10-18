-- Runtime mouse-message ownership is separate from the archive's scroll range.
-- Exercise the real feed/model with input samples; no process or account access.
local make=dofile(assert(arg[1]))
local make_model=dofile(assert(arg[2]))
local icons=dofile(assert(arg[3]))({},function()return true end).icons
local function fixture(mode)
    local f={now=0,calls={},mouse_reads=0,reader_reads=0,wheel_reads=0,wheel=0}
    f.geometry={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,
        alpha_address=0x50000,local_peer='0000000000000011',position={732,-237},
        width=420,height=747,root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
    f.mouse={x=10,y=10,w=1920,h=1080,left=false}
    f.gui={1920,1080}
    f.records={totals={ribbons={air=3},medals={democracy_harvester=2}}}
    f.history={revision=1,limit=500,entries={}}
    for i=1,20 do f.history.entries[i]={sequence=21-i,status='ended',kills=21-i,deaths=1,
        ended_at=200000-i*60,ribbons={air=i},medals={}} end
    local options={model=make_model(icons),records=function()return f.records end,
        history=function()return f.history end,summary=function()return {periods={}}end,
        mouse=function()f.mouse_reads=f.mouse_reads+1;return f.mouse end,
        gui_resolution=function()return unpack(f.gui)end,
        wheel=function()f.wheel_reads=f.wheel_reads+1;local v=f.wheel;f.wheel=0;return v end,
        reader=function()return {read=function()
            f.reader_reads=f.reader_reads+1;return f.geometry,'test_page_hidden'
        end}end}
    if mode~='missing' then options.block_input=function(spec)
        if spec==false then f.calls[#f.calls+1]=false else
            assert(type(spec)=='table' and spec.mouse==true and spec.keyboard==false,
                'capture must own only mouse messages, never keyboard input')
            f.calls[#f.calls+1]={mouse=spec.mouse,keyboard=spec.keyboard}
        end
        if mode=='error' then error('Runtime unavailable during transition')end
        return mode~='reject'
    end end
    f.api=make(options)
    function f:step(dt)
        self.now=self.now+(dt or .04)
        self.api:step(self.now,{}, {state=3,mission=false},{{['local']=true,peer='0000000000000011'}})
        return self.api:snapshot()
    end
    function f:sample(dt)
        self.now=self.now+(dt or .016);self.api:sample_input(self.now)
    end
    function f:plan()return assert(self.api:snapshot()).model end
    function f:aim(x,y,left)
        self.mouse={x=732+x,y=237+y,w=1920,h=1080,left=left==true}
    end
    function f:control(id)
        for _,c in ipairs(self:plan().nav_controls)do if c.id==id then return c end end
        error('missing control '..id)
    end
    function f:click(id)
        local c=self:control(id)
        self:aim(c.x+c.width/2,c.y+c.height/2,false);self:step()
        self.mouse.left=true;self:sample()
        self.mouse.left=false;self:sample()
        self:step()
    end
    function f:owns_mouse()
        local last=self.calls[#self.calls]
        return type(last)=='table' and last.mouse==true and last.keyboard==false
    end
    f:step()
    return f
end

-- Merely displaying the page does not clear another MOD's input ownership.
local idle=fixture()
idle:sample();idle.api:clear();idle.api:clear()
assert(#idle.calls==0,'outside/clear without a capture request must never send false')

-- The full half-open panel rectangle owns the mouse, including its perimeter.
for _,case in ipairs({
    {0,0,true},{419.999,0,true},{0,746.999,true},{419.999,746.999,true},
    {-0.001,200,false},{420,200,false},{200,-0.001,false},{200,747,false},
})do
    local f=fixture();f:aim(200,200);f:sample()
    assert(f:owns_mouse(),'hovering the archive must capture mouse messages before native career scrolling')
    f:aim(case[1],case[2]);f:sample()
    assert(f:owns_mouse()==case[3],'incorrect panel capture boundary '..case[1]..','..case[2])
    if not case[3] then
        assert(f.calls[#f.calls]==false,'leaving the panel releases its mouse lease')
        local count=#f.calls;f:sample();assert(#f.calls==count,'outside release occurs only once')
    end
end

local f=fixture()
f:aim(15,15);f.wheel=-3
local wheel_reads=f.wheel_reads
f:step()
assert(f:owns_mouse() and f:plan().view=='collection')
assert(f.wheel_reads==wheel_reads,'collection captures wheel messages without scrolling history')
f.wheel=0
-- Every frame renews the Runtime lease once; duplicate sample calls are inert.
local calls,mouse_reads,reader_reads=#f.calls,f.mouse_reads,f.reader_reads
f:sample();f.api:sample_input(f.now);f.api:sample_input(f.now)
assert(#f.calls==calls+1 and f.mouse_reads==mouse_reads+1,
    'one capture and raw mouse sample per frame, even with duplicate calls')
assert(f.reader_reads==reader_reads,'per-frame capture does not read native geometry')
f:sample();assert(#f.calls==calls+2,'inside panel renews capture on the next frame')

-- A short press remains available through mouse.left while messages are captured.
f:click('tab_history')
assert(f:plan().view=='history','captured 16ms click still opens history')
local plan=f:plan()
for _,y in ipairs({5,plan.list_top-1,plan.list_bottom,746})do
    f:aim(100,y);f.wheel=-3
    local scroll=f:plan().scroll;wheel_reads=f.wheel_reads
    f:step()
    assert(f:owns_mouse(),'header/footer must block the underlying career list')
    assert(f:plan().scroll==scroll and f.wheel_reads==wheel_reads,
        'header/footer do not consume archive list scroll distance')
    f.wheel=0
end
f:aim(100,(f:plan().list_top+f:plan().list_bottom)/2)
f.wheel=-3;f:step()
assert(f:plan().scroll>0 and f:owns_mouse(),'only the hovered archive history scrolls')
for i=1,10 do f.wheel=-20;f:step()end
assert(f:plan().scroll==f:plan().max_scroll and f:owns_mouse(),
    'at the bottom, wheel ownership does not pass to the native career list')
for i=1,10 do f.wheel=20;f:step()end
assert(f:plan().scroll==0 and f:owns_mouse(),
    'at the top, wheel ownership does not pass to the native career list')
f:aim(-1,400);f.wheel=-3;f:step()
assert(f:plan().scroll==0 and not f:owns_mouse(),'outside panel restores native wheel handling')
f.wheel=0
assert(f.records.totals.ribbons.air==3 and #f.history.entries==20 and f.history.revision==1,
    'input routing leaves stored awards and history untouched')

-- Lost focus is represented by the Runtime mouse provider returning no sample.
for _,failure in ipairs({'focus','projection','clear','stale','reader','ship'})do
    local q=fixture();q:aim(100,100);q:sample();assert(q:owns_mouse())
    if failure=='focus' then q.mouse=nil;q:sample()
    elseif failure=='projection' then q.gui={};q:sample()
    elseif failure=='clear' then q.api:clear('test_closed')
    elseif failure=='stale' then q:sample(.251)
    elseif failure=='reader' then q.geometry=nil;q:step()
    elseif failure=='ship' then q.api:step(q.now+.016,{}, {state=2,mission=false},{})end
    assert(q.calls[#q.calls]==false,'capture released on '..failure)
    local count=#q.calls;q.api:clear();q.api:clear()
    assert(#q.calls==count,'release after '..failure..' does not clear other MOD input twice')
end

-- Exact freshness threshold is allowed; crossing it releases without polling memory.
local stale=fixture();stale:aim(100,100)
stale.now=stale.api:snapshot().now+.25;stale.api:sample_input(stale.now)
assert(stale:owns_mouse(),'geometry valid at the .25 second freshness limit')
local native_reads=stale.reader_reads
stale:sample(.0001)
assert(not stale:owns_mouse() and stale.reader_reads==native_reads,'expired cached page releases cheaply')

-- Queued input from a destroyed native page cannot click its replacement.
local rebuilt=fixture()
local tab=rebuilt:control('tab_history')
rebuilt:aim(tab.x+4,tab.y+tab.height/2);rebuilt:step()
rebuilt.mouse.left=true;rebuilt:sample();assert(rebuilt:owns_mouse())
-- Reader snapshots are separate tables in production, not a mutable identity alias.
local old=rebuilt.geometry
rebuilt.geometry={}
for k,v in pairs(old)do rebuilt.geometry[k]=v end
rebuilt.geometry.parent=old.parent+1
rebuilt:step()
assert(not rebuilt.api:snapshot() and rebuilt.calls[#rebuilt.calls]==false,
    'native page replacement releases capture and invalidates pending clicks')
rebuilt.mouse.left=false;rebuilt:step();rebuilt:sample()
assert(rebuilt:plan().view=='collection' and rebuilt:owns_mouse(),
    'newly verified page reacquires capture without applying the old click')
rebuilt:click('tab_history');assert(rebuilt:plan().view=='history','new page accepts ordinary short clicks')

-- Runtime may set flags before returning false or raising: always release an
-- attempted lease on exit; a missing interface is also safe on older runtimes.
for _,mode in ipairs({'missing','reject','error'})do
    local q=fixture(mode);q:aim(100,100);q:sample()
    q:aim(-1,100);q:sample();q.api:clear()
    if mode=='missing' then assert(#q.calls==0)
    else assert(#q.calls==2 and type(q.calls[1])=='table' and q.calls[2]==false,
        'failed Runtime capture must still be released once: '..mode)end
end
print('PASS career wheel capture: full panel boundaries, renewable mouse-only lease, collection/header/footer ownership, list-only scroll with no edge passthrough, outside/focus/projection/stale/clear/rebuild release, one sample per frame, short clicks, unavailable/rejected/error APIs, unchanged history.')
