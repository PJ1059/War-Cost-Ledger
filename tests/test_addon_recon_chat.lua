-- Real built addon and native discovery reader; only Runtime/process boundaries
-- are owned fixtures. No recon module substitution and no game/account IO.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
saved.ui_settings={auto_ui_probe=false}
saved.probe_enabled=false
saved.native_hit_auto_install=false
world.game,world.runtime=0x180000000,{mode='live'}
local U32=4294967296
local function u32(n)return b.encode(n,'u32')end
local function ptr(n)return u32(n%U32)..u32(math.floor(n/U32))end
local HUD,STATE,USER,ROSTER,GUI,NAMES=0x300000000,0x310000000,0x320000000,0x330000000,0x340000000,0x350000000
local CHAT=HUD+0x14498
local LOCAL,OTHER='0000000000000011','0000000000000022'
local cells,chat_reads,chat_available={},0,true
local function put(at,raw)
    for _,r in ipairs(cells)do
        if at>=r[1]and at+#raw<=r[1]+#r[2]then
            local n=at-r[1];r[2]=r[2]:sub(1,n)..raw..r[2]:sub(n+#raw+1);return
        end
    end
    cells[#cells+1]={at,raw}
end
local function get(at,n)
    for _,r in ipairs(cells)do
        if at>=r[1]and at+n<=r[1]+#r[2]then return r[2]:sub(at-r[1]+1,at-r[1]+n)end
    end
end
local old_read=view.read
view.read=function(at,n)
    if at>=CHAT and at<CHAT+0x4390+64*0x3D8 then
        chat_reads=chat_reads+1
        if not chat_available then return nil end
    end
    return get(at,n)or old_read(at,n)
end
local function header(kind,parent,context,child,nxt)
    return u32(kind*262144)..string.rep('\0',220)..ptr(child or 0)..ptr(nxt or 0)..ptr(parent)..ptr(context)
end
put(world.game+0x3326340,ptr(STATE));put(STATE+705052,u32(4))
put(world.game+0x346D538,ptr(HUD));put(world.game+0x347CEF0,ptr(USER))
put(USER+0xB398,b.unhex(LOCAL):reverse());put(world.game+0x347CED8,ptr(ROSTER))
for i=0,3 do put(ROSTER+i*0xC0,string.rep('\0',72))end
local function player(i,who,label)put(ROSTER+i*0xC0,b.unhex(who):reverse()..label..string.rep('\0',64-#label))end
player(0,LOCAL,'本人');player(1,OTHER,'队友')
local pins={
    {0x12F2F81,'488b3db0a51702498bf0488bda80bf35e32400000f84b80000004c8b1d369f180233c0'},
    {0x12F3018,'488d8f98440100488bd0e849c45600'},
    {0x186042D,'488db75847000041be40000000'},
    {0x1860455,'488d8e38fcffff'},
    {0x18604C3,'4881c6d8030000'},
    {0x143C950,'40534883ec20488bd94881c110010000'},
    {0x143A1BA,'440fb69958010000'},
}
for _,pin in ipairs(pins)do put(world.game+pin[1],b.unhex(pin[2]))end
put(CHAT,header(1,0x360000000,GUI))
local function row_at(i)return CHAT+0x4390+i*0x3D8 end
for i=0,63 do
    local at=row_at(i)
    put(at,header(1,CHAT+0x330,GUI,at+0x110,i<63 and at+0x3D8 or 0)
        ..string.rep('\0',16)..header(8,at,GUI)..string.rep('\0',16)
        ..u32(0x14DCC78A)..string.rep('\0',341))
end
local function notice(i,label,target,template)
    local name_at=NAMES+i*0x100+3
    put(name_at,label..string.rep('\0',64-#label))
    local args=u32(0x341F7711)..u32(1)..ptr(name_at)..string.rep('\0',8)
        ..u32(0x38237B81)..u32(10)..ptr(0)..ptr(target)
    put(row_at(i)+0x220,u32(template or 0x92871A58)..u32(0)..args..string.rep('\0',336-#args)..'\2')
end
local function clear_row(i)put(row_at(i)+0x220,u32(0x14DCC78A)..string.rep('\0',341))end
-- This retained native notification predates loading the addon.
notice(0,'本人',0x101166A22E)
local module=dofile(path);state=module.state
local now=0
local function tick(n)
    for _=1,n or 1 do
        now=now+.1;clock=clock+100000
        put(STATE+705052,u32(active and 4 or 3))
        frame(.1)
    end
end
local function ribbon()return state.ribbons.recon end
local function total()return module.career_award_snapshot().totals.ribbons.recon or 0 end
local function popup()
    for _,item in ipairs(module.game_hud:native_model(now,true,600).awards.items)do
        if item.id=='R10'then return item end
    end
end
local function retained(sequence)
    for _,entry in ipairs(module.mission_history_snapshot().entries)do
        if entry.sequence==sequence then return entry end
    end
end
tick(40)
assert(chat_reads>0,'the real built reader never reached the owned native discovery rows')
assert(ribbon()==0 and total()==0 and not popup(),'first native sweep must baseline old notifications without R10')
-- A changed early slot may already have been read in the current partial sweep;
-- allow that partial cycle plus one complete 64-slot cycle to be published.
-- Exact low32 from the real 2026-10-16 discovery: Light Nest remains eligible.
notice(1,'本人',0x1166A22E);tick(32)
assert(ribbon()==1 and total()==1,'new unique local native discovery did not reach R10 accounting: '
    ..tostring(ribbon())..'/'..tostring(total())..' reader='..tostring(state.recon_status and state.recon_status.reason)
    ..' counter='..tostring(state.recon_status and state.recon_status.counter.reason)
    ..' scanned='..tostring(state.recon_status and state.recon_status.reader.rows_scanned))
local first=popup();assert(first and first.count==1 and first.total==1,'R10 acquisition missed actual HUD notification pipeline')
assert(retained(state.sequence).ribbons.recon==1,'R10 was not included in current mission history')
local first_sequence=state.sequence
notice(6,'本人',16*U32+0xDD55D46A)
notice(7,'本人',0x01F261DE,0xCD539459)
tick(32);assert(ribbon()==1 and total()==1,'special-place discoveries must not produce recon credit')
notice(2,'队友',0x101166A230,0xCD539459)
notice(3,'本人',0x101166A231,0x14DCC78A)-- User chat/non-discovery template cannot imitate a discovery.
tick(24);assert(ribbon()==1 and total()==1,'teammate or non-discovery text produced local recon credit')
local saved_descriptor=get(row_at(1)+0x220,345)
put(row_at(8)+0x220,saved_descriptor);clear_row(1)
tick(40);assert(ribbon()==1 and total()==1,'polling or moving one native descriptor replayed its R10')
-- A second destination for the same player must remain eligible.
notice(4,'本人',0x101166A232,0xCD539459);tick(32)
assert(ribbon()==2 and total()==2,'same NAME with a new DISCOVERY binding was permanently deduplicated')
-- Losing the chat surface must not disable independent combat/billing paths.
chat_available=false
stats.totals[SHOTS]=10;stats.totals[KILLS]=1
stats.sources['968211C0033DCE64']={[SHOTS]=10,[KILLS]=1}
tick(4)
assert(ribbon()==2 and total()==2,'unreadable discovery UI invented recon credit')
assert(state.total_cents==350 and state.kills==1,'chat reader failure broke native AR23 billing or kill accounting')
chat_available=true;tick(40)
assert(ribbon()==2 and total()==2,'unchanged retained discovery rows replayed after a read gap')
active=false;tick(3)
assert(saved.last_mission.ribbons.recon==2 and saved.career_awards_v1.totals.ribbons.recon==2)
assert(retained(first_sequence).ribbons.recon==2,'returning ship lost persisted R10 history')
-- The old native chat rows remain; the next mission must still baseline them.
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
actors={};active=true;tick(40)
assert(state.sequence~=first_sequence and ribbon()==0 and total()==2 and not popup(),
    'new mission failed to clear current R10 or replayed the prior chat backlog')
notice(5,'本人',0x101166A233);tick(32)
assert(ribbon()==1 and total()==3 and retained(state.sequence).ribbons.recon==1,
    'new mission fresh discovery did not resume normal R10 accounting')
active=false;tick(3)
assert(saved.career_awards_v1.totals.ribbons.recon==3)
assert(saved.mission_history_v1.entries[1].ribbons.recon==1 and saved.mission_history_v1.entries[2].ribbons.recon==2)
print('PASS: actual built native discovery -> R10 HUD/cumulative/history/save; old-row baseline, local vs teammate/non-discovery, same-player new target, moves/polling, unavailable UI with independent bills/kills, read-gap retention and ship/new-mission reset.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@recon-chat-integration'))()
