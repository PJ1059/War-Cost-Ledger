-- Retained image drawing. Real observations use ledger state; the eight-second
-- UI test has independent state/models and never reads game APIs.
local function clamp(v,lo,hi) return math.max(lo,math.min(hi,v)) end
local function finite(v) return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
local EMPTY={}
local DEFAULT={scale=1,opacity=.82,right_margin=0,top_margin=0,side_margin=0,
    side_vertical=.5,ribbon_mode='map',move_tasks=true,task_gap=12,currency='SC',width=600,
    hit_position='right',charge_position='right',kill_source_enabled=true}
local function alpha(v) return string.format('%02X',math.floor(clamp(v,0,1)*255+.5)) end

return function(hd2,state,battle,awards,art,factories)
    local localize=factories and factories.localize or function(value)return value end
    local read_locale_revision=factories and factories.locale_revision
    local last_locale_revision=read_locale_revision and read_locale_revision() or 0
    local images,cfg={},{}
    for k,v in pairs(DEFAULT) do cfg[k]=v end
    local supported=type(hd2.resources)=='table' and type(hd2.resources.image)=='function'
    local api={version=3,artwork='v18_icon_masks',native_binding=false,native_map_verified=false,
        collection_open=false,image_api_available=supported,image_count=#art.images+#(art.metrics or EMPTY)+#(art.indicators or EMPTY),notifications=awards,config=cfg}
    local definitions,ribbon_count,medal_count={},0,0
    for _,icon in ipairs(battle.icons or {}) do definitions[icon.id]=icon end
    local source_assets={}
    for _,asset in ipairs(art.images) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(art.metrics or EMPTY) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(art.indicators or EMPTY) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(source_assets) do
        if definitions[asset.id] and definitions[asset.id].kind=='ribbon' then ribbon_count=ribbon_count+1
        else medal_count=medal_count+1 end
        if supported then images[asset.id]={handle=hd2.resources.image(asset.image_id),asset=asset,
            opts={colours={r='#FFF9ED',g=asset.accent,b='#00000000'},colour='#FFFFFFD1',z=1}} end
    end
    if supported then images.frame={handle=hd2.resources.image(art.frame.image_id),asset=art.frame,
        opts={colours={r='#FFF9ED',g=art.frame.accent,b='#00000000'},colour='#FFFFFFD1',z=0}} end
    local side_started,geometry,last_view={},{},nil
    local previous_scale,previous_width,previous_height
    local viewport_width,viewport_height,viewport_scale
    local context={map_open=false,width=600}
    local layout=assert(factories and factories.layout,'native HUD needs its retained layout factory')(localize)
    local last_model,last_charge_source,last_charge_currency,formatted_charges
    local latest_width=600
    local styles,last_stats,map_state,preview
    local notice_source,notice_revision,notice_expiry,notice_view
    local function notice_line(value)
        if type(value)~='string'or #value==0 or #value>192 or value:find('[%z\1-\31\127]')then return nil end
        local function units(s)
            local n=0;for ch in s:gmatch('[%z\1-\127\194-\244][\128-\191]*')do n=n+(#ch==1 and .55 or 1)end
            return n
        end
        if units(value)<=32 then return value end
        -- Long labels may be elided, but every complete unknown resource hash
        -- remains visible and in order. Never leave half of a 64-bit identity.
        local hashes,seen={},{}
        for token in value:gmatch('%x+')do if #token==16 and not seen[token]then
            hashes[#hashes+1]=token;seen[token]=true
        end end
        local base=value
        for _,token in ipairs(hashes)do base=base:gsub(token,'')end
        local suffix=#hashes>0 and(' '..table.concat(hashes,' '))or''
        local budget=math.max(0,32-units(suffix)-1.65)
        local prefix,used={},0
        for ch in base:gmatch('[%z\1-\127\194-\244][\128-\191]*')do
            local n=#ch==1 and .55 or 1
            if used+n>budget then break end
            prefix[#prefix+1]=ch;used=used+n
        end
        return table.concat(prefix)..'...'..suffix
    end
    local function source_notices(shown_state,now)
        if cfg.kill_source_enabled==false then return EMPTY end
        local source=shown_state.kill_source_notices
        if shown_state.mission~=true or type(source)~='table'or type(source.items)~='table'then return EMPTY end
        if source==notice_source and source.revision==notice_revision and notice_view
            and(not notice_expiry or now<notice_expiry)then return notice_view end
        local view={revision=source.revision,items={}}
        notice_expiry=nil
        for index,item in ipairs(source.items)do
            if index>1 then break end
            if type(item)=='table'and(item.persistent==true or finite(item.expires_at)and item.expires_at>now)and type(item.lines)=='table'then
                local lines={}
                for line_index,value in ipairs(item.lines)do
                    if line_index>1 then break end
                    local line=notice_line(type(value)=='string' and localize(value) or value)
                    if line then lines[#lines+1]=line end
                end
                if #lines>0 then
                    view.items[#view.items+1]={lines=lines,expires_at=item.expires_at,persistent=item.persistent==true}
                    if item.persistent~=true then notice_expiry=math.min(notice_expiry or item.expires_at,item.expires_at)end
                end
            end
        end
        notice_source,notice_revision,notice_view=source,source.revision,view
        return view
    end
    local function invalidate()
        side_started,geometry,last_view,last_stats={},{},nil,nil
        previous_scale,previous_width,previous_height,styles=nil,nil,nil,nil
        last_model=nil;layout:clear()
    end
    function api:invalidate_locale()
        last_charge_source,last_charge_currency,formatted_charges=nil,nil,nil
        notice_source,notice_revision,notice_expiry,notice_view=nil,nil,nil,nil
        last_model=nil;layout:clear()
    end
    function api:configure(config)
        if type(config)~='table' then return cfg end
        for key,bounds in pairs({scale={.5,2},opacity={0,1},right_margin={0,320},top_margin={0,240},
            side_margin={0,320},side_vertical={0,.8},task_gap={0,120},width={160,600}}) do
            if finite(config[key]) then cfg[key]=clamp(config[key],bounds[1],bounds[2]) end
        end
        if config.ribbon_mode=='map' or config.ribbon_mode=='always' then cfg.ribbon_mode=config.ribbon_mode end
        for _,key in ipairs({'hit_position','charge_position'})do
            if config[key]=='right' or config[key]=='center' or config[key]=='hidden'then cfg[key]=config[key]end
        end
        if type(config.move_tasks)=='boolean' then cfg.move_tasks=config.move_tasks end
        if type(config.kill_source_enabled)=='boolean' then cfg.kill_source_enabled=config.kill_source_enabled end
        if factories and factories.currency then cfg.currency=factories.currency:code(config.currency or cfg.currency) end
        for _,image in pairs(images) do image.opts.colour='#FFFFFF'..alpha(cfg.opacity) end
        invalidate()
        return cfg
    end
    function api:set_map(value)
        -- The native bridge carries the HUD manager pointer, not a shown flag.
        local identity=type(value)=='table' and value.hud
        local valid_identity=finite(identity) and identity>=65536
            and identity<140737488355328 and identity%1==0
        if type(value)=='table' and type(value.mission)=='boolean' and type(value.map_open)=='boolean'
            and valid_identity then
            map_state=map_state or {}
            map_state.mission,map_state.map_open,map_state.hud=value.mission,value.map_open,value.hud
            self.native_map_verified=true
        else map_state=nil;self.native_map_verified=false end
        -- Gates collection only: the caller owns real combat HUD visibility.
    end
    local function collection_shown()
        if cfg.ribbon_mode=='always' then return true end
        if map_state then return map_state.mission and map_state.map_open end
        return api.collection_open
    end
    local function map_shown()
        if map_state then return map_state.mission and map_state.map_open end
        return api.collection_open
    end
    local function sync_batch(active_awards,active_charges,now)
        if active_charges then
            if active_charges.deadline and active_awards.extend_deadline then
                active_awards:extend_deadline(active_charges.deadline)
            end
            active_charges:update(now,active_awards.deadline)
        end
        active_awards:update(now)
        if active_charges then active_charges:update(now,active_awards.deadline) end
    end
    function api:toggle_collection() self.collection_open=not self.collection_open;return self.collection_open end
    function api:observe(now) sync_batch(awards,factories.charges,now) end

    local function preview_models(test_state,mode,now)
        local icons,side={},{}
        for _,asset in ipairs(art.images) do
            local icon=definitions[asset.id]
            if icon then
            icons[#icons+1]=icon
            local recent=icon.side~=false and (mode==2 or (mode==4 and (asset.id=='R01' or asset.id=='R02' or asset.id=='M01' or asset.id=='H04')))
            if icon.kind=='ribbon' then test_state.ribbons[icon.key]=recent and 0 or 7
            else test_state.mission_medals[icon.key]=not recent end
            if recent then side[#side+1]=icon end
            end
        end
        local test_battle,test_awards
        if factories and type(factories.battle)=='function' and type(factories.awards)=='function' then
            test_battle=factories.battle(test_state,function() return true end,factories.currency)
            test_awards=factories.awards(test_state,icons)
            test_awards:baseline(now)
        else
            local items,medals,ribbons,all_medals,all_ribbons={},{},{},{},{}
            for _,icon in ipairs(icons) do
                local item={id=icon.id,key=icon.key,kind=icon.kind,side_icon=icon.side_icon==true,count=7,total=7}
                local recent=icon.side~=false and (mode==2 or (mode==4 and (icon.id=='R01' or icon.id=='R02' or icon.id=='M01' or icon.id=='H04')))
                if recent then items[#items+1]=item
                elseif icon.kind=='medal' then medals[#medals+1]=item
                else ribbons[#ribbons+1]=item end
                if icon.kind=='medal' then all_medals[#all_medals+1]=item else all_ribbons[#all_ribbons+1]=item end
            end
            local stats={kills='648',shots='56222',kd='216.00',history_kd='44.83',bill='72431285.00',currency='SC',bill_text='72431285.00 SC'}
            local stats_view={stats=stats}
            test_battle={snapshot=function() return stats_view end}
            local view={items=items,medals=medals,ribbons=ribbons}
            local folded={items={},medals=all_medals,ribbons=all_ribbons}
            test_awards={update=function() end,snapshot=function(_,at)
                for _,item in ipairs(items) do
                    item.count=item.kind=='ribbon' and test_state.ribbons[item.key] or 1;item.total=item.count
                end
                return at>=now+4 and folded or view
            end}
        end
        for _,icon in ipairs(side) do
            if icon.kind=='ribbon' then test_state.ribbons[icon.key]=3 else test_state.mission_medals[icon.key]=true end
        end
        test_awards:update(now)
        return test_battle,test_awards,side
    end
    function api:start_preview(mode,now)
        if (mode~=2 and mode~=3 and mode~=4) or not finite(now) or now<0 then return nil,'INVALID_PREVIEW' end
        local test_state={sequence=1,shots=56222,kills=648,deaths=3,fire_kills=128,
            history_kills=15600,history_deaths=348,total_cents=7243128500,ribbons={},mission_medals={}}
        local test_battle,test_awards,side=preview_models(test_state,mode,now)
        preview={state=test_state,battle=test_battle,awards=test_awards,side=side,
            mode=mode,started=now,deadline=now+8,pulse=0}
        if factories.create_charges then
            preview.charges=factories.create_charges()
            if mode==2 or mode==4 then preview.charges:emit('stim','治疗针',250000,now) end
        end
        self.preview_mode=mode;invalidate();return true
    end
    function api:preview_active(now)
        if preview and finite(now) and now>=preview.deadline then preview=nil;self.preview_mode=nil;invalidate() end
        return preview~=nil
    end
    local function scale_at(width,height,scale,side_count)
        local s=math.max(.001,(finite(scale) and scale>0 and scale or math.min(width/1920,height/1080))*cfg.scale)
        local model=last_model
        s=math.min(s,width/(cfg.right_margin+(model and model.layout.width or cfg.width)),
            height/(cfg.top_margin+(model and model.height or 109)+cfg.task_gap+8))
        return math.max(.001,s)
    end
    function api:reserved_height(width,height,scale)
        if not finite(width) or not finite(height) or width<=0 or height<=0 or not cfg.move_tasks then return 0 end
        local s=scale_at(width,height,scale,0)
        local content=last_model and last_model.layout.top_height or 109
        return math.min(height,(cfg.top_margin+content+cfg.task_gap)*s)
    end
    -- Renderer dimensions only; native observations/writes happen in the 10 Hz update.
    function api:reservation(visible,native,now)
        if native then
            local model=self:native_model(now or 0,visible,latest_width)
            return {visible=visible==true,move_tasks=cfg.move_tasks,native=true,
                native_height=(cfg.top_margin+model.layout.top_height+cfg.task_gap)*cfg.scale}
        end
        return {visible=visible==true and viewport_width~=nil, move_tasks=cfg.move_tasks,
            width=viewport_width,height=viewport_height,
            reserved_height=viewport_width and self:reserved_height(viewport_width,viewport_height,viewport_scale) or 0}
    end
    local function styles_at(s)
        if styles and previous_scale==s then return end
        local a=alpha(cfg.opacity)
        styles={label={size=11*s,colour='#B4C0C6'..a,z=1},large={size=22*s,colour='#FFF9ED'..a,align='right',z=1},
            value={size=14*s,colour='#FFF9ED'..a,align='right',z=1},bill_label={size=11*s,colour='#F5D648'..a,z=1},
            bill={size=12*s,colour='#FFF9ED'..a,align='right',z=1},kd={size=11*s,colour='#FFF9ED'..a,align='right',z=1},
            count={size=10*s,colour='#FFF9ED'..a,align='right',z=3},recent={size=13*s,colour='#F5D648'..a,align='right',z=2}}
    end
    local function symbol(d,id,x,y,width,height,ribbon)
        local image=images[id]
        if not image or type(d.image)~='function' then return end
        if ribbon then d:image(images.frame.handle,x,y,width,height,images.frame.opts) end
        local asset,bbox=image.asset,image.asset.packed_bbox
        local bw,bh=bbox[3]-bbox[1],bbox[4]-bbox[2]
        local dw=ribbon and width*asset.symbol_width*asset.display_scale or width
        local dh=ribbon and height*.70*asset.display_scale or height
        local factor=math.min(dw/bw,dh/bh,d.width/256,d.height/256)
        local size=256*factor
        -- The actual Runtime requires the WHOLE quad, including its transparent
        -- padding, inside the viewport. Preserve aspect ratio and reviewed scale.
        local qx=clamp(x+(width-bw*factor)/2-bbox[1]*factor,0,d.width-size)
        local qy=clamp(y+(height-bh*factor)/2-bbox[2]*factor,0,d.height-size)
        d:image(image.handle,qx,qy,size,size,image.opts)
    end
    function api:native_model(now,visible,width)
        local revision=read_locale_revision and read_locale_revision() or 0
        if revision~=last_locale_revision then
            last_locale_revision=revision;self:invalidate_locale()
        end
        local testing=self:preview_active(now)
        local shown_state,shown_battle,shown_awards=state,battle,awards
        local collected,map_open=collection_shown(),map_shown()
        local shown_charges=factories.charges
        if testing then
            shown_state,shown_battle,shown_awards=preview.state,preview.battle,preview.awards
            shown_charges=preview.charges;collected,map_open=true,true
            -- Two demo increases, then two seconds idle and real collection.
            -- Use their synthetic event timestamps even after a long frame.
            local pulse=math.min(2,math.floor(math.max(0,now-preview.started)))
            if pulse>preview.pulse then
                for step=preview.pulse+1,pulse do
                    for _,icon in ipairs(preview.side) do
                        if icon.kind=='ribbon' then shown_state.ribbons[icon.key]=shown_state.ribbons[icon.key]+1 end
                    end
                    shown_awards:update(preview.started+step)
                    if shown_charges and (preview.mode==2 or preview.mode==4) then
                        shown_charges:emit('ammo','机枪弹药',1250,preview.started+step)
                    end
                end
                preview.pulse=pulse
            end
        end
        latest_width=finite(width) and width or cfg.width
        context.map_open=map_open
        context.width=latest_width
        context.currency=cfg.currency
        local stats_view=shown_battle:snapshot(context)
        local stats=stats_view.stats
        sync_batch(shown_awards,shown_charges,now)
        local view=shown_awards:snapshot(now,visible==true,collected)
        local charge_view=shown_state.billing_enabled~=false and shown_charges
            and shown_charges:snapshot(now,visible==true,shown_awards.deadline) or false
        if charge_view~=last_charge_source or cfg.currency~=last_charge_currency then
            formatted_charges={items={},deadline=charge_view and charge_view.deadline,revision=charge_view and charge_view.revision}
            local symbols={SC=' SC',USD='$',CNY='¥',EUR='€',GBP='£',SEK='kr'}
            for _,item in ipairs(charge_view and charge_view.items or {}) do
                local fallback=item.amount_cents/100
                local amount=factories.currency and factories.currency:format(item.amount_cents,cfg.currency)
                    or (fallback>0 and fallback<0.01 and '<0.01' or string.format('%.2f',fallback))
                local amount_text='-'..amount..(symbols[cfg.currency] or cfg.currency)
                local name=localize(item.name)
                formatted_charges.items[#formatted_charges.items+1]={id=item.key,name=name,
                    amount_text=amount_text,text=name..' '..amount_text,changed_at=item.changed_at}
            end
            last_charge_source,last_charge_currency=charge_view,cfg.currency
        end
        local plan=layout:build(stats,view,map_open,latest_width,formatted_charges,now,shown_state.sequence,cfg)
        local notices=source_notices(shown_state,now)
        if last_model and last_model.layout==plan and last_model.testing==testing and last_model.kill_source_notices==notices then return last_model end
        last_model={state=shown_state,stats=stats,stats_view=stats_view,awards=view,charges=formatted_charges,
            collected=collected,map_open=map_open,testing=testing,height=plan.height,layout=plan,kill_source_notices=notices}
        return last_model
    end
    function api:draw(d,now,visible)
        if finite(d.width) and finite(d.height) and d.width>0 and d.height>0 then
            viewport_width,viewport_height,viewport_scale=d.width,d.height,d.scale
        end
        if not visible then return end
        local model=self:native_model(now,true)
        local plan=model.layout
        local s=scale_at(d.width,d.height,d.scale);self.render_scale=s;styles_at(s)
        local x,y=d.width-(cfg.right_margin+plan.width)*s,cfg.top_margin*s
        local popup_scale=1.5
        local popup_top=math.max(plan.side_top,math.min((d.height*cfg.side_vertical-y)/s,
            (d.height-y)/s-plan.side_height*popup_scale-16))
        local popup_shift=popup_top-plan.side_top
        local center_x,center_y=d.width/2,d.height/2+70*s
        for _,box in ipairs(plan.glyphs) do
            local centered=box.group=='center_hits'
            local popup=centered or box.group:sub(1,5)=='side_'
            local size=popup and popup_scale or 1
            local origin=centered and 0 or plan.side_top
            local dy=centered and (center_y-y)/s or (popup and popup_shift or 0)
            local dx=centered and ((center_x-x)/s-plan.width+plan.center_hit_width*size/2) or 0
            local bx,by=x+(plan.width*(1-size)+dx)*s,y+(origin*(1-size)+dy)*s
            local scaled=s*size
            symbol(d,box.id,bx+box.icon_x*scaled,by+box.icon_y*scaled,box.icon_width*scaled,box.icon_height*scaled,
                box.kind=='ribbon' and not box.side_icon)
            styles.count.size=11*s*size
            if box.kind=='ribbon'and not box.side_icon and type(d.rect)=='function'then
                local w=(#box.count_text*7+4)*scaled
                d:rect(bx+box.count_x*scaled-w,by+(box.count_y-1)*scaled,w+scaled,14*scaled,'#0E0E0EFF',2)
            end
            d:text(box.count_text,bx+box.count_x*scaled,by+box.count_y*scaled,styles.count)
            for index,line in ipairs(box.name_lines or EMPTY) do
                styles.kd.size=11*s*size
                d:text(line,bx+box.name_x*scaled,by+(box.name_y+(index-1)*box.line_height)*scaled,styles.kd)
            end
        end
        for _,row in ipairs(plan.metrics) do
            symbol(d,row.id,x+row.icon_x*s,y+row.icon_y*s,row.icon_width*s,row.icon_height*s,false)
            local style=styles[row.key] or styles.value
            style.size=row.font_size*s
            if row.trend and images[row.trend.id] then
                d:text(row.text_body,x+row.body_text_x*s,y+row.text_y*s,style)
                local indicator=row.trend
                symbol(d,indicator.id,x+indicator.x*s,y+indicator.y*s,indicator.width*s,indicator.height*s,false)
                d:text(row.text_suffix,x+row.suffix_text_x*s,y+row.text_y*s,style)
            else
                d:text(row.text,x+row.text_x*s,y+row.text_y*s,style)
            end
        end
        for _,row in ipairs(plan.charges) do
            styles.kd.size=11*s*popup_scale;styles.kd.align='right'
            d:text(row.text,x+row.text_x*s,y+(plan.side_top+(row.text_y-plan.side_top)*popup_scale+popup_shift)*s,styles.kd)
        end
        for _,row in ipairs(plan.center_charges or EMPTY)do
            styles.kd.size=11*s*popup_scale;styles.kd.align='center'
            d:text(row.text,center_x,center_y+row.text_y*s*popup_scale,styles.kd)
        end
        local notice_top=plan.center_hit_height or 0
        for _,row in ipairs(plan.center_charges or EMPTY)do notice_top=math.max(notice_top,row.text_y+22)end
        notice_top=notice_top+12
        for _,entry in ipairs(model.kill_source_notices.items or EMPTY)do
            local top=center_y+notice_top*s*popup_scale
            local bottom=top+(#entry.lines*20-3.5)*s*popup_scale
            if(entry.persistent==true or now<entry.expires_at)and bottom<=d.height-12*s then
                styles.kd.size=11*s*popup_scale;styles.kd.align='center'
                for index,line in ipairs(entry.lines)do d:text(line,center_x,top+(index-1)*20*s*popup_scale,styles.kd)end
                notice_top=notice_top+#entry.lines*20+6
            end
        end
        styles.kd.align='right'
        self.kd_text=model.stats.kd_text
        previous_scale,previous_width,previous_height=s,d.width,d.height
    end
    return api
end
