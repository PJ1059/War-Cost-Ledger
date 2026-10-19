-- Shipping built entry: no F9 registration/window, normal Career entry and retained combat HUD.
-- Only game/memory, public input and Runtime draw primitives are owned fixtures.
local addon,runtime,fixture,art_path=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local root=assert(arg[5], 'repository root required')
local input=assert(io.open(fixture,'rb'));local source=input:read('*a'):gsub('\r\n','\n');input:close()
local boundary=assert(source:find('state=dofile(path).state',1,true))
local prefix=source:sub(1,boundary-1)
local changed
prefix,changed=prefix:gsub("return {version='0%.30%.3'}", "return dofile(runtime_root .. '/domains/metadata.lua')")
assert(changed==1,'integration metadata boundary changed')
local scenario=[=[
active=false
os.clock=function()return 0 end -- deterministic logical replay, no CPU claim
local actual_version=require('hd2runtime/domains/metadata').version
local art=dofile(_ART_PATH)
local art_ids={}
for _,row in ipairs(art.images)do art_ids[row.id]=row.image_id end
local bindings,surfaces,handles,captures,cursors={},{},{},{},{}
local pressed,keys={},{}
local mouse={x=0,y=0,w=1920,h=1080,left=false}
local screen_w,screen_h=1920,1080
local settings_open=false
local career_peer
local cursor_menu_at_hold,cursor_held=false,false
local now,sets,saves,memory_reads,world_opens=0,0,0,0,0
local old_set=store.set
function store:set(k,v)sets=sets+1;old_set(self,k,v)end
function store:save()saves=saves+1;return true end
function mod:bind(id,spec)bindings[id]=spec;return{state='active'}end
for _,name in ipairs({'read','fill','pointer','u32'})do
    local old=view[name]
    if old then view[name]=function(...)memory_reads=memory_reads+1;return old(...)end end
end
local old_world=package.preload['hd2runtime/runtime/event_world']
package.preload['hd2runtime/runtime/event_world']=function()
    local api=old_world()
    api.open=function()
        if not available then return nil,'owned world unavailable'end
        world_opens=world_opens+1
        -- Actual Runtime may return another table with the same game identity.
        local value={};for k,v in pairs(world)do value[k]=v end;return value
    end
    local players=api.players
    api.players=function(...)
        local result=players(...)
        if career_peer then result[1].peer=career_peer end
        return result
    end
    api.game_state=function()return{state=active and 4 or 3,mission=active,host=host}end
    return api
end
local old_hd2=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local api=old_hd2()
    api.resources={image=function(id)
        if not handles[id]then handles[id]={id=id}end;return handles[id]
    end}
    api.input={pressed=function(key)return pressed[key]==true end,
        down=function(key)return keys[key]==true end,
        mouse=function()return mouse end,wheel=function()return 0 end,
        focused=function()return true end,
        block=function(spec)captures[#captures+1]=spec;return true end}
    api.ui.settings_open=function()return settings_open end
    api.ui.cursor=function()
        -- Real mod_cursor keeps game_menu only while a hold is applied. Its
        -- release() clears that evidence; false does not prove a menu closed.
        return{held=cursor_held,holders={},game_menu=cursor_held and cursor_menu_at_hold}
    end
    api.ui.overlay=function(options)
        local surface={id=options.id,visible=options.visible~=false}
        function surface:draw(fn)self.callback=fn end
        function surface:show(on)self.visible=on~=false;return self end
        function surface:hide()self.visible=false;cursor_held=false;return self end
        function surface:free_cursor(on)
            self.cursor=on~=false;cursor_held=self.cursor;cursors[#cursors+1]=self.cursor;return self
        end
        surfaces[options.id]=surface;return surface
    end
    return api
end
rawset(_G,'stingray',{Gui={resolution=function()return screen_w,screen_h end}})
saved.ui_settings={auto_ui_probe=false,career_ship_sync=false,career_page_sync=false}
saved.career_awards_v1={version=1,totals={ribbons={air=7},medals={democracy_harvester=2}}}
saved.compat_sentinel={keep='existing-account'}
local module=dofile(path);state=module.state
assert(module.version=='0.4.69' and module.runtime_compatibility.version==actual_version)
assert(module.career_overlay_snapshot==nil and module.career_overlay_status==nil
    and type(module.hud_backend)=='function','retired independent archive remains wired into built entry')
assert(bindings['war_cost_ledger.toggle_collection']==nil,'retired collection shortcut registered')
for id,binding in pairs(bindings)do assert(binding.key~='F9','unexpected F9 registration: '..id)end
assert(surfaces.costs and not surfaces.archive,'independent archive overlay must not be created')
for id in pairs(surfaces)do assert(id=='costs','unexpected additional overlay: '..id)end
local function tick(dt)
    dt=dt or .1;now=now+dt;clock=clock+math.floor(dt*1000000);frame(dt);pressed={}
end
local function canon(value)
    if type(value)~='table'then return type(value)..':'..tostring(value)end
    local names={};for k in pairs(value)do names[#names+1]=k end
    table.sort(names,function(a,b)return tostring(a)<tostring(b)end)
    local out={};for _,k in ipairs(names)do out[#out+1]=canon(k)..'='..canon(value[k])end
    return'{'..table.concat(out,',')..'}'
end
local function account()return canon(saved)end
local function render()
    local result={texts={},images={},rects=0,surfaces={}}
    local reads_before,sets_before,saves_before=memory_reads,sets,saves
    for id,surface in pairs(surfaces)do
        if surface.visible and surface.callback then
            local d={width=screen_w,height=screen_h,scale=math.min(screen_w/1920,screen_h/1080)}
            function d:rect(x,y,w,h)
                assert(w>=0 and h>=0 and x==x and y==y,'invalid Runtime rectangle')
                -- Actual Runtime Builder:rect clips to the viewport; image
                -- quads below deliberately have the stricter whole-box rule.
                if math.min(screen_w,x+w)>math.max(0,x)and math.min(screen_h,y+h)>math.max(0,y)then
                    result.rects=result.rects+1
                end
            end
            function d:text(text,x,y,opts)
                assert(type(text)=='string'and x>=-.01 and y>=-.01 and x<=screen_w+.01 and y<=screen_h+.01)
                result.texts[#result.texts+1]=text
            end
            function d:image(handle,x,y,w,h)
                assert(type(handle)=='table'and handles[handle.id]==handle,'renderer bypassed retained image ownership')
                assert(w>0 and h>0 and x>=-.01 and y>=-.01 and x+w<=screen_w+.01 and y+h<=screen_h+.01,
                    'Runtime image quad outside viewport')
                result.images[handle.id]=(result.images[handle.id]or 0)+1
            end
            result.surfaces[id]=true;surface.callback(d)
        end
    end
    assert(reads_before==memory_reads and sets_before==sets and saves_before==saves,
        'a draw callback polled native memory or wrote the ledger')
    return result
end
local function contains(draw,text)
    for _,value in ipairs(draw.texts)do if value:find(text,1,true)then return true end end
    return false
end
tick();tick()
local original_account,original_sets,original_saves=account(),sets,saves
for _=1,12 do tick(.016);render()end
assert(#captures==0 and #cursors==0,'ordinary Ship frames must not request input leases or a free cursor')
assert(account()==original_account and sets==original_sets and saves==original_saves,'ordinary Ship frames changed stored data')
-- Open the real personal Career page through its native visible-parent fixture.
-- The built reader and feed remain unchanged; no shortcut or owned geometry is used.
local before_world=world
local saved_arg=arg
HD2_CAREER_PANEL_FIXTURE_ONLY=true
arg={_ROOT..'/src/native-career-panel-reader.lua',runtime_root,_ROOT..'/tests/fixtures/career-parent-headers.lua'}
local f=dofile(_ROOT..'/tests/test_native_career_panel_reader.lua')
HD2_CAREER_PANEL_FIXTURE_ONLY=nil;arg=saved_arg
local memory=f.memory();world=memory.world;world.view.slot=function()return{}end
career_peer=f.peer
tick();tick()
local career=assert(module.career_panel_snapshot(),'normal personal Career page did not publish a model')
assert(career.shown and career.parent==f.fixture.controller+0x4DAF8
    and career.gui_context==f.fixture.gui_context and career.model.view=='collection'
    and #career.model.header_texts>0,'normal Career lost native geometry or real layout')
local awards={};for _,item in ipairs(career.model.items)do awards[item.id]=item.count end
assert(awards.R01==7 and awards.M01==2,'normal Career did not retain saved ribbon and medal totals')
assert(not render().surfaces.archive and #captures==0 and #cursors==0,
    'normal Career entry created an independent overlay or captured input outside its controls')
assert(account()==original_account and sets==original_sets and saves==original_saves,
    'opening normal Career changed historical data')
memory:patch(f.fixture.controller+f.M.source.panel+f.M.source.alpha,f.b.encode(0,'f32'))
tick();assert(module.career_panel_snapshot()==nil,'closing the normal Career page left a stale feed')
world=before_world;career_peer=nil
assert(#captures==0 and #cursors==0,'normal page visibility cycle introduced a global input/cursor lease')
print('PASS built '..actual_version..': no F9 binding, no independent archive surface/export, no ordinary-frame input/cursor lease; normal Career native reader/feed retains saved awards')

active=true;tick();tick()
local source='968211C0033DCE64'
stats.sources[source]={[SHOTS]=10,[KILLS]=2}
stats.totals[SHOTS],stats.totals[KILLS]=10,2;tick()
assert(state.total_cents==350 and state.weapon_stats[source].kills==2,'actual ammo statistics/price path did not run')
next_id=next_id+1
local titan={id=next_id,pointer=100000+next_id*256,kind='9E2E17F2CCCCAFDD',life=0,credit=0}
actors[#actors+1]=titan
tick();tick();tick();titan.life,titan.credit=2,0x11;stats.totals[KILLS]=3;tick();tick()
assert(state.ribbons.giant_bile_titan==1,'actual native kill observer did not earn the unit ribbon')
-- Supply a classified-hit result at the renderer's retained state boundary.
-- Native 96-byte hit decoding/transport has its own actual-built regressions.
state.ribbons.hit_penetration=4;state.hit_classification_ready=true
module.game_hud:observe(now)
module.game_hud:configure({ribbon_mode='always'})
rawset(_G,'HD2WarCostLedgerNativeHUDV1',{ready=true})
assert(module.hud_backend()=='native')
local native_draw=render()
assert(#native_draw.texts==0 and next(native_draw.images)==nil and native_draw.rects==0,
    'a ready legacy native HUD was duplicated by Runtime combat drawing')
rawset(_G,'HD2WarCostLedgerNativeHUDV1',nil)
assert(module.hud_backend()=='runtime_overlay')
local fallback=render()
assert(fallback.images[art_ids.G02]and fallback.images[art_ids.H04]
    and contains(fallback,'SC')and contains(fallback,'弹药'),
    'Runtime backend must draw earned ribbon, classified hit and real ammo charge')
rawset(_G,'HD2WarCostLedgerNativeHUDV1',{ready=false})
local unready=render()
assert(module.hud_backend()=='runtime_overlay'and unready.images[art_ids.G02]and unready.images[art_ids.H04]
    and contains(unready,'SC'),'an unready native host must retain Runtime combat drawing')
rawset(_G,'HD2WarCostLedgerNativeHUDV1',{ready=true,backend='runtime_overlay'})
assert(module.hud_backend()=='runtime_overlay')
local modern=render()
assert(modern.images[art_ids.G02]and modern.images[art_ids.H04]and contains(modern,'SC'),
    'new Runtime-backed HUD host must not suppress combat drawing')
assert(bindings['war_cost_ledger.toggle_collection']==nil and not module.game_hud.collection_open,
    'combat restored the removed collection shortcut')
assert(#captures==0 and #cursors==0,'combat fallback requested global input/cursor ownership')
print('PASS built '..actual_version..': ready legacy native host draws no duplicate; absent/native-unready and new Runtime-backed hosts draw actual ribbon/hit/fee without F9')

active=false;tick();tick()
local saved_awards=canon(saved.career_awards_v1.totals)
local saved_history=canon(saved.mission_history_v1)
local completed=copy(saved.last_mission)
original_account,original_sets,original_saves=account(),sets,saves
render();tick(.016)
assert(account()==original_account and sets==original_sets and saves==original_saves)
active=true;tick()
assert(not surfaces.archive and #captures==0 and #cursors==0,
    'mission entry restored independent archive ownership')
assert(canon(saved.career_awards_v1.totals)==saved_awards and saved.compat_sentinel.keep=='existing-account',
    'mission entry changed historical awards or unrelated account data')
local old_match
for _,row in ipairs(module.mission_history_snapshot().entries or{})do
    if row.sequence==completed.sequence then old_match=row;break end
end
assert(old_match and old_match.patriotic_bill and old_match.patriotic_bill.total_cents==completed.total_cents and old_match.kills==completed.kills,
    'new mission rewrote the completed historical match')
assert(saved_history~='nil:nil','fixture did not exercise saved match history')
print('PASS built '..actual_version..': completed match, career awards and account sentinel remain intact across ship/mission transitions')
]=]
scenario=scenario:gsub('_ART_PATH',function()return string.format('%q',art_path)end)
scenario=scenario:gsub('_ROOT',function()return string.format('%q',root)end)
arg={addon,runtime}
assert(loadstring(prefix..scenario,'@actual-built-no-f9-owned'))()
