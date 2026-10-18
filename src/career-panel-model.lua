-- A pure, native-parent-local collection layout. It neither draws nor reads
-- the game; caller must verify the personal Career page and map the pointer.
local CONDITIONS={
    air='击杀 1 个空中敌方单位。',
    heavy='击杀 1 个重型敌方单位。',
    giant='击杀 1 个巨型敌方单位。',
    demolition='摧毁敌方飞船或机器人构造者；普通虫洞实际封闭并与本人爆炸关联，竞争爆炸仅作为证据保留。',
    melee='近战击杀 1 个敌方单位。',
    ignite='使用火焰或燃烧伤害击杀 1 个敌方单位。',
    firepower='一局中每累计射击 1,000 发，获得 1 次。',
    poison='使用毒气伤害击杀 1 个敌方单位。',
    level_not_problem='战斗中使用 2 级或以下穿甲的武器，击杀 1 个重型或巨型敌方单位。',
    tyranny_speed_bump='一场战斗中碾压击杀 100 个敌方单位。',
    recon='成为游戏发现通知指认的支线任务或敌方据点发现者。',
    hit_total='获得 1 次游戏记录的命中。',
    hit_ricochet='本人弹丸命中敌方装甲并发生实际反弹。',
    hit_blocked='本人弹丸命中敌方单位，但未击穿装甲。',
    hit_penetration='本人弹丸击穿敌方装甲，造成部分装甲倍率伤害。',
    hit_full_penetration='本人弹丸击穿敌方装甲，获得完整装甲倍率。',
    democracy_harvester='一命中每击杀 100 个轻型敌方单位，获得 1 次。',
    double_giant='极短时间内连续击杀两只巨型单位',
    killstreak='一段连杀中每累计击杀 5 个敌方单位，获得 1 次；相邻击杀间隔不超过 5 秒，阵亡重置。',
    crush='载具车体来源每击杀1个敌方单位，获得1次。',
    democracy_star='一段连杀击杀 50 个敌人（已确认机器人 30 个）；相邻击杀间隔不超过 5 秒，阵亡重置。',
    super_democracy_star='一段连杀击杀 80 个敌人（已确认机器人 50 个）；相邻击杀间隔不超过 5 秒，阵亡重置。',
    supreme_democracy_star='一段连杀击杀 100 个敌人（已确认机器人 60 个）；相邻击杀间隔不超过 5 秒，阵亡重置。',
    air_expert='一局击杀 36 个终结族、12 个机器人或 24 个光能者空中单位；按阵营分别累计。',
    democracy_undying='一命累计恢复 1,000 点生命值。',
    freedom_in_veins='一局累计恢复 5,000 点生命值。',
    foreign_parking='一局摧毁 10 艘光能族飞船。',
    fragrant='累计使用火焰或燃烧伤害击杀 500 个敌方单位。',
}
local function number(value)
    return type(value)=='number' and value==value and value>-math.huge and value<math.huge
end
local function total(records,icon)
    local group=icon.kind=='medal' and 'medals' or 'ribbons'
    local values=records and records.totals and records.totals[group]
    local value=type(values)=='table' and values[icon.key] or nil
    return number(value) and value>0 and value%1==0 and value or nil
end
return function(icons,conditions,create_combat,localize)
    assert(type(icons)=='table','career panel needs award definitions')
    local t=type(localize)=='function' and localize or function(value)return value end
    local api={version=5}
    local combat=type(create_combat)=='function' and create_combat(t) or nil
    local history_source,history_revision,ordered
    local function history_entries(history)
        history=type(history)=='table' and history or {}
        local source=history.entries or {}
        if ordered and source==history_source and history.revision==history_revision then return ordered end
        ordered={}
        for _,entry in ipairs(source)do
            if type(entry)=='table' and number(entry.sequence) then ordered[#ordered+1]=entry end
        end
        -- Persisted entries are a read-only view. Sort only our reference list.
        table.sort(ordered,function(a,b)return a.sequence>b.sequence end)
        history_source,history_revision=source,history.revision
        return ordered
    end
    local function count(value)
        return number(value) and value>=0 and value%1==0 and string.format('%.0f',value) or '--'
    end
    local function ratio(value)
        if type(value)~='table' or count(value.kills)=='--' or count(value.deaths)=='--' then return nil end
        return value.kills/math.max(1,value.deaths)
    end
    local function current_kd(entry)
        local value=ratio(entry)
        if not value then return '--' end
        return entry.deaths==0 and count(entry.kills)..'/0' or string.format('%.2f',value)
    end
    local function fit_text(text,width)
        text=t(text)
        -- Native labels are single lines. Conservatively reserve 14 px for CJK
        -- and 8 px for ASCII; truncation never splits a UTF-8 character.
        local parts,used={},0
        for char in tostring(text):gmatch('[%z\1-\127\194-\244][\128-\191]*')do
            local size=#char==1 and 8 or 14
            if used+size>width then
                while #parts>0 and used+16>width do
                    used=used-(#parts[#parts]==1 and 8 or 14);parts[#parts]=nil
                end
                return table.concat(parts)..(width>=16 and '..' or '')
            end
            parts[#parts+1]=char;used=used+size
        end
        return table.concat(parts)
    end
    local function award_sum(entry,kind)
        local key=kind=='medal' and 'medals' or 'ribbons'
        local values=type(entry[key])=='table' and entry[key] or {}
        local overflow=entry.overflow and entry.overflow[key]
        local sum=0
        for _,icon in ipairs(icons)do
            if icon.kind==kind then
                if overflow and overflow[icon.key] then return nil end
                local value=values[icon.key]
                if number(value) and value>0 and value%1==0 then
                    if sum>9007199254740991-value then return nil end
                    sum=sum+value
                end
            end
        end
        return sum
    end
    local SELECTED={0.96,0.96,0.96,1} -- Native Career selection uses white on grey.
    local INK={0.93,0.93,0.93,1}
    local MUTED={0.66,0.66,0.66,1}
    local GREEN={0.72,0.81,0.69,1}
    local RED={0.89,0.64,0.58,1}
    local LINE={0.65,0.65,0.65,0.30}
    local function signed(value)return number(value) and string.format('%+.4f',value) or '暂无对比'end
    local function tone(value)return (not number(value) or value==0) and MUTED or (value<0 and RED or GREEN)end
    local function smooth_points(points,steps)
        -- Shape-preserving Hermite interpolation goes through the observations.
        -- Local extrema stay local: never invent a higher/lower KD between them.
        local a={}
        for _,p in ipairs(points)do
            if a[#a]and p.x==a[#a].x then a[#a]={x=p.x,y=p.y}
            else a[#a+1]={x=p.x,y=p.y}end
        end
        if #a<2 then return a end
        local d,m={},{}
        for i=1,#a-1 do d[i]=(a[i+1].y-a[i].y)/(a[i+1].x-a[i].x)end
        m[1],m[#a]=d[1],d[#a-1]
        for i=2,#a-1 do
            if d[i-1]*d[i]<=0 then m[i]=0
            else
                local left,right=a[i].x-a[i-1].x,a[i+1].x-a[i].x
                local w1,w2=2*right+left,right+2*left
                m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i])
            end
        end
        for i=1,#a-1 do
            if d[i]==0 then m[i],m[i+1]=0,0
            else
                local left,right=m[i]/d[i],m[i+1]/d[i]
                local length=left*left+right*right
                if length>9 then local scale=3/math.sqrt(length);m[i],m[i+1]=scale*left*d[i],scale*right*d[i]end
            end
        end
        local out,segment={},1
        -- One sample per horizontal pixel keeps the native raster line thin.
        for i=0,steps do
            local x=a[1].x+(a[#a].x-a[1].x)*i/steps
            while segment<#a-1 and x>a[segment+1].x do segment=segment+1 end
            local first,last=a[segment],a[segment+1]
            local h=last.x-first.x;local t=(x-first.x)/h
            local t2,t3=t*t,t*t*t
            local y=(2*t3-3*t2+1)*first.y+(t3-2*t2+t)*h*m[segment]
                +(-2*t3+3*t2)*last.y+(t3-t2)*h*m[segment+1]
            out[#out+1]={x=x,y=math.max(math.min(first.y,last.y),math.min(math.max(first.y,last.y),y))}
        end
        out[1]={x=a[1].x,y=a[1].y};out[#out]={x=a[#a].x,y=a[#a].y}
        return out
    end
    local function aggregate(entries)
        local out={missions=#entries,kills=0,deaths=0,ribbons={},medals={},
            patriotic_bill={version=1,total_cents=0,recorded_missions=0,missing_missions=0,entries={}}}
        local bill_items={}
        for _,entry in ipairs(entries)do
            local source=entry.patriotic_bill;local bill=out.patriotic_bill
            if type(source)=='table'and source.version==1 and number(source.total_cents)and source.total_cents>=0 then
                bill.recorded_missions=bill.recorded_missions+1
                if bill.total_cents and bill.total_cents<=9007199254740991-source.total_cents then bill.total_cents=bill.total_cents+source.total_cents
                else bill.total_cents=nil;bill.overflow=true end
                for _,row in ipairs(source.entries or {})do
                    local key=row.key;local current=bill_items[key]
                    if not current then
                        if #bill.entries>=256 then key='other';current=bill_items[key]end
                        if not current then current={key=key,name=key=='other'and'其他已记录费用'or row.name,amount_cents=0}
                            bill_items[key]=current;bill.entries[#bill.entries+1]=current end
                    end
                    if current.amount_cents and current.amount_cents<=9007199254740991-row.amount_cents then current.amount_cents=current.amount_cents+row.amount_cents
                    else current.amount_cents=nil;bill.overflow=true end
                end
            else bill.missing_missions=bill.missing_missions+1 end
            for _,key in ipairs({'kills','deaths'})do
                if count(entry[key])=='--' or not out[key] or out[key]>9007199254740991-entry[key] then out[key]=nil
                else out[key]=out[key]+entry[key]end
            end
            for _,key in ipairs({'ribbons','medals'})do
                for id,value in pairs(entry[key] or {})do
                    if number(value) and value>0 and value%1==0 then
                        local previous=out[key][id] or 0
                        out.overflow=out.overflow or {ribbons={},medals={}}
                        if previous>9007199254740991-value then out.overflow[key][id]=true
                        elseif not out.overflow[key][id]then out[key][id]=previous+value end
                    end
                end
            end
        end
        table.sort(out.patriotic_bill.entries,function(a,b)
            local av,bv=a.amount_cents or -1,b.amount_cents or -1
            return av>bv or(av==bv and a.key<b.key)
        end)
        return out
    end
    function api:layout(records,context)
        context=context or {}
        if context.page_visible~=true or context.personal~=true then
            return {shown=false,items={},sections={},tooltip=nil,decorations={},header_texts={},nav_controls={}}
        end
        if combat and (context.view=='deaths' or context.view=='weapons' or context.view=='enemies')then
            return combat:layout(context)
        end
        local legacy=type(context.legacy_crush)=='table'and context.legacy_crush or {}
        local legacy_total=number(legacy.total)and legacy.total>0 and legacy.total%1==0 and legacy.total or 0
        local function with_crush(values,added)
            if not(number(added)and added>0 and added%1==0)then return values end
            values=type(values)=='table'and values or {}
            local previous=number(values.crush)and values.crush>=0 and values.crush or 0
            if previous>9007199254740991-added then return values end
            local out={};for id,value in pairs(values)do out[id]=value end
            out.crush=previous+added;return out
        end
        if legacy_total>0 then
            local totals=records and records.totals or {}
            records={totals={ribbons=with_crush(totals.ribbons,legacy_total),medals=totals.medals},derived_crush=legacy_total}
        end
        local width,height=context.width,context.height
        assert(number(width) and width>=120 and width<=2048
            and number(height) and height>=80 and height<=2160,'invalid career panel bounds')
        local billing=context.billing_enabled==true
        local view=context.view=='history'and'history'or(context.view=='bill'and billing and'bill'or'collection')
        local result={shown=true,view=view,width=width,height=height,items={},sections={},decorations={},
            header_texts={},nav_controls={},scroll=0,max_scroll=0}
        local pad=math.min(14,width/20)
        local inner=width-pad*2
        local compact=height<500
        local pointer=context.pointer
        local function inside(x,y,w,h)
            return type(pointer)=='table' and number(pointer.x) and number(pointer.y)
                and pointer.x>=x and pointer.x<x+w and pointer.y>=y and pointer.y<y+h
        end
        local function fits(x,y,w,h,top,bottom)
            return x>=0 and w>0 and h>0 and x+w<=width+0.001 and y>=(top or 0) and y+h<=(bottom or height)+0.001
        end
        local function deco(id,x,y,w,h,fill,border,top,bottom,accent)
            if #result.decorations>=48 or not fits(x,y,w,h,top,bottom)then return end
            result.decorations[#result.decorations+1]={id=id,x=x,y=y,width=w,height=h,fill=fill,border=border,accent=accent}
        end
        local function header(id,text,x,y,w,top,bottom,style)
            style=style or {};x=x or pad;w=w or width-pad-x
            local h=style.height or 18;local size=style.font_size or 12
            if #result.header_texts>=32 or not fits(x,y,w,h,top,bottom)then return end
            result.header_texts[#result.header_texts+1]={id=id,text=fit_text(text,w*14/size),x=x,y=y,width=w,height=h,
                font_size=size,colour=style.colour or INK,align=style.align or 0}
        end
        local function control(id,text,x,y,w,h,action,options,top,bottom)
            options=options or {}
            if #result.nav_controls>=24 or not fits(x,y,w,h,top,bottom)then return end
            local enabled=options.enabled~=false
            local hovered=enabled and inside(x,y,w,h)
            local kind=options.kind or 'button'
            local active=options.active==true
            local fill=active and {0.24,0.24,0.24,0.72} or {0.07,0.07,0.07,0.55}
            if hovered then fill={0.29,0.29,0.29,0.80}end
            if options.plain~=true or hovered then
                deco('button_'..id,x,y,w,h,fill,options.plain~=true and(active and SELECTED or LINE)or nil,top,bottom,active and kind=='match' and SELECTED or nil)
            end
            local align=options.align or 0.5
            local inset=options.inset or 8
            local size=options.font_size or 12
            result.nav_controls[#result.nav_controls+1]={id=id,text=fit_text(text,math.max(0,w-inset*2)*14/size),
                x=x,y=y,width=w,height=h,enabled=enabled,active=active,hovered=hovered,kind=kind,
                action=action or id,sequence=options.sequence,period=options.period,align=align,font_size=size,
                text_x=align==0.5 and x+w/2 or x+inset,text_y=y+(options.text_offset_y or (h-size)/2),
                colour=active and SELECTED or (enabled and INK or MUTED)}
        end
        local function date(at,unknown)
            if number(at) and type(context.format_time)=='function' then
                local ok,value=pcall(context.format_time,at)
                if ok and type(value)=='string' and value~='' then return value end
            end
            return unknown or '时间未记录'
        end
        local function money(cents)
            if not number(cents)or cents<0 or cents%1~=0 then return '未记录'end
            if type(context.format_money)=='function'then
                local ok,text,code=pcall(context.format_money,cents)
                if ok and type(text)=='string'and text~=''then
                    return text..(type(code)=='string'and code~=''and(' '..code)or'')
                end
            end
            return string.format('%.2f MC',cents/100)
        end
        local function acquired(source,kind)
            local entries={}
            for _,icon in ipairs(icons)do
                local value=icon.kind==kind and total(source,icon)
                if value then entries[#entries+1]={icon=icon,count=value,derived=icon.key=='crush'and source.derived_crush or nil}end
            end
            return entries
        end
        local function item(icon,value,x,y,w,h,derived)
            local condition=(conditions and conditions[icon.key])or icon.condition or CONDITIONS[icon.key]
            assert(condition,'missing career award condition: '..icon.key)
            if number(derived)and derived>0 then
                condition=condition..' 其中 '..count(derived)..' 次按旧局已保存的载具车体来源展示。'
            end
            return {id=icon.id,key=icon.key,kind=icon.kind,name=t(icon.name),count=value,condition=t(condition),
                x=x,y=y,width=w,height=h,colour=icon.colour,visible=true,derived_crush=derived}
        end
        local function finish()
            for _,award in ipairs(result.items)do
                if inside(award.x,award.y,award.width,award.height)then
                    result.tooltip={id=award.id,key=award.key,name=award.name,count=award.count,condition=award.condition,
                        anchor={x=award.x,y=award.y,width=award.width,height=award.height}}
                end
            end
            return result
        end
        deco('panel',0,0,width,height,{0.075,0.075,0.075,0.82},LINE)
        local tab_y,tab_h=compact and 32 or 44,compact and 28 or 36
        local bill_entry=billing and view=='collection'and height>=180
        local bottom=math.max(0,height-(bill_entry and 76 or 40))
        local all=(view=='history'or view=='bill'or bill_entry) and history_entries(context.history) or {}
        local period=context.period
        if period~='24h' and period~='7d' and period~='30d' then period='all'end
        local label=period=='all' and '全部' or (period=='24h' and '24小时' or (period=='7d' and '7天' or '30天'))
        local summary
        if view=='history'or view=='bill'or bill_entry then
            if period=='all'then summary=context.summary and context.summary.all
            else for _,value in ipairs(context.summary and context.summary.periods or {})do
                if value.key==period then summary=value;break end
            end end
        end
        local entries={}
        for _,entry in ipairs(all)do
            local dated=(entry.status=='ended' or entry.status=='interrupted') and number(entry.ended_at)
            if period=='all' or (summary and dated and number(summary.from_at) and number(summary.to_at)
                and entry.ended_at>=summary.from_at and entry.ended_at<=summary.to_at)then entries[#entries+1]=entry end
        end
        if (view=='history'or view=='bill'or bill_entry) and period=='all' and not summary then summary=aggregate(entries)end
        local period_derived=0
        if view=='history'then
            for _,entry in ipairs(entries)do
                local added=type(legacy.by_sequence)=='table'and legacy.by_sequence[entry.sequence]
                if entry.ribbons and entry.ribbons.crush==nil and number(added)and added>0 then period_derived=period_derived+added end
            end
            if summary and period_derived>0 then
                local out={};for id,value in pairs(summary)do out[id]=value end
                out.ribbons=with_crush(summary.ribbons,period_derived);summary=out
            end
        end
        result.period,result.history_count,result.total_history_count=period,#entries,#all
        local limit=context.history and context.history.limit
        result.capacity_full=number(limit) and limit>0 and #all>=limit or false
        local expanded=context.expanded_sequence
        if expanded==nil then expanded=entries[1] and entries[1].sequence or false end
        local exists=false
        for _,entry in ipairs(entries)do if entry.sequence==expanded then exists=true;break end end
        if not exists then expanded=false end
        local summary_expanded=view=='history' and summary~=nil and context.summary_expanded==true
        if summary_expanded then expanded=false end
        result.expanded_sequence,result.summary_expanded=expanded,summary_expanded
        local expanded_bill=billing and expanded and context.expanded_bill_sequence==expanded and expanded or false
        result.expanded_bill_sequence=expanded_bill
        local columns=math.max(1,math.floor((inner+8)/120))
        local gap,cell_width=8,(inner-(columns-1)*8)/columns
        local blocks,y,total_items={},0,0
        local function block(kind,data,h)
            blocks[#blocks+1]={kind=kind,data=data,y=y,height=h};y=y+h
        end
        local function grid(source)
            local any=false
            for _,kind in ipairs({'medal','ribbon'})do
                local awards=acquired(source,kind)
                if #awards>0 then
                    any=true;block('section',kind=='medal' and '成就' or '战果',24)
                    local h=kind=='medal' and 84 or 64
                    for first=1,#awards,columns do
                        local row={}
                        for at=first,math.min(first+columns-1,#awards)do
                            local v=awards[at]
                            row[#row+1]=item(v.icon,v.count,pad+(at-first)*(cell_width+gap),0,cell_width,h-gap,v.derived)
                            total_items=total_items+1
                        end
                        block('icons',row,h)
                    end
                    y=y+gap
                end
            end
            return any
        end
        local top
        if summary_expanded then
            result.modal=true
            header('summary_title',label..' · 战果',pad,16,inner-76,nil,nil,{height=24,font_size=17,colour=SELECTED})
            control('close_summary','收起',width-pad-68,10,68,32,'toggle_summary',{kind='close'})
            top=58
            if not grid({totals={ribbons=summary.ribbons,medals=summary.medals},derived_crush=period_derived})then block('note','这个时段没有已保存的战果。',28)end
        else
            header('panel_title','战果档案',pad,compact and 7 or 12,inner,nil,nil,{height=24,font_size=compact and 16 or 18})
            local tabs=combat and {{'collection','战果'},{'history','对局'},{'deaths','死因'},{'weapons','武器'},{'enemies','敌人'}}
                or {{'collection','累计战果'},{'history','历史对局'}}
            if billing then tabs[#tabs+1]={'bill','账单'}end
            local tab_gap=combat and 4 or 6
            local tw=(inner-tab_gap*(#tabs-1))/#tabs
            for index,tab in ipairs(tabs)do
                control('tab_'..tab[1],tab[2],pad+(index-1)*(tw+tab_gap),tab_y,tw,tab_h,nil,{kind='tab',active=view==tab[1]})
            end
            if view=='bill'then
                local py=compact and 68 or 90
                local pw=(inner-12)/4
                for index,value in ipairs({{'all','全部'},{'24h','24小时'},{'7d','7天'},{'30d','30天'}})do
                    control('period_'..value[1],value[2],pad+(index-1)*(pw+4),py,pw,compact and 26 or 30,'period',
                        {kind='period',period=value[1],active=period==value[1],font_size=12,inset=2})
                end
                local bill=summary and summary.patriotic_bill
                local recorded=bill and bill.recorded_missions or 0
                local missing=bill and bill.missing_missions or #entries
                local amount=recorded>0 and money(bill.total_cents)or'未记录'
                header('bill_title',period=='all'and'累计爱国账单'or(label..' · 爱国账单'),pad,py+42,inner,nil,nil,{height=22,font_size=16})
                header('bill_total',amount,pad,py+70,inner,nil,nil,{height=28,font_size=24})
                header('bill_coverage','已记录 '..count(recorded)..' 场 · 未记录 '..count(missing)..' 场',pad,py+105,inner,nil,nil,{height=18,font_size=11,colour=MUTED})
                top=py+140
                for index,row in ipairs(bill and bill.entries or {})do block('bill_row',{index=index,name=row.name,amount_cents=row.amount_cents},36)end
                if recorded==0 then block('bill_note','暂无已保存的账单。旧对局缺少金额时保留未记录。',44)end
            elseif view=='history'then
                local py=compact and 68 or 90
                local pw=(inner-12)/4
                for index,value in ipairs({{'all','全部'},{'24h','24小时'},{'7d','7天'},{'30d','30天'}})do
                    control('period_'..value[1],value[2],pad+(index-1)*(pw+4),py,pw,compact and 26 or 30,'period',
                        {kind='period',period=value[1],active=period==value[1],font_size=12,inset=2})
                end
                local career=summary and summary.career or {}
                local current=career.current_kd
                if not number(current)then current=context.summary and context.summary.current and context.summary.current.kd end
                local current_text=number(current) and string.format('%.2f',current) or '--'
                if compact then
                    header('period_career','生涯 KD '..current_text,pad,100,inner,nil,nil,{height=18,font_size=12})
                    top=124
                else
                    deco('overview',pad,130,inner,158,{0.035,0.035,0.035,0.68},LINE)
                    header('period_career','生涯 KD · '..(period=='all' and '记录基准' or label..'对比'),pad+12,139,inner-24,nil,nil,{height=16,font_size=11,colour=MUTED})
                    header('career_current',current_text,pad+12,159,math.min(125,inner-24),nil,nil,{height=30,font_size=26})
                    local delta_width=inner-153
                    if inner>=350 and type(career.baseline)=='table' and type(career.series)=='table' and #career.series>1 then
                        delta_width=inner-257 -- Keep an 8 px gap before the 96 px trend plot.
                    end
                    if inner>205 then header('career_delta',signed(career.delta),pad+141,172,delta_width,nil,nil,{height=17,font_size=12,colour=tone(career.delta)})end
                    local base=career.baseline
                    local base_text=type(base)=='table' and number(base.at) and ((career.partial and '记录起点 ' or '基准 ')..date(base.at)..'  '..(number(base.kd) and string.format('%.4f',base.kd) or '--')) or '缺少该时点的生涯记录'
                    header('period_baseline',base_text,pad+12,194,inner-24,nil,nil,{height=15,font_size=10,colour=MUTED})
                    deco('stats_rule',pad+1,214,inner-2,1,LINE)
                    local values={count(summary and summary.missions),count(summary and summary.kills),count(summary and summary.deaths),summary and summary.missions~=0 and current_kd(summary) or '--'}
                    for index,name in ipairs({'场对局','击杀','阵亡','时段 KD'})do
                        local sx=pad+(index-1)*inner/4
                        header('stat_value_'..index,values[index],sx,220,inner/4,nil,nil,{height=20,font_size=16,align=0.5})
                        header('stat_label_'..index,name,sx,242,inner/4,nil,nil,{height=14,font_size=10,colour=MUTED,align=0.5})
                        if index>1 then deco('stat_rule_'..index,sx,221,1,32,LINE)end
                    end
                    control('summary_toggle','查看'..label..'战果  ·  战果 '..count(summary and award_sum(summary,'ribbon'))..'  成就 '..count(summary and award_sum(summary,'medal')),
                        pad,260,inner,28,'toggle_summary',{kind='summary',enabled=summary~=nil,font_size=11,align=0,inset=12})
                    local series=career.series
                    if type(base)=='table' and type(series)=='table' and #series>1 and inner>=350 then
                        local min_kd,max_kd,first_at,last_at=math.huge,-math.huge,nil,nil
                        local valid={}
                        for _,point in ipairs(series)do
                            if type(point)=='table' and number(point.at) and number(point.kd)then
                                valid[#valid+1]=point;min_kd=math.min(min_kd,point.kd);max_kd=math.max(max_kd,point.kd)
                                first_at=first_at and math.min(first_at,point.at) or point.at;last_at=last_at and math.max(last_at,point.at) or point.at
                            end
                        end
                        if #valid>1 then
                            local sw,sh=96,38
                            result.sparkline={x=width-pad-108,y=149,width=sw,height=sh,points={}}
                            local points=result.sparkline.points
                            for index=1,math.min(24,#valid)do
                                local at=math.floor((index-1)*(#valid-1)/(math.min(24,#valid)-1))+1
                                local point=valid[at]
                                points[#points+1]={x=(point.at-first_at)/math.max(1,last_at-first_at)*sw,
                                    y=sh-(point.kd-min_kd+0.025)/math.max(0.05,max_kd-min_kd+0.05)*sh}
                            end
                            result.sparkline.samples=smooth_points(points,sw)
                            result.sparkline.interpolation='monotone_cubic'
                        end
                    end
                    header('list_count',label..' · '..count(#entries)..' 场',pad,299,inner/2,nil,nil,{height=17,font_size=11,colour=MUTED})
                    header('list_hint','点击展开详情',pad+inner/2,299,inner/2,nil,nil,{height=17,font_size=11,colour=MUTED,align=1})
                    top=322
                end
                local available=math.max(0,bottom-top)
                local row_height=math.max(66,math.ceil(available/6))
                local detail_height=math.max(26,math.ceil(available/6))
                local function combat_rows(entry,lane,title)
                    local queried
                    if type(context.combat_query)=='function'then
                        local ok,value=pcall(context.combat_query,lane,{sequence=entry.sequence,period='all'})
                        if ok and type(value)=='table'and type(value.rows)=='table'then queried=value.rows end
                    end
                    -- Old history can carry source totals without the new combat
                    -- record store. Use only the saved fields, never the held gun.
                    if not queried or #queried==0 then
                        queried={}
                        local raw=lane=='weapons'and entry.weapon_stats or entry.unit_kills
                        local observed,unknown=0,0
                        for id,row in pairs(type(raw)=='table'and raw or {})do
                            local n=type(row)=='table'and(row.kills or row.count)
                            if number(n)and n>0 then
                                observed=observed+n
                                local name=row.name_zh or row.name
                                local missing=type(name)~='string'or name==''
                                    or name:find('^未知')or name:find('^未记录')or name=='来源未知'
                                    or name:find('^entity/v1/unresolved/')or name:find('^0x[%x]+$')
                                    or #name==16 and not name:find('[^%x]')
                                if missing then unknown=unknown+n
                                else queried[#queried+1]={id=id,name=name,kills=n}end
                            end
                        end
                        if number(entry.kills)then unknown=unknown+math.max(0,entry.kills-observed)end
                        if unknown>0 then queried[#queried+1]={id='unknown',name='未知',kills=unknown,known=false}end
                        table.sort(queried,function(a,b)
                            if(a.id=='unknown')~=(b.id=='unknown')then return a.id~='unknown'end
                            return a.kills>b.kills or(a.kills==b.kills and a.id<b.id)
                        end)
                    end
                    block('combat_heading',{lane=lane,text=title},24)
                    if #queried==0 then block('combat_note',{lane=lane,text='本场尚无已保存的明细。'},26)
                    else for index,row in ipairs(queried)do
                        block('combat_row',{lane=lane,index=index,name=row.name or row.id,kills=row.kills},detail_height)
                    end end
                    y=y+8
                end
                for _,entry in ipairs(entries)do
                    block('match',entry,row_height)
                    if entry.sequence==expanded then
                        block('career',entry,42)
                        combat_rows(entry,'weapons','本场武器与战备击杀')
                        combat_rows(entry,'enemies','本场击杀的敌人')
                        local derived=entry.ribbons.crush==nil and type(legacy.by_sequence)=='table'and legacy.by_sequence[entry.sequence]or nil
                        if not grid({totals={ribbons=with_crush(entry.ribbons,derived),medals=entry.medals},derived_crush=derived})then block('note','本场没有保存的战果或成就。',28)end
                        y=y+8
                        if billing then
                            block('bill_total',{sequence=entry.sequence,bill=entry.patriotic_bill},54)
                            if expanded_bill==entry.sequence then
                                for index,row in ipairs(entry.patriotic_bill and entry.patriotic_bill.entries or {})do
                                    block('bill_row',{index=index,name=row.name,amount_cents=row.amount_cents},36)
                                end
                            end
                            y=y+8
                        end
                    end
                end
            else
                top=compact and 72 or 94
                local amount=0
                for _,icon in ipairs(icons)do if total(records,icon)then amount=amount+1 end end
                header('collection_total',count(amount)..' 种已获得战果',pad,top,inner,nil,nil,{height=24,font_size=17})
                top=top+38
                local pages={{items={},sections={}}}
                local page,cy=pages[1],top
                for _,kind in ipairs({'medal','ribbon'})do
                    local awards=acquired(records,kind)
                    if #awards>0 then
                        local row_h=kind=='medal' and 84 or 64
                        local section_page
                        for first=1,#awards,columns do
                            local title=section_page~=page and 24 or 0
                            if cy+title+row_h-gap>bottom and #page.items>0 then
                                page={items={},sections={}};pages[#pages+1]=page;cy=top;title=24
                            end
                            if title>0 then page.sections[#page.sections+1]={name=t(kind=='medal' and '成就' or '战果'),x=pad,y=cy,width=inner,height=20};cy=cy+24;section_page=page end
                            for at=first,math.min(first+columns-1,#awards)do
                                local value=awards[at]
                                page.items[#page.items+1]=item(value.icon,value.count,pad+(at-first)*(cell_width+gap),cy,cell_width,row_h-gap,value.derived)
                                total_items=total_items+1
                            end
                            cy=cy+row_h
                        end
                        cy=cy+gap
                    end
                end
                result.award_page_count=#pages
                result.award_page=math.max(1,math.min(#pages,math.floor(number(context.award_page) and context.award_page or 1)))
                for _,v in ipairs(pages[result.award_page].items)do if fits(v.x,v.y,v.width,v.height,top,bottom)then result.items[#result.items+1]=v end end
                for _,v in ipairs(pages[result.award_page].sections)do if fits(v.x,v.y,v.width,v.height,top,bottom)then result.sections[#result.sections+1]=v end end
                result.total_items,result.content_height=total_items,cy
                result.empty,result.empty_y,result.empty_text=total_items==0 and top+20<=bottom,top,t('暂无战果记录')
                if bill_entry then
                    local bill=summary and summary.patriotic_bill
                    local amount=bill and (bill.recorded_missions or 0)>0 and money(bill.total_cents)or'未记录'
                    control('collection_bill','爱国账单：'..amount,pad,height-69,inner,30,'tab_bill',
                        {kind='bill_entry',plain=true,align=0,inset=0,font_size=13})
                end
                if #pages>1 then
                    control('awards_previous','上一页',pad,height-32,82,26,nil,{enabled=result.award_page>1,kind='scroll'})
                    control('awards_next','下一页',width-pad-82,height-32,82,26,nil,{enabled=result.award_page<#pages,kind='scroll'})
                    header('award_page',string.format('%d / %d',result.award_page,#pages),pad+90,height-29,inner-180,nil,nil,{height=20,font_size=11,align=0.5})
                else header('help','悬停图案，查看获取条件。',pad,height-28,inner,nil,nil,{height=18,font_size=10,colour=MUTED})end
                return finish()
            end
        end
        top=math.min(top,bottom)
        result.list_top,result.list_bottom=top,bottom
        local available=math.max(0,bottom-top)
        result.total_items,result.content_height=total_items,y
        result.max_scroll=math.max(0,y-available)
        result.scroll=math.max(0,math.min(result.max_scroll,number(context.scroll) and context.scroll or 0))
        local row_slot=0
        for _,entry in ipairs(blocks)do
            local at=top+entry.y-result.scroll
            local value=entry.data
            if entry.kind=='match' and row_slot<6 and fits(pad,at,inner,entry.height,top,bottom)then
                row_slot=row_slot+1
                local active=value.sequence==expanded
                local title=(active and '- ' or '+ ')..date(value.ended_at or value.started_at)..'  #'..count(value.sequence)
                control('history_row'..row_slot,title,pad,at,inner,entry.height-6,'toggle_match',
                    {kind='match',active=active,sequence=value.sequence,align=0,inset=12,text_offset_y=10,font_size=12},top,bottom)
                local status=value.status=='active' and '当前记录' or (value.status=='interrupted' and '记录中断' or (value.end_reason=='returned_to_ship' and '中途返回' or '已结束'))
                if width>=350 then header('history_status'..row_slot,status,width-pad-92,at+11,80,top,bottom,{height=16,font_size=10,colour=active and SELECTED or MUTED,align=1})end
                header('history_stats'..row_slot,'击杀 '..count(value.kills)..'   阵亡 '..count(value.deaths)..'   KD '..current_kd(value),
                    pad+12,at+34,inner-24,top,bottom,{height=20,font_size=13})
            elseif entry.kind=='career' and fits(pad,at,inner,entry.height,top,bottom)then
                local before,after=ratio(value.history_before),ratio(value.history_after)
                local delta=before and after and after-before or nil
                deco('match_detail',pad,at,inner,entry.height,{0.12,0.12,0.12,0.82},LINE,top,bottom)
                header('match_career','本场对生涯 KD 的影响',pad+12,at+4,inner-24,top,bottom,{height=16,font_size=11,colour=MUTED})
                header('match_delta',delta and signed(delta) or '基准未记录',pad+12,at+23,inner-24,top,bottom,{height=16,font_size=12,colour=tone(delta)})
            elseif entry.kind=='note'then
                header('empty_awards',value,pad+12,at,inner-24,top,bottom,{height=20,font_size=11,colour=MUTED})
            elseif entry.kind=='bill_total'and fits(pad,at,inner,entry.height,top,bottom)then
                local open=expanded_bill==value.sequence
                control('match_bill',(open and '- ' or '+ ')..'本场爱国账单',pad,at,inner,entry.height-3,'toggle_match_bill',
                    {kind='bill_entry',active=open,sequence=value.sequence,align=0,inset=12,text_offset_y=5,font_size=12},top,bottom)
                header('match_bill_total',money(value.bill and value.bill.total_cents),pad+12,at+28,inner-24,top,bottom,{height=20,font_size=15})
            elseif entry.kind=='bill_row'and fits(pad,at,inner,entry.height,top,bottom)then
                local amount_width=math.min(inner*.48,170)
                header('bill_item_name_'..value.index,value.name,pad+12,at+4,inner-amount_width-24,top,bottom,{height=20,font_size=12})
                header('bill_item_amount_'..value.index,money(value.amount_cents),width-pad-amount_width-8,at+4,amount_width,top,bottom,{height=20,font_size=12,align=1})
            elseif entry.kind=='bill_note'then
                header('bill_note',value,pad+12,at,inner-24,top,bottom,{height=20,font_size=11,colour=MUTED})
            elseif entry.kind=='combat_heading'then
                header('match_'..value.lane..'_title',value.text,pad+12,at,inner-24,top,bottom,{height=20,font_size=13})
            elseif entry.kind=='combat_note'then
                header('match_'..value.lane..'_empty',value.text,pad+12,at,inner-24,top,bottom,{height=20,font_size=11,colour=MUTED})
            elseif entry.kind=='combat_row'and fits(pad,at,inner,entry.height,top,bottom)then
                deco('match_'..value.lane..'_'..value.index,pad+8,at,inner-16,entry.height-3,{.075,.075,.075,.75},LINE,top,bottom)
                local inset=math.min(12,inner/8)
                local value_width=math.min(70,inner*.32)
                header('match_'..value.lane..'_name'..value.index,value.name,pad+inset,at+4,inner-value_width-inset*2,top,bottom,{height=18,font_size=12})
                header('match_'..value.lane..'_kills'..value.index,count(value.kills),width-pad-inset-value_width,at+4,value_width,top,bottom,{height=18,font_size=12,align=1})
            elseif entry.kind=='section' and #result.sections<2 and fits(pad,at,inner,20,top,bottom)then
                result.sections[#result.sections+1]={name=t(value),x=pad,y=at,width=inner,height=20}
            elseif entry.kind=='icons'then
                for _,icon in ipairs(value)do
                    icon.y=at
                    if fits(icon.x,at,icon.width,icon.height,top,bottom)then result.items[#result.items+1]=icon end
                end
            end
        end
        result.empty=view=='history'and #entries==0 and not summary_expanded and available>=20
        result.empty_y=top+8
        if result.empty_y+20>bottom then result.empty=false end
        result.empty_text=t(period=='all' and '暂无历史对局' or '该时段暂无已保存对局')
        if available>0 and result.max_scroll>0 then
            local track_h=available
            local thumb_h=math.max(18,track_h*available/math.max(1,y))
            local thumb_y=top+(track_h-thumb_h)*result.scroll/result.max_scroll
            deco('scroll_track',width-7,top,3,track_h,{0.05,0.05,0.05,0.6})
            deco('scroll_thumb',width-7,thumb_y,3,thumb_h,{0.62,0.62,0.62,0.9})
            header('help',view=='bill'and'滚轮浏览 · 仅汇总已保存的实际费用'or'滚轮浏览 · 悬停查看条件',pad,height-27,inner,nil,nil,{height=18,font_size=10,colour=MUTED,align=0.5})
        else
            header('help',view=='bill'and'仅汇总已保存的实际费用；未记录的旧局不补造金额。'or'已包含中途返回舰船的记录；悬停图案查看条件。',pad,height-28,inner,nil,nil,{height=18,font_size=10,colour=MUTED})
        end
        return finish()
    end
    return api
end
