-- Load official module definitions without executing HUD+'s game entry.
local addon_path,host_path,art_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a');f:close();return s end
local source=read(host_path)
local terminal="return import('entry')"
source=source:sub(1,assert(source:find(terminal,1,true))-1)..'return import'
local import=assert(loadstring(source,'=official_hud_host'))()
local Addons=import('core.addons')
local result=assert(dofile(addon_path))
if type(result)=='function'then result=result({art=dofile(art_path),publish=false})end
assert(type(result)=='table'and type(result.screens)=='table'and #result.screens>0,'legacy declaration retained')
assert(result.id=='war-cost-ledger.runtime-overlay'and result.requires.lifecycle==1 and result.requires.widgets==1)
assert(#result.options==0 and #result.resources==0,'no extra HUD options or opaque resources')
local menu=import('game.menu_data')
assert(result.menu.template==menu.template and result.menu.resource==menu.resource,'valid strings already owned by host')
local reason,contract=Addons.compatible(Addons.contracts,result)
if Addons.contracts.lifecycle~=1 then
    assert(reason=='contract'and contract=='lifecycle','0.2.8 has no lifecycle contract; Runtime fallback remains separate')
    print('PASS HUD+ 0.2.8 explicitly lacks lifecycle=1; no fake native adaptation.')
    return
end
assert(reason==nil,'latest official host accepts real addon shape: '..tostring(reason))
local widgets_created,events=0,{}
local host=Addons.new({result},{widgets=function(resources)
    assert(#resources==0);widgets_created=widgets_created+1
    return setmetatable({},{__index=function()error('modern handshake must not draw native widgets')end})
end},function(event)events[#events+1]=event end)
assert(widgets_created==1 and host.instances[result.id],'official host created the real lifecycle instance')
local status=result.native_hud_status
assert(status.backend=='runtime_overlay'and status.modern_host and not status.ready)
assert(status.status=='runtime_overlay_selected'and not status.pixels_verified,'backend selection does not claim visible pixels')
host:prepare({});host:sample({});host:finish({})
if type(host.leave)=='function'then host:leave()end
host:close()
assert(status.modern_host==false and not status.ready)
for _,event in ipairs(events)do assert(event.action~='failed')end
print('PASS official HUD+ lifecycle=1 accepts Runtime backend handshake; no native widgets, new menu rows or false readiness.')
