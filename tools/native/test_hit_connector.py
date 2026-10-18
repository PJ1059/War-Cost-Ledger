"""Owned queue kept alive while HD2's LuaJIT calls its real native drain."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from test import run_lua
from hit_bridge_owned import OwnedBridge

def run():
    output=ROOT/'dist/hit-native-ffi-consumer-owned-20261012'
    output.mkdir(exist_ok=True)
    with OwnedBridge(capacity=8,epoch=7,local_peer=0xFEDCBA9876543210) as bridge:
        for delta in (-1.,0.,1.):
            assert bridge.publish(bridge.record(capture_flags=511,target_kind=1,native_branch=1,
                selected_ap=4.,armour=3.,factor=1.,ap_delta=delta))==1
        assert bridge.publish(bridge.record(capture_flags=323,target_kind=1,native_branch=2))==1
        handle={'abi':1,'stride':96,'bridge':bridge.base,
                'consumer':ctypes.cast(bridge.consumer,ctypes.c_void_p).value,'capacity':8,
                'epoch':'0000000000000007','peer':'FEDCBA9876543210'}
        from build import lua_table
        description=output/'owned-handle.lua';description.write_text('return '+lua_table(handle),encoding='utf8')
        run_lua(ROOT/'tests/test_native_hit_connector.lua',ROOT,
            Path('external/HD2Runtime'),description)
        assert bridge.stats()['count']==0
    files=['src/native-hit-connector.lua','tests/test_native_hit_connector.lua',
           'tools/native/test_hit_connector.py','tools/native/hit_bridge_owned.py']
    report={'status':'PASS','origin':'owned_same_process_native_ffi_fixture_not_game',
        'game_reads':0,'game_writes':0,'game_connector_installed':False,'buffer_bytes':6144,
        'maximum_records_per_step':64,'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'PASS','report':str(output/'verification.json')}))

if __name__=='__main__':run()
