-- Synthetic native buffers only; this does NOT prove live game hit semantics.
local module_path, runtime_path = assert(arg[1]), assert(arg[2])
package.preload['hd2runtime/core/bytes'] = function() return dofile(runtime_path .. '/core/bytes.lua') end
local b = require('hd2runtime/core/bytes')
local view_api = dofile(runtime_path .. '/runtime/native_view.lua')
local reader = dofile(module_path)
local L, tests = reader.layout, 0
local function check(name, fn)
    local ok, why = pcall(fn)
    assert(ok, name .. ': ' .. tostring(why)); tests = tests + 1; print('PASS ' .. name)
end
local function u32(n) return b.encode(n, 'u32') end
local function ptr(n) return u32(n % 4294967296) .. u32(math.floor(n / 4294967296)) end
local function patch(bytes, offset, insert)
    return bytes:sub(1, offset) .. insert .. bytes:sub(offset + #insert + 1)
end
local function record(target, kind, lo, hi, opts)
    opts = opts or {}
    local raw = string.rep('\0', L.stride)
    for at, value in pairs({[0]=target, [4]=kind, [8]=5, [0x0C]=0xABCDEF12,
        [0x10]=17, [0x14]=19, [0x18]=lo, [0x1C]=hi, [0x20]=0x11112222,
        [0x60]=0xDEADBEEF}) do raw = patch(raw, at, u32(value)) end
    raw = patch(raw, 0x2C, b.encode(opts.damage or 0, 'i32'))
    raw = patch(raw, 0x3C, opts.distance_bits and u32(opts.distance_bits) or b.encode(55.25, 'f32'))
    raw = patch(raw, 0x40, b.encode(-2.5, 'f32'))
    return raw
end
local function fixture(rows, opts)
    opts = opts or {}
    local f = {game=0x10000000, system=0x30000000, user=0x40000000, count=#rows,
        lo=0xFEEDBEEF, hi=0xFACED123, calls={}, pin_calls=0, fills=0, rows=table.concat(rows)}
    local function read(address, size)
        f.calls[#f.calls+1] = {address=address, size=size}
        if f.fail == address then return nil end
        if address == f.system + L.queue then f.fills = f.fills+1 end
        local segments = {{f.game+L.system_global,ptr(f.system)}, {f.game+L.local_user_global,ptr(f.user)},
            {f.system+L.queue_count,u32(f.count)}, {f.user+L.local_peer,u32(f.lo)..u32(f.hi)},
            {f.system+L.queue,f.rows}}
        for _, pair in ipairs(segments) do
            local at = address-pair[1]
            if at >= 0 and at+size <= #pair[2] then
                if f.change_count and address == f.system+L.queue_count and f.fills > 0 then
                    return u32(f.count+1)
                end
                local result = pair[2]:sub(at+1,at+size)
                return f.short == address and result:sub(1,#result-1) or result
            end
        end
    end
    local view = view_api.new({read=read})
    view.proves = function(address, hex)
        f.pin_calls = f.pin_calls+1
        if f.bad_pin == address then return false end
        for _, pin in ipairs(reader.pins) do if address == f.game+pin[1] then return hex == pin[2] end end
        error('unlisted pin')
    end
    f.world = {game=f.game,view=view}
    f.schema = {source={gameDllSha256=opts.hash or reader.source.game_sha256}}
    f.api = reader.create({open=function() if f.unavailable then return nil,'OFFLINE' end; return f.world end},f.schema)
    return f
end
local LO, HI = 0xFEEDBEEF, 0xFACED123
check('decodes native queue fields and exact u64 creditor without inventing classification',function()
    local f = fixture({record(42,1,LO,HI,{damage=-1}),record(43,0,LO,HI-1,{damage=7})})
    local x = assert(f.api.sample())
    assert(x.sampled_count==2 and x.observed_queue_count==2 and not x.truncated)
    assert(not x.classification_verified and not x.complete_stream)
    local a,c = x.records[1],x.records[2]
    assert(a.target==42 and a.source_kind==1 and a.hit_actor==0xABCDEF12)
    assert(a.dealer_goid==17 and a.owner_goid==19 and a.damage==-1)
    assert(a.creditor_lo==LO and a.creditor_hi==HI and a.local_player and not c.local_player)
    assert(a.unknown_key==0x11112222 and a.unknown_60==0xDEADBEEF)
    assert(a.telemetry_distance==55.25 and a.telemetry_height==-2.5)
    assert(not a.verified and a.direct==nil and a.result==nil and a.ricochet==nil)
    assert(a.attack==nil and a.count==nil and c.damage==7)
end)
check('bounded prefix reports truncation; no hidden draining or hit counting',function()
    local rows={}; for i=1,100 do rows[i]=record(i,0,LO,HI) end
    local f=fixture(rows)
    local x=assert(f.api.sample())
    assert(x.sampled_count==16 and x.observed_queue_count==100 and x.truncated)
    local queue_read
    for _,call in ipairs(f.calls) do if call.address==f.system+L.queue then queue_read=call.size end end
    assert(queue_read==16*0x70)
    x=assert(f.api.sample(64)); assert(x.sampled_count==64 and x.records[64].target==64)
end)
check('cached object and buffer; repeated queue snapshot does not become a new contact',function()
    local f=fixture({record(42,1,LO,HI)})
    local x=assert(f.api.sample()); local a=x.records[1]; local pins=f.pin_calls
    a.verified,a.result,a.direct,a.count=true,'ricochet',true,500
    local y=assert(f.api.sample())
    assert(y==x and y.records[1]==a and f.pin_calls==pins)
    assert(not a.verified and a.result==nil and a.direct==nil and a.count==nil)
    assert(y.observed_queue_count==1 and y.sampled_count==1)
end)
check('empty queue does not read entries; prior sample visible count clears',function()
    local f=fixture({record(42,0,LO,HI)}); local x=assert(f.api.sample())
    f.count=0; local fills=f.fills
    assert(f.api.sample()==x and x.sampled_count==0 and x.observed_queue_count==0)
    assert(f.fills==fills and not x.truncated)
end)
check('changed count rejects whole sample',function()
    local f=fixture({record(42,0,LO,HI)}); f.change_count=true
    local x,why=f.api.sample(); assert(x==nil and why=='SAMPLE_CHANGED')
end)
check('unreadable and short data reject rather than returning zero hits',function()
    for _,kind in ipairs({'fail','short'}) do
        local f=fixture({record(42,0,LO,HI)})
        f[kind]=f.system+L.queue
        local x,why=f.api.sample(); assert(x==nil and why=='QUEUE_UNREADABLE')
    end
end)
check('invalid bounds and local peer reject before bulk read',function()
    for _,value in ipairs({0,-1,0.5,65}) do
        local f=fixture({record(42,0,LO,HI)})
        local x,why=f.api.sample(value); assert(x==nil and why=='INVALID_LIMIT' and #f.calls==0)
    end
    local f=fixture({record(42,0,LO,HI)}); f.count=4097
    local x,why=f.api.sample(); assert(x==nil and why=='QUEUE_COUNT_INVALID' and f.fills==0)
    f.count=1; f.lo,f.hi=0,0; x,why=f.api.sample()
    assert(x==nil and why=='LOCAL_PEER_UNREADABLE' and f.fills==0)
end)
check('build mismatch and code mismatch never read the queue; proof reruns after world replacement',function()
    local f=fixture({}, {hash='OTHER'})
    local x,why=f.api.sample(); assert(x==nil and why=='BUILD_PROFILE_MISMATCH' and f.pin_calls==0)
    f=fixture({}); f.bad_pin=f.game+reader.pins[3][1]
    x,why=f.api.sample(); assert(x==nil and why=='NATIVE_CODE_MISMATCH_129E430' and #f.calls==0)
    f=fixture({}); assert(f.api.sample()); local pins=f.pin_calls
    f.world={game=f.game,view=f.world.view}; assert(f.api.sample()); assert(f.pin_calls==pins*2)
    f.unavailable=true; x,why=f.api.sample(); assert(x==nil and why=='OFFLINE')
end)
check('non-finite telemetry stays unknown and kind 1 does not imply initial ricochet',function()
    local f=fixture({record(42,1,LO,HI,{distance_bits=0x7FC00000})})
    local x=assert(f.api.sample()); local a=x.records[1]
    assert(a.telemetry_distance==nil and a.source_kind==1 and a.ricochet==nil and a.result==nil)
end)
print(string.format('native hit reader: %d synthetic checks passed; live classification UNVERIFIED',tests))
