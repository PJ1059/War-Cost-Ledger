"""Validate the Lua native-page loader inside this Python process only."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from build import lua_table
from test import run_lua
from hit_bridge_owned import OwnedBridge

def run(profile_path,output):
    output.mkdir(parents=True,exist_ok=True)
    profile=json.loads(profile_path.read_text(encoding='utf8'))
    with OwnedBridge(capacity=8) as owner:
        image=owner._allocate(0x4744000,executable=False)
        failure=owner._procedure(bytes.fromhex('b800010000c3'),ctypes.c_uint32,
            ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint64,unwind=bytes.fromhex('01000000'))
        material=output/'owned-image-and-profile.lua'
        material.write_text('return '+lua_table({'image':{'base':image,'size':0x4744000},'profile':profile,
            'rtl_add_failure':ctypes.cast(failure,ctypes.c_void_p).value}),encoding='utf8')
        run_lua(ROOT/'tests/test_native_hit_package.lua',ROOT,
            Path('external/HD2Runtime'),material)
    files=['src/native-hit-package.lua','src/native-hit-connector.lua','tests/test_native_hit_package.lua','tools/native/test_hit_package.py']
    report={'status':'PASS','origin':'own_process_LuaJIT_private_pages_not_game',
        'game_reads':0,'game_writes':0,'game_patch':False,'thread_paused':False,
        'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        'entries':len(profile['entries']),'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'PASS','report':str(output/'verification.json')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.profile.resolve(),a.output.resolve())
