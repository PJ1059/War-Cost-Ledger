"""One fixed17AC3E0 metadata determination, optional whole declared body twice.

Body is withheld on chain/fragments, unknown standard layout or pre-reserved
16KiB64IO2s budget. ShipPID27268 only, no helper/heap/input-value reads or calls.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-initializer-metadata-capture.py'
PARENT_SHA='3e63bc84276602f0dc7f1fe0babd489f9f420cc21fbc20592229158cd204a6fa'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_NOTIFICATION_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_career_tab_notification_private',PARENT)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
TARGET,CALLER,CALL_PIN=0x17AC3E0,0x17A9640,bytes.fromhex('e89b2d0000')
SOURCE=ROOT/'dist/career-tab-callback-body-live-20261013-v1'
SOURCE_BIN_SHA='8e60a2604a3e4e73daaac70fb2b09b086fe210676a89700f713b09ecf38a092a'
SOURCE_JSON_SHA='94ffff08d57cde9a0ef500934c97d7b0b87fb038c225922e59d5ee0d959a1d4c'


def validate_source():
    raw=(SOURCE/'body.bin').read_bytes();report=(SOURCE/'body.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_BIN_SHA or hashlib.sha256(report).hexdigest()!=SOURCE_JSON_SHA:
        raise ValueError('TAB_NOTIFICATION_CALL_SOURCE_CHANGED')
    m=json.loads(report)
    if (not m.get('complete') or not m.get('body_before_after_match') or not m.get('parent_RF_UW_before_after_match')
            or not m.get('fresh_gates_verified') or m.get('fingerprint')!=parent.base.profile.FINGERPRINT
            or (m.get('function_begin'),m.get('function_end'),len(raw))!=(0x17A9630,0x17A9755,293)
            or raw[CALLER-0x17A9630:CALLER-0x17A9630+5]!=CALL_PIN
            or CALLER+5+struct.unpack_from('<i',CALL_PIN,1)[0]!=TARGET):
        raise ValueError('TAB_NOTIFICATION_CALL_SOURCE_PROFILE')
    return {'path':str(SOURCE),'bin_sha256':SOURCE_BIN_SHA,'json_sha256':SOURCE_JSON_SHA,
        'caller_RVA':CALLER,'caller_pin':CALL_PIN.hex(),'callee_RVA':TARGET,
        'RCX':'same entry bar pointer','remaining_arguments_and_behavior_proven':False,
        'source_PID_is_current_identity':False}


old_capture=parent.capture
def capture(budget,evidence):
    raw=old_capture(budget,evidence)
    evidence.update(notification_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        body_capture_attempted=False,body_captured=False,body_readiness='WITHHELD_METADATA_ONLY',
        input_values_read=False,helpers_followed=False,provider_proven=False)
    nodes=evidence['unwind_nodes'];begin,end=evidence['function_begin'],evidence['function_end']
    n=end-begin
    if (len(nodes)!=1 or nodes[0].get('flags',0)&4 or begin!=TARGET
            or not all(node.get('standard_layout_complete')for node in nodes)
            or any(row['reason']!='OPAQUE_HANDLER_DATA_NOT_READ'for row in evidence['unknowns'])):
        evidence['body_readiness']='WITHHELD_FRAGMENT_OR_STANDARD_BOUNDARY';return raw
    if not 0<n<=4096:
        evidence['body_readiness']='WITHHELD_DECLARATION_EXCEEDS_4K';return raw
    node_bytes=sum(node['length']for node in nodes)
    # Fresh RF/UW again after body, and the parent's remaining PE/CALL/FSM gates.
    required_bytes=2*n+12+node_bytes+4096+5+12
    required_calls=2+1+len(nodes)+4
    try:
        budget.require_capacity(required_bytes,required_calls)
        if budget.query_calls+required_calls>parent.MAX_READS:raise ValueError('POST_QUERY_RESERVE')
        if (budget.declaration_bytes+2*n+12+node_bytes>parent.base.MAX_DECLARATION_BYTES
                or budget.declaration_reads+3+len(nodes)>parent.base.MAX_DECLARATION_READS
                or budget.declaration_queries+3+len(nodes)>parent.base.MAX_DECLARATION_READS):
            raise ValueError('DECLARATION_POST_RESERVE')
    except ValueError as error:
        evidence.update(body_readiness='WITHHELD_BODY_BUDGET',body_budget_reason=str(error));return raw
    evidence['body_capture_attempted']=True
    body=budget.read_module(begin,n,'declared_forwarder_code',True)
    after=budget.read_module(begin,n,'declared_forwarder_code',True)
    if body!=after:raise ValueError('TAB_NOTIFICATION_BODY_CHANGED_AFTER')
    rf=evidence['selected_runtime_function']
    if budget.read_module(rf['rva'],12,'exception_record').hex()!=rf['raw_hex']:
        raise ValueError('TAB_NOTIFICATION_RF_CHANGED_AFTER_BODY')
    for node in nodes:
        if budget.read_module(node['unwind_rva'],node['length'],'unwind_metadata').hex()!=node['raw_hex']:
            raise ValueError('TAB_NOTIFICATION_UW_CHANGED_AFTER_BODY')
    evidence.update(body_captured=True,body_readiness='ACTUAL_SINGLE_DECLARATION_CAPTURED',
        body_before_after_match=True,RF_UW_before_after_body_match=True,metadata_only=False,code_only=False,
        initializer_instructions_read=False,notification_instructions_read=True,
        body={'begin':begin,'end':end,'length':n,'binary_offset':len(raw),'sha256':hashlib.sha256(body).hexdigest()},
        logical_function_complete=False,all_sibling_fragments_proven_absent=False)
    evidence['ranges'].append({'kind':'actual_notification_declaration','rva':begin,'length':n,'binary_offset':len(raw)})
    return raw+body

parent.REVISION='career_single_tab_notification_declared_v1'
parent.TARGET_RVA,parent.CALLER,parent.CALL_PIN=TARGET,CALLER,CALL_PIN
parent.EXPECTED_PID=27268
parent.validate_source,parent.capture=validate_source,capture


def run(output,dependencies=None,clock=time.perf_counter):return parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
