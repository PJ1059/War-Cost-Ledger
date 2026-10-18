-- Exercise the real Runtime lease/counter logic with an entirely offline hook.
-- arg[1] is runtime/mouse_wheel.lua. Native message rewriting still needs a
-- live acceptance check; this test never allocates a hook or touches the game.
local source=assert(arg[1], 'expected Runtime runtime/mouse_wheel.lua')
local events={state={now=0,frame=0}}
local pollers,logs={},{}
function events.set_poller(name,fn)pollers[name]=fn end
function events.emit_log(message)logs[#logs+1]=message end
package.loaded['hd2runtime/runtime/events']=events
package.preload['hd2runtime/settings/wheel_hook_off']=function()return false end

local native_loads=0
local function refuse_native()
    native_loads=native_loads+1
    error('offline wheel test must never load Windows/native helpers')
end
for _,name in ipairs({'hd2runtime/runtime/windows_ffi','hd2runtime/runtime/windows_write','ffi'})do
    package.loaded[name]=nil
    package.preload[name]=refuse_native
end
local axis=0
_G.stingray={Mouse={
    axis_index=function(name)assert(name=='wheel');return 7 end,
    axis=function(index)assert(index==7);return {y=axis} end}}
_G.HD2RuntimeMouseWheelV2=nil
_G.HD2RuntimeMouseWheelPagesV1=nil
local wheel=dofile(source)
-- If a future change reaches allocation despite the mock below, fail closed.
wheel.pages=function()error('offline wheel test must never allocate native pages')end

local clock_ms=5000
local legacy,raw,messages=0,0,0
local flags,until_ms=0,0
local installs,reads,removes,block_calls=0,0,0,0
wheel.hooks.install=function()
    installs=installs+1
    return {thread=7,
        read=function()reads=reads+1;return legacy,raw,messages end,
        block=function(next_flags,next_until)
            block_calls=block_calls+1
            flags,until_ms=next_flags,next_until
        end,
        now=function()return clock_ms end,
        blocked=function()return 0 end,
        remove=function()removes=removes+1;flags=0 end}
end
local function tick(ms)
    clock_ms=clock_ms+(ms or 16)
    events.state.now=(clock_ms-5000)/1000
    events.state.frame=events.state.frame+1
    local sample=pollers.wheel
    if sample then sample(events.state.now)end
end
local cases=0
local function passed(name)
    cases=cases+1
    print('PASS '..name)
end

assert(wheel.block({keyboard=false,mouse=true})==true)
assert(installs==1 and flags==2 and flags%2==0,'only mouse is blocked; keyboard stays enabled')
assert(until_ms==5500 and until_ms-clock_ms==500,'Runtime grants exactly a 500 ms lease')
assert(wheel.status().blocking==2 and pollers.wheel,'status/poller expose the active mouse lease')
passed('mouse-only lease leaves keyboard enabled')

tick(16)
local previous_expiry,previous_calls=until_ms,block_calls
assert(wheel.block({keyboard=false,mouse=true})==true)
assert(flags==2 and until_ms==5516 and until_ms>previous_expiry)
assert(block_calls==previous_calls+1 and installs==1,'renew existing hook, not a new hook')
passed('per-frame renewal extends the lease')

-- Both window message types can report the same notch. Raw takes precedence;
-- even an engine-axis value must not add another copy of the same movement.
legacy,raw,messages,axis=-120,-120,2,-7
tick(16)
local sampled_reads=reads
assert(flags==2 and wheel.read()==-1,'raw wheel remains available while native mouse is blocked')
assert(wheel.read()==-1 and reads==sampled_reads,'same tick reads reuse the sampled value')
assert(wheel.status().source=='WM_INPUT')
axis=0
tick(16)
assert(wheel.read()==0,'a consumed counter delta is not replayed on the next frame')
passed('blocked raw wheel is readable and dual-source input is not doubled')

legacy,messages=legacy+240,messages+1
tick(16)
sampled_reads=reads
assert(flags==2 and wheel.read()==2,'legacy wheel works when the raw counter is unchanged')
assert(wheel.read()==2 and reads==sampled_reads)
tick(16)
assert(wheel.read()==0,'legacy input also lasts exactly one frame')
passed('blocked legacy wheel is readable without replay')

axis=.25
tick(16)
assert(wheel.read()==.25,'engine fallback preserves fractional wheel steps')
axis=0
assert(wheel.block(false)==true)
assert(flags==0 and until_ms==0 and wheel.status().blocking==0,'release is immediate, without another tick')
raw,messages=raw-120,messages+1
tick(16)
assert(wheel.read()==-1 and flags==0,'release does not break ordinary wheel reads')
passed('immediate release and unblocked wheel reading')

assert(wheel.block({keyboard=false,mouse=true})==true)
assert(flags==2 and until_ms==clock_ms+500)
-- The 500 ms cutoff itself is enforced by native code and is not simulated as
-- proof here. Verify the real Lua idle cleanup also releases/removes its hook.
tick(1100)
assert(flags==0 and wheel.status().blocking==0 and wheel.status().hooked==false)
assert(removes==1 and pollers.wheel==nil,'stopped callers do not leave the poller/hook active')
passed('idle Lua cleanup releases the lease and removes the hook')

assert(native_loads==0 and _G.HD2RuntimeMouseWheelPagesV1==nil,'no native helper or page was used')
assert(package.loaded['hd2runtime/runtime/windows_ffi']==nil)
assert(package.loaded['hd2runtime/runtime/windows_write']==nil)
print('career wheel Runtime: '..cases..' groups passed; native message interception requires live acceptance')
