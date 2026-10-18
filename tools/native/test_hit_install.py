"""Own-process private image and actual production Lua native install adapter."""
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


def run(profile_path,transaction_path,control_path,output):
    output.mkdir(parents=True,exist_ok=True)
    profile=json.loads(profile_path.read_text(encoding='utf8'))
    transaction=json.loads(transaction_path.read_text(encoding='utf8'))
    control=json.loads(control_path.read_text(encoding='utf8'))
    profile['entries']+=control['entries']+transaction['entries']
    with OwnedBridge(capacity=8) as owner:
        image=owner._allocate(0x4744000,executable=False)
        pages=set()
        for site in profile['sites']:
            at=image+site['rva'];pin=bytes.fromhex(site['pin_hex'])
            ctypes.memmove(at,pin,len(pin));pages.add(at&~4095)
        old=ctypes.c_uint32()
        for page in pages:
            assert owner.kernel.VirtualProtect(ctypes.c_void_p(page),4096,0x20,ctypes.byref(old))
        fixture=output/'owned-image-profile-and-transaction.lua'
        fixture.write_text('return '+lua_table({'image':{'base':image,'size':0x4744000},
            'profile':profile,'transaction':transaction}),encoding='utf8')
        run_lua(ROOT/'tests/test_native_hit_install.lua',ROOT,
            Path('external/HD2Runtime'),fixture)
    paths=['src/native-hit-install.lua','src/native-hit-package.lua','src/native-hit-connector.lua',
           'tools/native/hit_run_control_owned.py','tests/test_native_hit_install.lua','tools/native/test_hit_install.py']
    report={'status':'PASS','origin':'own_process_actual_game_LuaJIT_private_image_not_game',
        'game_reads':0,'game_writes':0,'game_patch':False,'native_entries':len(profile['entries']),
        'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        'transaction_sha256':hashlib.sha256(transaction_path.read_bytes()).hexdigest(),
        'control_sha256':hashlib.sha256(control_path.read_bytes()).hexdigest(),
        'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'PASS','report':str(output/'verification.json')}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['profile','transaction','control','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.profile,a.transaction,a.control,a.output)
