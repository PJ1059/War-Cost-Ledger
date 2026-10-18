"""Only the actual declaration/UW of stored function-address17A9630.

Fixed 28B initializer LEA+pair-writes, not a guessed callback invocation.
Private existing Ship67988/PE/module/fingerprint/state gates;16KiB64IO2s.
"""
import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-initializer-metadata-capture.py'
PARENT_SHA='3e63bc84276602f0dc7f1fe0babd489f9f420cc21fbc20592229158cd204a6fa'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CALLBACK_FROZEN_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_career_tab_callback_metadata_private',PARENT)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
TARGET=0x17A9630
WRITER=0x17A9933
WRITER_PIN=bytes.fromhex('488d05f6fcffff4889bf00010000488d9f1001000048898708010000')
SOURCE=ROOT/'dist/career-tab-initializer-body-live-20261013-v1'
SOURCE_BIN_SHA='194a0e58ed04345c2b278f771bcd7328dde5f03b7158c4ee5bf736615ff82d13'
SOURCE_JSON_SHA='a391f7303bb85a1344b632fbca650e2757553762b4311fac2cd097f271b9da76'


def validate_source():
    raw=(SOURCE/'body.bin').read_bytes();report=(SOURCE/'body.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_BIN_SHA or hashlib.sha256(report).hexdigest()!=SOURCE_JSON_SHA:
        raise ValueError('TAB_CALLBACK_INITIALIZER_SOURCE_CHANGED')
    m=json.loads(report)
    if (not m.get('complete') or not m.get('body_before_after_match') or not m.get('parent_RF_UW_before_after_match')
            or not m.get('fresh_gates_verified') or m.get('fingerprint')!=parent.base.profile.FINGERPRINT
            or (m.get('function_begin'),m.get('function_end'),len(raw))!=(0x17A9820,0x17AA47B,3163)):
        raise ValueError('TAB_CALLBACK_INITIALIZER_SOURCE_PROFILE')
    if (raw[WRITER-0x17A9820:WRITER-0x17A9820+len(WRITER_PIN)]!=WRITER_PIN
            or WRITER+7+struct.unpack_from('<i',WRITER_PIN,3)[0]!=TARGET):
        raise ValueError('TAB_CALLBACK_FUNCTION_ADDRESS_PAIR_SOURCE')
    return {'path':str(SOURCE),'bin_sha256':SOURCE_BIN_SHA,'json_sha256':SOURCE_JSON_SHA,
        'writer_RVA':WRITER,'writer_pin_hex':WRITER_PIN.hex(),'stored_function_RVA':TARGET,
        'pair_object_field':0x100,'pair_function_field':0x108,'object_expression':'entry.RCX = Armory + 0x570',
        'callback_signature_or_tab_request_proven':False,'source_PID_is_current_identity':False}


old_capture=parent.capture
def capture(budget,evidence):
    evidence.update(source_role='initializer_LEA_and_object_function_pair_stores',
                    callback_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return old_capture(budget,evidence)

parent.REVISION='career_stored_tab_function_standard_metadata_v1'
parent.TARGET_RVA,parent.CALLER,parent.CALL_PIN=TARGET,WRITER,WRITER_PIN
parent.POST_BYTES+=len(WRITER_PIN)-5
parent.validate_source,parent.capture=validate_source,capture
# Exactly two bounded PIN reads change from known CALL5 to known writer28.
source=inspect.getsource(parent.run)
anchor='budget.read_module(CALLER,5,'
if source.count(anchor)!=2:raise ValueError('TAB_CALLBACK_PARENT_PIN_READ_SHAPE_CHANGED')
exec(compile(source.replace(anchor,'budget.read_module(CALLER,len(CALL_PIN),'),__file__,'exec'),parent.__dict__)


def run(output,dependencies=None,clock=time.perf_counter):return parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
