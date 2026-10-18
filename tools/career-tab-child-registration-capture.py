"""Only 17AE3F0: bounded RF lookup/fixed8 ownership, then <=4KiB normal body.

Fresh CALL17A9F39 and the frozen initializer packet are the source. No child
object values, input values, handler code, foreign body or nested callees.
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
PARENT=ROOT/'tools/career-tab-notification-metadata-closure.py'
PARENT_SHA='97204176f75bfeef40bd6f7e65c654557aa52f69232eb60cf9f68cd4ad65b136'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CHILD_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_tab_child_fixed8_private',PARENT)
closure=importlib.util.module_from_spec(spec);spec.loader.exec_module(closure)
parent=closure.parent
SOURCE=ROOT/'dist/career-tab-initializer-body-live-20261013-v1'
BIN_SHA='194a0e58ed04345c2b278f771bcd7328dde5f03b7158c4ee5bf736615ff82d13'
JSON_SHA='a391f7303bb85a1344b632fbca650e2757553762b4311fac2cd097f271b9da76'
SOURCE_BEGIN,SOURCE_END=0x17A9820,0x17AA47B
TARGET,CALLER,CALL_PIN=0x17AE3F0,0x17A9F39,bytes.fromhex('e8b2440000')
MAX_BYTES,MAX_READS,MAX_SECONDS=32768,128,2.0
MAX_BODY_BYTES=4096

# Reuse the frozen ownership implementation only in this private module.
# Its old entry-UW PIN is not evidence for this new target; all new UW is
# instead exact reread. The budget query cap follows this private profile.
text=inspect.getsource(closure.capture)
old_query='budget.query_calls+1+post_calls>64'
old_uw='if at==ENTRY[2]and raw!=ENTRY_UW:'
if text.count(old_query)!=1 or text.count(old_uw)!=1:raise ValueError('TAB_CHILD_PRIVATE_REUSE_CHANGED')
text=text.replace(old_query,'budget.query_calls+1+post_calls>parent.MAX_READS')
text=text.replace(old_uw,'if ENTRY_UW is not None and at==ENTRY[2]and raw!=ENTRY_UW:')
exec(compile(text,str(PARENT),'exec'),closure.__dict__)
ownership_capture=closure.capture


def validate_source():
    raw=(SOURCE/'body.bin').read_bytes();meta_raw=(SOURCE/'body.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(meta_raw).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_CHILD_SOURCE_CHANGED')
    m=json.loads(meta_raw)
    if (len(raw)!=SOURCE_END-SOURCE_BEGIN or not m.get('complete') or not m.get('fresh_gates_verified')
            or not m.get('body_before_after_match') or not m.get('parent_RF_UW_before_after_match')
            or m.get('fingerprint')!=parent.base.profile.FINGERPRINT
            or (m.get('function_begin'),m.get('function_end'))!=(SOURCE_BEGIN,SOURCE_END)
            or m.get('ranges')!=[{'kind':'actual_initializer_body','rva':SOURCE_BEGIN,
                                 'length':3163,'binary_offset':0}]):
        raise ValueError('TAB_CHILD_SOURCE_PROFILE')
    off=CALLER-SOURCE_BEGIN
    if raw[off:off+5]!=CALL_PIN or CALLER+5+struct.unpack_from('<i',CALL_PIN,1)[0]!=TARGET:
        raise ValueError('TAB_CHILD_SOURCE_CALL')
    return {'path':str(SOURCE),'BIN_SHA256':BIN_SHA,'JSON_SHA256':JSON_SHA,
            'caller_rva':CALLER,'pin_hex':CALL_PIN.hex(),'target_rva':TARGET,
            'known_registers':{'RCX':'bar + 0x1DD0 + 0xD48*i; i=0..7','RDX':0,
                'R8_R9':'packed f32 (0.0,1.0)','stack_plus_20':901},
            'register_semantic_types_proven':False,'source_PID_is_current_identity':False}


def capture(budget,evidence):
    reader=parent.base.profile.private_reader()
    reader.TARGET_RVA,reader.TARGET_PIN=TARGET,''
    reader.IMAGE_SIZE=parent.base.IMAGE_SIZE
    reader.EXCEPTION_RVA,reader.EXCEPTION_SIZE=parent.base.EXCEPTION_RVA,parent.base.EXCEPTION_SIZE
    reader.MAX_FUNCTION_BYTES=parent.base.CODE_END-parent.base.CODE_BEGIN
    reader.MAX_TABLE_READS=20
    lookup=[]
    # At most eight RFs * four unique UW nodes. Reserve that whole metadata
    # phase and its postchecks before each binary-search read. Body is optional.
    worst_metadata_bytes=96*2+32*(4+128)+32*128+4096+5+12
    worst_metadata_calls=1+64+1+32+4
    def lookup_read(_,rva,n):
        if n!=12 or not reader.EXCEPTION_RVA<=rva<rva+n<=reader.EXCEPTION_RVA+reader.EXCEPTION_SIZE:
            raise ValueError('TAB_CHILD_LOOKUP_SCOPE')
        budget.require_capacity(n+worst_metadata_bytes,1+worst_metadata_calls)
        if budget.query_calls+1+worst_metadata_calls>MAX_READS:
            raise ValueError('TAB_CHILD_LOOKUP_QUERY_RESERVE')
        return budget.read_module(rva,n,'exception_record')
    reader.checked_metadata_read=lookup_read
    begin,end=reader.find_function(budget,lookup);selected=lookup[-1]
    if not parent.base.CODE_BEGIN<=begin<=TARGET<end<=parent.base.CODE_END:
        raise ValueError('TAB_CHILD_SELECTED_RF_NOT_CODE')
    if selected['index']+8>reader.EXCEPTION_SIZE//12:raise ValueError('TAB_CHILD_FIXED8_OUTSIDE_PDATA')
    closure.RF_INDEX,closure.RF_RVA=selected['index'],selected['rva']
    closure.ENTRY=(begin,end,selected['unwind_rva'])
    closure.ENTRY_RF=bytes.fromhex(selected['raw_hex']);closure.ENTRY_UW=None;closure.TARGETS=()
    evidence['binary_lookup_records']=lookup
    raw=ownership_capture(budget,evidence)
    evidence.update(target_rva=TARGET,all_known_targets_same_entry=None,
        capture_purpose='ONE_CHILD_CONSTRUCTOR_FIXED8_OWNERSHIP_AND_OPTIONAL_NORMAL_BODY',
        child_tool_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        global_siblings_proven_absent=False,foreign_body_read=False,unproven_gap_read=False,
        input_values_read=False,helpers_followed=False,normal_CFG_closed=False,
        callback_registration_proven=False,normal_tab_input_consumer_proven=False)
    handlers=[{'rva':node['unwind_rva']+node['length'],'reason':'OPAQUE_HANDLER_DATA_NOT_READ'}
              for node in evidence['unwind_nodes']if node.get('handler_data_unread')]
    evidence['unknowns']=handlers
    ranges=evidence['same_entry_ranges_within_fixed8'];foreign=evidence['first_foreign_RF']
    if (begin!=TARGET or len(ranges)!=1 or ranges[0][0]!=TARGET or not foreign
            or any(row['same_entry'] for row in evidence['exception_records']
                   if row['index']>=foreign['index'])):
        evidence['body_readiness']='WITHHELD_UNKNOWN_OR_DISJOINT_LOGICAL_BOUNDARY'
        return raw
    body_begin,body_end=ranges[0];n=body_end-body_begin
    if not 0<n<=MAX_BODY_BYTES:
        evidence['body_readiness']='WITHHELD_BODY_EXCEEDS4K'
        return raw
    nodes=evidence['unwind_nodes']
    post_bytes=96+sum(node['length']for node in nodes)+4096+5+12
    post_calls=1+len(nodes)+4
    try:
        budget.require_capacity(2*n+post_bytes,2+post_calls)
        if budget.query_calls+2+post_calls>MAX_READS:raise ValueError('TAB_CHILD_BODY_QUERY_RESERVE')
        if (budget.declaration_bytes+2*n+96+sum(node['length']for node in nodes)
                >parent.base.MAX_DECLARATION_BYTES):raise ValueError('TAB_CHILD_BODY_METADATA_RESERVE')
        if (budget.declaration_reads+2+1+len(nodes)
                >parent.base.MAX_DECLARATION_READS):raise ValueError('TAB_CHILD_BODY_METADATA_READ_RESERVE')
    except ValueError:
        evidence['body_readiness']='WITHHELD_BODY_BUDGET'
        return raw
    body=budget.read_module(body_begin,n,'declared_forwarder_code',True)
    if budget.read_module(body_begin,n,'declared_forwarder_code',True)!=body:
        raise ValueError('TAB_CHILD_BODY_CHANGED_AFTER')
    if budget.read_module(closure.RF_RVA,96,'exception_record')!=raw[:96]:
        raise ValueError('TAB_CHILD_RF_CHANGED_AFTER_BODY')
    for node in nodes:
        if budget.read_module(node['unwind_rva'],node['length'],'unwind_metadata').hex()!=node['raw_hex']:
            raise ValueError('TAB_CHILD_UW_CHANGED_AFTER_BODY')
    evidence.update(metadata_only=False,body_captured=True,body_readiness='FIXED_WINDOW_NORMAL_BODY_CAPTURED',
        body_before_after_match=True,full_fixed_RF_UW_after_body_match=True,
        body={'begin':body_begin,'end':body_end,'length':n,'binary_offset':len(raw),
              'sha256':hashlib.sha256(body).hexdigest()},
        logical_function_complete=False,fixed_window_contiguous_owner_boundary=True)
    evidence['ranges'].append({'kind':'same_primary_fixed8_normal_body','rva':body_begin,
                              'length':n,'binary_offset':len(raw)})
    return raw+body


parent.REVISION='career_tab_child_17AE3F0_registration_v1'
parent.TARGET_RVA,parent.CALLER,parent.CALL_PIN=TARGET,CALLER,CALL_PIN
parent.EXPECTED_PID=27268
parent.MAX_BYTES,parent.MAX_READS,parent.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
parent.base.MAX_DECLARATION_BYTES,parent.base.MAX_DECLARATION_READS=24576,128
parent.validate_source,parent.capture=validate_source,capture

def run(output,dependencies=None,clock=time.perf_counter):return parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
