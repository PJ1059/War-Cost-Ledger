-- Presentation cached on the existing update path. Native HUD+ consumes this
-- through its computed source; it neither re-reads combat nor scans game widgets.
return function(game_hud, state, battle, awards)
    local cached
    local api={}
    function api:clear() cached=nil end
    function api:snapshot() return cached end
    function api:update(geometry, now, visible)
        if not visible or not geometry then cached=nil;return end
        local cfg=game_hud.config
        local model=game_hud:native_model(now, true, cfg.width or 600)
        local stats=model.stats
        local scale=cfg.scale
        local available=geometry.available_height
        -- Only transient notices follow the native pickup anchor. Collected
        -- totals and the task reservation keep their established top layout.
        -- Root height is a span, not its bottom coordinate in an inset parent.
        local viewport_bottom=available and (geometry.center_y and geometry.center_y+available/2 or available)
        local remaining=viewport_bottom and math.max(0,(viewport_bottom-geometry.local_top)/scale-cfg.top_margin)
        local side_top=model.layout.side_top
        local popup_scale=1.5
        local side_height=model.layout.side_height*popup_scale
        local popup_x=0
        local pickup=geometry.pickup
        if pickup then
            local target=(pickup.top-geometry.local_top)/scale-cfg.top_margin
            if pickup.occupied then target=target-side_height-12 end
            side_top=math.max(side_top,remaining and math.min(target,remaining-side_height-16) or target)
            popup_x=(pickup.right-geometry.width)/scale+cfg.right_margin
        elseif remaining then
            -- A missing pickup label must not bring back the old lower-right
            -- placement. The root center is already in this parent's units;
            -- half the root height alone is wrong when that parent is inset.
            local midpoint=geometry.center_y or available*cfg.side_vertical
            side_top=math.max(side_top,math.min((midpoint-geometry.local_top)/scale-cfg.top_margin,
                remaining-side_height-16))
        end
        local popup_shift=side_top-model.layout.side_top
        local drawn_height=side_height>0 and math.max(model.layout.top_height,side_top+side_height)
            or model.layout.top_height
        local left=geometry.width-(cfg.right_margin+model.layout.width)*scale
        local center={(geometry.center_x or geometry.width/2)-left,
            (geometry.center_y or (available or 900)/2)+70*scale-geometry.local_top-cfg.top_margin*scale}
        center={center[1]/scale,-center[2]/scale}
        cached={immutable=true,shown=true,hud=geometry.hud,key=geometry.key,map_open=model.map_open,
            position={left,
                -(geometry.local_top+cfg.top_margin*scale)},
            scale={scale,scale},size={model.layout.width,drawn_height},block_height=model.layout.top_height,layout=model.layout,
            opacity=cfg.opacity,now=now,side_margin=cfg.side_margin,side_vertical=cfg.side_vertical,
            side_top=side_top,popup_shift=popup_shift,popup_shift_x=popup_x,
            popup_scale=popup_scale,side_height=side_height,
            center_position=center,
            kill_source_enabled=cfg.kill_source_enabled~=false,
            kill_source_notices=model.kill_source_notices,kill_notice_bottom=remaining,
            pickup_occupied=pickup and pickup.occupied,available_height=remaining,
            shots=tostring(model.state.shots or '--'),
            kills=tostring(stats.kills),fire=tostring(model.state.fire_kills or '--'),bill=tostring(stats.bill),
            currency=stats.currency or 'SC',
            kd=stats.kd,
            history_kd=stats.history_kd,
            kd_text=stats.kd_text,bill_text=stats.bill_text,
            medals=model.awards.medals,ribbons=model.awards.ribbons,side=model.awards.items}
    end
    return api
end
