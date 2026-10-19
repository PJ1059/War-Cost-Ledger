-- Public Mod Options Menu API only. No game memory reads or menu widget writes.
local PREFIX = 'hd2_costs.war_cost_ledger.'
-- Keep the former MC choice at index 1 so saved USD/CNY/etc. choices retain their meaning.
local CURRENCIES = {'SC', 'USD', 'CNY', 'EUR', 'GBP', 'SEK'}
local controls = {
    {id = 'enabled', type = 'toggle', label = '显示战果界面', default = true,
        description = 'F8也可切换。正常打开军械库的生涯页即可查看档案。关闭界面后仍记录真实战果与账单。'},
    {id = 'billing_enabled', type = 'toggle', label = '开启战争账单', default = true,
        description = '记录后续作战消费，并在战斗及生涯显示爱国账单。关闭时停止新增费用，保留已有账目。'},
    {id = 'currency', type = 'choice', label = '账单显示币种', default = 1,
        choices = {'SC（超级货币）', '美元（USD）', '人民币（CNY）', '欧元（EUR）', '英镑（GBP）', '瑞典克朗（SEK）'},
        description = '选择战争账单的显示币种。SC按1 SC＝1 USD折算，仅为本MOD的虚拟军费显示规则。'},
    {id = 'scale_percent', type = 'slider', label = '界面大小（百分比）', min = 60, max = 140, step = 5, default = 100},
    {id = 'opacity_percent', type = 'slider', label = '界面不透明度', min = 30, max = 100, step = 1, default = 82},
    {id = 'right_margin', type = 'slider', label = '整体右侧微调', min = 0, max = 180, step = 6, default = 0,
        description = '默认跟随游戏HUD边缘偏移；命中、绶带、成就与战果数字共用右边缘。'},
    {id = 'top_margin', type = 'slider', label = '整体顶部微调', min = 0, max = 180, step = 6, default = 0},
    {id = 'ribbon_mode', type = 'choice', label = '累计绶带显示', default = 1,
        choices = {'打开地图时显示', '始终显示'},
        description = '累计绶带可始终显示；打开地图还会在成就下显示四类命中累计，零命中不显示。'},
    {id = 'hit_position', type = 'choice', label = '命中提示位置', default = 1,
        choices = {'屏幕右侧', '准心下方', '不显示'},
        description = '仅调整即时命中提示；仍记录真实命中，打开地图可查看累计。绶带与成就保留在右侧。'},
    {id = 'charge_position', type = 'choice', label = '扣费提示位置', default = 1,
        choices = {'屏幕右侧', '准心下方', '不显示'},
        description = '独立选择每次消费的提示位置；关闭提示仍正常累计战争账单。'},
    {id = 'kill_source_enabled', type = 'toggle', label = '显示击杀来源', default = true,
        description = '显示最近一次的击杀目标和来源，5秒后消失。关闭只隐藏提示，武器击杀、绶带和生涯仍正常记录；重新开启后显示新的击杀。'},
    {id = 'move_tasks', type = 'toggle', label = '任务列表让位', default = true,
        description = '界面显示时增加原生任务前间距；资源栏和计时器保留位置。关闭此项或按F8隐藏界面可恢复。'},
    {id = 'task_gap', type = 'slider', label = '任务预留间隔', min = 0, max = 120, step = 6, default = 12,
        description = '任务列表与右上战果区域之间的额外空隙，按画面缩放自适应。'},
    {id = 'auto_ui_probe', type = 'toggle', label = '自动补齐任务布局代码（测试）', default = true, gap = true,
        description = '启动游戏后在舰上即可完成；只读取两处缺失的布局函数，共14KiB，每步至多4KiB。成功一次后停读；无需进入任务或手动采集。旧UI树样本保留。'},
    {id = 'career_ship_sync', type = 'toggle', label = '上舰时自动同步历史KD', default = true,
        description = '登录上舰和任务返回飞船后，短时核对游戏的真实生涯计数。同步后停止读取；战斗中使用最近结果。'},
    {id = 'career_page_sync', type = 'toggle', label = '打开生涯页时同步历史KD', default = true,
        description = '在飞船打开自己的完整生涯统计页，保持约3秒，即可同步。关闭页面后保留最近结果；战斗中停止读取。'},
    {id = 'preview', type = 'choice', label = '运行界面预览测试', default = 1,
        choices = {'关闭', '侧边绶带与成就', '收纳后的累计图标', '侧边与收纳一起显示'},
        description = '选择后按应用。演示三行通知、成就名称、数字动画与扣费提示；8秒后结束，舰上也可测试，不写入真实战果或账单。'},
    {id = 'capture', type = 'choice', label = '采集任务UI定位样本', default = 1,
        choices = {'关闭', '地图关闭样本', '地图打开样本', '取消本次采集'},
        description = '应用后5秒开始等待对应地图状态（最多30秒）。关闭菜单，保持该状态约15秒。仅手动启用，每次最多64KiB读取，单份约4.7MiB；输出到本地HD2Runtime/mod_data。'},
    {id = 'code_copy_test', type = 'choice', label = '运行命中接口副本测试', default = 1,
        choices = {'关闭', '执行2秒测试', '取消本次测试'},
        description = '应用后关闭菜单并留在飞船；5秒后运行2秒并恢复入口。每次游戏启动只运行一次，结果保存于本地诊断文件；不计入战果或账单。'},
}
local function action(id) return id=='preview' or id=='capture' or id=='code_copy_test' end
local by_id = {}
for _, c in ipairs(controls) do by_id[c.id] = c end
local function valid(c, value)
    if c.type == 'toggle' then if type(value) == 'boolean' then return value end; return nil end
    if type(value) ~= 'number' or value ~= value or value == math.huge or value == -math.huge then return nil end
    if c.type == 'choice' then return value % 1 == 0 and value >= 1 and value <= #c.choices and value or nil end
    value = math.max(c.min, math.min(c.max, value))
    return c.min + math.floor((value - c.min) / c.step + 0.5) * c.step
end
return function(mod, store, callbacks)
    callbacks = callbacks or {}
    local localize = type(callbacks.localize)=='function' and callbacks.localize or nil
    local function translated_text(source, dynamic)
        if not localize then return source end
        local function text()
            local value=type(source)=='function' and source() or source
            return localize(value)
        end
        return dynamic and text or text()
    end
    local saved = store:get('ui_settings', {})
    if type(saved) ~= 'table' then saved = {} end
    local api = {config = {}, values = {}, status = 'waiting_for_menu', registered = {}, controls = controls}
    local menu, elapsed, check_elapsed, warned = nil, 0, 0.5, false
    local before_menu_changes = {}
    for _, c in ipairs(controls) do
        local stored = saved[c.id]
        if c.id == 'currency' and (stored == 'MC' or stored == 'SC') then stored = 1 end
        local value = valid(c, stored)
        if c.id == 'enabled' then value = store:get('hud_enabled', true) ~= false end
        if action(c.id) then value = 1 end
        api.values[c.id] = value == nil and c.default or value
    end
    -- Migrate only the former stock inset. Explicit non-default adjustments stay.
    local migrate_layout = saved.layout_revision ~= 'hud-common-right-edge-v6'
    if migrate_layout then
        for _, id in ipairs({'right_margin','top_margin'}) do
            if api.values[id] == 18 then api.values[id] = 0 end
            before_menu_changes[id] = true
        end
    end
    local function config()
        local v, out = api.values, api.config
        out.enabled, out.scale, out.opacity = v.enabled, v.scale_percent / 100, v.opacity_percent / 100
        out.billing_enabled = v.billing_enabled
        out.right_margin, out.top_margin = v.right_margin, v.top_margin
        out.ribbon_mode = v.ribbon_mode == 1 and 'map' or 'always'
        local positions={'right','center','hidden'}
        out.hit_position,out.charge_position=positions[v.hit_position],positions[v.charge_position]
        out.kill_source_enabled = v.kill_source_enabled
        out.move_tasks, out.task_gap = v.move_tasks, v.task_gap
        out.auto_ui_probe = v.auto_ui_probe
        out.career_page_sync = v.career_page_sync
        out.career_ship_sync = v.career_ship_sync
        out.currency = CURRENCIES[v.currency]
    end
    local function save(id)
        if id == 'enabled' then store:set('hud_enabled', api.values.enabled); return end
        local previous = store:get('ui_settings', {})
        local copy = {}
        if type(previous) == 'table' then for key, value in pairs(previous) do copy[key] = value end end
        copy.enabled, copy.preview, copy.capture,copy.code_copy_test = nil, nil, nil,nil
        copy.layout_revision = 'hud-common-right-edge-v6'
        for _, c in ipairs(controls) do
            if c.id ~= 'enabled' and not action(c.id) then copy[c.id] = api.values[c.id] end
        end
        store:set('ui_settings', copy)
    end
    function api:set(id, value, mirror, startup)
        local c = by_id[id]
        if not c then return false end
        value = valid(c, value)
        if value == nil then return false end
        if action(id) then
            self.values[id] = 1
            if menu then menu.set(PREFIX .. id, 1) end
            if not startup and value > 1 and callbacks[id] then callbacks[id](value) end
            return true
        end
        local changed = self.values[id] ~= value
        self.values[id] = value
        if menu and mirror ~= false then menu.set(PREFIX .. id, value) end
        if changed then
            if not menu and not startup then before_menu_changes[id] = true end
            config(); save(id)
            if callbacks.changed then callbacks.changed(self.config, id) end
        end
        return true
    end
    function api:toggle_enabled() self:set('enabled', not self.values.enabled); return self.values.enabled end
    function api:update(dt)
        if menu then return end
        elapsed, check_elapsed = elapsed + dt, check_elapsed + dt
        if check_elapsed < 0.5 then return end
        check_elapsed = 0
        local candidate = rawget(_G, 'ModOptionsMenu')
        if type(candidate) ~= 'table' or candidate.api ~= 1 or type(candidate.register_option) ~= 'function'
            or type(candidate.get) ~= 'function' or type(candidate.set) ~= 'function'
            or type(candidate.on_change) ~= 'function' then
            if elapsed >= 5 and not warned then
                warned = true; self.status = 'menu_unavailable'
                mod:log('游戏内设置入口尚不可用：需要启用Mod Options Menu；F8仍可使用。')
            end
            return
        end
        menu = candidate
        for _, c in ipairs(controls) do
            local id, spec = c.id, {}
            for key, value in pairs(c) do if key ~= 'id' then spec[key] = value end end
            spec.mod, spec.default = '战果与战争账单', self.values[id]
            if id == 'career_page_sync' and callbacks.career_status then
                spec.description = (candidate.version or 0) >= 2 and callbacks.career_status
                    or callbacks.career_status()
            end
            if id == 'career_ship_sync' and callbacks.career_ship_status then
                spec.description = (candidate.version or 0) >= 2 and callbacks.career_ship_status
                    or callbacks.career_ship_status()
            end
            local dynamic=(candidate.version or 0)>=2
            spec.mod=translated_text(spec.mod,dynamic)
            spec.label=translated_text(spec.label,dynamic)
            if spec.description then spec.description=translated_text(spec.description,dynamic) end
            if localize and spec.choices then
                local choices={}
                for index,text in ipairs(spec.choices)do choices[index]=translated_text(text,dynamic) end
                spec.choices=choices
            end
            if (candidate.version or 0) >= 3 then spec.mod_id = 'hd2_costs.war_cost_ledger' end
            local accepted, reason = menu.register_option(PREFIX .. id, spec)
            if accepted then
                self.registered[id] = true
                if before_menu_changes[id] then menu.set(PREFIX .. id, self.values[id])
                else self:set(id, menu.get(PREFIX .. id), false, true) end
                menu.on_change(PREFIX .. id, function(value) self:set(id, value, false) end)
            else
                self.status = 'menu_registration_failed'
                mod:log('设置注册失败 ' .. id .. '：' .. tostring(reason))
            end
        end
        if self.status ~= 'menu_registration_failed' then
            self.status = 'registered'
            mod:log('游戏内设置已注册：ESC → MODS → 战果与战争账单；修改后按应用。')
        end
    end
    config()
    if migrate_layout then save('right_margin') end
    return api
end
