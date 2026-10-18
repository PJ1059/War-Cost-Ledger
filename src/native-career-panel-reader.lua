-- The observed personal Armory Career root and adjacent title/viewport only.
-- No row traversal, UI writes, cursor ownership or native function calls.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local bit=require('bit')
local M={source={exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    state=0x3326340,state_offset=705052,dispatch=0x3326E68,count=5740,rows=5744,
    local_user=0x347CEF0,local_peer=0xB398,root=0x4DAF8,panel=0x4DC08,
    viewport=0x4E4B0,list=0x4E5C0,name=0x7DD18,root_parent=0xA0,alpha=195256+84},
    pins={{0x143C950,'40534883ec20488bd94881c110010000'},{0x143A1BA,'440fb69958010000'},
          {0x143A1E3,'4c8d0440423954c108'},{0x143A212,'c744242401000000'}}}
local function finite(v)return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
local function pointer(v)return finite(v) and v>=65536 and v<140737488355328 and v%8==0 end
local function kind(raw)return bit.band(bit.rshift(b.u32(raw,0),18),15)end
local function number(raw,offset)return b.value(raw,offset,'f32')end
local function geometry(raw)
    local g={width=number(raw,0x24),height=number(raw,0x28),sx=number(raw,0x64),sy=number(raw,0x8C),
        x=number(raw,0x94),y=number(raw,0x9C)}
    for _,v in pairs(g)do assert(finite(v),'CAREER_PANEL_GEOMETRY')end
    assert(g.width>0 and g.width<=8192 and g.height>0 and g.height<=8192
        and g.sx>.1 and g.sx<=4 and g.sy>.1 and g.sy<=4,'CAREER_PANEL_GEOMETRY')
    for _,offset in ipairs({0x68,0x6C,0x74,0x7C,0x84,0x88})do
        assert(math.abs(number(raw,offset))<.0001,'CAREER_PANEL_MATRIX')
    end
    return g
end
function M.new(options)
    options=options or {}
    local api={clock=options.clock or os.clock,diagnostics={reads=0,bytes=0,ready=false}}
    function api:read(world,peer)
        local d=self.diagnostics;d.reads,d.bytes,d.ready=0,0,false
        local started=self.clock()
        local function get(at,n)
            assert(finite(at) and at>=65536 and at+n<140737488355328 and n>0 and n<=4096,'CAREER_PANEL_ADDRESS')
            assert(d.reads<48 and d.bytes+n<=8192,'CAREER_PANEL_BUDGET')
            assert(self.clock()-started<.002,'CAREER_PANEL_TIME_BUDGET')
            d.reads,d.bytes=d.reads+1,d.bytes+n
            local raw=world.view.read(at,n)
            assert(type(raw)=='string' and #raw==n,'CAREER_PANEL_READ_FAILED')
            return raw
        end
        local function ptr(at)
            local value=b.pointer(get(at,8),0)
            assert(value==0 or pointer(value),'CAREER_PANEL_POINTER')
            return value
        end
        local function locate()
            local state=ptr(world.game+M.source.state)
            assert(state~=0 and b.u32(get(state+M.source.state_offset,4),0)==3,'CAREER_PANEL_NOT_SHIP')
            local dispatch=ptr(world.game+M.source.dispatch)
            assert(dispatch~=0,'CAREER_PANEL_NOT_VISIBLE')
            local count=b.u32(get(dispatch+M.source.count,4),0)
            assert(count<=64,'CAREER_PANEL_REGISTRY')
            if count==0 then error('CAREER_PANEL_NOT_VISIBLE',0)end
            local entries=get(dispatch+M.source.rows,count*16)
            local chosen
            for index=0,count-1 do
                if b.u32(entries,index*16+8)==224 then
                    local controller=b.pointer(entries,index*16)
                    assert(pointer(controller),'CAREER_PANEL_CONTROLLER')
                    local alpha=number(get(controller+M.source.panel+M.source.alpha,4),0)
                    assert(finite(alpha) and alpha>=0 and alpha<=1.001,'CAREER_PANEL_ALPHA')
                    if alpha>.95 then
                        assert(not chosen,'CAREER_PANEL_AMBIGUOUS')
                        chosen={game=world.game,state_context=state,dispatch=dispatch,controller=controller,
                            alpha_address=controller+M.source.panel+M.source.alpha,headers={}}
                    end
                end
            end
            assert(chosen,'CAREER_PANEL_NOT_VISIBLE')
            local local_user=ptr(world.game+M.source.local_user)
            assert(local_user~=0 and b.hex(get(local_user+M.source.local_peer,8):reverse()):upper()==peer,
                'CAREER_PANEL_LOCAL_PEER')
            chosen.local_user,chosen.local_peer=local_user,peer
            local context
            for _,role in ipairs({'root','panel','viewport','list','name'})do
                local address=chosen.controller+M.source[role]
                local raw=get(address,256)
                assert(kind(raw)==1,'CAREER_PANEL_WIDGET_KIND')
                local gui=b.pointer(raw,0xF8)
                assert(pointer(gui) and (not context or context==gui),'CAREER_PANEL_CONTEXT')
                context=gui
                local parent=b.pointer(raw,0xF0)
                local parent_role=role=='root' and 'root_parent' or role=='panel' and 'root'
                    or role=='list' and 'viewport' or 'panel'
                assert(parent==chosen.controller+M.source[parent_role],'CAREER_PANEL_PARENT')
                chosen.headers[role]=raw
            end
            chosen.gui_context,chosen.parent=context,chosen.controller+M.source.root
            return chosen
        end
        local ok,result=pcall(function()
            assert(profile.exe_sha==M.source.exe_sha and profile.dll_sha==M.source.dll_sha,'CAREER_PANEL_BUILD')
            assert(type(world)=='table' and pointer(world.game) and world.game%4096==0
                and type(world.view)=='table' and type(world.view.read)=='function'
                and world.runtime and world.runtime.mode=='live','CAREER_PANEL_WORLD')
            assert(type(peer)=='string' and #peer==16 and not peer:find('[^%x]') and peer~='0000000000000000',
                'CAREER_PANEL_LOCAL_PEER')
            peer=peer:upper()
            local before=locate()
            if self.proven_game~=world.game or self.proven_view~=world.view then
                for _,pin in ipairs(M.pins)do assert(get(world.game+pin[1],#pin[2]/2)==b.unhex(pin[2]),'CAREER_PANEL_CODE')end
                self.proven_game,self.proven_view=world.game,world.view
            end
            local root,viewport,name=geometry(before.headers.root),geometry(before.headers.viewport),geometry(before.headers.name)
            local x=(name.x-root.x)/root.sx
            local y=root.height-(name.y-root.y)/root.sy+12
            local width=math.min(420,root.width-x-32)
            local height=root.height-(viewport.y-root.y)/root.sy-y
            assert(x>=0 and y>=0 and width>=240 and height>=160,'CAREER_PANEL_SPACE')
            local after=locate()
            for _,field in ipairs({'game','state_context','dispatch','controller','local_user','local_peer','gui_context','parent'})do
                assert(before[field]==after[field],'CAREER_PANEL_REBUILT')
            end
            for role,raw in pairs(before.headers)do
                local final=after.headers[role]
                assert(kind(raw)==kind(final) and raw:sub(37,44)==final:sub(37,44)
                    and raw:sub(101,160)==final:sub(101,160) and raw:sub(241,256)==final:sub(241,256),
                    'CAREER_PANEL_REBUILT')
            end
            return {parent=after.parent,controller=after.controller,gui_context=after.gui_context,
                parent_parent=after.controller+M.source.root_parent,local_peer=peer,
                alpha_address=after.alpha_address,root=root,position={x,-y},width=width,height=height,
                page_visible=true,personal=true,source='personal_career_fixed_root_v1'}
        end)
        d.elapsed_ms=(self.clock()-started)*1000
        d.reason=ok and 'visible' or tostring(result)
        if not ok then return nil,d.reason end
        d.ready=true
        return result,'visible'
    end
    return api
end
return M
