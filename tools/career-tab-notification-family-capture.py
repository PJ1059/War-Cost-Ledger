"""Only the proven threeRF family194B, twice; excludes14B gap/foreign17AC4B0."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-notification-metadata-closure.py'
PARENT_SHA='97204176f75bfeef40bd6f7e65c654557aa52f69232eb60cf9f68cd4ad65b136'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_FAMILY_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_tab_notification_family_private',PARENT)
closure=importlib.util.module_from_spec(spec);spec.loader.exec_module(closure)
PACKET=ROOT/'dist/career-tab-notification-metadata-closure-live-20261013-v1'
BIN_SHA='550c96ae1544b3cbb4fb700d63b6963c0fc928bca9bb0fa95bd6a0eab94672f3'
JSON_SHA='869a39ce2738edda848c2a8d721ab5d3fa5b5d5f8b30852b096931ae68d4c08f'
BEGIN,END=0x17AC3E0,0x17AC4A2
_validate=closure.validate_source
old_capture=closure.capture

def material():
    raw=(PACKET/'metadata.bin').read_bytes();report=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(report).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_FAMILY_METADATA_SOURCE_CHANGED')
    m=json.loads(report)
    if (not m.get('complete') or not m.get('fresh_gates_verified') or not m.get('fixed_window_before_after_match')
            or m.get('same_entry_ranges_within_fixed8')!=[[BEGIN,END]] or not m.get('all_known_targets_same_entry')
            or m.get('first_foreign_RF',{}).get('begin')!=0x17AC4B0
            or [row['RF_index']for row in m['ownership']if row['same_entry']]!=[96757,96758,96759]):
        raise ValueError('TAB_FAMILY_METADATA_SOURCE_PROFILE')
    return raw,m

def validate_source():
    result=_validate();material()
    result['family_source']={'path':str(PACKET),'BIN_SHA256':BIN_SHA,'JSON_SHA256':JSON_SHA,
                            'body_begin':BEGIN,'body_end':END,'gap_and_foreign_code_not_in_scope':True}
    return result

def capture(budget,evidence):
    expected,m=material();raw=old_capture(budget,evidence)
    if raw!=expected or evidence['same_entry_ranges_within_fixed8']!=[[BEGIN,END]]:
        raise ValueError('TAB_FAMILY_FRESH_METADATA_CHANGED')
    nodes=m['unwind_nodes'];post_bytes=96+sum(n['length']for n in nodes)+4096+5+12
    post_calls=1+len(nodes)+4;n=END-BEGIN
    budget.require_capacity(2*n+post_bytes,2+post_calls)
    if budget.query_calls+2+post_calls>64:raise ValueError('TAB_FAMILY_POST_QUERY_RESERVE')
    body=budget.read_module(BEGIN,n,'declared_forwarder_code',True)
    if budget.read_module(BEGIN,n,'declared_forwarder_code',True)!=body:raise ValueError('TAB_FAMILY_BODY_CHANGED_AFTER')
    if budget.read_module(closure.RF_RVA,96,'exception_record')!=expected[:96]:raise ValueError('TAB_FAMILY_RF_CHANGED_AFTER_BODY')
    for node in nodes:
        if budget.read_module(node['unwind_rva'],node['length'],'unwind_metadata').hex()!=node['raw_hex']:
            raise ValueError('TAB_FAMILY_UW_CHANGED_AFTER_BODY')
    evidence.update(metadata_only=False,body_captured=True,body_before_after_match=True,
        full_fixed_RF_UW_after_body_match=True,body={'begin':BEGIN,'end':END,'length':n,'binary_offset':len(raw),
        'sha256':hashlib.sha256(body).hexdigest()},family_tool_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        foreign_body_read=False,unproven_gap_read=False,global_siblings_proven_absent=False)
    evidence['ranges'].append({'kind':'same_primary_threeRF_family','rva':BEGIN,'length':n,'binary_offset':len(raw)})
    return raw+body

closure.parent.REVISION='career_tab_notification_threeRF_family_body_v1'
closure.parent.validate_source,closure.parent.capture=validate_source,capture

def run(output,dependencies=None,clock=time.perf_counter):return closure.parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
