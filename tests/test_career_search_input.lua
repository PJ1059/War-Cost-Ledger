local create=dofile(assert(arg[1]))
local pressed,down={},{}
local pastes=0
local api=create({key_pressed=function(k)return pressed[k]==true end,key_down=function(k)return down[k]==true end,
    paste_text=function()pastes=pastes+1;return '机炮 ABC-123' end})
local function sample(p,d)pressed=p or {};down=d or {};return api:sample()end
assert(sample({V=true},{CTRL=true})==nil and pastes==0,'unfocused clipboard is never read')
api:focus('');for i=1,5 do sample()end;assert(pastes==0)
assert(sample({A=true})=='a')
assert(sample({C=true},{SHIFT=true})=='aC')
assert(sample({MINUS=true})=='aC-')
assert(sample({V=true},{CTRL=true})=='aC-机炮 ABC-123' and pastes==1)
assert(sample({BACKSPACE=true})=='aC-机炮 ABC-12')
assert(sample({A=true},{CTRL=true})=='')
assert(sample({B=true},{ALT=true})==nil and api.value=='')
api:focus('机炮');assert(sample({BACKSPACE=true})=='机','backspace keeps complete UTF8')
api:focus(string.rep('中',100));assert(#api.value==192 and api.value==string.rep('中',64))
sample({ENTER=true});assert(not api.active)
assert(sample({V=true},{CTRL=true})==nil and pastes==1)
api:focus('test');sample({ESCAPE=true});assert(not api.active)
local missing=create({});missing:focus('x');missing:sample();assert(not missing.active and missing.status=='unavailable')
local nil_input=create({key_pressed=function()return nil end,key_down=function()return nil end})
nil_input:focus('x');nil_input:sample();assert(not nil_input.active and nil_input.status=='unavailable','nil is not a successful false key state')
local bad=create({key_pressed=function(k)return k=='V' end,key_down=function(k)return k=='CTRL'end,
    paste_text=function()return nil end});bad:focus('x');assert(bad:sample()==nil and bad.value=='x' and bad.status=='paste_unavailable')
print('PASS Career search: focused explicit Ctrl+V only, ASCII/Unicode edits, bounded complete UTF8, blur/Enter/Escape, unavailable adapters.')
