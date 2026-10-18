"""One exact 4705B declared range learned from the retained failed attempt.

Fresh-check the actual call and the single .pdata record; do not increase the
general metadata reader's 4096B cap. Each body read remains <=4096B.
Only code/declared metadata is read, in Ship, with no writes or native calls.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'impact_consumer_exact_declared_4705_v1'
CALLER, CALL_PIN = 0x12A7A69, bytes.fromhex('e8124b69ff')
BEGIN, END, UNWIND = 0x93C580, 0x93D7E1, 0x247CEB0
RECORD_RVA, RECORD = 0x403A6B4, bytes.fromhex('80c59300e1d79300b0ce4702')
SIZE = END - BEGIN
spec = importlib.util.spec_from_file_location('known_impact_consumer_session',
                                            ROOT / 'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = REVISION


def capture(process, identity, clock=time.perf_counter, evidence=None):
    started = clock()
    chunks, parts = [], []
    def read(rva, n, executable):
        if clock()-started >= 2 or not 0 < n <= 4096:
            raise ValueError('KNOWN_CONSUMER_BUDGET')
        address = identity['game_base'] + rva
        if not 0 <= rva < rva+n <= identity['game_size']:
            raise ValueError('KNOWN_CONSUMER_RANGE')
        region=process.query(address)
        allowed=(0x20,0x40,0x80) if executable else (2,4,8,0x20,0x40,0x80)
        if (region['state']!=0x1000 or region['type']!=0x1000000
                or region['protect']&0x100 or region['protect']&0xff not in allowed
                or not region['base']<=address<address+n<=region['base']+region['size']):
            raise ValueError('KNOWN_CONSUMER_PAGE')
        raw=process.read(address,n)
        chunks.append({'rva':rva,'length':n,'kind':'code' if executable else 'metadata'})
        if len(raw)!=n: raise ValueError('KNOWN_CONSUMER_SHORT_READ')
        parts.append(raw)
        return raw
    if evidence is not None:
        evidence.update(chunks=chunks,source_revision=REVISION)
    prefix=read(CALLER,5,True)
    if prefix!=CALL_PIN or CALLER+5+struct.unpack_from('<i',prefix,1)[0]!=BEGIN:
        raise ValueError('KNOWN_CONSUMER_CALL_PIN')
    record=read(RECORD_RVA,12,False)
    if record!=RECORD or struct.unpack('<III',record)!=(BEGIN,END,UNWIND):
        raise ValueError('KNOWN_CONSUMER_PDATA_CHANGED')
    header=read(UNWIND,4,False)
    session.reader.check_unwind_header(header)
    # Only this exact declared entry; header flags do not authorise other ranges.
    first=read(BEGIN,4096,True)
    last=read(BEGIN+4096,SIZE-4096,True)
    binary=b''.join(parts)
    return binary, {'source_revision':REVISION,'complete':True,'code_only':True,
                    'native_written':False,'native_called':False,'classification_ready':False,
                    'complete_stream':False,'logical_function_complete':False,
                    'captured_at':datetime.now(timezone.utc).isoformat(),
                    'source_failure_sha256':'980ca338ca8240df7eb134ffa182adb2ea30a464f46fb96407ccb694fa45c8c3',
                    'caller_rva':CALLER,'caller_pin':prefix.hex(),
                    'exception_record':{'rva':RECORD_RVA,'raw_hex':record.hex(),
                                        'begin':BEGIN,'end':END,'unwind_rva':UNWIND},
                    'unwind_header':{'rva':UNWIND,'raw_hex':header.hex()},
                    'body_rva':BEGIN,'body_length':SIZE,'body_binary_offset':21,
                    'chunks':chunks,'code_bytes_read':5+len(first)+len(last),
                    'metadata_bytes_read':16,'read_calls':len(chunks),
                    'budget':{'bytes_requested':len(binary),'read_calls':len(chunks),
                              'elapsed_ms':(clock()-started)*1000,'per_read_limit':4096},
                    'binary_sha256':hashlib.sha256(binary).hexdigest()}


session.reader.capture = capture

if __name__=='__main__':
    session.main()
