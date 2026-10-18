-- Retained presentation geometry in native-parent local units. No game reads,
-- render callbacks, font measurements, or animation timers live in this module.
local function finite(v) return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
local function positive(v) return finite(v) and v>0 end
local function copy_item(item,group)
    return {id=item.id,key=item.key,name=item.name,kind=item.kind,group=group,
        count=item.count,total=item.total,side_icon=item.side_icon==true,
        count_text='x'..tostring(item.count or 1)}
end
local function name_lines(name,width)
    -- Wrap Latin words together; CJK retains the established glyph spacing.
    local out,line,used={},'',0
    local value=tostring(name or '')
    local function push(token,space)
        local weight=0
        for ch in token:gmatch('[%z\1-\127\194-\244][\128-\191]*')do weight=weight+(#ch==1 and 6 or 11)end
        if #line>0 and used+(space and 6 or 0)+weight>width then out[#out+1]=line;line,used='',0 end
        if space and #line>0 then line=line..' ';used=used+6 end
        for ch in token:gmatch('[%z\1-\127\194-\244][\128-\191]*')do
            local size=#ch==1 and 6 or 11
            if used+size>width and #line>0 then out[#out+1]=line;line,used='',0 end
            line,used=line..ch,used+size
        end
    end
    if not value:find('[\128-\255]')then
        for word in value:gmatch('%S+')do push(word,true)end
    else
        for char in value:gmatch('[%z\1-\127\194-\244][\128-\191]*')do push(char,false)end
    end
    if #line>0 then out[#out+1]=line end
    return out
end

local function place(items,left,right,top,cell_width,cell_height,gap,group)
    local boxes={}
    if #items==0 then return boxes,0 end
    local columns=math.max(1,math.floor((right-left+gap)/(cell_width+gap)))
    for first=1,#items,columns do
        local last=math.min(#items,first+columns-1)
        local n=last-first+1
        local row_height=cell_height
        if group=='side_medals' then
            for index=first,last do
                row_height=math.max(row_height,35+3+#name_lines(items[index].name,cell_width)*15)
            end
        end
        local row_left=right-n*cell_width-(n-1)*gap
        for index=first,last do
            local box=copy_item(items[index],group)
            box.x,box.y=row_left+(index-first)*(cell_width+gap),top
            box.width,box.height=cell_width,row_height
            box.icon_x,box.icon_y=box.x,box.y
            box.icon_width,box.icon_height=cell_width,cell_height
            box.count_x,box.count_y=box.x+cell_width,box.y+cell_height-11
            if box.side_icon then
                box.icon_width,box.icon_height=18,20
                if group=='collected_hits' then box.count_text=tostring(box.count) end
            elseif box.kind=='medal' then
                box.icon_width,box.icon_height=31,35
                box.icon_x=box.x+cell_width-box.icon_width
                box.count_x,box.count_y=box.x+cell_width,box.y+24
                if group=='side_medals' then
                    box.name_lines=name_lines(box.name,cell_width)
                    box.name_x,box.name_y,box.line_height=box.x+cell_width,box.y+38,15
                end
            elseif group=='side_ribbons' then
                box.icon_height=26
            end
            boxes[#boxes+1]=box
        end
        top=top+row_height+gap
    end
    local last=boxes[#boxes]
    return boxes,last.y+last.height-boxes[1].y
end
local function append(target,source) for _,v in ipairs(source) do target[#target+1]=v end end

return function(localize)
    local translate=type(localize)=='function'and localize or function(s)return s end
    local place_original=place
    local function place(items,...)
        local translated={}
        for i,item in ipairs(items)do
            local copy={};for k,v in pairs(item)do copy[k]=v end
            copy.name=translate(item.name);translated[i]=copy
        end
        return place_original(translated,...)
    end
    local cached,previous={},{}
    local peak_side_height,previous_deadline,sequence=0,nil,nil
    local api={version=1,revision='hud-common-right-edge-v6'}
    function api:clear()
        cached,previous,peak_side_height,previous_deadline,sequence=nil,{},0,nil,nil
    end
    function api:build(stats,awards,map_open,width,charges,now,current_sequence,positions)
        local hit_position=positions and positions.hit_position or 'right'
        local charge_position=positions and positions.charge_position or 'right'
        width=math.max(160,math.min(600,math.floor(finite(width) and width or 600)))
        now=finite(now) and now or 0
        charges=charges or false
        if cached and previous.stats==stats and previous.awards==awards
            and previous.map==map_open and previous.width==width and previous.charges==charges
            and previous.sequence==current_sequence and previous.hit_position==hit_position
            and previous.charge_position==charge_position then return cached end
        if sequence~=current_sequence or (previous_deadline and now>=previous_deadline)
            or previous.hit_position~=hit_position or previous.charge_position~=charge_position then peak_side_height=0 end
        sequence=current_sequence
        local plan={revision=self.revision,width=width,height=0,
            collected={ribbons={},medals={},hits={}},side={hits={},ribbons={},medals={}},
            charges={},center_hits={},center_charges={},metrics={},glyphs={}}
        local metric_width=math.min(math.max(112,width*.25),164)
        local award_right=width-metric_width-12
        local ribbon_items,medal_items,hit_items={},{},{}
        for _,item in ipairs(awards.ribbons or {}) do
            if not item.side_icon and positive(item.count) then ribbon_items[#ribbon_items+1]=item end
        end
        for _,item in ipairs(awards.medals or {}) do
            if positive(item.count) then medal_items[#medal_items+1]=item end
        end
        if map_open then
            for _,item in ipairs(awards.hits or {}) do
                if positive(item.count) then hit_items[#hit_items+1]=item end
            end
        end
        -- Narrow native parents still retain one intact ribbon; move metrics to
        -- their own upper row only when both columns cannot physically fit.
        local top=0
        if award_right<68 then award_right=width;top=117 end
        local used
        plan.collected.ribbons,used=place(ribbon_items,0,award_right,top,68,23,6,'collected_ribbons')
        if used>0 then top=top+used+8 end
        plan.collected.medals,used=place(medal_items,0,award_right,top,31,35,6,'collected_medals')
        if used>0 then top=top+used+8 end
        plan.collected.hits,used=place(hit_items,0,award_right,top,31,29,3,'collected_hits')
        if used>0 then top=top+used+8 end
        plan.top_height=math.max(109,top>0 and top-8 or 0)
        local metric_x=width-metric_width
        local kd_text=stats.kd_text or (tostring(stats.kd)..'['..tostring(stats.history_kd)..']')
        -- The native HUD font lacks full-width brackets and arrow glyphs.
        -- Keep the already-computed comparison; render its sign as native art.
        local trend=stats.history_trend
        if trend~=1 and trend~=-1 and trend~=0 then
            local arrow=stats.history_arrow or kd_text
            trend=arrow:find('↑',1,true) and 1 or (arrow:find('↓',1,true) and -1 or 0)
        end
        kd_text=kd_text:gsub('［','['):gsub('］',']'):gsub('↑',''):gsub('↓','')
        local values={kills=stats.kills,bill=stats.bill_text or stats.bill,shots=stats.shots,kd=kd_text}
        for _,row in ipairs({{'kills','U01',0,39,31},{'bill','U02',42,20,12},
            {'shots','U03',65,20,13},{'kd','U04',88,20,11}}) do
            local key,id,y,h,size=row[1],row[2],row[3],row[4],row[5]
            if key~='bill' or stats.bill_visible~=false then
            plan.metrics[#plan.metrics+1]={key=key,id=id,x=metric_x,y=y,width=metric_width,height=h,
                icon_x=metric_x+13-(key=='kills' and 13 or 5.25),
                icon_y=y+(h-(key=='kills' and 29 or 10.5))/2,icon_width=key=='kills' and 26 or 10.5,
                icon_height=key=='kills' and 29 or 10.5,text=values[key] or '--',
                text_x=width,text_y=y+(h-size)/2,font_size=size}
            if key=='kd' and trend~=0 and kd_text:sub(-1)==']' then
                local metric=plan.metrics[#plan.metrics]
                metric.history_trend=trend
                metric.text_body,metric.text_suffix=kd_text:sub(1,-2),']'
                metric.body_text_x,metric.suffix_text_x=width-18,width
                metric.trend={id=trend==1 and 'I01' or 'I02',x=width-16,
                    y=y+(h-4)/2,width=8,height=4}
            end
            end
        end
        local side_groups={hits={},ribbons={},medals={}}
        for _,item in ipairs(awards.items or {}) do
            local group=item.side_icon and 'hits' or (item.kind=='medal' and 'medals' or 'ribbons')
            side_groups[group][#side_groups[group]+1]=item
        end
        plan.side_top=plan.top_height+8
        local side_y=plan.side_top
        for _,row in ipairs({{'hits',31,29,3},{'ribbons',78,31,6},{'medals',104,53,6}}) do
            local key=row[1]
            if key~='hits' or hit_position=='right'then
                plan.side[key],used=place(side_groups[key],0,width,side_y,row[2],row[3],row[4],'side_'..key)
                if used>0 then side_y=side_y+used+8 end
            end
        end
        local center_hit_height=0
        if hit_position=='center'then
            plan.center_hits,center_hit_height=place(side_groups.hits,0,width,0,31,29,3,'center_hits')
        end
        plan.center_hit_width=#plan.center_hits>0 and width-plan.center_hits[1].x or 0
        plan.center_hit_height=center_hit_height
        local combat_height=side_y>plan.side_top and side_y-plan.side_top-8 or 0
        local charge_items=type(charges)=='table' and charges.items or {}
        local charge_top=plan.side_top+combat_height+(combat_height>0 and #charge_items>0 and 6 or 0)
        for index,item in ipairs(charge_items) do
            local center=charge_position=='center'
            local top=center and (center_hit_height>0 and center_hit_height+6 or 0) or charge_top
            if charge_position~='hidden'then
                local target=center and plan.center_charges or plan.charges
                target[index]={id=item.id,name=item.name,text=item.text,amount_text=item.amount_text,
                    x=0,y=top+(index-1)*24,width=width,height=22,text_x=center and width/2 or width,
                    text_y=top+(index-1)*24,font_size=11}
            end
        end
        local actual_side_height=combat_height+#plan.charges*24+(combat_height>0 and #plan.charges>0 and 6 or 0)
        local deadline=awards.deadline
        if type(charges)=='table' and finite(charges.deadline) then deadline=math.max(deadline or 0,charges.deadline) end
        if actual_side_height==0 then peak_side_height=0 else peak_side_height=math.max(peak_side_height,actual_side_height) end
        previous_deadline=deadline
        plan.side_height,plan.side_content_height=peak_side_height,actual_side_height
        plan.height=plan.top_height+(peak_side_height>0 and 8+peak_side_height or 0)
        for _,group in ipairs({'ribbons','medals','hits'}) do append(plan.glyphs,plan.collected[group]) end
        for _,group in ipairs({'hits','ribbons','medals'}) do append(plan.glyphs,plan.side[group]) end
        append(plan.glyphs,plan.center_hits)
        previous={stats=stats,awards=awards,map=map_open,width=width,charges=charges,sequence=current_sequence,
            hit_position=hit_position,charge_position=charge_position}
        cached=plan
        return plan
    end
    return api
end
