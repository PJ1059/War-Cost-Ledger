-- Native geometry stays at 10 Hz; cheap input is sampled every frame.
return function(options)
    local api={status='waiting_page'}
    local cached,geometry,reader,identity
    local view,period,expanded,summary_expanded='collection','all',nil,false
    local scroll,award_page=0,1
    local expanded_bill=false
    local previous_left,sampled_at,recent_sequence
    local pending,wheel,menu_wheel={},0,0
    local capture_requested=false
    local mouse_capture={keyboard=false,mouse=true}
    local combat={query='',role='all',weapon_type='all',faction='all',size='all',category='all',mode='rank',
        focus_id=nil,open_ids={},pages={},related_pages={},record_id=nil,back={}}
    local search=type(options.search_input)=='function' and options.search_input({
        key_pressed=options.key_pressed,key_down=options.key_down,paste_text=options.paste_text}) or nil
    local function combat_view(value)return value=='deaths' or value=='weapons' or value=='enemies'end
    local function reset_pages()
        combat.pages={};combat.related_pages={};combat.record_id=nil;scroll=0
    end
    local function blur()if search then search:blur()end;combat.jump=nil end
    local function jump_submit()
        local target=combat.jump
        if not target then return end
        local value=math.max(1,math.min(target.last,math.floor(tonumber(target.value)or target.current)))
        if target.scope=='related'then combat.related_pages[target.group_id]=value
        else combat.pages[target.page_kind]=value;combat.open_ids[view]=nil;scroll=0 end
        combat.record_id=nil;combat.jump=nil
    end
    local function filters()
        return {period=period,query=combat.query,role=combat.role,weapon_type=combat.weapon_type,
            faction=combat.faction,size=combat.size,category=combat.category,mode=combat.mode,focus_id=combat.focus_id}
    end
    local function capture(active)
        -- Runtime capture is a renewable mouse-message lease. Keep keyboard
        -- input available, and never release a lease we did not request.
        if type(options.block_input)~='function' then return end
        if active then
            capture_requested=true
            mouse_capture.keyboard=(search~=nil and search.active==true)or combat.dropdown~=nil
            pcall(options.block_input,mouse_capture)
        elseif capture_requested then
            capture_requested=false
            pcall(options.block_input,false)
        end
    end
    local function finite(v)return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
    local function project(mouse,g)
        local ok,w,h=pcall(options.gui_resolution or function()end)
        if type(mouse)~='table' or not finite(mouse.x) or not finite(mouse.y)
            or not finite(mouse.w) or not finite(mouse.h) or mouse.w<=0 or mouse.h<=0
            or not ok or not finite(w) or not finite(h) or w<320 or h<240 then return end
        local r=g.root
        local gx,gy=mouse.x*w/mouse.w,mouse.y*h/mouse.h
        return {x=(gx-r.x)/r.sx-g.position[1],
            y=r.height-(h-gy-r.y)/r.sy+g.position[2]}
    end
    local function at(model,p)
        if not p then return end
        local menu=model.dropdown
        if menu then
            for _,c in ipairs(menu.controls)do
                if c.enabled and p.x>=c.x and p.x<c.x+c.width and p.y>=c.y and p.y<c.y+c.height then return c end
            end
            -- A menu owns the click until dismissed. Only another select may
            -- switch menus; records, tabs and input beneath it cannot fire.
            for _,c in ipairs(model.nav_controls or {})do
                if c.action=='combat_dropdown' and c.enabled and p.x>=c.x and p.x<c.x+c.width and p.y>=c.y and p.y<c.y+c.height then return c end
            end
            return {id='dropdown_close',action='dropdown_close',text='',enabled=true}
        end
        for _,c in ipairs(model.nav_controls or {})do
            if c.enabled and p.x>=c.x and p.x<c.x+c.width and p.y>=c.y and p.y<c.y+c.height then return c end
        end
    end
    function api:clear(reason)
        -- Reader timeouts hide the view without erasing browsing state.
        -- Losing the page always cancels queued input.
        capture(false)
        blur()
        combat.dropdown=nil
        cached,geometry,identity=nil,nil,nil
        previous_left,sampled_at=nil,nil
        pending,wheel,menu_wheel={},0,0
        self.status=reason or 'hidden'
    end
    function api:snapshot()return cached end
    function api:sample_input(now)
        if sampled_at==now then return end
        sampled_at=now
        if not cached or not geometry or now-cached.now>.25 then
            blur()
            combat.dropdown=nil
            capture(false)
            pending,wheel,menu_wheel,previous_left={},0,0,nil;return
        end
        local ok,mouse=pcall(options.mouse or function()end)
        local left=ok and type(mouse)=='table' and mouse.left==true
        local p=ok and project(mouse,geometry)
        if not ok or type(mouse)~='table' or not p then
            blur();combat.dropdown=nil;capture(false);pending,wheel,menu_wheel,previous_left={},0,0,nil;return
        end
        -- The whole visible archive owns mouse input, including its header,
        -- footer and list ends. Only its list consumes scroll distance below.
        local c=at(cached.model,p)
        if left and previous_left==false and (not c or(c.action~='search_focus'and c.action~='combat_jump_focus'))then blur()end
        if search and search.active then
            local value=search:sample()
            if combat.jump then
                if value~=nil then combat.jump.value=value:gsub('%D','');search.value=combat.jump.value end
                if not search.active then if search.exit_reason=='submit'then jump_submit()else combat.jump=nil end end
            elseif value~=nil and combat.query~=value then combat.query=value;combat.focus_id=nil;combat.back={};reset_pages()end
        end
        if combat.dropdown and type(options.key_pressed)=='function'then
            local ok,value=pcall(options.key_pressed,'ESCAPE')
            if ok and value==true then combat.dropdown=nil;pending={};menu_wheel=0 end
        end
        capture((search and search.active==true)or combat.dropdown~=nil or(p.x>=0 and p.x<geometry.width and p.y>=0 and p.y<geometry.height))
        if previous_left==false and left and c and #pending<8 then
            pending[#pending+1]={id=c.id,sequence=c.sequence,text=c.text,filter=c.filter,value=c.value,action=c.action,
                parent=geometry.parent,gui_context=geometry.gui_context,
                mouse={x=mouse.x,y=mouse.y,w=mouse.w,h=mouse.h}}
        end
        previous_left=left
        if (cached.model.view=='history' or cached.model.view=='bill' or combat_view(cached.model.view)) and p.x>=0 and p.x<geometry.width and p.y>=0 and p.y<geometry.height then
            local wok,value=pcall(options.wheel or function()return 0 end)
            if wok and finite(value) then
                local menu=cached.model.dropdown
                if menu then
                    if combat.dropdown and p.x>=menu.x and p.x<menu.x+menu.width and p.y>=menu.y and p.y<menu.y+menu.height then
                        menu_wheel=math.max(-20,math.min(20,menu_wheel+value))
                    end
                elseif p.y>=(cached.model.list_top or 0) and p.y<(cached.model.list_bottom or 0)then
                    wheel=math.max(-20,math.min(20,wheel+value))
                end
            end
        end
    end
    function api:step(now,world,game,players)
        local latest=options.latest_ended and options.latest_ended()
        if finite(latest) and latest~=recent_sequence then
            blur()
            combat.dropdown=nil
            recent_sequence=latest
            view,period,expanded,summary_expanded='history','all',latest,false
            scroll,award_page=0,1
        end
        if not world or not game or game.state~=3 or game.mission then self:clear('waiting_ship');return end
        local peer
        for _,p in ipairs(players or {})do if p['local']==true then
            if peer then self:clear('ambiguous_player');return end
            peer=p.peer
        end end
        if not peer then self:clear('waiting_player');return end
        if not reader then reader=options.reader()end
        local ok,g,why=pcall(reader.read,reader,world,peer)
        self.reader_diagnostics=reader.diagnostics
        if not ok or not g then self:clear(ok and why or 'reader_error');return end
        if identity and (identity.parent~=g.parent or identity.gui_context~=g.gui_context
            or identity.local_peer~=g.local_peer) then self:clear('parent_rebuilt');return end
        self:sample_input(now)
        geometry,identity=g,g
        local mouse_ok,mouse=pcall(options.mouse or function()end)
        local pointer=mouse_ok and project(mouse,g)
        if previous_left==nil then previous_left=mouse_ok and type(mouse)=='table' and mouse.left==true end
        local records=options.records()
        local billing=false
        if type(options.billing_enabled)=='function'then
            local ok,value=pcall(options.billing_enabled);billing=ok and value==true
        end
        if not billing then expanded_bill=false end
        if view=='bill'and not billing then view='collection';scroll=0 end
        local history=options.history and options.history() or nil
        local legacy_crush
        if type(options.crush_summary)=='function'then
            local ok,value=pcall(options.crush_summary,history)
            if ok and type(value)=='table'then legacy_crush=value end
        end
        local summary=(view=='history'or view=='bill'or billing and view=='collection') and options.summary and options.summary() or nil
        local function layout()
            local combat_data
            if combat_view(view)then
                local ok,value=pcall(options.combat or function()return nil end,view,filters())
                combat_data=ok and type(value)=='table'and value or {rows={},message='暂无已保存的相关明细。',coverage='unavailable'}
            end
            combat.open_id=combat.open_ids[view]
            combat.search_active=search and search.active==true and combat.jump==nil or false
            combat.search_status=search and search.status or 'unavailable'
            return options.model:layout(records,{page_visible=true,personal=true,
                width=g.width,height=g.height,pointer=pointer,view=view,period=period,
                expanded_sequence=expanded,expanded_bill_sequence=expanded_bill,summary_expanded=summary_expanded,scroll=scroll,
                award_page=award_page,format_time=options.format_time,
                billing_enabled=billing,format_money=options.format_money,
                history=history,summary=summary,combat=combat_data,combat_state=combat,combat_query=options.combat,legacy_crush=legacy_crush})
        end
        local function take(model)
            scroll=model.scroll or 0;award_page=model.award_page or 1
            if model.view=='history' and model.expanded_sequence~=nil then expanded=model.expanded_sequence end
            if model.view=='history' then expanded_bill=model.expanded_bill_sequence or false end
            if model.combat_page_kind then combat.pages[model.combat_page_kind]=model.combat_page end
            if model.dropdown and combat.dropdown then combat.dropdown.scroll=model.dropdown.scroll end
            if combat.dropdown and not model.dropdown then combat.dropdown=nil;capture(false)end
            if combat.open_ids[view] and model.related_page then combat.related_pages[combat.open_ids[view]]=model.related_page end
            return model
        end
        local model=take(layout())
        if model.dropdown and combat.dropdown and menu_wheel~=0 then
            combat.dropdown.scroll=math.max(0,math.min(model.dropdown.max_scroll,model.dropdown.scroll-menu_wheel))
            model=take(layout())
        elseif not model.dropdown and wheel~=0 and (view=='history' or view=='bill' or combat_view(view)) then
            scroll=math.max(0,math.min(model.max_scroll or 0,scroll-wheel*52))
            model=take(layout())
        end
        wheel,menu_wheel=0,0
        for _,event in ipairs(pending)do
            local c=at(model,project(event.mouse,g))
            if event.parent==g.parent and event.gui_context==g.gui_context and c
                and c.id==event.id and c.sequence==event.sequence and c.text==event.text
                and c.filter==event.filter and c.value==event.value and c.action==event.action then
                local action=c.action or c.id
                if action=='tab_collection' or action=='tab_history' or action=='tab_deaths' or action=='tab_weapons' or action=='tab_enemies' or(action=='tab_bill'and billing)then
                    blur();local next_view=action:sub(5)
                    if view~=next_view then
                        combat.query='';combat.role='all';combat.weapon_type='all';combat.faction='all';combat.size='all';combat.category='all';combat.focus_id=nil;combat.back={};reset_pages()
                    end
                    view=next_view;scroll=0;expanded_bill=false
                    summary=(view=='history'or view=='bill'or billing and view=='collection') and options.summary and options.summary() or nil
                    award_page=1
                elseif action=='period' then
                    period,expanded,summary_expanded,expanded_bill=c.period,nil,false,false
                    reset_pages()
                elseif action=='toggle_match' then
                    if expanded==c.sequence then expanded=false else expanded=c.sequence end
                    summary_expanded=false;expanded_bill=false
                elseif action=='toggle_match_bill' then
                    if expanded==c.sequence then expanded_bill=expanded_bill~=c.sequence and c.sequence or false end
                elseif action=='toggle_summary' then
                    summary_expanded=not summary_expanded;expanded=false;scroll=0
                elseif action=='awards_previous' or action=='awards_next' then
                    award_page=award_page+(action=='awards_previous' and -1 or 1)
                elseif action=='search_focus' then
                    combat.jump=nil
                    if search and type(options.key_pressed)=='function' and type(options.key_down)=='function'then search:focus(combat.query)end
                elseif action=='combat_jump_focus' then
                    if search and type(options.key_pressed)=='function'and type(options.key_down)=='function'then
                        combat.jump={scope=c.scope,group_id=c.group_id,page_kind=c.page_kind,current=c.value,last=c.last_page,value=tostring(c.value)}
                        search:focus(tostring(c.value))
                    end
                elseif action=='search_clear' then
                    combat.query='';combat.focus_id=nil;combat.back={};reset_pages()
                    if search then search:clear()end
                elseif action=='combat_dropdown' then
                    local old=combat.dropdown
                    combat.dropdown=not(old and old.filter==c.filter)and{filter=c.filter}or nil
                    if combat.dropdown and type(options.key_pressed)=='function'then pcall(options.key_pressed,'ESCAPE')end
                elseif action=='dropdown_close' then
                    combat.dropdown=nil
                elseif action=='combat_filter' then
                    combat.dropdown=nil
                    combat[c.filter]=c.value;if c.filter=='role'then combat.weapon_type='all'end
                    combat.focus_id=nil;combat.back={};reset_pages()
                elseif action=='death_mode' then
                    combat.mode=c.value;combat.record_id=nil;scroll=0
                elseif action=='combat_open' then
                    if combat.open_ids[view]==c.value then combat.open_ids[view]=nil
                    else combat.open_ids[view]=c.value end
                    combat.record_id=nil
                elseif action=='combat_record' then
                    if combat.record_id==c.value then combat.record_id=nil
                    else combat.record_id=c.value end
                elseif action=='combat_page' then
                    combat.pages[c.page_kind]=c.value;combat.open_ids[view]=nil;combat.record_id=nil;scroll=0
                elseif action=='combat_related_page' then
                    combat.related_pages[c.group_id]=c.value;combat.record_id=nil
                elseif action=='combat_association' then
                    combat.back[#combat.back+1]={view=view,filters=filters(),open=combat.open_ids[view],scroll=scroll,
                        pages=combat.pages,related_pages=combat.related_pages,record_id=combat.record_id}
                    if #combat.back>8 then table.remove(combat.back,1)end
                    view=c.target_view;combat.focus_id=c.value;combat.query='';combat.role='all';combat.weapon_type='all';combat.faction='all';combat.size='all'
                    combat.open_ids[view]=c.value;reset_pages()
                elseif action=='combat_back' then
                    local previous=table.remove(combat.back)
                    if previous then view=previous.view;combat.focus_id=nil;for key,value in pairs(previous.filters)do if key~='period'then combat[key]=value end end
                        period=previous.filters.period;combat.open_ids[view]=previous.open;scroll=previous.scroll
                        combat.pages=previous.pages or {};combat.related_pages=previous.related_pages or {};combat.record_id=previous.record_id end
                elseif action=='combat_unfocus' then
                    combat.focus_id=nil;combat.back={};reset_pages()
                end
                model=take(layout())
            end
        end
        pending={}
        -- A newly focused field owns keyboard messages from this update onward.
        if (search and search.active)or combat.dropdown then capture(true)end
        -- HUD+ 0.2.4 text() directly dereferences its address. Keep the
        -- per-frame lifetime guard on Runtime's existing safe read boundary,
        -- restricted to these two already-proven ranges of this snapshot.
        local guard_parent,guard_alpha=g.parent,g.alpha_address
        local safe_read=world.view and world.view.read
        local function guard_read(at,n)
            if not ((at==guard_parent and n==256)or(at==guard_alpha and n==4))
                or type(safe_read)~='function' then return nil end
            local ok,raw=pcall(safe_read,at,n)
            return ok and type(raw)=='string' and #raw==n and raw or nil
        end
        cached={shown=true,immutable=true,parent=g.parent,controller=g.controller,
            gui_context=g.gui_context,parent_parent=g.parent_parent,
            alpha_address=g.alpha_address,local_peer=g.local_peer,root=g.root,
            position=g.position,size={g.width,g.height},model=model,now=now,guard_read=guard_read}
        self.status='visible'
    end
    return api
end
