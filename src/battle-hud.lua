-- Read-only presentation of existing ledger data, in the native parent's local UI units.
-- The native adapter must supply a verified map-open state and panel width.
-- This module does not poll memory, infer map state from a key, or move native widgets.
local ICONS = {
    {id = 'R01', key = 'air', name = '防空', kind = 'ribbon', colour = '#8BBAD6'},
    {id = 'R02', key = 'heavy', name = '反重', kind = 'ribbon', colour = '#D9A159'},
    {id = 'R03', key = 'giant', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC'},
    {id = 'G01', key = 'giant_dragonroach', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Dragonroach', unit = '蟑龙', condition = '击杀1个蟑龙。'},
    {id = 'G02', key = 'giant_bile_titan', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Bile Titan', unit = '吐酸泰坦', condition = '击杀1个吐酸泰坦。'},
    {id = 'G03', key = 'giant_spore_burst_bile_titan', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Spore Burst Bile Titan', unit = '孢裂吐酸泰坦', condition = '击杀1个孢裂吐酸泰坦。'},
    {id = 'G04', key = 'giant_vox_engine', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Vox Engine', unit = '噪轰引擎', condition = '击杀1个噪轰引擎。'},
    {id = 'G05', key = 'giant_factory_strider', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Factory Strider', unit = '移动工厂', condition = '击杀1个移动工厂。'},
    {id = 'G06', key = 'giant_leviathan', name = '巨人杀手', kind = 'ribbon', colour = '#B5A2DC',
        unit_key = 'Leviathan', unit = '利维坦', condition = '击杀1个利维坦。'},
    {id = 'T01', key = 'heavy_charger', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Charger', unit = '强袭虫', condition = '击杀1个强袭虫。'},
    {id = 'T02', key = 'heavy_charger_behemoth', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Charger Behemoth', unit = '巨兽级强袭虫', condition = '击杀1个巨兽级强袭虫。'},
    {id = 'T03', key = 'heavy_spore_charger', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Spore Charger', unit = '孢子强袭虫', condition = '击杀1个孢子强袭虫。'},
    {id = 'T04', key = 'heavy_rupture_charger', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Rupture Charger', unit = '爆裂强袭虫', condition = '击杀1个爆裂强袭虫。'},
    {id = 'T05', key = 'heavy_impaler', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Impaler', unit = '穿刺虫', condition = '击杀1个穿刺虫。'},
    {id = 'T06', key = 'heavy_hulk_bruiser', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Hulk Bruiser', unit = '巨型碾压者', condition = '击杀1个巨型碾压者。'},
    {id = 'T07', key = 'heavy_hulk_scorcher', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Hulk Scorcher', unit = '巨型炙炎者', condition = '击杀1个巨型炙炎者。'},
    {id = 'T08', key = 'heavy_hulk_obliterator', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Hulk Obliterator', unit = '巨型抹煞者', condition = '击杀1个巨型抹煞者。'},
    {id = 'T09', key = 'heavy_hulk_firebomber', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Hulk Firebomber', unit = '巨型烈焰轰炸者', condition = '击杀1个巨型烈焰轰炸者。'},
    {id = 'T10', key = 'heavy_annihilator_tank', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Annihilator Tank', unit = '湮灭坦克', condition = '击杀1个湮灭坦克。'},
    {id = 'T11', key = 'heavy_barrager_tank', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Barrager Tank', unit = '铁幕坦克', condition = '击杀1个铁幕坦克。'},
    {id = 'T12', key = 'heavy_shredder_tank', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Shredder Tank', unit = '碎裂坦克', condition = '击杀1个碎裂坦克。'},
    {id = 'T13', key = 'heavy_war_strider', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'War Strider', unit = '战争纵步者', condition = '击杀1个战争纵步者。'},
    {id = 'T14', key = 'heavy_veracitor', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Veracitor', unit = '证真者', condition = '击杀1个证真者。'},
    {id = 'T15', key = 'heavy_gatekeeper', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Gatekeeper', unit = '御门者', condition = '击杀1个御门者。'},
    {id = 'T16', key = 'heavy_fleshmob', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Fleshmob', unit = '肉瘤体', condition = '击杀1个肉瘤体。'},
    {id = 'T17', key = 'heavy_crusher', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Crusher', unit = '粉碎者', condition = '击杀1个粉碎者。'},
    {id = 'T18', key = 'heavy_harvester', name = '反重', kind = 'ribbon', colour = '#D9A159',
        unit_key = 'Harvester', unit = '猎杀器', condition = '击杀1个猎杀器。'},
    {id = 'R04', key = 'demolition', name = '拆除', kind = 'ribbon', colour = '#C5AE69'},
    {id = 'R05', key = 'melee', name = '近战杀敌', kind = 'ribbon', colour = '#8FC7C0'},
    {id = 'R06', key = 'ignite', name = '燃烧击杀', kind = 'ribbon', colour = '#E09A60'},
    {id = 'R07', key = 'firepower', name = '火力倾泻', kind = 'ribbon', colour = '#D6CB84'},
    {id = 'R09', key = 'poison', name = '毒气击杀', kind = 'ribbon', colour = '#92B96B'},
    {id = 'R10', key = 'recon', name = '侦察', kind = 'ribbon', colour = '#8BBAD6'},
    {id = 'R11', key = 'killstreak', name = '连杀', kind = 'ribbon', colour = '#D6CB84'},
    {id = 'R12', key = 'crush', name = '碾压', kind = 'ribbon', colour = '#D0B982'},
    {id = 'H01', key = 'hit_total', name = '命中', kind = 'ribbon', colour = '#E7D46A', side = false},
    {id = 'H02', key = 'hit_ricochet', name = '跳弹', kind = 'ribbon', colour = '#8BBAD6', side_icon = true},
    {id = 'H03', key = 'hit_blocked', name = '未击穿（碎弹）', kind = 'ribbon', colour = '#D7A16F', side_icon = true},
    {id = 'H04', key = 'hit_penetration', name = '击穿', kind = 'ribbon', colour = '#D6D8BD', side_icon = true},
    {id = 'H05', key = 'hit_full_penetration', name = '完全击穿', kind = 'ribbon', colour = '#E7D46A', side_icon = true},
    {id = 'M01', key = 'democracy_harvester', name = '民主收割机', kind = 'medal', colour = '#B1C8A0'},
    {id = 'M02', key = 'air_expert', name = '防空专家', kind = 'medal', colour = '#8BBAD6'},
    {id = 'M03', key = 'democracy_undying', name = '民主永不死', kind = 'medal', colour = '#9BCFB1'},
    {id = 'M04', key = 'freedom_in_veins', name = '血管中全是自由的香气', kind = 'medal', colour = '#7FC7B9'},
    {id = 'M05', key = 'foreign_parking', name = '这里不让停外地车', kind = 'medal', colour = '#B7A4D4'},
    {id = 'M06', key = 'fragrant', name = '香喷喷', kind = 'medal', colour = '#DEA36C'},
    {id = 'M07', key = 'double_giant', name = '一炮双响', kind = 'medal', colour = '#D5C19B'},
    {id = 'M08', key = 'democracy_star', name = '民主之星', kind = 'medal', colour = '#B1C8A0'},
    {id = 'M09', key = 'super_democracy_star', name = '超级民主之星', kind = 'medal', colour = '#B1C8A0'},
    {id = 'M10', key = 'supreme_democracy_star', name = '超级无上民主之星', kind = 'medal', colour = '#B1C8A0'},
    {id = 'M11', key = 'level_not_problem', name = '等级不是问题', kind = 'medal', colour = '#B1C8A0'},
    {id = 'M12', key = 'tyranny_speed_bump', name = '摧毁暴政减速带', kind = 'medal', colour = '#B1C8A0'},
}

local function kd(kills, deaths, no_deaths_label)
    if kills == nil or deaths == nil then return '--' end
    if deaths == 0 and no_deaths_label then return tostring(kills) .. '/0' end
    return string.format('%.2f', kills / math.max(deaths, 1))
end

local function icon_value(state, icon)
    local values
    if icon.kind == 'ribbon' then values = state.ribbons else values = state.mission_medals end
    return values and values[icon.key] or false
end

return function(state, is_visible, currency)
    local previous, cached = {}, nil
    local api = {version = 1, artwork = 'placeholders', native_binding = false, icons = ICONS}
    function api:snapshot(context)
        assert(type(context) == 'table' and type(context.map_open) == 'boolean',
            'battle HUD needs a verified native map-open state')
        local width = context.width or 336
        assert(type(width) == 'number' and width >= 160 and width <= 1024 and width < math.huge,
            'battle HUD width must use the native parent local UI units')
        width = math.floor(width)
        local shown = is_visible() == true
        local code = currency and currency:code(context.currency or state.display_currency) or 'SC'
        local changed = cached == nil or previous.shown ~= shown or previous.map ~= context.map_open
            or previous.width ~= width or previous.sequence ~= state.sequence
            or previous.kills ~= state.kills or previous.deaths ~= state.deaths
            or previous.hk ~= state.history_kills or previous.hd ~= state.history_deaths
            or previous.bill ~= state.total_cents or previous.currency ~= code or previous.shots ~= state.shots
            or previous.billing_enabled ~= state.billing_enabled
        for index, icon in ipairs(ICONS) do
            local value = icon_value(state, icon)
            if previous[index] ~= value then changed = true end
            previous[index] = value
        end
        if not changed then return cached end
        previous.shown, previous.map, previous.width, previous.sequence = shown, context.map_open, width, state.sequence
        previous.kills, previous.deaths = state.kills, state.deaths
        previous.hk, previous.hd, previous.bill = state.history_kills, state.history_deaths, state.total_cents
        previous.currency = code
        previous.shots = state.shots
        previous.billing_enabled = state.billing_enabled
        local fallback = (state.total_cents or 0) / 100
        local bill = currency and currency:format(state.total_cents, code)
            or (fallback > 0 and fallback < 0.01 and '<0.01' or string.format('%.2f', fallback))
        local current_kd=kd(state.kills,state.deaths,true)
        local history_kd=kd(state.history_kills,state.history_deaths)
        local arrow=''
        if type(state.kills)=='number' and type(state.deaths)=='number'
            and type(state.history_kills)=='number' and type(state.history_deaths)=='number' then
            local current=state.kills/math.max(1,state.deaths)
            local history=state.history_kills/math.max(1,state.history_deaths)
            if current>history then arrow='↑' elseif current<history then arrow='↓' end
        end
        local symbols={SC=' SC',USD='$',CNY='¥',EUR='€',GBP='£',SEK='kr'}
        local view = {version = 1, artwork = 'placeholders', native_binding = false,
            mode = context.map_open and 'map' or 'combat', shown = shown, width = width,
            medals = {}, ribbons = {}, height = 0, task_offset_y = 0,
            stats = {kills = state.kills == nil and '--' or tostring(state.kills),
                shots = state.shots == nil and '--' or tostring(state.shots),
                kd = current_kd, history_kd = history_kd, history_arrow=arrow,
                kd_text=current_kd..'［'..history_kd..arrow..'］',
                bill = bill, bill_text=bill..(symbols[code] or code), bill_visible=state.billing_enabled~=false, currency = code}}
        if shown then
            local medal_columns = math.max(1, math.floor((width - 112 - 8 + 4) / 30))
            for index, icon in ipairs(ICONS) do
                if icon.kind == 'medal' and (previous[index] == true
                    or type(previous[index]) == 'number' and previous[index] > 0) then
                    local position = #view.medals
                    view.medals[position + 1] = {id = icon.id, key = icon.key, name = icon.name,
                        colour = icon.colour, placeholder = true, x = (position % medal_columns) * 30,
                        y = math.floor(position / medal_columns) * 36, width = 26, height = 32}
                end
            end
            local medal_rows = math.ceil(#view.medals / medal_columns)
            view.height = math.max(52, medal_rows * 36 - (medal_rows > 0 and 4 or 0))
            view.stats.x, view.stats.y, view.stats.width = width - 112, 0, 112
            if context.map_open then
                local columns = math.max(1, math.floor((width + 6) / 74))
                local top = view.height + 8
                for index, icon in ipairs(ICONS) do
                    local value = previous[index]
                    if icon.kind == 'ribbon' and type(value) == 'number' and value > 0 then
                        local position = #view.ribbons
                        view.ribbons[position + 1] = {id = icon.id, key = icon.key, name = icon.name,
                            colour = icon.colour, count = value, placeholder = true,
                            x = (position % columns) * 74, y = top + math.floor(position / columns) * 28,
                            width = 68, height = 22}
                    end
                end
                if #view.ribbons > 0 then view.height = top + math.ceil(#view.ribbons / columns) * 28 - 6 end
            end
            -- The native adapter applies this to the COMPLETE objective list as one block.
            view.task_offset_y = view.height + 8
        end
        cached = view
        return view
    end
    return api
end
