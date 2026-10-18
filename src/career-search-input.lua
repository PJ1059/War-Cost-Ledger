-- Explicitly focused Career search only. Runtime supplies pressed/down keys;
-- Unicode clipboard text is read only on the user's focused Ctrl+V action.
local function clean(value)
    if type(value)~='string' then return '' end
    value=value:gsub('[%z\1-\31\127]',' ')
    local out,bytes={},0
    for ch in value:gmatch('[\1-\127\194-\244][\128-\191]*')do
        if #out>=64 or bytes+#ch>192 then break end
        out[#out+1]=ch;bytes=bytes+#ch
    end
    return table.concat(out)
end
local function clipboard()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    local function proc(dll,name,signature)
        local handle=kernel.GetModuleHandleA(dll)
        local address=handle~=nil and kernel.GetProcAddress(handle,name) or nil
        assert(address~=nil,'clipboard unavailable')
        return ffi.cast(win.fn(signature),address)
    end
    local open=proc('user32.dll','OpenClipboard','int (*)(void *)')
    local close=proc('user32.dll','CloseClipboard','int (*)(void)')
    local get=proc('user32.dll','GetClipboardData','void *(*)(uint32_t)')
    local lock=proc('kernel32.dll','GlobalLock','void *(*)(void *)')
    local unlock=proc('kernel32.dll','GlobalUnlock','int (*)(void *)')
    local size=proc('kernel32.dll','GlobalSize','size_t (*)(void *)')
    if open(nil)==0 then return nil end
    local handle,pointer
    local ok,value=pcall(function()
        handle=get(13) -- CF_UNICODETEXT; no clipboard history or other formats.
        if handle==nil then return nil end
        local n=tonumber(size(handle));if not n or n<2 then return nil end
        pointer=lock(handle);if pointer==nil then return nil end
        local words=ffi.cast('const uint16_t *',pointer)
        local out,i={},0
        while i<math.min(128,math.floor(n/2))do
            local v=tonumber(words[i]);i=i+1
            if v==0 then break end
            if v>=0xD800 and v<=0xDBFF and i<math.min(128,math.floor(n/2))then
                local low=tonumber(words[i])
                if low>=0xDC00 and low<=0xDFFF then v=0x10000+(v-0xD800)*1024+low-0xDC00;i=i+1 else v=0xFFFD end
            elseif v>=0xD800 and v<=0xDFFF then v=0xFFFD end
            if v<128 then out[#out+1]=string.char(v)
            elseif v<2048 then out[#out+1]=string.char(192+math.floor(v/64),128+v%64)
            elseif v<65536 then out[#out+1]=string.char(224+math.floor(v/4096),128+math.floor(v/64)%64,128+v%64)
            else out[#out+1]=string.char(240+math.floor(v/262144),128+math.floor(v/4096)%64,128+math.floor(v/64)%64,128+v%64)end
        end
        return table.concat(out)
    end)
    if pointer~=nil and handle~=nil then unlock(handle)end
    close()
    return ok and value or nil
end
return function(options)
    local api={active=false,value='',status='idle'}
    local function pressed(name)local ok,v=pcall(options.key_pressed or function()end,name);return ok and v==true end
    local function down(name)local ok,v=pcall(options.key_down or function()end,name);return ok and v==true end
    function api:focus(value)
        self.value=clean(value);self.active=true;self.status='typing';self.exit_reason=nil
        -- Runtime begins following a key on its first query. Prime while the
        -- field receives focus so the user's first later press is observable.
        for _,key in ipairs({'ESCAPE','ENTER','TAB','BACKSPACE','DELETE','SPACE','MINUS','PERIOD','SLASH','EQUALS'})do pressed(key)end
        for code=65,90 do pressed(string.char(code))end
        for i=0,9 do pressed(tostring(i));pressed('NUMPAD'..i)end
        down('CTRL');down('SHIFT');down('ALT')
    end
    function api:blur()self.active=false;self.status='idle'end
    function api:clear()self.value='';return self.value end
    function api:sample()
        if not self.active then return nil end
        if type(options.key_pressed)~='function' or type(options.key_down)~='function'then self:blur();self.status='unavailable';return nil end
        local down_ok,down_value=pcall(options.key_down,'CTRL')
        local press_ok,press_value=pcall(options.key_pressed,'ENTER')
        if not down_ok or type(down_value)~='boolean'or not press_ok or type(press_value)~='boolean'then
            self:blur();self.status='unavailable';return nil
        end
        local before=self.value
        if pressed('ESCAPE')then self:blur();self.exit_reason='cancel';return nil end
        if pressed('ENTER')or pressed('TAB')then self:blur();self.exit_reason='submit';return nil end
        if down('CTRL')then
            if pressed('V')then
                local ok,value=pcall(options.paste_text or clipboard)
                if ok and type(value)=='string'then self.value=clean(self.value..value);self.status='typing'
                else self.status='paste_unavailable'end
            elseif pressed('A')then self.value=''end
        elseif not down('ALT')then
            if pressed('BACKSPACE')then
                local at
                for start in self.value:gmatch('()[\1-\127\194-\244][\128-\191]*')do at=start end
                if at then self.value=self.value:sub(1,at-1)end
            elseif pressed('DELETE')then self.value=''
            else
                local shift=down('SHIFT')
                for code=65,90 do local key=string.char(code);if pressed(key)then self.value=clean(self.value..(shift and key or key:lower()))end end
                for code=0,9 do local key=tostring(code);if pressed(key)or pressed('NUMPAD'..key)then self.value=clean(self.value..key)end end
                for key,pair in pairs({SPACE={' ',' '},MINUS={'-','_'},PERIOD={'.','>'},SLASH={'/','?'},EQUALS={'=','+'}})do
                    if pressed(key)then self.value=clean(self.value..pair[shift and 2 or 1])end
                end
            end
        end
        if self.value~=before then return self.value end
    end
    return api
end
