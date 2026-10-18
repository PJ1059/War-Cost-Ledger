local HD2_HUD_ADDON = "mods/hd2_costs/war_cost_native_hud"
-- HUD+ owns these native widgets. Combat and award data come only from a cache.
return function(options)
    options=options or {}
    -- Refresh optional aliases before the parent in both Reader generations.
    -- A computed barrier has linear dependencies; choose expands short-circuit
    -- paths in HUD+ 0.2.4 and exceeds LuaJIT's compiler limits for Career.
    local function refresh_aliases(sources,name,leaves)
        local values,optional={},{}
        for index,source in ipairs(leaves)do
            local key=tostring(index);values[key]=source;optional[key]=index>1
        end
        sources[name]={ledger_alias_refresh={values=values,optional=optional,entry={},calls={}}}
    end
    local status={ready=false,feed_runs=0,accepted=0,status='waiting_for_feed',
        source='HUD+ 0.2.1 / 0.2.4 native widgets',pixels_verified=false,version=1}
    if options.publish~=false then rawset(_G,'HD2WarCostLedgerNativeHUDV1',status) end
    local previous,previous_feed,transitions=nil,nil,{}
    local notice_expiry
    local notice_feed,notice_clock_anchor,notice_ledger_anchor
    local animating=false
    local app=rawget(_G,'stingray') and stingray.Application
    local clock=options.clock or (app and app.time_since_launch)
    local function finite(v) return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
    local function pair(v,positive)
        if type(v)~='table' or not finite(v[1]) or not finite(v[2]) then return nil end
        if math.abs(v[1])>16384 or math.abs(v[2])>16384 then return nil end
        if positive and (v[1]<=0 or v[2]<=0) then return nil end
        return {v[1],v[2]}
    end
    local function text(v)
        if finite(v) then v=tostring(v) end
        if v==nil then return '--' end
        if type(v)~='string' or #v>96 or v:find('[%z\1-\31\127]') then return nil end
        return v
    end
    local function hash(v)
        return type(v)=='string' and #v==16 and not v:find('[^%da-fA-F]') and v:lower() or nil
    end
    local function colour(v)
        if type(v)~='string' or not v:match('^#%x%x%x%x%x%x$') then return {1,249/255,237/255,1} end
        return {tonumber(v:sub(2,3),16)/255,tonumber(v:sub(4,5),16)/255,tonumber(v:sub(6,7),16)/255,1}
    end
    local assets,order={},{}
    local art=options.art or {}
    local source_assets={}
    for _,asset in ipairs(art.images or {}) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(art.metrics or {}) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(art.indicators or {}) do source_assets[#source_assets+1]=asset end
    for _,asset in ipairs(source_assets) do
        local resource=hash(asset.resource_hash)
        local box=asset.packed_bbox
        if type(asset.id)=='string' and not assets[asset.id] and resource and type(box)=='table'
            and finite(box[1]) and finite(box[2]) and finite(box[3]) and finite(box[4])
            and box[3]>box[1] and box[4]>box[2] then
            assets[asset.id]={resource=resource,box=box,colour=colour(asset.accent),
                symbol_width=asset.symbol_width or .34,display_scale=asset.display_scale or 1}
            order[#order+1]=asset.id
        end
    end
    local frame=art.frame and hash(art.frame.resource_hash)
    local solid=art.ui and art.ui.solid and hash(art.ui.solid.resource)
    status.art_count=#(art.images or {})
    status.metric_count=#(art.metrics or {})
    status.indicator_count=#(art.indicators or {})
    status.layout_revision='hud-common-right-edge-v6'
    status.curvature_path='native parent; HUD+ curved mask material c2'
    local function same(a,b)
        if a==b then return true end
        if type(a)~='table' or type(b)~='table' then return false end
        for k,v in pairs(a) do if not same(v,b[k]) then return false end end
        for k in pairs(b) do if a[k]==nil then return false end end
        return true
    end
    local function bounded(v,limit)
        if #v<=limit then return v end
        -- KD can contain the native Chinese "无阵亡" label. Count codepoints,
        -- keeping complete UTF-8 characters when truncating a long value.
        local count, cut = 0, 0
        for at in v:gmatch('()[^\128-\191]') do
            count = count + 1
            if count == limit - 2 then cut = at - 1 end
        end
        if count <= limit then return v end
        return v:sub(1,cut)..'...'
    end
    local function artwork(view,prefix,id,x,y,width,height,ribbon)
        local asset=assets[id]
        if not asset then return end
        local box=asset.box
        local bw,bh=box[3]-box[1],box[4]-box[2]
        local dw=ribbon and width*asset.symbol_width*asset.display_scale or width
        local dh=ribbon and height*.70*asset.display_scale or height
        local factor=math.min(dw/bw,dh/bh)
        local quad=256*factor
        view[prefix..'texture']=asset.resource
        view[prefix..'position']={x+(width-bw*factor)/2-box[1]*factor,
            -(y+(height-bh*factor)/2-box[2]*factor)}
        view[prefix..'size']={quad,quad}
        if ribbon and frame then
            view[prefix..'frame']=frame
            view[prefix..'frame_position']={x,-y}
            view[prefix..'frame_size']={width,height}
        end
    end
    local function collect_art(view,feed,now,notice_now)
        local plan=feed.layout
        local seen={}
        animating=false
        for _,box in ipairs(plan.glyphs or {}) do
            local centered=box.group=='center_hits'
            local group=(centered or box.group:sub(1,5)=='side_') and 'side' or 'collected'
            local size=group=='side' and (feed.popup_scale or 1) or 1
            local base_x=plan.width*(1-size)
            local origin=centered and 0 or plan.side_top
            local base_y=origin*(1-size)
            local prefix=group..'_'..box.id..'_'
            local count=text(box.count_text)
            local dy=group=='side' and (feed.popup_shift or 0) or 0
            local shift_x=group=='side' and (feed.popup_shift_x or 0) or 0
            if centered then
                local center=feed.center_position or {plan.width/2,-plan.side_top}
                shift_x=center[1]-plan.width+(plan.center_hit_width or 0)*size/2
                dy=-center[2]
            end
            if assets[box.id] and count then
                seen[prefix]=true
                local motion=transitions[prefix]
                if not motion then
                    motion={count=count,changed=group=='side' and now or -1,entered=group=='side' and now or -1}
                    transitions[prefix]=motion
                elseif motion.count~=count then motion.count=count;motion.changed=now end
                local pulse=motion.changed>=0 and math.max(0,1-(now-motion.changed)/.18) or 0
                local slide=motion.entered>=0 and math.max(0,1-(now-motion.entered)/.18) or 0
                if pulse>0 or slide>0 then animating=true end
                local dx=18*size*slide*slide*slide+shift_x
                artwork(view,prefix,box.id,base_x+box.icon_x*size+dx,base_y+box.icon_y*size+dy,box.icon_width*size,box.icon_height*size,
                    box.kind=='ribbon' and not box.side_icon)
                view[prefix..'count']=count
                view[prefix..'count_position']={base_x+box.count_x*size+dx,-(base_y+box.count_y*size+dy)}
                local grow=(1+.18*pulse)*size
                view[prefix..'count_scale']={grow,grow}
                view[prefix..'count_colour']={.88+.12*pulse,.89+.11*pulse,.85+.15*pulse,1}
                if box.kind=='ribbon'and not box.side_icon and solid then
                    local w=(#count*7+4)*grow
                    view[prefix..'count_back']=solid
                    view[prefix..'count_back_position']={view[prefix..'count_position'][1]-w,
                        view[prefix..'count_position'][2]+size}
                    view[prefix..'count_back_size']={w+size,14*grow}
                end
                for i,line in ipairs(box.name_lines or {}) do
                    if i>2 then break end
                    view[prefix..'name'..i]=text(line)
                    view[prefix..'name'..i..'_position']={base_x+box.name_x*size+dx,
                        -(base_y+(box.name_y+(i-1)*box.line_height)*size+dy)}
                    view[prefix..'name'..i..'_scale']={size,size}
                end
            end
        end
        for key in pairs(transitions) do if not seen[key] then transitions[key]=nil end end
        for _,row in ipairs(plan.metrics or {}) do
            local key=row.key
            view[key]=text(row.text)
            view[key..'_position']={row.text_x,-row.text_y}
            artwork(view,'metric_'..row.id..'_',row.id,row.icon_x,row.icon_y,row.icon_width,row.icon_height,false)
            if key=='kd' and row.trend and assets[row.trend.id] then
                view[key]=text(row.text_body)
                view[key..'_position']={row.body_text_x,-row.text_y}
                view.kd_suffix=text(row.text_suffix)
                view.kd_suffix_position={row.suffix_text_x,-row.text_y}
                local indicator=row.trend
                artwork(view,'indicator_'..indicator.id..'_',indicator.id,
                    indicator.x,indicator.y,indicator.width,indicator.height,false)
            end
        end
        for i,row in ipairs(plan.charges or {}) do
            if i>9 then break end
            local size=feed.popup_scale or 1
            view['charge_'..i]=text(row.text)
            view['charge_'..i..'_position']={plan.width+(row.text_x-plan.width)*size+(feed.popup_shift_x or 0),
                -(plan.side_top+(row.text_y-plan.side_top)*size+(feed.popup_shift or 0))}
            view['charge_'..i..'_scale']={size,size}
        end
        for i,row in ipairs(plan.center_charges or {})do
            if i>9 then break end
            local size=feed.popup_scale or 1
            local center=feed.center_position or {plan.width/2,-plan.side_top}
            local key='center_charge_'..i
            view[key]=text(row.text)
            view[key..'_position']={center[1],center[2]-row.text_y*size}
            view[key..'_scale']={size,size}
        end
        local notices=feed.kill_source_enabled~=false and feed.kill_source_notices or nil
        local size=feed.popup_scale or 1.5
        local center=feed.center_position or {plan.width/2,-plan.side_top}
        local top=plan.center_hit_height or 0
        for _,row in ipairs(plan.center_charges or {})do top=math.max(top,row.text_y+22)end
        top=top+12;notice_expiry=nil
        for index,item in ipairs(type(notices)=='table'and notices.items or {})do
            if index>1 then break end
            if type(item)=='table'and(item.persistent==true or finite(item.expires_at)and item.expires_at>notice_now)and type(item.lines)=='table'then
                local lines={}
                for line_index,line in ipairs(item.lines)do
                    if line_index>1 then break end
                    if type(line)=='string'and #line>0 and #line<=192 and not line:find('[%z\1-\31\127]')then lines[#lines+1]=line end
                end
                local bottom=-center[2]+(top+#lines*20-3.5)*size
                if #lines>0 and(not finite(feed.kill_notice_bottom)or bottom<=feed.kill_notice_bottom-12)then
                    for line_index,line in ipairs(lines)do
                        local key='kill_notice_'..index..'_'..line_index
                        view[key]=line;view[key..'_position']={center[1],center[2]-(top+(line_index-1)*20)*size}
                        view[key..'_scale']={size,size}
                    end
                    top=top+#lines*20+6
                    if item.persistent~=true then notice_expiry=math.min(notice_expiry or item.expires_at,item.expires_at)end
                end
            end
        end
    end
    local function snapshot()
        if options.feed then return options.feed() end
        local ledger=rawget(_G,'HD2WarCostLedgerV1')
        if type(ledger)~='table' or type(ledger.native_hud_snapshot)~='function' then return nil end
        return ledger.native_hud_snapshot()
    end
    local function refuse(why)
        previous=nil;previous_feed=nil;transitions={};notice_expiry=nil;notice_feed=nil
        notice_clock_anchor,notice_ledger_anchor=nil,nil;animating=false;status.ready=false;status.status=why;return nil
    end
    local function run(_,_,_,_,values)
        status.feed_runs=status.feed_runs+1
        local ok,feed=pcall(snapshot)
        if not ok then return refuse('feed_error') end
        if type(feed)~='table' or feed.shown~=true then return refuse('hidden') end
        if not finite(feed.hud) or feed.hud<65536 or feed.hud>=140737488355328
            or feed.hud%8~=0 or type(values)~='table' or feed.hud~=values.hud then
            return refuse('hud_identity_changed')
        end
        local now=finite(feed.now) and feed.now or 0
        if type(clock)=='function' then
            local clock_ok,value=pcall(clock)
            if clock_ok and finite(value) then now=value end
        end
        local ledger_now=finite(feed.now)and feed.now or now
        if notice_feed~=feed or notice_ledger_anchor~=ledger_now then
            notice_feed,notice_clock_anchor,notice_ledger_anchor=feed,now,ledger_now
        end
        -- Expiry is supplied in the ledger clock. Native animation time may
        -- start at application launch, so bridge only elapsed time, not epochs.
        local notice_now=notice_ledger_anchor+math.max(0,now-notice_clock_anchor)
        -- The root publishes immutable snapshots at its existing 10 Hz. Only
        -- active 180 ms animations use the native application clock per frame.
        -- Never take this shortcut for callers that mutate a snapshot in place.
        if feed.immutable==true and feed==previous_feed and previous and not animating and(not notice_expiry or notice_now<notice_expiry)then
            status.ready=true;status.status='feed_ready';return previous
        end
        local position,scale=pair(feed.position),pair(feed.scale,true)
        local size=pair(feed.size or {336,feed.block_height or 106},true)
        if not position or not scale or not size or scale[1]>4 or scale[2]>4
            or not finite(feed.opacity) or feed.opacity<0 or feed.opacity>1 then return refuse('invalid_geometry') end
        if type(feed.layout)~='table' or feed.layout.revision~='hud-common-right-edge-v6' then return refuse('invalid_layout') end
        local view={hud=feed.hud,position=position,scale=scale,size=size,opacity=feed.opacity}
        collect_art(view,feed,now,notice_now)
        if not same(previous,view) then previous=view;status.accepted=status.accepted+1 end
        previous_feed=feed.immutable==true and feed or nil
        status.ready=true;status.status='feed_ready'
        return previous
    end
    local refresh={'ledger.native.feed'}
    local sources={
        ['ledger.native.feed']={ledger_cached_feed={values={hud='hud.manager'},entry={},optional={},calls={}}},
        ['ledger.native.parent']={from='hud.manager',offset='ledger_native_right_parent',form='address',
            requires={'ledger.native.feed','ledger.native.refresh'}},
    }
    local function bind(field)
        local name='ledger.native.'..field
        sources[name]={from='ledger.native.feed',part=field}
        -- A lifecycle dependency keeps optional icon aliases fresh every frame;
        -- optional nils must not gate the native parent while that icon is absent.
        refresh[#refresh+1]=name
        return name
    end
    for _,field in ipairs({'position','scale','size','opacity'}) do bind(field) end
    local rows={{id='ledger_block',kind='frame',source='ledger.native.feed',
        anchor={0,1},pivot={0,1},
        transform={position='ledger.native.position',scale='ledger.native.scale',size='ledger.native.size'},
        paint={opacity='ledger.native.opacity'}}}
    local font={'hud_text_font','hud_text_variant','hud_text_variant'}
    local function text_row(id,field,height,animated,align,layer)
        local owner=id..'_frame'
        local transform={position=bind(field..'_position')}
        if animated or field:match('charge_') or field:match('^kill_notice_')or field:match('^side_.*name%d$')then
            transform.scale=bind(field..'_scale')
        end
        rows[#rows+1]={id=owner,kind='frame',parent='ledger_block',source=bind(field),
            anchor={0,1},pivot={0,1},transform=transform}
        local row={id=id,kind='text',parent=owner,source='ledger.native.'..field,
            font=font,layer=layer or 'hud_text_layer',anchor={0,1},pivot={align or 1,1},position={0,0},text_height=height}
        if animated then row.paint={colour=bind(field..'_colour')}
        else row.colour={.88,.89,.85} end
        rows[#rows+1]=row
    end
    for _,row in ipairs({{'kills',31},{'bill',12},{'shots',13},{'kd',11}}) do
        text_row('ledger_'..row[1],row[1],row[2],false)
    end
    text_row('ledger_kd_suffix','kd_suffix',11,false)
    for i=1,9 do text_row('ledger_charge_'..i,'charge_'..i,11,false) end
    for i=1,9 do text_row('ledger_center_charge_'..i,'center_charge_'..i,11,false,.5)end
    for index=1,1 do for line=1,1 do
        local field='kill_notice_'..index..'_'..line
        text_row('ledger_'..field,field,11,false,.5)
    end end
    if #order>0 then
        sources['ledger.native.curve']={module='game',offset='picture_bend_data',form='vec4'}
        for _,id in ipairs(order) do
            local metric=id:sub(1,1)=='U'
            local indicator=id:sub(1,1)=='I'
            for _,group in ipairs(metric and {'metric'} or (indicator and {'indicator'} or {'collected','side'})) do
                local prefix=group..'_'..id..'_'
                local asset=assets[id]
                local function image(suffix,accent)
                    rows[#rows+1]={id='ledger_'..prefix..suffix,kind='image',parent='ledger_block',
                        source=bind(prefix..suffix),material='mask_material',layer='hud_text_layer',
                        anchor={0,1},pivot={0,1},
                        transform={position=bind(prefix..(suffix=='frame' and 'frame_position' or 'position')),
                            size=bind(prefix..(suffix=='frame' and 'frame_size' or 'size'))},
                        constants={{key='mask_c0',value={1,249/255,237/255,1}},{key='mask_c1',value=accent}},
                        vectors={{key='mask_c2',source='ledger.native.curve',count=4}}}
                end
                local ribbon=id:match('^[RHGT]')~=nil
                if ribbon and frame then image('frame',colour(art.frame.accent)) end
                image('texture',asset.colour)
                if not metric and not indicator then
                    if ribbon and solid then
                        rows[#rows+1]={id='ledger_'..prefix..'count_back',kind='image',parent='ledger_block',
                            source=bind(prefix..'count_back'),material='mask_material',layer='ledger_count_back_layer',
                            anchor={0,1},pivot={0,1},
                            transform={position=bind(prefix..'count_back_position'),size=bind(prefix..'count_back_size')},
                            constants={{key='mask_c0',value={.055,.055,.055,1}},{key='mask_c1',value={0,0,0,0}}},
                            vectors={{key='mask_c2',source='ledger.native.curve',count=4}}}
                    end
                    text_row('ledger_'..prefix..'count',prefix..'count',11,true,nil,'ledger_count_text_layer')
                    if group=='side' and id:sub(1,1)=='M' then
                        for i=1,2 do text_row('ledger_'..prefix..'name'..i,prefix..'name'..i,11,false) end
                    end
                end
            end
        end
    end
    refresh_aliases(sources,'ledger.native.refresh',refresh)
    local result={
        pin={exe='f5fee03dcfdb2e553a4752c283590950ac13316b376d8196aa556ff0400d5f06',
            game='2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e'},
        title=0x57434C4E,strings='94a17a3a1257fc23',
        numbers={ledger_native_right_parent=0x2944A0,ledger_count_back_layer=552,ledger_count_text_layer=553},sources=sources,
        compute={ledger_cached_feed={run=run,gather=function() return {} end},
            ledger_alias_refresh={run=function()return true end,gather=function()return {} end}},
        screens={{id='ledger.native.stats',parent='ledger.native.parent',rows=rows}},
        native_hud_status=status,
    }
    if type(options.career)=='function' then
        local career=options.career({assets=assets,artwork=artwork,frame=frame,
            frame_colour=colour(art.frame and art.frame.accent),solid=art.ui and art.ui.solid,
            feed=options.career_feed,refresh_aliases=refresh_aliases})
        for key,value in pairs(career.numbers or {})do result.numbers[key]=value end
        for key,value in pairs(career.sources)do result.sources[key]=value end
        for key,value in pairs(career.compute)do result.compute[key]=value end
        for _,screen in ipairs(career.screens)do result.screens[#result.screens+1]=screen end
        result.native_career_status=career.status
        status.career=career.status
    end
    return result
end
