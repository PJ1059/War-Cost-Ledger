-- Bounded, pure Career combat layout. Only ten ranking/recent rows, five
-- related records and one record's facts are constructed per page.
return function(localize)
    local t=type(localize)=='function' and localize or function(value)return value end
    local api={}
    local INK,MUTED,LINE,WHITE={.93,.93,.93,1},{.66,.66,.66,1},{.5,.5,.5,.35},{.96,.96,.96,1}
    local roles={{'all','全部分类'},{'primary','主武器'},{'secondary','副武器'},{'support','支援武器'},{'throwable','投掷物'},{'stratagem','战备'}}
    local categories={{'all','全部来源'},{'enemy','敌方单位'},{'player','队友'},{'self','自身'},{'environment','环境'},{'unknown','未知死因'}}
    local factions={{'all','全部阵营'},{'bugs','终结族'},{'bots','机器人'},{'illuminate','光能者'}}
    local sizes={{'all','全部体型'},{'轻型','轻型'},{'中型','中型'},{'中型精英','中型精英'},{'重型','重型'},{'巨型','巨型'},{'BOSS','BOSS'}}
    local function count(v)return type(v)=='number' and v>=0 and v%1==0 and string.format('%.0f',v)or'--'end
    local function str(v,fallback)return type(v)=='string' and v~='' and v or (fallback or '未记录')end
    local function unknown(row)return row.id=='unknown'or row.id=='legacy'or row.id=='unrecorded'or row.known==false end
    local function name(row,death)return unknown(row)and(death and'未知死因'or'未知')or str(row.name,death and'未知死因'or'未知')end
    local function source_name(value,fallback)
        if value==nil or value==''or value=='未知'or value=='未知来源'or value=='来源未知'or value=='未知敌人'
            or value=='未知单位'or value=='未能确认'or value=='未记录'then return fallback end
        return str(value,fallback)
    end
    local function associations(rows)
        local result,missing={},0
        for _,row in ipairs(type(rows)=='table'and rows or {})do
            if unknown(row)then
                local amount=row.kills or row.count
                if type(amount)=='number'and amount>=0 and amount%1==0 then missing=missing+amount end
            else result[#result+1]=row end
        end
        if missing>0 then result[#result+1]={id='unknown',name='未知',known=false,kills=missing}end
        return result
    end
    local function fit(value,width,size,raw)
        if not raw then value=t(value)end
        local out,used={},0
        for char in tostring(value):gmatch('[%z\1-\127\194-\244][\128-\191]*')do
            local n=(#char==1 and .56 or 1)*(size or 12)
            if used+n>width then return table.concat(out)..'..'end
            out[#out+1]=char;used=used+n
        end
        return table.concat(out)
    end
    local function page(rows,index,size)
        local last=math.max(1,math.ceil(#rows/size))
        local current=math.max(1,math.min(last,math.floor(tonumber(index)or 1)))
        return current,last,(current-1)*size+1,math.min(#rows,current*size)
    end
    function api:layout(context)
        local w,h=context.width,context.height
        local s=context.combat_state or {};local data=context.combat or {}
        local view=context.view;local death=view=='deaths'
        local r={shown=true,view=view,period=context.period,width=w,height=h,items={},sections={},
            header_texts={},nav_controls={},decorations={},scroll=0,max_scroll=0}
        local pad=math.min(14,w/20);local inner=w-2*pad
        local pointer=context.pointer
        local function fits(x,y,bw,bh,top,bottom)return x>=0 and bw>0 and bh>0 and x+bw<=w+.01 and y>=(top or 0)and y+bh<=(bottom or h)+.01 end
        local function deco(id,x,y,bw,bh,fill,border,top,bottom)
            if #r.decorations<48 and fits(x,y,bw,bh,top,bottom)then r.decorations[#r.decorations+1]={id=id,x=x,y=y,width=bw,height=bh,fill=fill,border=border}end
        end
        local function label(id,value,x,y,bw,size,muted,top,bottom,raw)
            local bh=size+5
            if #r.header_texts<48 and fits(x,y,bw,bh,top,bottom)then r.header_texts[#r.header_texts+1]={id=id,text=fit(value,bw-3,size,raw),x=x,y=y,width=bw,height=bh,font_size=size,colour=muted and MUTED or INK}end
        end
        local function control(id,value,x,y,bw,bh,action,extra,top,bottom)
            if #r.nav_controls>=32 or not fits(x,y,bw,bh,top,bottom)then return end
            extra=extra or {};local hover=pointer and pointer.x>=x and pointer.x<x+bw and pointer.y>=y and pointer.y<y+bh
            local c={id=id,text=fit(value,bw-14,extra.font_size or 12,extra.raw_text),x=x,y=y,width=bw,height=bh,action=action or id,
                enabled=extra.enabled~=false,active=extra.active==true,hovered=hover==true,kind=extra.kind or 'button',
                text_x=x+8,text_y=y+(bh-(extra.font_size or 12))/2,font_size=extra.font_size or 12,colour=extra.enabled==false and MUTED or INK,align=0}
            for key,v in pairs(extra)do c[key]=v end
            r.nav_controls[#r.nav_controls+1]=c
            deco('button_'..id,x,y,bw,bh,hover and {.29,.29,.29,.8}or(c.active and {.24,.24,.24,.72}or{.07,.07,.07,.55}),c.active and WHITE or LINE,top,bottom)
            return c
        end
        deco('panel',0,0,w,h,{.075,.075,.075,.82},LINE)
        label('panel_title','战果档案',pad,12,inner,18)
        local tabs={{'collection','战果'},{'history','对局'},{'deaths','死因'},{'weapons','武器'},{'enemies','敌人'}}
        if context.billing_enabled==true then tabs[#tabs+1]={'bill','账单'}end
        local tw=(inner-4*(#tabs-1))/#tabs
        for i,v in ipairs(tabs)do
            control('tab_'..v[1],v[2],pad+(i-1)*(tw+4),44,tw,36,'tab_'..v[1],{active=view==v[1],kind='tab'})
        end
        local pw=(inner-12)/4
        for i,v in ipairs({{'all','全部'},{'24h','24小时'},{'7d','7天'},{'30d','30天'}})do
            control('period_'..v[1],v[2],pad+(i-1)*(pw+4),90,pw,28,'period',{period=v[1],active=context.period==v[1],kind='period'})
        end
        local y=128
        if not death then
            local totals=data.totals or {};local bw=inner/2
            for i,v in ipairs({{count(totals.kills),'当前筛选击杀'},{count(totals.known_kinds),view=='weapons' and '种武器/战备' or '种敌人'}})do
                label('total_'..i,v[1],pad+(i-1)*bw,y,bw,21);label('total_label_'..i,v[2],pad+(i-1)*bw,y+27,bw,10,true)
            end
            y=y+54
        end
        -- Query text is user input. Only the prefix is localizable.
        control('combat_search',(s.search_active and '| 'or t('搜索：'))..str(s.query,''),pad,y,inner-50,30,'search_focus',{active=s.search_active,raw_text=true})
        control('combat_search_clear','清空',w-pad-46,y,46,30,'search_clear',{font_size=11})
        label('search_hint',s.search_status=='paste_unavailable'and'暂时无法粘贴，请重试。'or'输入型号/ID，中文可粘贴',pad,y+33,inner,10,true);y=y+53
        local dropdown_anchor
        local function filter(id,values,value,x,bw)
            local selected=1
            for i,v in ipairs(values)do if v[1]==value then selected=i;break end end
            local opened=s.dropdown and s.dropdown.filter==id
            local trigger=control('filter_'..id,values[selected][2]..(opened and' ^'or' v'),x,y,bw,28,'combat_dropdown',
                {filter=id,value=values[selected][1],active=opened,font_size=11,kind='select'})
            if opened and trigger then dropdown_anchor={filter=id,x=x,y=y,width=bw,values=values,selected=selected}end
        end
        if death then
            control('death_rank','死因排名',pad,y,(inner-4)/2,28,'death_mode',{value='rank',active=s.mode~='recent'})
            control('death_recent','最近记录',pad+(inner+4)/2,y,(inner-4)/2,28,'death_mode',{value='recent',active=s.mode=='recent'});y=y+34
            filter('category',categories,s.category,pad,inner)
        elseif view=='weapons'then
            filter('role',roles,s.role,pad,inner)
        else filter('faction',factions,s.faction,pad,(inner-4)/2);filter('size',sizes,s.size,pad+(inner+4)/2,(inner-4)/2)end
        y=y+36
        if s.focus_id then
            control('combat_back','< 返回',pad,y,82,26,'combat_back')
            control('combat_unfocus','查看全部',w-pad-92,y,92,26,'combat_unfocus')
            label('combat_context','关联查询',pad+90,y+4,inner-190,11,true);y=y+32
        end
        local rows=type(data.rows)=='table'and data.rows or {};local pages=s.pages or {}
        local page_kind=death and(s.mode=='recent'and'recent'or'rank')or view
        local current,last,first,final=page(rows,pages[page_kind],10)
        r.combat_page=current;r.combat_page_kind=page_kind
        local death_count=0
        if death and s.mode=='recent'then
            -- Query places its only aggregate last. Count it without walking
            -- every real event again on each bounded layout refresh.
            death_count=#rows
            local grouped=rows[#rows]
            if grouped and grouped.unknown_group==true and type(grouped.count)=='number'then
                death_count=death_count-1+grouped.count
            end
        end
        label('combat_count',count(death and s.mode=='recent'and death_count or #rows)
            ..(death and(s.mode=='recent'and' 次阵亡'or' 种来源')or' 项'),pad,y,inner,11,true);y=y+23
        local top,bottom=y,math.max(y, h-76);r.list_top,r.list_bottom=top,bottom
        local blocks,cy={},0
        local function block(kind,v,bh)blocks[#blocks+1]={kind=kind,value=v,y=cy,height=bh};cy=cy+bh end
        local function stamp(row)
            local at=row.at or row.occurred_at
            if type(at)=='number'and type(context.format_time)=='function'then local ok,v=pcall(context.format_time,at);if ok and type(v)=='string'then return v end end
            return '时间未记录'
        end
        local function facts(row)
            local player=row.player or {};local category=row.category
            local actor=category=='player'and'队友'or source_name(row.actor or row.actor_name,'未知死因')
            local fields={{'发生时间',stamp(row)},{'对局编号',tostring(row.match or row.sequence or '未记录')},
                {'来源分类',category=='player'and'队友'or category=='enemy'and'敌方单位'or category=='self'and'自身'or category=='environment'and'环境'or'未知死因'},
                {'攻击单位',actor},{'伤害来源',source_name(row.weapon or row.weapon_name,'未知')},{'伤害类型',str(row.attack or row.damage_kind,'未知')}}
            local evidence=row.evidence
            if type(evidence)=='table'then
                local observed={dead_state='生命状态进入死亡',avatar_removed='角色实体已移除',runtime_player_died='原生死亡事件',native_death_counter='原生阵亡计数增加'}
                local channels={native_health_last_owner_creditor='生命记录中的最后攻击方',native_health_last_owner_type='最后攻击单位种类',recent_runtime_player_damaged='近期受伤事件线索',
                    local_damage_queue='角色伤害记录',latest_native_damage_event='最近原生受伤记录',native_owned_health_death_cause='生命记录中的死亡机制',
                    nearby_simultaneous_death='附近同时死亡线索'}
                local reasons={COUNTER_GAP_ATTRIBUTION_SKIPPED='计数间断，缺少来源',CONFLICTING_SOURCE_EVIDENCE='来源线索冲突',NO_PROVEN_RECENT_SOURCE='近期来源无法确认',DEATH_SOURCE_NOT_SAMPLED='本次未采到来源',DEATH_SOURCE_AVATAR_CHANGED='采样时角色已变化',
                    DEATH_AVATAR_UNMAPPED='角色实体未能对齐',DEATH_SOURCE_CHANGED_AFTER_DEATH='阵亡后来源记录变化',DEATH_SOURCE_IDENTITY_CHANGED='来源单位身份已变化',
                    COUNTER_VICTIM_AVATAR_NOT_DEAD='计数增加时未确认角色已阵亡',NATIVE_DAMAGE_WEAPON_UNRESOLVED='已识别伤害类型，武器未能对齐'}
                fields[#fields+1]={'死亡依据',observed[evidence.death_observed]or str(evidence.death_observed,'未记录')}
                fields[#fields+1]={'来源线索',channels[evidence.source_channel]or'未记录'}
                if evidence.source_reason then fields[#fields+1]={'来源说明',reasons[evidence.source_reason]or'来源读取未完成'}end
                if evidence.used_downing_source then fields[#fields+1]={'补充线索','倒地阶段来源'}end
                if evidence.nearby_death_inferred then fields[#fields+1]={'补充线索','附近队友同时死亡'}end
            else fields[#fields+1]={'记录证据',str(row.evidence_text or evidence)}end
            if category=='player'then
                fields[#fields+1]={'当时昵称',str(player.name or player.display_name,t('未记录')),raw=true}
                fields[#fields+1]={'原生呼号',str(player.callsign,t('未记录')),raw=true}
                fields[#fields+1]={'队伍位置',player.slot and tostring(player.slot)or'未记录'}
                fields[#fields+1]={'会话标识',str(player.peerId or player.peer_id,t('未记录')),raw=true}
                fields[#fields+1]={'永久账号','未取得（Steam/PSN/游戏账号 ID）'}
                fields[#fields+1]={'内部槽位',player.personaIndex~=nil and tostring(player.personaIndex)or player.persona_index~=nil and tostring(player.persona_index)or'未记录'}
                if player.slot_index~=nil then fields[#fields+1]={'原生队伍索引',tostring(player.slot_index)}end
                fields[#fields+1]={'标识说明','会话标识不能代替永久账号。'}
            end
            for _,field in ipairs(fields)do block('fact',field,24)end
        end
        local function record(row)
            block('record',row,58)
            if row.id==s.record_id then facts(row)end
        end
        for i=first,final do
            local row=rows[i]
            if death and s.mode=='recent'and row.unknown_group~=true then record(row)
            else
                block('rank',{row=row,index=i},60)
                if row.id==s.open_id then
                    if death then
                        local related=type(row.records)=='table'and row.records or {}
                        local cp,lp,a,z=page(related,(s.related_pages or {})[row.id],5)
                        r.related_page,r.related_last=cp,lp
                        block('related_heading','相关死亡记录 · '..count(#related)..' 条',25)
                        for j=a,z do record(related[j])end
                        if lp>1 then block('related_pager',{id=row.id,page=cp,last=lp},32)end
                        if type(row.unrecorded_count)=='number'and row.unrecorded_count>0 then
                            block('missing_summary',row.unrecorded_count,30)
                        end
                    else
                        block('related_heading',view=='weapons'and'击杀过的敌人'or'击杀武器来源',25)
                        for j,detail in ipairs(associations(row.detail_rows))do
                            if j>20 then break end
                            block('association',detail,32)
                        end
                        if #(row.detail_rows or {})==0 then block('note','未记录武器与敌人关联。',26)end
                    end
                end
            end
        end
        if #rows==0 then block('note',str(data.message or(type(data.coverage)=='table'and data.coverage.message),'暂无符合条件的记录。'),32)end
        local available=math.max(0,bottom-top);r.content_height=cy
        r.max_scroll=math.max(0,cy-available);r.scroll=math.max(0,math.min(r.max_scroll,tonumber(context.scroll)or 0))
        local serial=0
        for _,b in ipairs(blocks)do
            local by=top+b.y-r.scroll;local v=b.value
            if b.kind=='rank'then
                local row=v.row;local amount=death and row.count or row.kills
                control('combat_rank_'..v.index,(row.id==s.open_id and'- 'or'+ ')
                    ..(row.unknown_group==true and''or count(v.index)..'  ')..name(row,death)..'  '..count(amount),pad,by,inner,b.height-6,'combat_open',
                    {value=row.id,active=row.id==s.open_id,sequence=row.id,font_size=12},top,bottom)
            elseif b.kind=='record'then
                local actor=v.category=='player'and(t('队友')..' · '..str(v.player and(v.player.name or v.player.display_name),t('昵称未记录')))or t(source_name(v.actor or v.actor_name,'未知死因'))
                control('combat_record_'..str(v.id,''),(v.id==s.record_id and'- 'or'+ ')..stamp(v)..'  #'..tostring(v.match or v.sequence or '--'),pad+6,by,inner-12,b.height-4,'combat_record',
                    {value=v.id,sequence=v.id,active=v.id==s.record_id,font_size=11},top,bottom)
                label('record_source_'..str(v.id,''),actor..' · '..t(source_name(v.weapon or v.weapon_name or v.attack or v.damage_kind,'未知')),pad+16,by+29,inner-32,11,true,top,bottom,true)
            elseif b.kind=='fact'then
                serial=serial+1;label('fact_key_'..serial,v[1],pad+16,by,76,10,true,top,bottom)
                label('fact_value_'..serial,v[2],pad+96,by,inner-110,11,false,top,bottom,v.raw)
            elseif b.kind=='association'then
                serial=serial+1
                local known=not unknown(v)and v.linkable~=false
                control('association_'..serial,name(v,false)..'  '..count(v.kills or v.count)..(known and' >'or''),pad+12,by,inner-24,28,'combat_association',
                    {value=v.id,target_view=view=='weapons'and'enemies'or'weapons',enabled=known,align=0,font_size=12},top,bottom)
            elseif b.kind=='missing_summary'then
                label('unrecorded_summary','未知死因：'..count(v)..' 次阵亡缺少明细。',pad+12,by,inner-24,11,true,top,bottom)
            elseif b.kind=='related_pager'then
                control('related_previous','上一页',pad+12,by,74,28,'combat_related_page',{value=v.page-1,group_id=v.id,enabled=v.page>1,font_size=11},top,bottom)
                if v.last>5 then
                    local active=s.jump and s.jump.scope=='related'and s.jump.group_id==v.id
                    control('related_jump',active and('页码 '..s.jump.value..' [Enter]')or('页码 '..v.page..' / '..v.last..' >'),pad+94,by,inner-190,28,'combat_jump_focus',
                        {scope='related',group_id=v.id,value=v.page,last_page=v.last,active=active,font_size=10},top,bottom)
                else label('related_number',v.page..' / '..v.last,pad+94,by+5,inner-190,11,true,top,bottom)end
                control('related_next','下一页',w-pad-86,by,74,28,'combat_related_page',{value=v.page+1,group_id=v.id,enabled=v.page<v.last,font_size=11},top,bottom)
            else serial=serial+1;label('note_'..serial,v,pad+12,by,inner-24,11,true,top,bottom)end
        end
        if last>1 then
            local py=h-68
            control('combat_previous','上一页',pad,py,74,28,'combat_page',{value=current-1,enabled=current>1,page_kind=page_kind,font_size=11})
            if last>5 then
                local active=s.jump and s.jump.scope=='main'
                control('combat_jump',active and('页码 '..s.jump.value..' [Enter跳转]')or('页码 '..current..' / '..last..' >'),pad+82,py,inner-164,28,'combat_jump_focus',
                    {scope='main',page_kind=page_kind,value=current,last_page=last,active=active,font_size=11})
            else label('combat_page_number',current..' / '..last..' 页',pad+82,py+6,inner-164,11,true)end
            control('combat_next','下一页',w-pad-74,py,74,28,'combat_page',{value=current+1,enabled=current<last,page_kind=page_kind,font_size=11})
        end
        if available>0 and r.max_scroll>0 then
            local thumb=math.max(18,available*available/math.max(1,cy))
            deco('scroll_track',w-7,top,3,available,{.05,.05,.05,.6})
            deco('scroll_thumb',w-7,top+(available-thumb)*r.scroll/r.max_scroll,3,thumb,{.62,.62,.62,.9})
        end
        label('help',death and'缺少明细的阵亡汇入未知死因。'or'仅统计保存的明细；未识别项归为未知。',pad,h-28,inner,10,true)
        if dropdown_anchor then
            local a=dropdown_anchor
            local visible=math.min(6,#a.values,math.floor((h-20)/30))
            local max_scroll=math.max(0,#a.values-visible)
            local offset=math.max(0,math.min(max_scroll,math.floor(tonumber(s.dropdown.scroll)or math.max(0,a.selected-visible+1))))
            local dh=visible*30+4
            local dy=a.y+30
            if dy+dh>h-8 then dy=math.max(8,a.y-dh-2)end
            local menu={filter=a.filter,x=a.x,y=dy,width=a.width,height=dh,controls={},decorations={},
                first=offset+1,last=offset+visible,total=#a.values,scroll=offset,max_scroll=max_scroll}
            menu.decorations[1]={x=a.x,y=dy,width=a.width,height=dh,fill={.055,.055,.055,1},border=WHITE}
            for i=menu.first,menu.last do
                local value=a.values[i];local oy=dy+2+(i-menu.first)*30
                local hover=pointer and pointer.x>=a.x and pointer.x<a.x+a.width and pointer.y>=oy and pointer.y<oy+30
                local active=i==a.selected
                if hover or active then menu.decorations[#menu.decorations+1]={x=a.x+1,y=oy,width=a.width-2,height=30,
                    fill=hover and{.32,.32,.32,1}or{.23,.23,.23,1}}end
                menu.controls[#menu.controls+1]={id='dropdown_option_'..i,text=fit((active and'* 'or'  ')..value[2],a.width-20,11),
                    x=a.x+1,y=oy,width=a.width-2,height=30,text_x=a.x+8,text_y=oy+9,font_size=11,colour=INK,align=0,
                    action='combat_filter',filter=a.filter,value=value[1],enabled=true,active=active,hovered=hover==true,kind='option'}
            end
            if max_scroll>0 then
                local th=math.max(12,(dh-4)*visible/#a.values)
                menu.decorations[#menu.decorations+1]={x=a.x+a.width-5,y=dy+2,width=2,height=dh-4,fill={.18,.18,.18,1}}
                menu.decorations[#menu.decorations+1]={x=a.x+a.width-5,y=dy+2+(dh-4-th)*offset/max_scroll,width=2,height=th,fill={.75,.75,.75,1}}
            end
            r.dropdown=menu
        end
        r.constructed_blocks=#blocks;r.source_rows=#rows;r.combat_last_page=last
        return r
    end
    return api
end
