"""One fixed actual RF17A9820..17AA47B body, twice; no extra code/heap/call."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-initializer-metadata-capture.py'
PARENT_SHA='3e63bc84276602f0dc7f1fe0babd489f9f420cc21fbc20592229158cd204a6fa'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_BODY_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_career_tab_body_private',PARENT)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
PACKET=ROOT/'dist/career-tab-initializer-metadata-live-20261013-v1'
PACKET_JSON_SHA='254217a058b05eb1dc3389a08896cd12e2ecf9fe68de21601dda70a54779b685'
PACKET_BIN_SHA='4fc749398008bb57ed1ffeee88f7f8e1cddffb36c2cf0a545027fd058305e1ea'
BEGIN,END=0x17A9820,0x17AA47B
BODY_BYTES=END-BEGIN
RF_RVA,RF_HEX=0x40EE9C0,'20987a017ba47a01e8f55602'
UW_RVA,UW_BYTES=0x256F5E8,52
_validate=parent.validate_source


def material():
    raw=(PACKET/'metadata.bin').read_bytes();meta_raw=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PACKET_BIN_SHA or hashlib.sha256(meta_raw).hexdigest()!=PACKET_JSON_SHA:
        raise ValueError('TAB_BODY_METADATA_PACKET_CHANGED')
    m=json.loads(meta_raw);rf=m.get('selected_runtime_function',{})
    if (not m.get('complete') or not m.get('fresh_gates_verified') or m.get('sha256')!=PACKET_BIN_SHA
            or m.get('fingerprint')!=parent.base.profile.FINGERPRINT
            or (m.get('function_begin'),m.get('function_end'))!=(BEGIN,END)
            or (rf.get('index'),rf.get('rva'),rf.get('raw_hex'),rf.get('unwind_rva'))!=(96719,RF_RVA,RF_HEX,UW_RVA)
            or len(raw)!=12+UW_BYTES or raw[:12].hex()!=RF_HEX or len(m.get('unwind_nodes',[]))!=1
            or m['unwind_nodes'][0].get('raw_hex')!=raw[12:].hex()
            or m['unwind_nodes'][0].get('length')!=UW_BYTES
            or m['unwind_nodes'][0].get('header_hex')!='19431500'):
        raise ValueError('TAB_BODY_METADATA_PACKET_PROFILE')
    return raw,m


def validate_source():
    source=_validate();raw,m=material()
    source['body_metadata_source']={'path':str(PACKET),'json_sha256':PACKET_JSON_SHA,
        'bin_sha256':PACKET_BIN_SHA,'RF_RVA':RF_RVA,'RF_hex':RF_HEX,'UW_RVA':UW_RVA,
        'UW_length':UW_BYTES,'body_begin':BEGIN,'body_end':END,'source_PID_is_current_identity':False}
    return source


def capture(budget,evidence):
    source,m=material();rf,uw=source[:12],source[12:]
    outer_post_bytes,outer_post_calls=4096+5+12,4
    budget.require_capacity(2*BODY_BYTES+2*len(source)+outer_post_bytes,6+outer_post_calls)
    if budget.query_calls+6+outer_post_calls>parent.MAX_READS:raise ValueError('TAB_BODY_POST_QUERY_RESERVE')
    if budget.read_module(RF_RVA,12,'exception_record')!=rf:raise ValueError('TAB_BODY_RF_CHANGED_BEFORE')
    if budget.read_module(UW_RVA,UW_BYTES,'unwind_metadata')!=uw:raise ValueError('TAB_BODY_UW_PIN_CHANGED_BEFORE')
    first=budget.read_module(BEGIN,BODY_BYTES,'declared_forwarder_code',True)
    second=budget.read_module(BEGIN,BODY_BYTES,'declared_forwarder_code',True)
    if first!=second:raise ValueError('TAB_BODY_CHANGED_AFTER')
    if budget.read_module(RF_RVA,12,'exception_record')!=rf:raise ValueError('TAB_BODY_RF_CHANGED_AFTER')
    if budget.read_module(UW_RVA,UW_BYTES,'unwind_metadata')!=uw:raise ValueError('TAB_BODY_UW_PIN_CHANGED_AFTER')
    evidence.update(function_begin=BEGIN,function_end=END,selected_runtime_function=m['selected_runtime_function'],
        unwind_nodes=m['unwind_nodes'],unknowns=m['unknowns'],metadata_readiness=m['metadata_readiness'],
        metadata_only=False,code_only=True,capture_purpose='ONE_ACTUAL_INITIALIZER_DECLARATION_BODY_ONLY',
        body_bytes=BODY_BYTES,body_before_after_match=True,parent_RF_UW_before_after_match=True,
        initializer_instructions_read=True,handler_code_read=False,opaque_handler_data_read=False,
        callback_registration_proven=False,normal_tab_input_consumer_proven=False,logical_function_complete=False,
        additional_ancestry_code_read=False,ranges=[{'kind':'actual_initializer_body','rva':BEGIN,
            'length':BODY_BYTES,'binary_offset':0}],body_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return first


parent.REVISION='career_tab_initializer_declared_body_v1'
parent.validate_source=validate_source
parent.capture=capture


def run(output,dependencies=None,clock=time.perf_counter):
    # Reuse every identity, Ship/context, CALL and PE pre/post gate unchanged.
    result=parent.run(output,dependencies,clock)
    folder=Path(output).resolve();old_bin=Path(result['binary_path']);old_json=Path(result['json_path'])
    binary,report=folder/'body.bin',folder/'body.json'
    old_bin.rename(binary);m=json.loads(old_json.read_text('utf8'))
    m['binary_path']=str(binary)
    report.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf8');old_json.unlink()
    result.update(binary_path=str(binary),json_path=str(report))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
