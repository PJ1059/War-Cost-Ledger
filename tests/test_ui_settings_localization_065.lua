-- Real MOM registration/refresh: language changes only presentation, not saved options.
local create=dofile(assert(arg[1]))
local mom_root=assert(arg[2])
local Text=dofile(mom_root..'/src/bingus_text.lua')
local load_options=assert(loadfile(mom_root..'/src/options.lua'))
local load_api=assert(loadfile(mom_root..'/src/api.lua'))
local PREFIX='hd2_costs.war_cost_ledger.'
local lang='en'
local translations={['战果与战争账单']='Combat Results & War Costs',
    ['显示战果界面']='Show Combat HUD',['账单显示币种']='Bill Currency',
    ['SC（超级货币）']='SC (Super Credits)',['美元（USD）']='US Dollar (USD)',
    ['人民币（CNY）']='Chinese Yuan (CNY)',['欧元（EUR）']='Euro (EUR)',
    ['英镑（GBP）']='British Pound (GBP)',['瑞典克朗（SEK）']='Swedish Krona (SEK)',
    ['同步状态一']='Sync status one',['同步状态二']='Sync status two'}
local function t(value)return lang=='en' and (translations[value] or value) or value end
local function fresh(version)
    local state={mods={},refused={},refused_count=0,options={},option_count=0,values={},pending={},
        pending_count=0,queued={},queued_any=false,saved={},callbacks={},revision=0,dirty=false,save_timer=0}
    local mom={state=state,note=function()end,loader={log_directory='/unused'},
        translation={T=Text,tr=function(x)return x end},TEXT_TEMPLATE=123,MAX_MODS=112,MAX_ROWS=32,
        descriptor=function(option)return option.sequence,{} end}
    load_options(mom);load_api(mom)
    mom.api.version=version
    local data={hud_enabled=false,ui_settings={currency=3,scale_percent=115,layout_revision='hud-common-right-edge-v6'}}
    local writes,registers,changes=0,0,0
    local real_register=mom.api.register_option
    mom.api.register_option=function(id,spec)registers=registers+1;return real_register(id,spec)end
    local status='同步状态一'
    local settings=create({log=function()end},{get=function(_,key,default)
        if data[key]==nil then return default end;return data[key]
    end,set=function(_,key,value)writes=writes+1;data[key]=value end},{localize=t,
        career_status=function()return status end,changed=function()changes=changes+1 end})
    _G.ModOptionsMenu=mom.api;settings:update(.5)
    assert(settings.status=='registered')
    return {state=state,mom=mom,settings=settings,data=data,
        counts=function()return writes,registers,changes end,
        status=function(value)status=value end}
end

for _,version in ipairs({2,3})do
    lang='en'
    local f=fresh(version)
    local enabled=f.state.options[PREFIX..'enabled']
    local currency=f.state.options[PREFIX..'currency']
    local career=f.state.options[PREFIX..'career_page_sync']
    assert(enabled.label=='Show Combat HUD' and type(enabled.sources.label)=='function')
    assert(type(f.state.mods[1].source)=='function' and f.state.mods[1].title=='COMBAT RESULTS & WAR COSTS')
    assert(currency.choices[1]=='SC (SUPER CREDITS)' and currency.choices[2]=='US DOLLAR (USD)')
    assert(type(currency.sources.choices[1])=='function' and type(currency.sources.choices[6])=='function')
    assert(career.description=='Sync status one')
    assert(f.settings.config.enabled==false and f.settings.config.currency=='CNY' and f.settings.config.scale==1.15)
    local writes,registers,changes=f.counts()
    lang='zh';f.status('同步状态二');f.mom.translation.refresh()
    assert(enabled.label=='显示战果界面' and currency.choices[1]=='SC（超级货币）')
    assert(currency.choices[2]=='美元（USD）' and currency.choices[6]=='瑞典克朗（SEK）',
        'each choice must keep its own source, not the final loop value')
    assert(career.description=='同步状态二' and f.state.mods[1].title=='战果与战争账单')
    lang='en';f.mom.translation.refresh();f.settings:update(1)
    assert(career.description=='Sync status two' and enabled.label=='Show Combat HUD')
    local after_writes,after_registers,after_changes=f.counts()
    assert(after_writes==writes and after_registers==registers and after_changes==changes,
        'language refresh must not register again, change a value, or write preferences')
    assert(#f.state.mods==1 and f.settings.config.currency=='CNY')
end
lang='en'
local old=fresh(1)
assert(type(old.state.options[PREFIX..'enabled'].sources.label)=='string')
assert(old.state.options[PREFIX..'enabled'].label=='Show Combat HUD')
assert(type(old.state.options[PREFIX..'currency'].sources.choices[1])=='string')
assert(old.state.options[PREFIX..'career_page_sync'].description=='Sync status one')
_G.ModOptionsMenu=nil
print('PASS: MOM 2/3 labels, category, dynamic descriptions and choices refresh in both directions; MOM 1 receives translated strings; saved IDs/values and callbacks unchanged.')
