-- HUD+ declaration for a separate Career root. No ordinary overlay is used.
return function(options)
    local assets,artwork=options.assets,options.artwork
    local status={ready=false,source='personal Career native widgets',pixels_verified=false}
    local sources,rows,refresh={},{},{'ledger.career.feed'}
    local header_limit,control_limit=48,32 -- Fixed pools; combat lists paginate before layout.
    local shape_limit=240 -- 48 decorations x 5 rectangles
    local chart_limit=97 -- 96 one-pixel columns + the latest observation
    local solid=options.solid and options.solid.resource
    -- Career has its own flat style and same-name menu materials. Combat
    -- retains HUD+ curvature. Native pixels still require in-game acceptance.
    local career_layer='ledger_career_layer'
    -- UI primitives are depth-sorted by layer, across materials. Declaration
    -- order cannot keep an opaque backing behind text at the same depth.
    local art_layer='ledger_career_art_layer'
    local count_back_layer='ledger_career_count_back_layer'
    local text_layer='ledger_career_text_layer'
    local tooltip_back_layer='ledger_career_tooltip_back_layer'
    local tooltip_text_layer='ledger_career_tooltip_text_layer'
    local function bind(field)
        local name='ledger.career.'..field
        sources[name]={from='ledger.career.feed',part=field}
        refresh[#refresh+1]=name
        return name
    end
    local function snapshot()
        if options.feed then return options.feed()end
        local ledger=rawget(_G,'HD2WarCostLedgerV1')
        if type(ledger)=='table' and type(ledger.career_panel_snapshot)=='function' then return ledger.career_panel_snapshot()end
    end
    local function finite(v)return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
    local function safe_text(s)return type(s)=='string' and #s<=400 and not s:find('[%z\1-\31\127]') and s or nil end
    local function wrap(s,width,max_lines)
        s=safe_text(s)or''
        local result,line,used={},'',0
        -- English award names should wrap between words. Keep the original
        -- CJK character layout; a single oversized word still splits safely.
        if not s:find('[\128-\255]')and s:find(' ',1,true)then
            for word in s:gmatch('%S+')do
                if used>0 and used+.55+#word*.55>width then result[#result+1]=line;line,used='',0 end
                if used>0 then line=line..' ';used=used+.55 end
                for ch in word:gmatch('.')do
                    if used+.55>width then result[#result+1]=line;line,used='',0 end
                    line,used=line..ch,used+.55
                end
            end
            if #line>0 then result[#result+1]=line end
            while #result>max_lines do table.remove(result)end
            return result
        end
        for ch in s:gmatch('[%z\1-\127\194-\244][\128-\191]*')do
            local units=#ch==1 and .55 or 1
            if used+units>width then result[#result+1]=line;line,used='',0 end
            line,used=line..ch,used+units
        end
        if #line>0 then result[#result+1]=line end
        while #result>max_lines do table.remove(result)end
        return result
    end
    local last_feed,last_view
    local function hide(reason)
        last_feed,last_view=nil,nil;status.ready=false;status.reason=reason;return nil
    end
    local function guard(read,feed)
        if type(read)~='table' or type(read.bytes)~='table'
            or type(read.bytes.decode)~='function' or type(read.bytes.u32)~='function' then return false end
        -- 260 bytes per native update hides on close/resize/rebuild between
        -- the bounded 10 Hz parent samples. Nothing is written here.
        local raw,alpha
        if type(read.span)=='function' then
            raw=read:span(feed.parent,256)
            alpha=read:span(feed.alpha_address,4)
        elseif type(feed.guard_read)=='function' then
            -- HUD+ 0.2.4 text() dereferences memory directly. The snapshot
            -- supplies a safe reader limited to its proven parent and alpha.
            raw=feed.guard_read(feed.parent,256)
            alpha=feed.guard_read(feed.alpha_address,4)
            if type(raw)~='string' or #raw~=256 or type(alpha)~='string' or #alpha~=4 then return false end
        else return false end
        if raw==nil or alpha==nil then return false end
        local bytes=read.bytes
        local function pointer_at(offset)
            if type(read.pointer_in)=='function' then return read:pointer_in(raw,offset)end
            -- The newer facade keeps byte decoders but has no pointer helper.
            local low,high=bytes.u32(raw,offset),bytes.u32(raw,offset+4)
            if low==nil or high==nil then return nil end
            return low+high*4294967296
        end
        local flags=bytes.u32(raw,0)
        if not flags or math.floor(flags/262144)%16~=1
            or pointer_at(0xF0)~=feed.parent_parent
            or pointer_at(0xF8)~=feed.gui_context then return false end
        local opacity=bytes.decode(alpha,0,'f32')
        if not finite(opacity) or opacity<=.95 or opacity>1.001 then return false end
        for field,at in pairs({width=0x24,height=0x28,sx=0x64,sy=0x8C,x=0x94,y=0x9C})do
            if bytes.decode(raw,at,'f32')~=feed.root[field]then return false end
        end
        return true
    end
    local function compute(read)
        local ok,feed=pcall(snapshot)
        if not ok or type(feed)~='table' or feed.shown~=true then return hide('hidden')end
        if not finite(feed.parent) or feed.parent<65536 or feed.parent%8~=0
            or type(feed.root)~='table' or type(feed.model)~='table' then return hide('invalid_feed')end
        local guarded,accepted=pcall(guard,read,feed)
        if not guarded or not accepted then return hide('parent_changed')end
        if last_feed==feed and last_view then return last_view end
        local view={parent=feed.parent,position=feed.position,size=feed.size,opacity=1}
        local plan=feed.model
        local function styled(field,item,is_control)
            local align=item.align or 0
            view[field]=safe_text(item.text)
            view[field..(align==1 and '_right' or align==0.5 and '_center' or '_left')]=view[field]
            view[field..'_position']={is_control and (item.text_x or item.x) or (item.x+(item.width or 0)*align),
                -(is_control and (item.text_y or item.y) or item.y)}
            local size=item.font_size or 14
            view[field..'_scale']={size/14,size/14}
            view[field..'_colour']=item.colour or {.88,.88,.88}
        end
        for index,header in ipairs(plan.header_texts or {})do
            if index<=header_limit and header.y>=0 and header.y+header.height<=plan.height then
                styled('header'..index,header,false)
            end
        end
        for index,control in ipairs(plan.nav_controls or {})do
            if index<=control_limit and control.x>=0 and control.x+control.width<=plan.width
                and control.y>=0 and control.y+control.height<=plan.height then
                styled('nav'..index,control,true)
            end
        end
        local shapes=0
        local function rectangle(field,x,y,w,h,colour)
            if not solid or not colour or w<=0 or h<=0 then return end
            view[field]=solid;view[field..'_position']={x,-y};view[field..'_size']={w,h}
            view[field..'_colour']={colour[1],colour[2],colour[3]};view[field..'_opacity']=colour[4] or 1
        end
        local function shape(x,y,w,h,colour)
            if shapes>=shape_limit then return end
            shapes=shapes+1;rectangle('shape_'..shapes,x,y,w,h,colour)
        end
        for _,d in ipairs(plan.decorations or {})do
            if d.fill then shape(d.x,d.y,d.width,d.height,d.fill)end
            if d.border then
                shape(d.x,d.y,d.width,1,d.border);shape(d.x,d.y+d.height-1,d.width,1,d.border)
                shape(d.x,d.y,1,d.height,d.accent or d.border);shape(d.x+d.width-1,d.y,1,d.height,d.border)
            elseif d.accent then shape(d.x,d.y,1,d.height,d.accent)end
        end
        local chart=plan.sparkline
        if chart then
            local previous,marks=nil,0
            for index,p in ipairs(chart.samples or chart.points or {})do
                if index>chart_limit then break end
                if previous then
                    -- Each column connects adjacent pixel samples. There is no
                    -- area fill, gradient, or differently shaded time interval.
                    marks=marks+1
                    rectangle('chart_'..marks,chart.x+previous.x,chart.y+math.min(previous.y,p.y)-.75,
                        math.min(1,p.x-previous.x),math.max(1.5,math.abs(p.y-previous.y)+1.5),{.93,.93,.90,1})
                end
                previous=p
            end
            if previous then rectangle('chart_'..(marks+1),chart.x+previous.x-1.5,chart.y+previous.y-1.5,
                3,3,{1,1,.96,1})end
        end
        for index,section in ipairs(plan.sections or {})do
            if index<=2 and section.y>=0 and section.y+20<=plan.height then
                view['section'..index]=safe_text(section.name)
                view['section'..index..'_position']={section.x or 0,-section.y}
            end
        end
        if plan.empty then
            view.empty=safe_text(plan.empty_text)or'暂无战果记录'
            view.empty_position={14,-(plan.empty_y or 28)}
        end
        for _,item in ipairs(plan.items or {})do
            if item.visible and item.y>=0 and item.y+item.height<=plan.height and assets[item.id]then
                local prefix='award_'..item.id..'_'
                local medal=item.kind=='medal'
                local width,height=medal and 42 or 96,medal and 42 or 24
                local x,y=item.x+(item.width-width)/2,item.y
                artwork(view,prefix,item.id,x,y,width,height,not medal)
                view[prefix..'count']='x'..tostring(item.count)
                view[prefix..'count_position']={x+width,-(y+height-10)}
                if not medal then
                    -- Keep the accepted text anchor. Cover only its bottom-right
                    -- patch of ribbon artwork, including the decorative border.
                    local w=#view[prefix..'count']*7+4
                    rectangle(prefix..'count_back',x+width-w,y+height-11,w+1,14,{.055,.055,.055,1})
                end
                for index,line in ipairs(wrap(item.name,9,medal and 2 or 1))do
                    view[prefix..'name'..index]=line
                    view[prefix..'name'..index..'_position']={item.x+item.width/2,-(y+height+4+(index-1)*14)}
                end
            end
        end
        local height=feed.size[2]
        if plan.tooltip then
            local has_details=type(plan.tooltip.details)=='table'and #plan.tooltip.details>0
            local h=has_details and 164 or 104
            local x,y,w=8,math.max(0,height-h-8),plan.width-16
            local anchor=plan.tooltip.anchor
            if anchor and anchor.y<y+h and anchor.y+anchor.height>y then
                local above=anchor.y-h-8
                if above>=0 then y=above
                elseif anchor.y+anchor.height+h+8<=height then y=anchor.y+anchor.height+8 end
            end
            rectangle('tooltip_shape_1',x,y,w,h,{.035,.035,.035,.98})
            rectangle('tooltip_shape_2',x,y,w,1,{.7,.7,.7,.8})
            rectangle('tooltip_shape_3',x,y+h-1,w,1,{.7,.7,.7,.8})
            rectangle('tooltip_shape_4',x,y,1,h,{.7,.7,.7,.8})
            rectangle('tooltip_shape_5',x+w-1,y,1,h,{.7,.7,.7,.8})
            view.tooltip_title=(safe_text(plan.tooltip.name) or '')..'  x'..tostring(plan.tooltip.count)
            view.tooltip_title_position={x+12,-(y+10)}
            for index,line in ipairs(wrap(plan.tooltip.condition,math.max(8,(w-24)/13),3))do
                view['tooltip'..index]=line;view['tooltip'..index..'_position']={x+12,-(y+36+(index-1)*18)}
            end
            for index,line in ipairs(plan.tooltip.details or {})do
                if index<=3 then
                    view['tooltip_history'..index]=line
                    view['tooltip_history'..index..'_position']={x+12,-(y+98+(index-1)*18)}
                end
            end
        end
        -- Select menus share the existing tooltip depth bands, above the
        -- normal list text. Slots stay fixed when options scroll or close.
        if plan.dropdown then
            for index,item in ipairs(plan.dropdown.controls or {})do
                if index<=6 then styled('dropdown'..index,item,true)end
            end
            local n=0
            local function menu_shape(x,y,w,h,colour)
                if n>=20 then return end
                n=n+1;rectangle('dropdown_shape_'..n,x,y,w,h,colour)
            end
            for _,d in ipairs(plan.dropdown.decorations or {})do
                if d.fill then menu_shape(d.x,d.y,d.width,d.height,d.fill)end
                if d.border then
                    menu_shape(d.x,d.y,d.width,1,d.border);menu_shape(d.x,d.y+d.height-1,d.width,1,d.border)
                    menu_shape(d.x,d.y,1,d.height,d.border);menu_shape(d.x+d.width-1,d.y,1,d.height,d.border)
                end
            end
        end
        last_feed,last_view=feed,view;status.ready=true;status.reason='visible'
        return view
    end
    sources['ledger.career.feed']={ledger_career_feed={values={},entry={},optional={},calls={}}}
    sources['ledger.career.parent']={from='ledger.career.feed',part='parent',requires={'ledger.career.refresh'}}
    rows[1]={id='ledger_career_block',kind='frame',source='ledger.career.feed',anchor={0,1},pivot={0,1},
        transform={position=bind('position'),size=bind('size')},paint={opacity=bind('opacity')}}
    local function rectangle_row(field,layer)
        local source=bind(field)
        rows[#rows+1]={id='ledger_career_'..field,kind='image',parent='ledger_career_block',
            source=source,material_source=source,layer=layer or career_layer,anchor={0,1},pivot={0,1},
            transform={position=bind(field..'_position'),size=bind(field..'_size')},
            paint={colour=bind(field..'_colour'),opacity=bind(field..'_opacity')},
            constants={{key='mask_c0',value={1,1,1,1}},{key='mask_c1',value={0,0,0,0}},
                {key='mask_c2',value={0,0,0,0}},{key='ledger_career_c3',value={0,0,0,0}}}}
    end
    -- Reused slots are hidden when absent; no widgets are allocated by hover,
    -- scrolling or filtering. HUD+ skips unchanged native setters.
    for index=1,shape_limit do rectangle_row('shape_'..index)end
    -- The plot must be above the translucent overview backing. Sharing its
    -- depth can let native ordering dim arbitrary portions of the same line.
    for index=1,chart_limit do rectangle_row('chart_'..index,art_layer)end
    local function text_row(field,height,align,styled,layer)
        local owner='ledger_career_'..field..'_frame'
        local transform={position=bind(field..'_position')}
        if styled then transform.scale=bind(field..'_scale')end
        rows[#rows+1]={id=owner,kind='frame',parent='ledger_career_block',source=bind(field),anchor={0,1},pivot={0,1},
            transform=transform}
        local function label(suffix,pivot)
            local row={id='ledger_career_'..field..suffix,kind='text',parent=owner,
                source=suffix=='' and 'ledger.career.'..field or bind(field..suffix),
                font={'ledger_career_font','ledger_career_flat','ledger_career_flat'},layer=layer or text_layer,
                anchor={0,1},pivot={pivot,1},position={0,0},text_height=height}
            if styled then row.paint={colour=bind(field..'_colour')}else row.colour={.88,.88,.88}end
            rows[#rows+1]=row
        end
        -- HUD+ retained text supports a fixed pivot, not dynamic transforms.
        -- Reuse three static children so the engine measures exact glyph width.
        if styled then label('_left',0);label('_center',0.5);label('_right',1)
        else label('',align or 0)end
    end
    local function intensity_colour(rgba)return {rgba[4] or 1,rgba[1],rgba[2],rgba[3]}end
    local award_order={}
    for id in pairs(assets)do if id:match('^[RHMGT]')then award_order[#award_order+1]=id end end
    table.sort(award_order)
    for _,id in ipairs(award_order)do
        local asset=assets[id]
        local prefix='award_'..id..'_'
        local function image(suffix,accent)
            local source=bind(prefix..suffix)
            rows[#rows+1]={id='ledger_career_'..prefix..suffix,kind='image',parent='ledger_career_block',
                source=source,material_source=source,layer=art_layer,anchor={0,1},pivot={0,1},
                transform={position=bind(prefix..(suffix=='frame' and 'frame_position' or 'position')),
                    size=bind(prefix..(suffix=='frame' and 'frame_size' or 'size'))},
                constants={{key='mask_c0',value={1,1,249/255,237/255}},
                    {key='mask_c1',value=intensity_colour(accent)},
                    {key='mask_c2',value={0,0,0,0}},{key='ledger_career_c3',value={0,0,0,0}}}}
        end
        if id:sub(1,1)~='M' and options.frame then image('frame',options.frame_colour)end
        image('texture',asset.colour)
        if id:sub(1,1)~='M'then rectangle_row(prefix..'count_back',count_back_layer)end
    end
    for index=1,header_limit do text_row('header'..index,14,0,true)end
    for index=1,control_limit do text_row('nav'..index,14,0,true)end
    for index=1,20 do rectangle_row('dropdown_shape_'..index,tooltip_back_layer)end
    for index=1,6 do text_row('dropdown'..index,14,0,true,tooltip_text_layer)end
    for _,field in ipairs({'section1','section2','empty'})do text_row(field,15)end
    for _,id in ipairs(award_order)do
        local prefix='award_'..id..'_'
        text_row(prefix..'count',11,1);text_row(prefix..'name1',12,.5)
        if id:sub(1,1)=='M'then text_row(prefix..'name2',12,.5)end
    end
    -- Tooltip backing must cover the ordinary content while staying below
    -- its own labels. Native layer ordering, not Lua row order, enforces this.
    for index=1,5 do rectangle_row('tooltip_shape_'..index,tooltip_back_layer)end
    text_row('tooltip_title',15,nil,nil,tooltip_text_layer)
    for index=1,3 do text_row('tooltip'..index,13,nil,nil,tooltip_text_layer)end
    for index=1,3 do text_row('tooltip_history'..index,12,nil,nil,tooltip_text_layer)end
    options.refresh_aliases(sources,'ledger.career.refresh',refresh)
    return {numbers={ledger_career_layer=24,ledger_career_art_layer=25,ledger_career_count_back_layer=26,ledger_career_text_layer=27,
        ledger_career_tooltip_back_layer=28,ledger_career_tooltip_text_layer=29,
        ledger_career_font=2,ledger_career_flat=0,ledger_career_c3=2893348421},
        sources=sources,compute={ledger_career_feed={run=compute,gather=function()return {}end}},
        screens={{id='ledger.career.collection',parent='ledger.career.parent',rows=rows}},status=status}
end
