local M=assert(loadfile(arg[1]))()
local cases=0
local LOCAL,OTHER='0102030405060708','1112131415161718'
local function row(key,owned,template)
    return{signature=key,system_discovery=true,template=template or 0x92871A58,
        local_player=owned~=false,peer=owned~=false and LOCAL or OTHER}
end
local function sample(rows,identity)return{complete=true,identity=identity or'mission_chat',local_peer=LOCAL,rows=rows or{}}end
local context={mission=true,sequence=27}
local function test(fn)fn();cases=cases+1 end
test(function()
    local r=M.new();r:update(sample(),context)
    local poi=row('poi');poi.discovery_kind='point_of_interest'
    assert(r:update(sample({poi}),context)==0)
    assert(r:update(sample({poi,row('nest'),row('unknown-target')}),context)==2)
    assert(r:update(sample({poi,row('nest'),row('unknown-target')}),context)==0)
    assert(r.diagnostics.total==2)
end)
test(function()
    local r=M.new();assert(r:update(sample({row('old')}),context)==0)
    assert(r:update(sample({row('old')}),context)==0)
    assert(r:update(sample({row('old'),row('new')}),context)==1)
    assert(r:update(sample({row('old'),row('new')}),context)==0)
    for i=1,8 do assert(r:update(sample({row('new'),row('old')}),context)==0)end
    assert(r.diagnostics.total==1)
end)
test(function()
    local r=M.new();r:update(sample(),context)
    local chat=row('fake');chat.system_discovery=false
    local wrong=row('wrong',true,0x14DCC78A)
    local teammate=row('theirs',false)
    for i=1,3 do assert(r:update(sample({chat,wrong,teammate}),context)==0)end
end)
test(function()
    local r=M.new();r:update(sample(),context)
    local both={row('NAME+target1'),row('NAME+target2',true,0xCD539459)}
    assert(r:update(sample(both),context)==2);assert(r:update(sample(both),context)==0)
    assert(r:update(sample({row('NAME+target1')}),context)==0)
    assert(r:update(sample(both),context)==1)-- Accepted disappear/reappear inference.
end)
test(function()
    local r=M.new();r:update(sample({row('same')}),context)
    local twice={row('same'),row('same')}
    assert(r:update(sample(twice),context)==1);assert(r:update(sample(twice),context)==0)
    r:update(sample(),context);r:update(sample(),context)
    assert(r:update(sample({row('same')}),context)==1)-- Disappear/reappear inference, not unique event proof.
    assert(r:update(sample({row('same')}),context)==0)
end)
test(function()
    local r=M.new();local unresolved=row('old');unresolved.local_player=false;unresolved.peer=nil
    r:update(sample({unresolved}),context)
    assert(r:update(sample({row('old')}),context)==0)
    assert(r:update(sample({row('old')}),context)==0)-- Later NAME resolution must not replay the baseline.
    local weird=row('peer-conflict');weird.peer=OTHER
    r:update(sample({weird}),context);assert(r:update(sample({weird}),context)==0)
end)
test(function()
    local r=M.new();r:update(sample(),context);assert(r:update(sample({row('new')}),context)==1)
    assert(r:update(nil,context)==0)
    assert(r:update(sample({row('new')}),context)==0)
    assert(r:update(sample({row('old')},'new-hud'),context)==0)
    assert(r:update(sample({row('old')},'new-hud'),context)==0)
    assert(r:update(sample(),{mission=false,sequence=27})==0)
    assert(r:update(sample({row('old')}),{mission=true,sequence=28})==0)
    assert(r:update(sample({row('old')}),{mission=true,sequence=29})==0)
end)
test(function()
    local r=M.new();r:update(sample(),context)
    local many={};for i=1,64 do many[#many+1]=row('target'..i)end
    assert(r:update(sample(many),context)==64);assert(r:update(sample(many),context)==0)
    many[65]=row('over-limit');assert(r:update(sample(many),context)==0)
    assert(r.diagnostics.reason=='WAITING_FOR_SWEEP')
end)
print('recon chat: '..cases..' cases passed')
