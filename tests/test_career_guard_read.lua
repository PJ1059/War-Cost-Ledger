-- Safe Runtime boundary shared with the HUD+ 0.2.4 lifetime guard.
-- No process access: only the two proven ranges may reach this owned reader.
local create=dofile(assert(arg[1]))
local g={parent=65536,alpha_address=0x50000,controller=65536,gui_context=0x40000,
    parent_parent=0x41000,local_peer='0000000000000011',position={0,0},width=420,height=747,
    root={x=0,y=0,width=1920,height=1080,sx=1,sy=1}}
local calls,mode=0,'ok'
local world={view={read=function(at,n)
    calls=calls+1
    assert((at==65536 and n==256)or(at==0x50000 and n==4))
    if mode=='error'then error('owned unreadable page')end
    if mode=='nil'then return nil end
    return string.rep('a',mode=='short'and n-1 or n)
end}}
local api=create({reader=function()return {read=function()return g end}end,
    records=function()return {totals={}}end,
    model={layout=function()return {shown=true,width=420,height=747,nav_controls={},items={},sections={}}end}})
api:step(1,world,{state=3,mission=false},{{['local']=true,peer=g.local_peer}})
local snapshot=assert(api:snapshot());local guard=assert(snapshot.guard_read)
assert(#guard(65536,256)==256 and #guard(0x50000,4)==4 and calls==2)
for _,range in ipairs({{65536,4},{0x50000,256},{65544,256},{0x50004,4},{65536,0},{65536,257}})do
    assert(guard(range[1],range[2])==nil)
end
assert(calls==2,'unproven addresses and sizes never reach Runtime IO')
g.parent=65544;g.alpha_address=0x50004
assert(guard(g.parent,256)==nil and guard(g.alpha_address,4)==nil and calls==2,
    'a later mutable geometry object cannot broaden a retained snapshot')
for _,failure in ipairs({'nil','short','error'})do
    mode=failure
    assert(guard(65536,256)==nil and guard(0x50000,4)==nil)
end
mode='ok';assert(#guard(65536,256)==256)
assert(api:snapshot()==snapshot,'guard failures do not mutate the cached layout')
print('PASS Career guard read: two exact frozen ranges, safe nil/short/error handling, no arbitrary IO or layout mutation.')
