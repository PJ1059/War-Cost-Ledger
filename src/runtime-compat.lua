-- Check the API used by this addon, not an unrelated release label.
-- Native readers retain their own executable/schema/code-pin proofs.
local M={}
local function missing(path)
    return nil,'War Cost Ledger cannot initialize: missing HD2Runtime API '..path
        ..'. Enable the official HD2Runtime with the required API; no exact release version is required.'
end
local function methods(value,names,prefix)
    for _,name in ipairs(names)do
        if type(value)~='table'or type(value[name])~='function'then return missing(prefix..'.'..name)end
    end
    return true
end
function M.check(hd2,world,beacons,loadout,natives,metadata)
    for _,item in ipairs({{hd2,{'mod'},'hd2'},{type(hd2)=='table'and hd2.ui,{'overlay'},'hd2.ui'},
        {world,{'open','game_state','players','entity_state','stat_breakdown'},'event_world'},
        {beacons,{'prove','beacons','clock'},'beacon_redirect'},
        {loadout,{'prove','id_of'},'stratagem_loadout'}})do
        local ok,reason=methods(item[1],item[2],item[3]);if not ok then return nil,reason end
    end
    local keys=type(natives)=='table'and type(natives.stats)=='table'and natives.stats.keys
    for _,key in ipairs({'projectiles_fired','dealt_kills','received_deaths','projectiles_hit'})do
        local value=type(keys)=='table'and keys[key]
        if type(value)~='number'or value<0 or value>=4294967296 or value%1~=0 then return missing('event_natives.stats.keys.'..key)end
    end
    for _,source in ipairs({hd2,metadata or {}})do
        if source.api_version~=nil and source.api_version~=1 then
            return nil,'War Cost Ledger cannot initialize: unsupported HD2Runtime api_version '
                ..tostring(source.api_version)..'; requires API 1.'
        end
    end
    return true
end
function M.check_mod(mod)
    return methods(mod,{'store','log','bind','on_frame'},'mod')
end
function M.check_objects(mod,store,overlay)
    local ok,reason=M.check_mod(mod);if not ok then return nil,reason end
    for _,item in ipairs({{store,{'get','set','save'},'store'},{overlay,{'draw','show','hide'},'overlay'}})do
        local ok,reason=methods(item[1],item[2],item[3]);if not ok then return nil,reason end
    end
    return true
end
function M.load(loader)
    local modules={}
    for _,name in ipairs({'mods/skyeshade/hd2runtime','hd2runtime/domains/metadata',
        'hd2runtime/runtime/event_world','hd2runtime/runtime/beacon_redirect',
        'hd2runtime/runtime/stratagem_loadout','hd2runtime/domains/event_natives'})do
        local ok,value=pcall(loader,name)
        if not ok or type(value)~='table'then
            return nil,'War Cost Ledger cannot initialize: HD2Runtime module '..name..' failed to load: '..tostring(value)
        end
        modules[#modules+1]=value
    end
    local hd2,metadata,world,beacons,loadout,natives=unpack(modules)
    local ok,reason=M.check(hd2,world,beacons,loadout,natives,metadata)
    if not ok then return nil,reason end
    return hd2,metadata,world,beacons,loadout,natives.stats.keys
end
return M
