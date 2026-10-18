local create=dofile(assert(arg[1]))
local function lines(name)
    local plan={shown=true,width=462,height=747,items={{id='M01',kind='medal',name=name,count=1,
        visible=true,x=14,y=150,width=135,height=76}},header_texts={},nav_controls={},decorations={},sections={}}
    local feed={shown=true,parent=65536,parent_parent=65544,gui_context=65552,alpha_address=65560,
        root={width=462,height=747,sx=1,sy=1,x=0,y=0},size={462,747},position={0,0},model=plan}
    local read={bytes={u32=function(raw,off)return off==0 and 262144 or 0 end,
        decode=function(raw,off)if raw=='alpha'then return 1 end;return ({[0x24]=462,[0x28]=747,[0x64]=1,[0x8C]=1,[0x94]=0,[0x9C]=0})[off]end},
        pointer_in=function(_,raw,off)return off==0xF0 and 65544 or 65552 end,
        span=function(_,at,n)return at==65560 and'alpha'or'root'end}
    local api=create({assets={M01={colour={1,1,1,1}}},artwork=function()end,solid={resource='solid'},feed=function()return feed end,refresh_aliases=function()end})
    local view=assert(api.compute.ledger_career_feed.run(read))
    return view.award_M01_name1,view.award_M01_name2
end
for _,case in ipairs({
    {'Democracy Harvester','Democracy','Harvester'},
    {'Democracy Never Dies','Democracy Never','Dies'},
    {'Smells Like Freedom','Smells Like','Freedom'},
    {'Star of Democracy','Star of','Democracy'},
    {'Super Star of Democracy','Super Star of','Democracy'},
    {'Supreme Star of Democracy','Supreme Star of','Democracy'},
    {'Rank Is No Obstacle','Rank Is No','Obstacle'},
})do
    local a,b=lines(case[1]);assert(a==case[2]and b==case[3],case[1]..' wraps at word boundaries')
    assert(#a*.55<=9 and #b*.55<=9,'both lines stay inside native label width')
end
local a,b=lines('超长中文甲乙丙丁戊己庚辛')
assert(a=='超长中文甲乙丙丁戊'and b=='己庚辛','Chinese wrapping remains character-based')
a,b=lines('ABCDEFGHIJKLMNOPQRSTUVWXYZ short')
assert(a=='ABCDEFGHIJKLMNOP'and b=='QRSTUVWXYZ short','oversized words split without overflowing')
print('PASS native Career English word wrapping, unchanged Chinese wrapping, long-word fallback and bounded two-line award names.')
