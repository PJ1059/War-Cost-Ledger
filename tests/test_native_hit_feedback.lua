-- Actual Runtime bytes decoder; records use the proposed observer ABI.
package.preload['hd2runtime/core/bytes']=function() return dofile(assert(arg[3])..'/core/bytes.lua') end
local b=require('hd2runtime/core/bytes')
local M=dofile(assert(arg[1]))
local feedback=dofile(assert(arg[2]))
local PEER,EPOCH='FEDCBA9876543210','0000000000000007'
local tests=0
local function check(name,fn)
    local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));tests=tests+1;print('PASS '..name)
end
local function u(n) return b.encode(n,'u32') end
local function q(s) return u(tonumber(s:sub(9,16),16))..u(tonumber(s:sub(1,8),16)) end
local function f(n) return b.encode(n,'f32') end
local function record(options)
    options=options or {}
    return q(options.seq or '0000000000000001')..q(options.epoch or EPOCH)..q(options.peer or PEER)
        ..q('0000000000000000')..u(options.projectile_id or 0)..u(options.damage_info_id or 0)..u(1)..u(123)..u(42)..u(99)
        ..u(options.effects or 0)..u(options.branch or 1)
        ..f(options.ap or 4)..f(options.armour or 3)..f(options.factor or 1)..f(0)
        ..u(options.kind or 0)..u(options.hostile==false and 0 or 1)..u(options.flags or 511)
        ..(options.delta_bytes or f(options.delta or 1))
end
local function transport(n,changes)
    local t={abi=1,stride=96,count=n,epoch=EPOCH,dropped='0000000000000000',connector_proven=true}
    for k,v in pairs(changes or {})do t[k]=v end
    return t
end
check('binary layout equals the 96-byte native record',function()
    local raw=record();assert(#raw==96)
    local r=M.decode(raw);assert(r.target==123 and r.source==42 and r.owner==99)
    assert(r.peer==PEER and r.epoch==EPOCH and r.delta==1 and r.source_kind==0)
    assert(M.decode(raw:sub(1,95))==nil)
end)
check('four classes use actual branch and native float delta',function()
    for _,case in ipairs({{-1,'blocked'},{0,'penetration'},{.999,'penetration'},{1,'full_penetration'}})do
        assert(M.classify(M.decode(record({delta=case[1]})),PEER,EPOCH).result==case[2])
    end
    local r=M.decode(record({branch=2,flags=323,delta_bytes=u(0x7fc00000)}))
    assert(M.classify(r,PEER,EPOCH).result=='ricochet')
    assert(M.classify(M.decode(record({branch=0})),PEER,EPOCH)==nil)
end)
check('native delta is not double recomputed from AP fields',function()
    local r=M.decode(record({ap=4,armour=3,delta=.9999999403953552}))
    assert(M.classify(r,PEER,EPOCH).result=='penetration')
end)
check('peer identity greater than 2^53 remains exact',function()
    assert(M.classify(M.decode(record({peer='FEDCBA9876543211'})),PEER,EPOCH)==nil)
    assert(M.classify(M.decode(record({epoch='0000000000000008'})),PEER,EPOCH)==nil)
    assert(not pcall(M.new,{peer='0000000000000000',epoch=EPOCH,accept=function()end}))
    assert(not pcall(M.new,{peer=PEER,epoch='0000000000000000',accept=function()end}))
end)
check('every missing normal field is unknown; no factor fallback',function()
    for _,flag in pairs(M.flags)do
        if flag<=256 then
            local r=M.decode(record({flags=511-flag}))
            assert(M.classify(r,PEER,EPOCH)==nil)
        end
    end
    for _,effect in ipairs({1,2,4,8})do
        assert(M.classify(M.decode(record({effects=effect,factor=1})),PEER,EPOCH)==nil)
    end
end)
check('optional concrete damage ID needs new producer validity',function()
    local old=M.decode(record({damage_info_id=220}))
    assert(old.damage_info_id==nil and M.classify(old,PEER,EPOCH).damage_info_id==nil)
    for _,id in ipairs({0,220,428,4294967295})do
        local r=M.decode(record({damage_info_id=id,flags=1023}))
        local c=assert(M.classify(r,PEER,EPOCH))
        assert(r.damage_info_id==id and c.damage_info_id==id and c.count==1)
    end
end)
check('attribution-only contact keeps classification with zero hit count',function()
    for _,case in ipairs({{-1,'blocked'},{0,'penetration'},{1,'full_penetration'}})do
        local c=assert(M.classify(M.decode(record({damage_info_id=220,flags=2047,delta=case[1]})),PEER,EPOCH))
        assert(c.attribution_only==true and c.count==0 and c.damage_info_id==220 and c.result==case[2])
    end
    local r=M.decode(record({damage_info_id=220,flags=1859,branch=2}))
    local c=assert(M.classify(r,PEER,EPOCH))
    assert(c.count==0 and c.result=='ricochet' and c.damage_info_id==220)
    assert(M.classify(M.decode(record({flags=1535})),PEER,EPOCH)==nil)
end)
check('optional native projectile type needs its own flag and does not reinterpret legacy slot bytes',function()
    local legacy=M.decode(record({projectile_id=312,damage_info_id=380,flags=1023}))
    assert(legacy.projectile_id==nil and M.classify(legacy,PEER,EPOCH).projectile_id==nil)
    for _,case in ipairs({{3071,1,1},{4095,1,0},{2883,2,1},{3907,2,0}})do
        local r=M.decode(record({projectile_id=312,damage_info_id=380,flags=case[1],branch=case[2]}))
        local contact=assert(M.classify(r,PEER,EPOCH))
        assert(r.projectile_id==312 and contact.projectile_id==312 and contact.damage_info_id==380)
        assert(contact.count==case[3] and contact.direct and contact.local_player)
    end
end)
check('unknown mode or target cannot award; raw kind is not attack mode',function()
    assert(M.classify(M.decode(record({hostile=false})),PEER,EPOCH)==nil)
    assert(M.classify(M.decode(record({flags=255,kind=0})),PEER,EPOCH)==nil)
    assert(M.classify(M.decode(record({kind=987})),PEER,EPOCH).result=='full_penetration')
end)
check('nonfinite AP results never pass as armour categories',function()
    assert(M.classify(M.decode(record({delta_bytes=u(0x7f800000)})),PEER,EPOCH)==nil)
    assert(M.classify(M.decode(record({delta_bytes=u(0x7fc00000)})),PEER,EPOCH)==nil)
end)
check('exact 64-bit transport order rejects duplicate deliveries',function()
    local count=0
    local api=M.new({peer=PEER,epoch=EPOCH,accept=function()count=count+1 end})
    local raw=record({seq='0020000000000001'})..record({seq='0020000000000002'})
    assert(api:consume(raw,1,transport(2)));assert(count==2)
    assert(api:consume(raw,2,transport(2)));assert(count==2 and api.stale==2)
    assert(api.last_sequence=='0020000000000002')
end)
check('transport identity, byte length and batch cap are required',function()
    local api=M.new({peer=PEER,epoch=EPOCH,accept=function()error('must not run')end})
    for _,change in ipairs({{connector_proven=false},{count=65},{stride=112},{abi=2},{epoch='0000000000000008'}})do
        assert(api:consume(record(),1,transport(1,change))==nil)
    end
    assert(api:consume(record():sub(1,95),1,transport(1))==nil)
    assert(api.last_sequence=='0000000000000000')
end)
check('drop marks observed counts partial and never invents missing events',function()
    local n=0;local api=M.new({peer=PEER,epoch=EPOCH,accept=function()n=n+1 end})
    assert(api:consume(record(),1,transport(1,{dropped='0000000000000004'})))
    assert(n==1 and api.partial)
    assert(api:consume('',2,transport(0,{dropped='0000000000000003'}))==nil)
    assert(n==1)
end)
check('unclassified records advance sequence without becoming a guessed class',function()
    local n=0;local api=M.new({peer=PEER,epoch=EPOCH,accept=function()n=n+1 end})
    assert(api:consume(record({effects=2}),1,transport(1)))
    assert(n==0 and api.unclassified==1 and api.last_sequence=='0000000000000001')
    assert(api:consume(record(),2,transport(1)));assert(n==0 and api.stale==1)
end)
check('native decoder feeds the existing two-second collection model',function()
    local model=feedback()
    local api=M.new({peer=PEER,epoch=EPOCH,accept=function(c,t)return model:accept(c,t)end})
    local raw=record({delta=-1})..record({seq='0000000000000002',delta=0})
    assert(api:consume(raw,1,transport(2)))
    assert(model.recent.blocked==1 and model.recent.penetration==1 and model.cumulative.total==2)
    assert(model:visible(2.999,false,true)~=nil and model:visible(3,false,true)==nil)
    assert(model:visible(3,true,true).total==2)
    assert(api:consume('',.5,transport(0))==nil)
end)
print('Native hit feedback: '..tests..' checks passed; producer is not installed')
