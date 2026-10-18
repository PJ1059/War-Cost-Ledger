-- Read-only regression investigation: production feed/model, simulated Runtime
-- mouse and Career reader. No native memory, game, UI setters or file writes.
local make=dofile(assert(arg[1]))
local make_model=dofile(assert(arg[2]))
local icons=dofile(assert(arg[3]))({},function()return true end).icons
local geometry={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,
    alpha_address=0x50000,local_peer='0000000000000011',position={732,-237},width=420,height=747,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local function fixture()
    local mouse={x=geometry.position[1]+geometry.width/2+8,y=-geometry.position[2]+8,
        w=1920,h=1080,left=false}
    local fail=false
    local api=make({model=make_model(icons),records=function()return {totals={ribbons={},medals={}}}end,
        history=function()return {version=1,revision=1,entries={{sequence=1,status='ended',kills=4,deaths=0,
            ribbons={},medals={}}}}end,
        mouse=function()return mouse end,gui_resolution=function()return 1920,1080 end,
        reader=function()return {read=function()
            if fail then return nil,'CAREER_PANEL_TIME_BUDGET' end
            return geometry
        end}end})
    return {api=api,mouse=mouse,fail=function(value)fail=value end,
        step=function(now)api:step(now,{}, {state=3,mission=false},{{['local']=true,peer=geometry.local_peer}})end,
        view=function()local snap=api:snapshot();return snap and snap.model.view end}
end

-- Control: the same coordinates and held input activate the actual model tab.
local f=fixture();f.step(0);f.mouse.left=true
for tick=1,10 do f.step(tick/10);assert(f.view()=='history')end
f.mouse.left=false;f.step(1.1);assert(f.view()=='history')
print('CONTROL: 1-second held click at native panel-local (218,8) switches to history and stays there.')

-- Existing addon samples at 0.1-second intervals. Runtime exposes current
-- GetAsyncKeyState high-bit, not a retained down event. A 40 ms click can vanish.
f=fixture();f.step(0)
f.mouse.left=true -- t=0.02, no producer observation
f.mouse.left=false -- t=0.06, no producer observation
f.step(.1);assert(f.view()=='collection')
print('REPRO: a down/up wholly between 10 Hz observations is lost.')

-- More relevant to a held-click failure: one transient reader failure clears
-- previous_left. Recovery while still down establishes true, not a rising edge.
f=fixture();f.step(0);f.mouse.left=true;f.fail(true);f.step(.1)
assert(f.view()==nil and f.api.status=='CAREER_PANEL_TIME_BUDGET')
f.fail(false)
for tick=2,10 do f.step(tick/10);assert(f.view()=='collection')end
f.mouse.left=false;f.step(1.1);assert(f.view()=='collection')
print('REPRO: one reader failure at first down sample loses a full 1-second held click; recovery stays collection.')

-- Even a successful click is undone by the first later transient read failure.
f=fixture();f.step(0);f.mouse.left=true;f.step(.1);assert(f.view()=='history')
f.fail(true);f.step(.2);assert(f.view()==nil)
f.fail(false)
for tick=3,10 do f.step(tick/10);assert(f.view()=='collection')end
f.mouse.left=false;f.step(1.1);assert(f.view()=='collection')
print('REPRO: successful tab activation followed by one reader failure resets to collection and cannot reactivate while held.')

-- Genuine mouse release and another press work again, showing the loss is the
-- feed reset contract, not the model disabled flag, hit rectangle or pcall.
f.mouse.left=true;f.step(1.2);assert(f.view()=='history')
print('CONTROL: after stable recovery, a new released-to-pressed edge works at identical coordinates.')
