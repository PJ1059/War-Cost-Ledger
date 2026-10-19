local create=dofile(assert(arg[1]))
local icons=dofile(assert(arg[2]))({},function()return true end).icons
local locale=dofile(assert(arg[3]))(dofile(assert(arg[4])))
local api=create(icons,nil,nil,function(s)return locale:text(s)end)
local context={page_visible=true,personal=true,width=420,height=747,view='history',expanded_sequence=false,
    history={revision=1,entries={{sequence=3,status='ended',kills=11,deaths=2,ended_at=100,ribbons={air=5},medals={fragrant=1}}}},
    format_time=function()return '2026-10-19 23:26'end}
local data={totals={ribbons={air=5},medals={fragrant=1}}}
local function ascii(s)assert(not s:find('[\128-\255]'),'untranslated non-English text: '..s)end
for _,lang in ipairs({'en','fr','jp','unknown'})do
    locale:set_language(lang);context.view='history'
    local p=api:layout(data,context)
    for _,c in ipairs(p.nav_controls)do if c.id:find('record_',1,true)then ascii(c.text)end end
    context.view='collection';context.pointer=nil;p=api:layout(data,context)
    for _,item in ipairs(p.items)do
        context.pointer={x=item.x+2,y=item.y+2}
        local tip=assert(api:layout(data,context).tooltip)
        for _,line in ipairs(tip.details)do ascii(line)end
    end
end
locale:set_language('cn');context.view='history';context.pointer=nil
local p=api:layout(data,context)
local found=false;for _,c in ipairs(p.nav_controls)do if c.text=='单局最高击杀'then found=true end end;assert(found)
print('PASS .67 Chinese/English record and award history localization with non-Chinese fallback.')
