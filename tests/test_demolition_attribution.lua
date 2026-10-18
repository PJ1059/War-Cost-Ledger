local create=dofile(assert(arg[1]))
local function blast(at,owner,x,radius)
    return {time=at,position={x=x or 0,y=0,z=0},radius=radius or 10,local_player=owner}
end
local function hole(id,at,x)
    return {id=id,time=at,position={x=x or 0,y=0,z=0},kind='bug_hole',stage=1}
end
local function one(api,at)
    local awards=api:advance(at);assert(#awards==1,'expected one inferred closure');return awards[1]
end
local api=create()
assert(api:observe_explosion(blast(9.8,true),9.8))
assert(api:observe_closure(hole('a',10),10))
local award=one(api,10)
assert(award.id=='a' and award.confidence=='inferred' and not award.creditor_verified and award.ribbon_eligible)
assert(award.evidence.wait==2.25 and award.evidence.lookback==2.5 and award.evidence.late_window==0.35)
assert(award.evidence.local_explosion_count==1 and award.evidence.conflict_count==0)
assert(#api:advance(12.5)==0 and select(2,api:observe_closure(hole('a',12.5),12.5))=='CLOSURE_DUPLICATE')

for _,owner in ipairs({false,'unknown'}) do
    api=create()
    api:observe_explosion(blast(9.8,true),9.8)
    api:observe_closure(hole('contested',10),10)
    local other=blast(10.25,nil)
    if owner==false then other.local_player=false end
    api:observe_explosion(other,10.25)
    local contested=one(api,10.25)
    assert(contested.evidence.conflict_count==1 and api.diagnostics.conflicts==1,
        'other-player and unconfirmed ownership are recorded without vetoing local coverage')
end

api=create()
api:observe_explosion(blast(9.9,true),9.9)
local unknown=blast(9.95,nil,45);unknown.radius=nil
api:observe_explosion(unknown,9.95)
api:observe_closure(hole('unknown-radius',10),10)
assert(one(api,10).evidence.conflict_count==1,'unknown competitor radius remains visible in evidence')

api=create()
api:observe_explosion(blast(7.49,false),7.49)
api:observe_explosion(blast(9.8,true),9.8)
api:observe_explosion(blast(9.9,false,11),9.9)
api:observe_closure(hole('uncontested',10),10)
one(api,12.25)

for _,offset in ipairs({0.3,0.36}) do
    api=create()
    api:observe_closure(hole('late',10),10)
    api:observe_explosion(blast(10+offset,true),10+offset)
    local awards=api:advance(12.25)
    assert(#awards==(offset==0.3 and 1 or 0),'only narrow delivery skew may follow closure')
end
api=create()
api:observe_explosion(blast(7.49,true),7.49)
api:observe_closure(hole('too-old',10),10)
assert(#api:advance(12.25)==0,'explosions before the closure lookback cannot grant')

api=create()
api:observe_explosion(blast(9.9,true),9.9)
local foreign=hole('known-other',10);foreign.responsible_local=false
assert(select(2,api:observe_closure(foreign,10))=='EXPLICIT_OTHER_RESPONSIBILITY')
assert(#api:advance(12.25)==0)
assert(select(2,api:observe_closure(hole('known-other',12.25),12.25))=='CLOSURE_DUPLICATE')

api=create()
local invalid=blast(9.9,true);invalid.radius=nil
assert(api:observe_explosion(invalid,9.9),'unknown local radius uses BFV 9m fallback')
api:observe_closure(hole('no-radius',10),10)
assert(one(api,10).evidence.selected_explosion.radius==9)
for _,meters in ipairs({8.9,9.1})do
    api=create()
    api:observe_explosion(blast(9.9,true,0,1),9.9)
    api:observe_closure(hole('small-radius',10,meters),10)
    local found=api:advance(10)
    assert(#found==(meters<9 and 1 or 0),'known small explosions have minimum 9m, without exceeding it')
    if meters>9 then assert(#api:advance(12.25)==0)end
end
for _,edit in ipairs({function(e)e.kind='decoration'end,function(e)e.stage=0 end,
    function(e)e.stage=1.5 end,function(e)e.position.x=0/0 end,function(e)e.position.z=math.huge end,
    function(e)e.id=''end,function(e)e.time=11 end}) do
    api=create();local event=hole('invalid',10);edit(event)
    assert(select(2,api:observe_closure(event,10))=='INVALID_CLOSURE')
end
api=create()
api:observe_explosion(blast(9.8,true),9.8)
local missing=blast(9.9,nil);missing.position=nil
assert(select(2,api:observe_explosion(missing,9.9))=='EXPLOSION_POSITION_UNAVAILABLE')
assert(api:observe_closure(hole('position-gap',10),10))
one(api,10)

api=create()
api:observe_explosion(blast(9.9,false),9.9)
api:observe_closure(hole('foreign-only',10),10)
assert(#api:advance(10)==0 and #api:advance(12.25)==0,'foreign explosion alone never awards')
api=create()
api:observe_closure(hole('waiting',10),10)
assert(#api:advance(10)==0 and api.diagnostics.pending==1,'no local evidence waits instead of guessing')
api:observe_explosion(blast(10.2,true),10.2)
one(api,10.2)

api=create()
local source=blast(9.9,true);api:observe_explosion(source,9.9)
source.position.x=500;source.local_player=false;source.radius=1
local closed=hole('copied',10);api:observe_closure(closed,10);closed.position.x=500;closed.stage=0
one(api,12.25)

api=create()
api:observe_explosion(blast(9.9,true,0,30),9.9)
api:observe_closure(hole('first',10,0),10)
api:observe_closure(hole('second',10,20),10)
local awards=api:advance(12.25)
assert(#awards==2 and awards[1].id~=awards[2].id,'one blast may cover multiple independent holes')
assert(#api:advance(12.3)==0)

api=create({mission=1})
local scoped=blast(9.9,true);scoped.mission=1;api:observe_explosion(scoped,9.9)
local mismatch=hole('wrong-mission',10);mismatch.mission=2
assert(select(2,api:observe_closure(mismatch,10))=='MISSION_MISMATCH')
api:reset(2)
local reset_hole=hole('reused-id',1);reset_hole.mission=2;assert(api:observe_closure(reset_hole,1))
assert(#api:advance(3.25)==0,'reset removes previous mission explosions')
api:reset(3)
local new_blast=blast(0.9,true);new_blast.mission=3;api:observe_explosion(new_blast,0.9)
local new_hole=hole('reused-id',1);new_hole.mission=3;api:observe_closure(new_hole,1)
one(api,3.25)

api=create()
api:observe_explosion(blast(9.9,true),9.9)
api:observe_closure(hole('before-rewind',10),10)
assert(#api:advance(1)==0 and api.diagnostics.clock_rewinds==1 and api.diagnostics.pending==0)
assert(select(2,api:observe_closure(hole('before-rewind',1),1))=='CLOSURE_DUPLICATE')
api:observe_explosion(blast(3.6,true),3.6)
api:observe_closure(hole('after-rewind',3.7),3.7)
one(api,6)

api=create()
api:observe_explosion(blast(9.8,true),9.8)
api:observe_closure(hole('overflowed-window',10),10)
for i=1,96 do api:observe_explosion(blast(10+i/1000,true,0,10),10+i/1000) end
assert(api.diagnostics.overflows==1 and api.diagnostics.explosions==96)
one(api,10.1)
assert(select(2,api:observe_closure(hole('overflowed-window',12.25),12.25))=='CLOSURE_DUPLICATE')
api:advance(20)
api:observe_explosion(blast(20.1,true),20.1)
api:observe_closure(hole('clean-window',20.2),20.2)
one(api,22.5)

api=create()
api:observe_explosion(blast(9.9,true,0,1000),9.9)
api:observe_closure(hole('far-away',10,46.6),10)
assert(#api:advance(12.25)==0,'supplied radius cannot exceed supported 46.5m bound')
api=create()
api:observe_explosion(blast(9.9,true),9.9)
for i=1,64 do assert(api:observe_closure(hole('pending-'..i,10),10)) end
assert(select(2,api:observe_closure(hole('pending-full',10),10))=='CLOSURE_PENDING_LIMIT')
assert(#api:advance(12.25)==64)
assert(select(2,api:observe_closure(hole('pending-full',12.25),12.25))=='CLOSURE_DUPLICATE')

api=create()
for i=1,2048 do
    local at=i*3
    api:observe_closure(hole('seen-'..i,at),at)
    api:advance(at+2.25)
end
assert(select(2,api:observe_closure(hole('seen-overflow',6147),6147))=='CLOSURE_IDENTITY_LIMIT')
assert(select(2,api:observe_closure(hole('seen-1',6147),6147))=='CLOSURE_DUPLICATE')
print('PASS: reward-favoring inferred demolition: immediate local coverage, bounded waiting, competitor evidence, BFV 9m fallback, frozen input, one blast/many holes, dedupe, mission reset, clock rewind and bounded caches.')
