-- Run the built addon and real translator. Only existing game-memory/UI input boundaries are fixtures.
local addon,runtime,fixture,mom_root=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local source=read(fixture)
local boundary=assert(source:find('state=dofile(path).state',1,true))
local setup=[=[
local language_code='cn'
local language_reads=0
world.runtime={language_fixture=true}
package.loaded['hd2runtime/runtime/text_resources']=nil
package.preload['hd2runtime/runtime/text_resources']=function()return {language=function(runtime)
    assert(runtime==world.runtime);language_reads=language_reads+1;return language_code
end}end
local MOM_ROOT=arg[3]
local Text=dofile(MOM_ROOT..'/src/bingus_text.lua')
local mom={state={mods={},refused={},refused_count=0,options={},option_count=0,values={},pending={},
    pending_count=0,queued={},queued_any=false,saved={},callbacks={},revision=0,dirty=false,save_timer=0},
    note=function()end,loader={log_directory='/unused'},translation={T=Text,tr=function(s)return s end},
    TEXT_TEMPLATE=123,MAX_MODS=112,MAX_ROWS=32,descriptor=function(option)return option.sequence,{} end}
assert(loadfile(MOM_ROOT..'/src/options.lua'))(mom)
assert(loadfile(MOM_ROOT..'/src/api.lua'))(mom)
_G.ModOptionsMenu=mom.api
local module=dofile(path);state=module.state
assert(module.localization,'built addon must include the production localization module')
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function find_upvalue(fn,key)
    for i=1,100 do local name,value=debug.getupvalue(fn,i)
        if not name then break end;if name==key then return value end
    end;error('missing expected fixture boundary '..key)
end
local feed=find_upvalue(module.career_panel_snapshot,'career_panel_feed')
local feed_options=find_upvalue(feed.step,'options')
local geometry={parent=65536,controller=65536,gui_context=0x40000,parent_parent=0x41000,
    alpha_address=0x50000,local_peer='0000000000000011',position={732,-237},width=600,height=1000,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
feed_options.reader=function()return {read=function()return geometry end}end
feed_options.mouse=function()return nil end
local function career()
    feed:step(now,world,{state=3,mission=false},{{['local']=true,peer='0000000000000011'}})
    return assert(module.career_panel_snapshot()).model
end
local function title(plan)
    for _,row in ipairs(plan.header_texts)do if row.id=='panel_title'then return row.text end end
end
local function stable(value)
    if type(value)~='table'then return type(value)..':'..tostring(value)end
    local keys={};for key in pairs(value)do keys[#keys+1]=key end
    table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
    local out={};for _,key in ipairs(keys)do out[#out+1]=stable(key)..'='..stable(value[key])end
    return '{'..table.concat(out,';')..'}'
end
-- Let the actual five-second save batch flush the first observed zero totals.
-- Taking a disk baseline at two seconds would mistake that pending startup
-- save (missing kills/deaths -> zero) for a later locale write.
tick(60)
assert(module.localization.language=='zh' and language_reads>0)
assert(module.ui_settings.status=='registered')
assert(stable(saved.combat_records_v1)==stable(module.combat_records_snapshot()),
    'locale preservation baseline must include the complete observed combat snapshot')
local before={}
for _,key in ipairs({'combat_history','fire_history','combat_records_v1','mission_history_v1','ui_settings'})do before[key]=stable(saved[key])end
local prefix='hd2_costs.war_cost_ledger.'
local expected={cn='zh',tc='zh',us='en',de='en',jp='en'}
for _,code in ipairs({'cn','us','tc','de','jp','cn'})do
    language_code=code;tick(12)
    assert(module.localization.language==expected[code],'live native locale must select '..code)
    mom.translation.refresh()
    local english=expected[code]=='en'
    local label=mom.state.options[prefix..'enabled'].label
    assert(label==(english and 'Show combat HUD' or '显示战果界面'))
    for _,option in pairs(mom.state.options)do
        assert(type(option.label)=='string' and #option.label>0)
        if english then
            assert(not option.label:find('[\228-\233][\128-\191][\128-\191]'),'untranslated setting label '..option.label)
            assert(not (option.description or ''):find('[\228-\233][\128-\191][\128-\191]'),'untranslated description '..(option.description or ''))
            for _,choice in ipairs(option.choices or {})do
                assert(not choice:find('[\228-\233][\128-\191][\128-\191]'),'untranslated choice '..choice)
            end
        end
    end
    state.kill_source_notices={revision=now,items={{expires_at=now+5,lines={'阿尔法指挥官 [R-36 爆裂铳]'}}}}
    local hud=module.game_hud:native_model(now,true)
    assert(hud.kill_source_notices.items[1].lines[1]==(english and 'Alpha Commander [R-36 Eruptor]' or '阿尔法指挥官 [R-36 爆裂铳]'))
    module.charge_notifications:emit('locale-test','治疗针',100,now)
    hud=module.game_hud:native_model(now,true)
    assert(hud.charges.items[1].name==(english and 'Stim' or '治疗针'))
    assert(title(career())==(english and 'Service Record' or '战果档案'))
    for key,value in pairs(before)do
        local actual=stable(saved[key])
        assert(actual==value,'language switch modified saved '..key..' at '..code..'\nBEFORE '..value..'\nAFTER '..actual)
    end
end
assert(#mom.state.mods==1 and mom.state.option_count==19,'language changes must not duplicate settings categories')
assert(state.kills==0 and state.total_cents==0,'presentation charges do not create real bills or kills')
print('PASS built .65: real game language reader selects cn/tc/us/de/jp; actual MOM settings, kill/fee HUD and Career refresh; saved combat/history/preferences and counters stay unchanged.')
]=]
arg={addon,runtime,mom_root}
assert(loadstring(source:sub(1,boundary-1)..setup,'@addon-localization-065'))()
