"""Only the registered 17AED40..17AED60 leaf window, twice; no ABI claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-child-registration-capture.py'
PARENT_SHA='7e52b95432f2b5f8e802c60df184c2146aea2352d740b382a8d7bfc5d6b529f2'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CHILD_LEAF_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_tab_child_callback_leaf_private',PARENT)
constructor=importlib.util.module_from_spec(spec);spec.loader.exec_module(constructor)
parent=constructor.parent
PACKET=ROOT/'dist/career-tab-child-registration-live-20261013-v1'
BIN_SHA='ca65cf2e6fa29cfa599d2bed1535521e04e5cab31b16b9d1152dc5e0678384ac'
JSON_SHA='8661a8dd01ef1869a758b2f057f18dff116ac5902aa045a97146612029ef8b3b'
BEGIN,END=0x17AED40,0x17AED60
PAIR_RVA=0x17AE5E0
PAIR_PIN=bytes.fromhex('488d05590700004d89a42400010000498d9c24100100004989842408010000')
RF_RVA=0x40EED14
RF_PIN=bytes.fromhex('f0e37a0128ed7a0120fb560260ed7a018aed7a0150fb5602')
MAX_BYTES,MAX_READS,MAX_SECONDS=16384,64,2.0
_validate=constructor.validate_source


def validate_source():
    result=_validate();raw=(PACKET/'metadata.bin').read_bytes();meta_raw=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(meta_raw).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_CHILD_LEAF_PACKET_CHANGED')
    m=json.loads(meta_raw);body=m.get('body',{})
    if (not m.get('complete') or not m.get('fresh_gates_verified')
            or not m.get('body_before_after_match') or not m.get('full_fixed_RF_UW_after_body_match')
            or m.get('fingerprint')!=parent.base.profile.FINGERPRINT or raw[:24]!=RF_PIN
            or (body.get('begin'),body.get('end'),body.get('length'),body.get('binary_offset'))
                !=(0x17AE3F0,0x17AED28,2360,232)
            or m.get('first_foreign_RF',{}).get('begin')!=END
            or m['selected_runtime_function'].get('rva')!=RF_RVA):
        raise ValueError('TAB_CHILD_LEAF_PACKET_PROFILE')
    off=body['binary_offset']+PAIR_RVA-body['begin']
    if raw[off:off+len(PAIR_PIN)]!=PAIR_PIN or PAIR_RVA+7+struct.unpack_from('<i',PAIR_PIN,3)[0]!=BEGIN:
        raise ValueError('TAB_CHILD_LEAF_SOURCE_PAIR')
    result['registered_pair_source']={'path':str(PACKET),'BIN_SHA256':BIN_SHA,'JSON_SHA256':JSON_SHA,
        'PAIR_RVA':PAIR_RVA,'PAIR_PIN':PAIR_PIN.hex(),'RF_RVA':RF_RVA,'RF_PIN':RF_PIN.hex(),
        'window_begin':BEGIN,'window_end':END,'window_is_not_proven_function_declaration':True,
        'source_PID_is_current_identity':False}
    return result


def capture(budget,evidence):
    # Exact known parent pair plus two actual RFs gate the registered address
    # and foreign entry. No RF lookup, opaque data or child values are read.
    n=END-BEGIN
    post_bytes=4096+5+12+len(PAIR_PIN)+len(RF_PIN)
    post_calls=4+2
    budget.require_capacity(2*n+2*len(PAIR_PIN)+2*len(RF_PIN)+4096+5+12,10)
    if budget.query_calls+10>MAX_READS:raise ValueError('TAB_CHILD_LEAF_POST_QUERY_RESERVE')
    if budget.read_module(PAIR_RVA,len(PAIR_PIN),'registered_parent_pair_pin',True)!=PAIR_PIN:
        raise ValueError('TAB_CHILD_LEAF_PARENT_PAIR_CHANGED')
    if budget.read_module(RF_RVA,len(RF_PIN),'exception_record')!=RF_PIN:
        raise ValueError('TAB_CHILD_LEAF_RF_BOUNDARY_CHANGED')
    a,b,u=struct.unpack_from('<III',RF_PIN);foreign,foreign_end,foreign_u=struct.unpack_from('<III',RF_PIN,12)
    if not parent.base.CODE_BEGIN<=a<b<=BEGIN<END==foreign<foreign_end<=parent.base.CODE_END:
        raise ValueError('TAB_CHILD_LEAF_BOUNDARY_PROFILE')
    budget.require_capacity(2*n+post_bytes,2+post_calls)
    body=budget.read_module(BEGIN,n,'declared_forwarder_code',True)
    if budget.read_module(BEGIN,n,'declared_forwarder_code',True)!=body:
        raise ValueError('TAB_CHILD_LEAF_WINDOW_CHANGED_AFTER')
    if budget.read_module(PAIR_RVA,len(PAIR_PIN),'registered_parent_pair_pin_after',True)!=PAIR_PIN:
        raise ValueError('TAB_CHILD_LEAF_PARENT_PAIR_CHANGED_AFTER')
    if budget.read_module(RF_RVA,len(RF_PIN),'exception_record')!=RF_PIN:
        raise ValueError('TAB_CHILD_LEAF_RF_BOUNDARY_CHANGED_AFTER')
    evidence.update(metadata_only=False,capture_purpose='REGISTERED_CALLBACK_FIXED32_WINDOW_ONLY',
        metadata_readiness='FIXED_LEAF_WINDOW_CAPTURED_NOT_FUNCTION_DECLARATION',
        target_rva=BEGIN,window_begin=BEGIN,window_end=END,window_is_function_declaration=False,
        leaf_abi_proven=False,logical_function_complete=False,normal_CFG_closed=False,
        callback_registration_proven=True,normal_tab_input_consumer_proven=False,
        input_values_read=False,helpers_followed=False,handler_code_read=False,opaque_handler_data_read=False,
        foreign_body_read=False,window_before_after_match=True,parent_pair_before_after_match=True,
        RF_boundary_before_after_match=True,body_captured=True,
        source_primary_end=b,source_foreign_entry=foreign,
        body={'begin':BEGIN,'end':END,'length':n,'binary_offset':len(RF_PIN),'sha256':hashlib.sha256(body).hexdigest()},
        leaf_tool_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ranges=[{'kind':'known_RF_boundaries','rva':RF_RVA,'length':len(RF_PIN),'binary_offset':0},
                {'kind':'registered_callback_fixed_window','rva':BEGIN,'length':n,'binary_offset':len(RF_PIN)}])
    return RF_PIN+body


parent.REVISION='career_tab_child_callback_fixed32_v1'
parent.TARGET_RVA=BEGIN
parent.MAX_BYTES,parent.MAX_READS,parent.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
parent.base.MAX_DECLARATION_BYTES,parent.base.MAX_DECLARATION_READS=8192,64
parent.validate_source,parent.capture=validate_source,capture

def run(output,dependencies=None,clock=time.perf_counter):return parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
