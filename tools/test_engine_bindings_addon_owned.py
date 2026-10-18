"""One actual 0.4.21 built-addon integration in our own Lua host only."""
from pathlib import Path
import ctypes as c
import hashlib
import json
import os
import re

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(r'external/HD2Runtime')
DLL=Path(r'G:/SteamLibrary/steamapps/common/Helldivers 2/bin/lua51.dll')
DLL_SHA='2c8720c9f446c848436ad993b1a88099d76f0b0b09df53689719b797c3039ce7'
READER_SHA='881948948430f7b7a4ad03127e066feb108b6ce4c4d0923d4e3e59b8c9611833'
def quote(value):return '"'+''.join('\\%03d'%b for b in str(value).replace('\\','/').encode())+'"'
def bind(d,name,args,result=None):
    f=getattr(d,name);f.argtypes=args;f.restype=result;return f
def main():
    addon=ROOT/'dist/addon.lua';body=addon.read_bytes()
    assert re.search(rb"local VERSION = '0\.4\.21'",body),'wait for built 0.4.21; do not run old addon'
    assert READER_SHA.encode()in body,'wait for final frozen reader in built addon'
    assert hashlib.sha256(DLL.read_bytes()).hexdigest()==DLL_SHA
    out=ROOT/'dist/engine-bindings-built-addon-owned-0.4.21';out.mkdir(exist_ok=True)
    folder=out/('store-'+str(os.getpid()));folder.mkdir(exist_ok=False)
    d=c.CDLL(str(DLL));bind(d,'luaL_newstate',[],c.c_void_p);bind(d,'luaL_openlibs',[c.c_void_p])
    bind(d,'lua_close',[c.c_void_p]);bind(d,'lua_pushinteger',[c.c_void_p,c.c_ssize_t])
    bind(d,'lua_pushcclosure',[c.c_void_p,c.c_void_p,c.c_int]);bind(d,'lua_setfield',[c.c_void_p,c.c_int,c.c_char_p])
    bind(d,'lua_getfield',[c.c_void_p,c.c_int,c.c_char_p]);bind(d,'lua_settop',[c.c_void_p,c.c_int])
    bind(d,'lua_tocfunction',[c.c_void_p,c.c_int],c.c_void_p)
    bind(d,'luaL_loadbuffer',[c.c_void_p,c.c_char_p,c.c_size_t,c.c_char_p],c.c_int)
    bind(d,'lua_pcall',[c.c_void_p,c.c_int,c.c_int,c.c_int],c.c_int)
    bind(d,'lua_tolstring',[c.c_void_p,c.c_int,c.c_void_p],c.c_char_p)
    sentinel_calls={'count':0};CALLBACK=c.CFUNCTYPE(c.c_int,c.c_void_p)
    @CALLBACK
    def sentinel(_):sentinel_calls['count']+=1;return 0
    state=d.luaL_newstate();assert state
    symbols=['lua_gettop','luaopen_math','luaopen_table','luaopen_string','luaopen_os','luaopen_debug']
    addresses=[]
    try:
        d.luaL_openlibs(state)
        d.lua_pushcclosure(state,c.cast(sentinel,c.c_void_p).value,0);d.lua_setfield(state,-10002,b'owned_sentinel')
        for i,name in enumerate(symbols,1):
            addr=c.cast(getattr(d,name),c.c_void_p).value
            for j in range(8):d.lua_pushinteger(state,0x12340000+j)
            d.lua_pushcclosure(state,addr,8);d.lua_setfield(state,-10002,('owned_fn_'+str(i)).encode())
            d.lua_getfield(state,-10002,('owned_fn_'+str(i)).encode())
            assert d.lua_tocfunction(state,-1)==addr;d.lua_settop(state,0);addresses.append(addr)
        args=[addon,RUNTIME,folder,json.dumps(addresses)]
        script=('arg={'+','.join(quote(v)for v in args)+'}\nreturn dofile('
            +quote(ROOT/'tests/test_engine_bindings_addon_owned.lua')+')').encode()
        status=d.luaL_loadbuffer(state,script,len(script),b'=built_engine_bindings_owned')
        if status==0:status=d.lua_pcall(state,0,1,0)
        value=d.lua_tolstring(state,-1,None);text=value.decode('utf8')if value else '<no result>'
        if status:raise AssertionError(text)
        report=json.loads(text)
    finally:d.lua_close(state)
    assert sentinel_calls['count']==1,'owned C-call detector expected exactly one sentinel call'
    report.update(dll_sha256=DLL_SHA,reader_sha256=READER_SHA,addon_sha256=hashlib.sha256(body).hexdigest(),
        owned_pid=os.getpid(),sentinel_calls=sentinel_calls['count'],expected_c_api_symbols=symbols,
        saved_fixture_folder=str(folder),installed=False,published=False)
    zip_path=ROOT/'dist/HD2-War-Cost-Ledger-0.4.21.zip'
    if zip_path.exists():report['zip_sha256']=hashlib.sha256(zip_path.read_bytes()).hexdigest()
    path=out/('verification-'+str(os.getpid())+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'cases':report['count'],'version':report['version'],
        'target_callbacks_executed':report['counts']['target_callbacks_executed'],
        'addon_sha256':report['addon_sha256'],'report':str(path)},ensure_ascii=False))
if __name__=='__main__':main()
