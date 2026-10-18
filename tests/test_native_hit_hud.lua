-- Actual owned native records through the production presentation modules.
-- The game process is never opened; the real LuaJIT and HUD+ Reader run here.
package.preload['hd2runtime/core/bytes']=function()return dofile(arg[2]..'/core/bytes.lua')end
local root=assert(arg[1])
local decoder=dofile(root..'/src/native-hit-feedback.lua')
local make_battle=dofile(root..'/src/battle-hud.lua')
local make_awards=dofile(root..'/src/award-notifications.lua')
local make_hud=dofile(root..'/src/game-hud.lua')
local make_feed=dofile(root..'/src/native-hud-feed.lua')
local make_native=dofile(root..'/src/native-hud-addon.lua')
local art=dofile(assert(arg[3]))
assert(#art.images==18)
local assets={};for _,a in ipairs(art.images)do assets[a.id]=a end
for _,id in ipairs({'H01','H02','H03','H04','H05'})do assert(assets[id])end
local state={sequence=1,shots=0,kills=0,deaths=0,total_cents=0,ribbons={hit_total=7},mission_medals={}}
local battle=make_battle(state,function()return true end)
local icons={}
for _,icon in ipairs(battle.icons)do if assets[icon.id] then
    icons[#icons+1]=icon
    if icon.kind=='ribbon' then state.ribbons[icon.key]=state.ribbons[icon.key] or 0 end
end end
local awards=make_awards(state,icons);awards:baseline(0)
local allocations=0
local hud=make_hud({resources={image=function(id)allocations=allocations+1;return id end}},
    state,battle,awards,art,{battle=make_battle,awards=make_awards})
local geometry={hud=0x20000000,key='owned-hud',local_top=96,width=480,available_height=900}
hud:set_map({hud=geometry.hud,mission=true,map_open=false})
local feed=make_feed(hud,state,battle,awards)
local file=assert(io.open(arg[4],'rb'));local raw=file:read('*a');file:close();assert(#raw==384)
local transport={abi=1,stride=96,count=4,epoch='0000000000000001',dropped='0000000000000000',connector_proven=true}
local observer=decoder.new({peer='FEDCBA9876543210',epoch=transport.epoch,accept=function(contact)
    local key='hit_'..contact.result
    state.ribbons[key]=state.ribbons[key]+contact.count
    return true
end})
local function snapshot(now,map,visible)
    hud:set_map({hud=geometry.hud,mission=true,map_open=map})
    feed:update(geometry,now,visible~=false)
    return feed:snapshot()
end
assert(observer:consume(raw,10,transport))
local side=snapshot(10,false)
assert(#side.side==4 and #side.ribbons==0)
for _,item in ipairs(side.side)do assert(item.side_icon==true and item.count==1)end
assert(state.ribbons.hit_total==7,'classified contacts must not double-add the existing native total')
assert(observer:consume(raw,10.1,transport) and observer.stale==4)
assert(#snapshot(11.999,false).side==4)
assert(#snapshot(12,false).side==0)
local collected=snapshot(12,true)
assert(#collected.ribbons==5 and #collected.side==0)
assert(collected.block_height>side.block_height,'the complete task list must reserve the second ribbon row')
for _,item in ipairs(collected.ribbons)do assert(item.count==(item.id=='H01' and 7 or 1))end
-- Start another burst: one icon per type, the batch number grows, totals persist.
local next_raw=raw:gsub('^.',string.char(5),1)
assert(observer:consume(next_raw:sub(1,96),13,{abi=1,stride=96,count=1,epoch=transport.epoch,
    dropped=transport.dropped,connector_proven=true}))
local fresh=snapshot(13,true)
assert(#fresh.side==1 and fresh.side[1].id=='H03' and fresh.side[1].count==1)
assert(state.ribbons.hit_blocked==2)
local repeated=raw:sub(1,96):gsub('^.',string.char(6),1)
assert(observer:consume(repeated,13.2,{abi=1,stride=96,count=1,epoch=transport.epoch,
    dropped=transport.dropped,connector_proven=true}))
local grown=snapshot(13.2,true)
assert(#grown.side==1 and grown.side[1].id=='H03' and grown.side[1].count==2)
assert(state.ribbons.hit_blocked==3,'same type must add its number, not another icon')
assert(snapshot(13.3,true,false)==nil and state.ribbons.hit_blocked==3)
assert(#snapshot(15.2,true).ribbons==5 and #snapshot(15.2,true).side==0)

-- The real installed host accepts the compiled artwork and resolves native sources.
local hf=assert(io.open(assert(arg[5]),'rb'));local hs=hf:read('*a');hf:close()
local entry=assert(hs:find('\nlocal __entry, __argument = __module_registry',1,true))
stingray={Application={},Vector2={},Vector3={}}
local host=assert(loadstring(hs:sub(1,entry)..'\nreturn {modules=__module_registry,errors=__module_errors}'))()
assert(#host.errors==0)
local current=side
local native=make_native({art=art,publish=false,feed=function()return current end})
assert(host.modules.Main.merge(host.modules.GameBaked,native)==nil)
local reader=host.modules.Reader.new({module=function()return 1000000 end,
    ptr=function()return geometry.hud end},host.modules.GameBaked.sources,host.modules.GameBaked.numbers,nil,native.compute,4)
local wanted={value={'ledger.native.feed'},position={},paint={},life={}}
assert(reader:plan({{wanted=wanted}}))
local view=reader:step()['ledger.native.feed']
for _,id in ipairs({'H02','H03','H04','H05'})do
    assert(view['side_'..id..'_texture'] and not view['side_'..id..'_frame'])
    assert(view['side_'..id..'_count']=='1')
end
current=collected
view=reader:step()['ledger.native.feed']
local rows={};for _,row in ipairs(native.screens[1].rows)do rows[row.id]=row end
for _,id in ipairs({'H02','H03','H04','H05'})do
    assert(view['collected_'..id..'_frame'] and view['collected_'..id..'_texture'])
    assert(rows['ledger_collected_'..id..'_frame'] and rows['ledger_collected_'..id..'_count'])
    assert(view['collected_'..id..'_count']=='1')
end
assert(allocations==19,'image handles must be allocated once only')
print('PASS owned native records -> four icons -> 2-second folding -> collected native ribbons')
print('PASS real HUD+ Reader/merge, one icon per type, independent total, hidden retention and task height')
