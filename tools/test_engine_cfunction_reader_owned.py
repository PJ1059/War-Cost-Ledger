"""Run reader in our own LuaState, with C closure addresses from this same DLL."""
from pathlib import Path
import ctypes as c
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(r'external/HD2Runtime')
DLL=Path(r'G:/SteamLibrary/steamapps/common/Helldivers 2/bin/lua51.dll')
EXPECTED='2c8720c9f446c848436ad993b1a88099d76f0b0b09df53689719b797c3039ce7'
def quote(value):
    return '"'+''.join('\\%03d'%b for b in str(value).replace('\\','/').encode('utf8'))+'"'
def bind(d,name,args,result=None):
    f=getattr(d,name);f.argtypes=args;f.restype=result;return f
def main():
    assert hashlib.sha256(DLL.read_bytes()).hexdigest()==EXPECTED
    assert (ROOT/'src/engine-cfunction-reader.lua').read_bytes()==(RUNTIME/'runtime/engine_cfunction.lua').read_bytes()
    d=c.CDLL(str(DLL))
    bind(d,'luaL_newstate',[],c.c_void_p);bind(d,'luaL_openlibs',[c.c_void_p]);bind(d,'lua_close',[c.c_void_p])
    bind(d,'lua_pushinteger',[c.c_void_p,c.c_ssize_t]);bind(d,'lua_pushcclosure',[c.c_void_p,c.c_void_p,c.c_int])
    bind(d,'lua_setfield',[c.c_void_p,c.c_int,c.c_char_p]);bind(d,'lua_getfield',[c.c_void_p,c.c_int,c.c_char_p])
    bind(d,'lua_tocfunction',[c.c_void_p,c.c_int],c.c_void_p);bind(d,'lua_settop',[c.c_void_p,c.c_int])
    bind(d,'luaL_loadbuffer',[c.c_void_p,c.c_char_p,c.c_size_t,c.c_char_p],c.c_int)
    bind(d,'lua_pcall',[c.c_void_p,c.c_int,c.c_int,c.c_int],c.c_int)
    bind(d,'lua_tolstring',[c.c_void_p,c.c_int,c.c_void_p],c.c_char_p)
    state=d.luaL_newstate();assert state
    names=['lua_gettop','luaopen_math','luaopen_table','luaopen_string','luaopen_os','luaopen_debug']
    expected=[];counter={'calls':0}
    CALLBACK=c.CFUNCTYPE(c.c_int,c.c_void_p)
    @CALLBACK
    def callback(_):counter['calls']+=1;return 0
    try:
        d.luaL_openlibs(state)
        for n in range(8):d.lua_pushinteger(state,0x56780000+n)
        d.lua_pushcclosure(state,c.cast(callback,c.c_void_p).value,8)
        d.lua_setfield(state,-10002,b'owned_callback')
        for i,name in enumerate(names,1):
            addr=c.cast(getattr(d,name),c.c_void_p).value
            for n in range(8):d.lua_pushinteger(state,0x12340000+n)
            d.lua_pushcclosure(state,addr,8);d.lua_setfield(state,-10002,('owned_fn_'+str(i)).encode())
            d.lua_getfield(state,-10002,('owned_fn_'+str(i)).encode())
            assert d.lua_tocfunction(state,-1)==addr;d.lua_settop(state,0);expected.append(addr)
        script=('arg={'+','.join(quote(v)for v in [ROOT/'src/engine-cfunction-reader.lua',RUNTIME,
            json.dumps(expected)])+'}\nreturn dofile('+quote(ROOT/'tests/test_engine_cfunction_reader_owned.lua')+')').encode()
        status=d.luaL_loadbuffer(state,script,len(script),b'=owned_engine_identity_reader')
        if status==0:status=d.lua_pcall(state,0,1,0)
        raw=d.lua_tolstring(state,-1,None);text=raw.decode('utf8')if raw else '<no result>'
        if status:raise AssertionError(text)
        report=json.loads(text)
    finally:d.lua_close(state)
    assert counter['calls']==0
    report['fixed_callback_calls']=counter['calls']
    report['dll_sha256']=EXPECTED
    report['reader_sha256']=hashlib.sha256((ROOT/'src/engine-cfunction-reader.lua').read_bytes()).hexdigest()
    report['expected_c_api_symbols']=names
    report['byteexact_runtime_copy']=True
    report['raw_sampling_limit_bytes']=288
    report['actual_hash_file_bytes']=DLL.stat().st_size
    out=ROOT/'dist/engine-cfunction-reader-owned-20261012';out.mkdir(exist_ok=True)
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'cases':report['count'],'reader_sha256':report['reader_sha256'],
        'report':str(out/'verification.json')},ensure_ascii=False))
if __name__=='__main__':main()
