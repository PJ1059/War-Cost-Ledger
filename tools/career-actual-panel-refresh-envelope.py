"""Read only the actual18E6DC0 refresh's adjacent chained declarations.

One known call, at most8 adjacent RF records, existing32-IO/8KiB/2s cap.
Stop at the next different primary function; never read that function's code.
No invocation, UI data, account write, wait, retry or arbitrary target input.
"""
from pathlib import Path
import importlib.util
import hashlib
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'dist/career-actual-panel-refresh-live-20261013-v1/capture'
BIN_SHA = '09effc5522ccde8c5716ec370497729b05a4584c8cfd9be834f2e250ce0945db'
original = (SOURCE/'drain.bin').read_bytes()
saved = json.loads((SOURCE/'drain.json').read_text('utf-8'))
if (hashlib.sha256(original).hexdigest()!=BIN_SHA or len(original)!=18
        or original[:5].hex()!='e8dd89ffff'
        or original[5:].hex()!='48894c2408415441554883ec48'):
    raise ValueError('CAREER_REFRESH_HEAD_SOURCE_CHANGED')
anchor = saved['exception_records'][-1]
PRIMARY = (anchor['begin'],anchor['end'],anchor['unwind_rva'])
if PRIMARY[:2]!=(0x18E6DC0,0x18E6DCD):
    raise ValueError('CAREER_REFRESH_HEAD_DECLARATION_CHANGED')

spec = importlib.util.spec_from_file_location('_career_refresh_envelope_private',
    ROOT/'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
reader = session.reader
REVISION='career_actual_refresh_chained_envelope_v1'
session.REVISION=reader.REVISION=REVISION

def capture(process,identity,clock=time.perf_counter,evidence=None):
    budget=reader.Budget(process,identity,clock)
    call=reader.checked_metadata_read(budget,0x18EE3DE,5)
    if call!=original[:5]:raise ValueError('CAREER_REFRESH_CALL_PIN_CHANGED')
    record_rva=reader.EXCEPTION_RVA+anchor['index']*12
    records=reader.checked_metadata_read(budget,record_rva,96)
    entries=[struct.unpack_from('<III',records,i*12) for i in range(8)]
    if entries[0]!=PRIMARY:raise ValueError('CAREER_REFRESH_PRIMARY_CHANGED')
    cache={}
    def metadata(rva,n):
        key=(rva,n)
        if key not in cache:cache[key]=reader.checked_metadata_read(budget,rva,n)
        return cache[key]
    selected=[];chains=[];stopped=False
    for i,entry in enumerate(entries):
        nodes=[]
        reader.unwind_ancestry(entry,metadata,nodes)
        last=nodes[-1]
        if (last['begin'],last['end'],last['unwind_rva'])!=PRIMARY:
            stopped=True;break
        if selected and selected[-1][1]!=entry[0]:
            raise ValueError('CAREER_REFRESH_NONCONTIGUOUS_FAMILY')
        selected.append(entry);chains.append(nodes)
    if evidence is not None:
        evidence.update(adjacent_record_rva=record_rva,adjacent_records_hex=records.hex(),
            selected_declarations=selected,unwind_families=chains,budget=budget.summary())
    if not stopped:raise ValueError('CAREER_REFRESH_FAMILY_EXCEEDS_EIGHT_RECORD_PLAN')
    length=selected[-1][1]-PRIMARY[0]
    if not 13<=length<=4096:raise ValueError('CAREER_REFRESH_CODE_SIZE')
    window=reader.window_capture((('actual_career_refresh_chained_declarations',PRIMARY[0],length),))
    window.PINS=((PRIMARY[0],original[5:].hex()),)
    binary,meta=window.capture(budget,identity,sleep=lambda _:None)
    if (reader.checked_metadata_read(budget,0x18EE3DE,5)!=call
            or reader.checked_metadata_read(budget,record_rva,96)!=records):
        raise ValueError('CAREER_REFRESH_SOURCE_CHANGED_DURING_CAPTURE')
    meta.update(source_revision=REVISION,source_sha256=BIN_SHA,caller_rva=0x18EE3DE,
        caller_pin=call.hex(),primary_declaration=PRIMARY,
        declarations=[{'index':anchor['index']+i,'begin':a,'end':b,'unwind_rva':u}
                      for i,(a,b,u) in enumerate(selected)],unwind_families=chains,
        stopped_before_different_primary=True,declared_family_complete=True,
        logical_function_complete=False,native_called=False,native_written=False,
        code_only=True,budget=budget.summary())
    return binary,meta

session.reader.capture=capture

if __name__=='__main__':
    session.main()
