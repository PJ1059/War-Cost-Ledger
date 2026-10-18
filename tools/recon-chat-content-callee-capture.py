"""One declared RF capture for the proven chat-update callee at 185F8F0.

Revalidate the exact original CALL at 186000B in the same single capture. The
callee is not assumed to be content or visibility code before inspection.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'dist/recon-chat-hud-handler-live-20261013-v2/handler.bin'
SOURCE_SHA='ad82ac5125eac0b4d1acc2424abf91b7a7dfb901d4c67f114c830ce3b8ac17b2'
CALL_RVA,CALL_PIN,TARGET=0x186000B,'e8e0f8ffff',0x185F8F0
spec=importlib.util.spec_from_file_location('_recon_chat_content_capture',ROOT/'tools/recon-session-event-code-capture.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
reader=base.reader
reader.REVISION='recon_chat_known_update_callee_v1'
base.TARGET_RVA=reader.TARGET_RVA=TARGET
base.TARGET_PIN=reader.TARGET_PIN=''
base.CAPTURE_SCOPE='known_chat_update_callee_semantics_unknown'
reader.SOURCE_REFERENCE=str(SOURCE)+': CALL 186000B to 185F8F0'
original_ancestry=reader.unwind_ancestry
original_ranges=reader.ancestry_ranges
original_window=reader.window_capture


def source():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('RECON_CHAT_CALL_SOURCE_CHANGED')
    meta=json.loads(SOURCE.with_suffix('.json').read_text('utf8'))
    record=next(r for r in meta['ranges'] if r['rva']<=CALL_RVA<r['rva']+r['length'])
    offset=record['binary_offset']+CALL_RVA-record['rva']
    pin=raw[offset:offset+5]
    if pin.hex()!=CALL_PIN or CALL_RVA+5+struct.unpack('<i',pin[1:])[0]!=TARGET:
        raise ValueError('RECON_CHAT_DIRECT_CALL_CHANGED')
    return SOURCE_SHA


def ancestry(initial,read,nodes):
    if initial[0]!=TARGET:raise ValueError('RECON_CHAT_CALLEE_ENTRY_NOT_DECLARED')
    original_ancestry(initial,read,nodes)


def ranges(nodes):
    return original_ranges(nodes)+(('proven_chat_update_call',CALL_RVA,5),)


def window(selected):
    instance=original_window(selected)
    instance.PINS=((CALL_RVA,CALL_PIN),)
    return instance


base.verify_source=source
reader.unwind_ancestry=ancestry
reader.ancestry_ranges=ranges
reader.window_capture=window
if __name__=='__main__':base.main()
