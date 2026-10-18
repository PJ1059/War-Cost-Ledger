"""Stored function17A9630's actual293B declaration only, twice."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-callback-metadata-capture.py'
PARENT_SHA='96a50d31c21ccff8eee8822f7c40e4081ab6361d376d79b6dd3c483a60c44aa1'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CALLBACK_BODY_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_career_callback_body_private',PARENT)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
PACKET=ROOT/'dist/career-tab-callback-metadata-live-20261013-v1'
JSON_SHA='00746f58e707c34255f47f005de230b9983c794bba5cd147331878ab893d5913'
BIN_SHA='5bf3caf63133c3ab60cd39d4b8ae1c8c012662ec7d21f9be4530ef56dcf895f3'
BEGIN,END=0x17A9630,0x17A9755
RF_RVA,RF_HEX=0x40EE99C,'30967a0155977a01c0f55602'
UW_RVA,UW_BYTES=0x256F5C0,8
_validate=parent.validate_source


def material():
    raw=(PACKET/'metadata.bin').read_bytes();report=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(report).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_CALLBACK_BODY_METADATA_SOURCE_CHANGED')
    m=json.loads(report);rf=m.get('selected_runtime_function',{})
    if (not m.get('complete') or not m.get('fresh_gates_verified') or m.get('sha256')!=BIN_SHA
            or m.get('fingerprint')!=parent.parent.base.profile.FINGERPRINT
            or (m.get('function_begin'),m.get('function_end'))!=(BEGIN,END)
            or (rf.get('index'),rf.get('rva'),rf.get('raw_hex'),rf.get('unwind_rva'))!=(96716,RF_RVA,RF_HEX,UW_RVA)
            or len(raw)!=20 or raw[:12].hex()!=RF_HEX or raw[12:].hex()!='0106020006320230'
            or len(m.get('unwind_nodes',[]))!=1 or m['unwind_nodes'][0].get('raw_hex')!=raw[12:].hex()
            or m.get('unknowns')!=[]):
        raise ValueError('TAB_CALLBACK_BODY_METADATA_SOURCE_PROFILE')
    return raw,m


def validate_source():
    source=_validate();material()
    source['body_metadata_source']={'path':str(PACKET),'json_sha256':JSON_SHA,'bin_sha256':BIN_SHA,
        'actual_body_begin':BEGIN,'actual_body_end':END,'actual_RF_index':96716,
        'end_inferred_from_initializer_start':False}
    return source


def capture(budget,evidence):
    pin,m=material();rf,uw=pin[:12],pin[12:];n=END-BEGIN
    budget.require_capacity(2*n+2*len(pin)+4096+28+12,10)
    if budget.query_calls+10>64:raise ValueError('TAB_CALLBACK_BODY_POST_QUERY_RESERVE')
    if budget.read_module(RF_RVA,12,'exception_record')!=rf:raise ValueError('TAB_CALLBACK_BODY_RF_CHANGED_BEFORE')
    if budget.read_module(UW_RVA,UW_BYTES,'unwind_metadata')!=uw:raise ValueError('TAB_CALLBACK_BODY_UW_CHANGED_BEFORE')
    raw=budget.read_module(BEGIN,n,'declared_forwarder_code',True)
    after=budget.read_module(BEGIN,n,'declared_forwarder_code',True)
    if raw!=after:raise ValueError('TAB_CALLBACK_BODY_CHANGED_AFTER')
    if budget.read_module(RF_RVA,12,'exception_record')!=rf:raise ValueError('TAB_CALLBACK_BODY_RF_CHANGED_AFTER')
    if budget.read_module(UW_RVA,UW_BYTES,'unwind_metadata')!=uw:raise ValueError('TAB_CALLBACK_BODY_UW_CHANGED_AFTER')
    evidence.update(function_begin=BEGIN,function_end=END,selected_runtime_function=m['selected_runtime_function'],
        unwind_nodes=m['unwind_nodes'],unknowns=[],metadata_readiness='STANDARD_METADATA_COMPLETE',
        metadata_only=False,code_only=True,capture_purpose='STORED_FUNCTION_ACTUAL_DECLARATION_BODY_ONLY',
        body_before_after_match=True,parent_RF_UW_before_after_match=True,body_bytes=n,
        callback_signature_proven=False,normal_tab_input_consumer_proven=False,handler_code_read=False,
        opaque_handler_data_read=False,logical_function_complete=False,additional_ancestry_code_read=False,
        body_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ranges=[{'kind':'actual_stored_function_body','rva':BEGIN,'length':n,'binary_offset':0}])
    return raw

parent.parent.REVISION='career_stored_tab_function_actual_body_v1'
parent.parent.validate_source=validate_source
parent.parent.capture=capture


def run(output,dependencies=None,clock=time.perf_counter):
    result=parent.run(output,dependencies,clock);folder=Path(output).resolve()
    old_bin,old_json=Path(result['binary_path']),Path(result['json_path'])
    binary,report=folder/'body.bin',folder/'body.json';old_bin.rename(binary)
    m=json.loads(old_json.read_text('utf8'));m['binary_path']=str(binary)
    report.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf8');old_json.unlink()
    result.update(binary_path=str(binary),json_path=str(report));return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
