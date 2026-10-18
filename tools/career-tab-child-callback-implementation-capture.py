"""Only actual callback17AF020..17AF15D,317B; no helper/child heap reads."""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-child-callback-leaf-capture.py'
PARENT_SHA='c83f13920e2731ff255a9128a06315356d5cb00bbc20d7537cd2fe40a589a755'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CALLBACK_IMPL_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_tab_callback_implementation_private',PARENT)
leaf=importlib.util.module_from_spec(spec);spec.loader.exec_module(leaf)
parent=leaf.parent
PACKET=ROOT/'dist/career-tab-child-callback-leaf-live-20261013-v1'
BIN_SHA='6e1b1157fc572aed328e4d197d48e8825bb6f25ca53d230e3722323e3e9a7a27'
JSON_SHA='32a45843d1c0358c722dca0449c7391324b2dc5d475968d6a781a5b5dd100e65'
BEGIN,END=0x17AF020,0x17AF15D
JMP_RVA,JMP_PIN=0x17AED40,bytes.fromhex('e9db020000')
PAIR_RVA,PAIR_PIN=leaf.PAIR_RVA,leaf.PAIR_PIN
RF_RVA=0x40EED44
RF_PIN=bytes.fromhex('20f07a015df17a016cfb560260f17a01c7f27a017cfb5602')
UW_PINS=((0x256FB6C,bytes.fromhex('01120600126802000a340a000a520670')),
         (0x256FB7C,bytes.fromhex('011c06001c7802001468030006720230')))
MAX_BYTES,MAX_READS,MAX_SECONDS=16384,64,2.0
EXPECTED_PID=1632
EXPECTED_PATH='G:/SteamLibrary/steamapps/common/Helldivers 2/bin/helldivers2.exe'
EXPECTED_START='2026-10-13T13:06:32.6144034+09:00'
_delta=datetime(2026,10,13,13,6,32,tzinfo=timezone(timedelta(hours=9)))-datetime(1601,1,1,tzinfo=timezone.utc)
EXPECTED_CREATION_TICK=(_delta.days*86400+_delta.seconds)*10000000+6144034
_validate=leaf.validate_source


def validate_source():
    result=_validate();raw=(PACKET/'metadata.bin').read_bytes();meta_raw=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(meta_raw).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_CALLBACK_IMPL_JMP_PACKET_CHANGED')
    m=json.loads(meta_raw)
    if (not m.get('complete') or not m.get('fresh_gates_verified')
            or not m.get('window_before_after_match') or not m.get('parent_pair_before_after_match')
            or not m.get('RF_boundary_before_after_match') or raw[24:29]!=JMP_PIN
            or m.get('body',{}).get('begin')!=JMP_RVA
            or JMP_RVA+5+struct.unpack_from('<i',JMP_PIN,1)[0]!=BEGIN):
        raise ValueError('TAB_CALLBACK_IMPL_JMP_PACKET_PROFILE')
    cached_raw=(leaf.PACKET/'metadata.bin').read_bytes()
    cached=json.loads((leaf.PACKET/'metadata.json').read_text('utf8'))
    if cached_raw[48:72]!=RF_PIN:raise ValueError('TAB_CALLBACK_IMPL_CACHED_RF_CHANGED')
    records=cached['exception_records']
    for row,index in zip(records[4:6],(96794,96795)):
        if row['index']!=index or row['primary_entry']!=[row['begin'],row['end'],row['unwind_rva']]:
            raise ValueError('TAB_CALLBACK_IMPL_CACHED_OWNER_PROFILE')
    for rva,pin in UW_PINS:
        ranges=[r for r in cached['ranges']if r['kind']=='standard_UW'and r['rva']==rva]
        if len(ranges)!=1:raise ValueError('TAB_CALLBACK_IMPL_CACHED_UW_MISSING')
        off=ranges[0]['binary_offset']
        if ranges[0]['length']!=16 or cached_raw[off:off+16]!=pin:
            raise ValueError('TAB_CALLBACK_IMPL_CACHED_UW_CHANGED')
        if pin[0]!=1 or pin[2]!=6 or pin[3]!=0:raise ValueError('TAB_CALLBACK_IMPL_STANDARD_UW_PROFILE')
    result['implementation_source']={'JMP_packet':str(PACKET),'BIN_SHA256':BIN_SHA,'JSON_SHA256':JSON_SHA,
        'JMP_RVA':JMP_RVA,'JMP_PIN':JMP_PIN.hex(),'RF_RVA':RF_RVA,'RF_PIN':RF_PIN.hex(),
        'UW_pins':[{'rva':rva,'raw_hex':pin.hex()}for rva,pin in UW_PINS],
        'body_begin':BEGIN,'body_end':END,'body_bytes':END-BEGIN,
        'source_PID_is_current_identity':False,'mutable_addon_docs_used_as_source':False}
    result['authorized_process']={'PID':EXPECTED_PID,'exe_path':EXPECTED_PATH,
        'startup':EXPECTED_START,'creation_time_filetime':EXPECTED_CREATION_TICK}
    return result


def capture(budget,evidence):
    n=END-BEGIN
    # All fixed metadata/PIN rereads plus outer PE/JMP/FSM post gates reserved.
    extra=2*n+2*len(PAIR_PIN)+2*len(RF_PIN)+2*sum(len(pin)for rva,pin in UW_PINS)+4096+5+12
    budget.require_capacity(extra,14)
    if budget.query_calls+14>MAX_READS:raise ValueError('TAB_CALLBACK_IMPL_POST_QUERY_RESERVE')
    if budget.read_module(PAIR_RVA,len(PAIR_PIN),'registered_parent_pair_pin',True)!=PAIR_PIN:
        raise ValueError('TAB_CALLBACK_IMPL_PARENT_PAIR_CHANGED')
    if budget.read_module(RF_RVA,len(RF_PIN),'exception_record')!=RF_PIN:
        raise ValueError('TAB_CALLBACK_IMPL_RF_CHANGED')
    a,b,u=struct.unpack_from('<III',RF_PIN);f,g,fu=struct.unpack_from('<III',RF_PIN,12)
    if (a,b,u)!=(BEGIN,END,UW_PINS[0][0])or not END<f<g<=parent.base.CODE_END or fu!=UW_PINS[1][0]:
        raise ValueError('TAB_CALLBACK_IMPL_FIXED_BOUNDARY_PROFILE')
    for rva,pin in UW_PINS:
        if not parent.RO_BEGIN<=rva<rva+len(pin)<=parent.RO_END:raise ValueError('TAB_CALLBACK_IMPL_UW_SCOPE')
        if budget.read_module(rva,len(pin),'unwind_metadata')!=pin:
            raise ValueError('TAB_CALLBACK_IMPL_UW_CHANGED')
    body=budget.read_module(BEGIN,n,'declared_forwarder_code',True)
    if budget.read_module(BEGIN,n,'declared_forwarder_code',True)!=body:
        raise ValueError('TAB_CALLBACK_IMPL_BODY_CHANGED_AFTER')
    if budget.read_module(PAIR_RVA,len(PAIR_PIN),'registered_parent_pair_pin_after',True)!=PAIR_PIN:
        raise ValueError('TAB_CALLBACK_IMPL_PARENT_PAIR_CHANGED_AFTER')
    if budget.read_module(RF_RVA,len(RF_PIN),'exception_record')!=RF_PIN:
        raise ValueError('TAB_CALLBACK_IMPL_RF_CHANGED_AFTER')
    for rva,pin in UW_PINS:
        if budget.read_module(rva,len(pin),'unwind_metadata')!=pin:
            raise ValueError('TAB_CALLBACK_IMPL_UW_CHANGED_AFTER')
    metadata=RF_PIN+b''.join(pin for rva,pin in UW_PINS)
    evidence.update(metadata_only=False,capture_purpose='ONE_REGISTERED_CALLBACK_ACTUAL317_BODY',
        metadata_readiness='KNOWN_TWO_RF_AND_UW_BEFORE_AFTER_COMPLETE',
        function_begin=BEGIN,function_end=END,selected_RF_index=96794,foreign_RF_index=96795,
        selected_RF_has_CHAIN=False,first_foreign_begin=f,body_captured=True,
        body_before_after_match=True,parent_pair_before_after_match=True,RF_UW_before_after_match=True,
        callback_registration_proven=True,normal_tab_input_consumer_proven=False,
        normal_CFG_closed=False,logical_function_complete=False,
        input_values_read=False,helpers_followed=False,handler_code_read=False,opaque_handler_data_read=False,
        foreign_body_read=False,extra_callee_reads=0,
        process_creation_time_queries=2,process_start_checked_in_before_after_identity=True,
        body={'begin':BEGIN,'end':END,'length':n,'binary_offset':len(metadata),'sha256':hashlib.sha256(body).hexdigest()},
        implementation_tool_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ranges=[{'kind':'two_known_RF','rva':RF_RVA,'length':24,'binary_offset':0},
                {'kind':'known_primary_UW','rva':UW_PINS[0][0],'length':16,'binary_offset':24},
                {'kind':'known_foreign_UW','rva':UW_PINS[1][0],'length':16,'binary_offset':40},
                {'kind':'actual_callback_body','rva':BEGIN,'length':n,'binary_offset':56}])
    return metadata+body


def native_creation_tick(pid,process_factory):
    """GetProcessTimes only, from an existing read/query-only Process adapter."""
    import ctypes
    from ctypes import wintypes
    with process_factory(pid)as process:
        fn=process._kernel.GetProcessTimes
        fn.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4;fn.restype=wintypes.BOOL
        creation,exit_time,kernel_time,user_time=(wintypes.FILETIME()for _ in range(4))
        if not fn(process._require_open(),ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel_time),ctypes.byref(user_time)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (creation.dwHighDateTime<<32)|creation.dwLowDateTime


parent.REVISION='career_tab_callback_17AF020_actual317_v1'
parent.TARGET_RVA,parent.CALLER,parent.CALL_PIN=BEGIN,JMP_RVA,JMP_PIN
parent.EXPECTED_PID=EXPECTED_PID
parent.MAX_BYTES,parent.MAX_READS,parent.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
parent.base.MAX_DECLARATION_BYTES,parent.base.MAX_DECLARATION_READS=8192,64
parent.validate_source,parent.capture=validate_source,capture

def run(output,dependencies=None,clock=time.perf_counter):
    deps=dict(dependencies if dependencies is not None else parent.base.profile.load_dependencies())
    original=deps['resolve_game']
    creation=deps.get('process_creation_tick',lambda pid:native_creation_tick(pid,deps['Process']))
    def resolve(pid):
        if pid!=EXPECTED_PID:raise ValueError('TAB_CALLBACK_IMPL_AUTHORIZED_PID_ONLY')
        identity=original(pid)
        if identity.get('exe_path','').replace('\\','/').casefold()!=EXPECTED_PATH.casefold():
            raise ValueError('TAB_CALLBACK_IMPL_EXE_PATH_CHANGED')
        tick=creation(pid)
        if tick!=EXPECTED_CREATION_TICK:raise ValueError('TAB_CALLBACK_IMPL_PROCESS_START_CHANGED')
        return {**identity,'process_creation_time_filetime':tick,'authorized_process_start':EXPECTED_START}
    deps['resolve_game']=resolve
    return parent.run(output,deps,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError)as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
