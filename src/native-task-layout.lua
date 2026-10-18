-- Current-build objective layout, proved from the 0.4.6 HUD and 0.4.7 code captures.
-- Change the first visible objective's native gap, not its animated screen position.
local profile = require('hd2runtime/schemas/current')
local bytes = require('hd2runtime/core/bytes')
local bit = require('bit')
local M = {source = {
    exe_sha = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    layout = 0x392328, parent_widget = 0x2944A0, root = 0x258,
    child_widgets = {0x299BD8, 0x2949A0, 0x29B180, 0x38CA10},
    pickup = {anchor=0x392828,body=0x3932D8,title=0x393020,title_parent=0x392938,
        title_key=0x1586C8C1}, -- Native localized "Acquired", observed 2026-10-14.
    place = 0x18F5C70, fixture_sha = 'ee338b1688205b060d545a99659a36005fb3c9d370f52314df3acef92eab9648',
    layout_code_sha = '2ede865741ec7c69a70162c6e051f331bbcc113a5b17c6c5935400fdc72b39a9',
}, pins = {
    {rva=0x18F5C70, hex='40574883ec704883790800488BF90F85B5010000E817FFFFFF'},
    {rva=0x18F60AB, hex='F30F104F2CF30F104114F30F594918F3410F59C0F30F5CF9F30F5CF0'},
    {rva=0x17D08DD, hex='488D8D98DF0F00E887531200'},
}}
local Layout = {}; Layout.__index = Layout
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<100000 end
local function address(v) return type(v)=='number' and v>=65536 and v<140737488355328 and v%8==0 end
local function kind(raw) return bit.band(bit.rshift(bytes.u32(raw,0),18),15) end
local function field(raw, at) return bytes.value(raw, at, 'f32') end
local function shown(raw) return bit.band(bytes.u32(raw,0),16)~=0 end
local function writable(w, at, n)
    local ok,r=pcall(w.runtime.query,at)
    if not ok or not r or r.state~=0x1000 or type(r.base)~='number' or type(r.size)~='number'
        or r.base>at or r.base+r.size<at+n or type(r.protect)~='number' or bit.band(r.protect,0x100)~=0 then return false end
    local p=bit.band(r.protect,0xFF)
    return p==4 or p==8 or p==0x40 or p==0x80
end
local function read(w,at,n)
    local s=w.view.read(at,n)
    if type(s)=='string' and #s==n then return s end
end
local function axis(raw)
    return field(raw,0x64)>0 and field(raw,0x8C)>0
        and math.abs(field(raw,0x6C))<0.00001 and math.abs(field(raw,0x84))<0.00001
end
function M.new(options)
    options=options or {}
    return setmetatable({status='WAITING_FOR_TASK_LAYOUT', log=options.log or function() end,
        place_factory=options.place_factory, changes=0, native_calls=0, read_last=0},Layout)
end
function Layout:status_snapshot()
    return {status=self.status, changes=self.changes, native_calls=self.native_calls,
        selected=self.selected, baseline_top=self.baseline_top, desired_top=self.desired_top,
        extra_gap=self.extra_gap, owned=self.owner~=nil, read_last=self.read_last}
end
function Layout:geometry_snapshot() return self.geometry end
-- Four fixed reads, 772 bytes. The retained pickup row stays shown after its
-- animation moves it offscreen, so the shown bit alone cannot detect occupancy.
function Layout:pickup_geometry(s)
    local p=M.source.pickup
    local anchor=self:read(s.world,s.hud+p.anchor,256)
    if not anchor then return nil end
    local body=self:read(s.world,s.hud+p.body,256)
    local title=self:read(s.world,s.hud+p.title,256)
    local key=self:read(s.world,s.hud+p.title+0x110,4)
    if not body or not title or not key or bytes.u32(key,0)~=p.title_key
        or kind(anchor)~=1 or kind(body)~=1 or kind(title)~=7
        or bytes.pointer(anchor,0xF0)~=s.hud+0x820
        or bytes.pointer(body,0xF0)~=s.hud+p.anchor
        or bytes.pointer(title,0xF0)~=s.hud+p.title_parent then return nil end
    for _,raw in ipairs({anchor,body,title})do
        if bytes.pointer(raw,0xF8)~=s.context or not axis(raw)then return nil end
        for _,at in ipairs({0x24,0x28,0x40,0x64,0x8C,0x94,0x9C})do
            if not finite(field(raw,at))then return nil end
        end
    end
    local function right(raw)return field(raw,0x94)+field(raw,0x24)*field(raw,0x64)end
    local function top(raw)return field(raw,0x9C)+field(raw,0x28)*field(raw,0x8C)end
    local sx,sy=field(s.parent,0x64),field(s.parent,0x8C)
    local occupied=shown(anchor) and shown(body) and field(anchor,0x40)>.01 and field(body,0x40)>.01
        and field(body,0x94)<right(s.root) and right(body)>field(s.root,0x94)
        and field(body,0x9C)<top(s.root) and top(body)>field(s.root,0x9C)
    return {right=(right(anchor)-field(s.parent,0x94))/sx,
        top=(top(s.parent)-top(anchor))/sy,occupied=occupied}
end
function Layout:mark(status)
    if self.status~=status then self.status=status;self.log('任务让位：'..status) end
    return nil,status
end
function Layout:read(w,at,n)
    self.read_last=self.read_last+n
    return read(w,at,n)
end
function Layout:sample(w, state)
    self.read_last=0
    if profile.exe_sha~=M.source.exe_sha or profile.dll_sha~=M.source.dll_sha then return nil,'TASK_LAYOUT_BUILD_MISMATCH' end
    if type(w)~='table' or not address(w.game) or type(w.runtime)~='table' or w.runtime.mode~='live'
        or type(w.runtime.write)~='function' or type(w.runtime.query)~='function'
        or type(w.view)~='table' or type(w.view.read)~='function' or type(state)~='table'
        or not address(state.hud) then return nil,'TASK_LAYOUT_UNAVAILABLE' end
    local function get(at,n) return self:read(w,at,n) end
    -- Re-prove exact call/code each observation, not an address retained from a past world.
    for _,pin in ipairs(M.pins) do if get(w.game+pin.rva,#pin.hex/2)~=bytes.unhex(pin.hex) then return nil,'TASK_LAYOUT_CODE_MISMATCH' end end
    local hud=state.hud
    local root=get(hud+M.source.root,256)
    local records=get(hud+M.source.layout,640)
    local parent=get(hud+M.source.parent_widget,256)
    if not root or not records or not parent then return nil,'TASK_LAYOUT_READ_FAILED' end
    local context=bytes.pointer(root,0xF8)
    if not address(context) or kind(root)~=0 or bytes.pointer(root,0xF0)~=0
        or kind(parent)~=1 or bytes.pointer(parent,0xF0)~=hud+0x294390
        or bytes.pointer(parent,0xF8)~=context or not axis(parent) then return nil,'TASK_LAYOUT_IDENTITY_MISMATCH' end
    if bytes.pointer(records,0)~=hud+M.source.parent_widget or bytes.pointer(records,8)~=0
        or bytes.pointer(records,0x10)~=hud+M.source.layout+128 or bytes.pointer(records,0x18)~=0
        or bytes.u32(records,0x20)~=2 then return nil,'TASK_LAYOUT_PARENT_MISMATCH' end
    for _,off in ipairs({0x24,0x28,0x9C}) do
        if not finite(field(parent,off)) then return nil,'TASK_LAYOUT_INVALID_FIELD' end
    end
    for _,off in ipairs({0x3C,0x40,0x44,0x48}) do
        if not finite(field(records,off)) then return nil,'TASK_LAYOUT_INVALID_FIELD' end
    end
    local s={world=w,hud=hud,context=context,root=root,records=records,parent=parent,widgets={},state=state,
        key=tostring(w.game)..':'..tostring(hud)..':'..tostring(context)}
    for i,off in ipairs(M.source.child_widgets) do
        local entry=records:sub(i*128+1,(i+1)*128)
        local widget=get(hud+off,256)
        if not widget then return nil,'TASK_LAYOUT_READ_FAILED' end
        for _,field_offset in ipairs({0x2C,0x30,0x34,0x38}) do
            if not finite(field(entry,field_offset)) then return nil,'TASK_LAYOUT_INVALID_FIELD' end
        end
        for _,field_offset in ipairs({0x0C,0x10,0x14,0x18,0x28,0x9C}) do
            if not finite(field(widget,field_offset)) then return nil,'TASK_LAYOUT_INVALID_FIELD' end
        end
        if bytes.pointer(entry,0)~=hud+off or bytes.pointer(entry,8)~=hud+M.source.layout
            or bytes.pointer(entry,0x18)~=(i<4 and hud+M.source.layout+(i+1)*128 or 0)
            or bytes.pointer(widget,0xF0)~=hud+M.source.parent_widget or bytes.pointer(widget,0xF8)~=context
            or kind(widget)~=1 or bytes.u32(entry,0x24)~=0 or not axis(widget)
            or field(widget,0x18)<=0 or math.abs(field(widget,0x20)-1)>0.00001
            or math.abs(field(widget,0x8C)-field(parent,0x8C)*field(widget,0x18))>0.001 then
            return nil,'TASK_LAYOUT_CHILD_MISMATCH'
        end
        s.widgets[i],s[i]=widget,entry
    end
    if not writable(w,hud+M.source.layout,640) then return nil,'TASK_LAYOUT_NOT_WRITABLE' end
    return s
end
local function live_place(w)
    local win=require('hd2runtime/runtime/windows_ffi')
    local native=win.ffi.cast(win.fn('void (*)(uintptr_t)'),w.game+M.source.place)
    return function(at) native(at);return true end
end
function Layout:apply(s, targets)
    local w,at=s.world,s.hud+M.source.layout
    local journal={}
    for _,i in ipairs({3,4}) do
        local before=s[i]:sub(0x2D,0x30)
        if before~=targets[i] then
            local where=at+i*128+0x2C
            if self:read(w,where,4)~=before then return self:mark('TASK_LAYOUT_CHANGED_BY_OTHER_MOD') end
            journal[#journal+1]={at=where,before=before,after=targets[i],index=i}
        end
    end
    if #journal==0 then return true,'TASK_LAYOUT_UNCHANGED' end
    local call=self.place_factory and self.place_factory(w) or live_place(w)
    if type(call)~='function' then return self:mark('TASK_LAYOUT_CALL_UNAVAILABLE') end
    local wrote={}
    local function rollback()
        for i=#wrote,1,-1 do local row=wrote[i]
            if self:read(w,row.at,4)==row.after then w.runtime.write(row.at,row.before) end
        end
    end
    for _,row in ipairs(journal) do
        wrote[#wrote+1]=row
        local ok,_,n=w.runtime.write(row.at,row.after)
        if not ok or (n and n~=4) or self:read(w,row.at,4)~=row.after then rollback();return self:mark('TASK_LAYOUT_WRITE_FAILED') end
    end
    -- Only the parent layout's dirty byte: the game's own layout performs all child propagation.
    local ok,_,n=w.runtime.write(at+0x28,'\1')
    if not ok or (n and n~=1) then rollback();return self:mark('TASK_LAYOUT_WRITE_FAILED') end
    local invoked,result=pcall(call,at)
    if not invoked or result==false then rollback();return self:mark('TASK_LAYOUT_CALL_FAILED') end
    self.native_calls=self.native_calls+1
    for _,row in ipairs(journal) do self.owner.last[row.index]=row.after end
    self.changes=self.changes+1
    return true,'TASK_LAYOUT_CHANGED'
end
function Layout:reserve(w,state,options)
    self.geometry=nil
    local requested=type(options)=='table' and options.visible==true and (options.move_tasks~=false or options.native==true)
        and type(state)=='table' and state.mission==true
    if not requested and not self.owner then self.geometry=nil;self.read_last=0;self.status='TASK_LAYOUT_INACTIVE';return true,self.status end
    local good,s,why=pcall(self.sample,self,w,state)
    if not good then return self:mark('TASK_LAYOUT_INVALID_FIELD') end
    if not s then self.geometry=nil;return self:mark(why) end
    if self.owner and self.owner.key~=s.key then self.owner=nil;self.blocked=nil end
    if self.blocked==s.key then return self:mark('TASK_LAYOUT_CHANGED_BY_OTHER_MOD') end
    if not self.owner then
        self.owner={key=s.key,base={},last={}}
        for _,i in ipairs({3,4}) do
            local raw=s[i]:sub(0x2D,0x30)
            self.owner.base[i],self.owner.last[i]=raw,raw
        end
    end
    for _,i in ipairs({3,4}) do
        if s[i]:sub(0x2D,0x30)~=self.owner.last[i] then
            self.blocked=s.key
            -- Restore only the other field still owned by us; never replace the foreign value.
            local targets={}
            for _,j in ipairs({3,4}) do targets[j]=s[j]:sub(0x2D,0x30)==self.owner.last[j] and self.owner.base[j] or s[j]:sub(0x2D,0x30) end
            self:apply(s,targets);self.owner=nil
            return self:mark('TASK_LAYOUT_CHANGED_BY_OTHER_MOD')
        end
    end
    local targets={[3]=self.owner.base[3],[4]=self.owner.base[4]}
    local native=type(options)=='table' and options.native==true and finite(options.native_height) and options.native_height>0
    local active=type(options)=='table' and options.visible==true and (options.move_tasks~=false or native)
        and state.mission==true and (native or (finite(options.width) and finite(options.height)
        and finite(options.reserved_height) and options.reserved_height>0))
    local selected
    if active and shown(s.parent) then
        if shown(s.widgets[3]) then selected=3 elseif shown(s.widgets[4]) then selected=4 end
    end
    self.selected,self.extra_gap=selected,0
    if selected then
        -- Native flow cursor uses source sizes and gaps, NEVER animated current task XY.
        local scale=field(s.parent,0x8C)
        local parent_top=finite(options.height) and options.height-(field(s.parent,0x9C)+field(s.parent,0x28)*scale) or 0
        local cursor=field(s.records,0x3C)
        for i=1,selected-1 do
            if shown(s.widgets[i]) then
                local gap=(i>=3 and field(self.owner.base[i],0) or field(s[i],0x2C))
                cursor=cursor+(gap+field(s.widgets[i],0x10)+field(s[i],0x30))*field(s.widgets[i],0x18)
            end
        end
        local native_scale=scale*field(s.widgets[selected],0x18)
        local original=field(self.owner.base[selected],0)
        local local_top=cursor+original*field(s.widgets[selected],0x18)
        local baseline=parent_top+local_top*scale
        local extra=native and (options.move_tasks==false and 0 or options.native_height/field(s.widgets[selected],0x18))
            or math.max(0,(options.reserved_height-baseline)/native_scale)
        if not finite(extra) or extra>2000 then return self:mark('TASK_LAYOUT_RESERVATION_INVALID') end
        local proposed=bytes.encode(original+extra,'f32')
        -- Native matrices round to float32. Do not restart the 0.2 s animation
        -- for an invisible rounding difference; exact original bytes still restore.
        if math.abs(field(proposed,0)-field(self.owner.last[selected],0))*native_scale<0.01 then
            targets[selected]=self.owner.last[selected]
        else targets[selected]=proposed end
        self.baseline_top,self.desired_top,self.extra_gap=baseline,native and baseline+options.native_height*scale or options.reserved_height,extra
        self.geometry={hud=s.hud,context=s.context,key=s.key,local_top=local_top,
            width=field(s.parent,0x24),scale=scale,selected=selected}
        local root_height,root_scale=field(s.root,0x28),field(s.root,0x8C)
        if finite(root_height) and root_height>0 and finite(root_scale) and root_scale>0 then
            self.geometry.available_height=root_height*root_scale/scale
            self.geometry.center_y=(field(s.parent,0x9C)+field(s.parent,0x28)*scale
                -field(s.root,0x9C)-root_height*root_scale/2)/scale
            self.geometry.center_x=(field(s.root,0x94)+field(s.root,0x24)*field(s.root,0x64)/2
                -field(s.parent,0x94))/field(s.parent,0x64)
        end
        if native then self.geometry.pickup=self:pickup_geometry(s)end
    end
    local ok,reason=self:apply(s,targets)
    if not ok then self.geometry=nil;return nil,reason end
    self.status=selected and 'TASK_LAYOUT_RESERVED' or 'TASK_LAYOUT_RESTORED'
    if not selected then self.owner=nil;self.geometry=nil end
    return true,self.status
end
function Layout:restore(w,state) return self:reserve(w,state,{visible=false}) end
return M
