"""Read one 154-byte local gap joining two already captured ring code windows.

This locates a leaf reader prefix; it does not claim a RUNTIME_FUNCTION boundary
or discoverer semantics. The boundary is from two saved reference windows.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'dist/recon-session-ring-index-live-20261013-v3/references.json'
SOURCE_SHA = '6d589d88d9b4ec20784dda857b9f71e5de104c11dc7797a12db09acb354f2380'
BEGIN, END = 0x1350E98, 0x1350F32
PIN_RVA, PIN = 0x1350F05, '488bc148c1e005480538f001004903c1498900'
spec = importlib.util.spec_from_file_location('_session_reader_local_capture', ROOT/'tools/fire_code_capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
reader.REVISION = 'recon_session_next_record_local_v1'
reader.RANGES = (('session_reader_local_prefix_not_function_boundary', BEGIN, END-BEGIN),)
reader.TOTAL_BYTES = END-BEGIN
reader.PINS = ((PIN_RVA, PIN),)


def validate_source():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('RECON_NEXT_RECORD_INDEX_CHANGED')
    source = json.loads(raw)
    match = next(r for r in source['candidates'] if r['rva'] == 0x1350F0E)
    at = PIN_RVA-match['window_rva']
    window = bytes.fromhex(match['window_hex'])
    if window[at:at+len(bytes.fromhex(PIN))].hex() != PIN or match['window_rva']+len(window) != END:
        raise ValueError('RECON_NEXT_RECORD_PIN_CHANGED')
    previous = next(r for r in source['candidates'] if r['rva'] == 0x1350E74)
    before = bytes.fromhex(previous['window_hex'])
    if previous['window_rva']+len(before) != BEGIN or not before.endswith(bytes.fromhex('c3cccccccccccc')):
        raise ValueError('RECON_NEXT_RECORD_LEFT_BOUNDARY_CHANGED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    validate_source()
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    stamps = reader.fingerprints()
    if tuple(game_processes()) != (args.pid,): raise ValueError('RECON_NEXT_RECORD_PID_CHANGED')
    identity=resolve_game(args.pid)
    reader.validate_identity(identity,stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process:
        data,meta=reader.capture(process,identity)
    final=resolve_game(args.pid)
    reader.validate_identity(final,stamps)
    if final != identity: raise ValueError('RECON_NEXT_RECORD_IDENTITY_CHANGED')
    meta.update(game_pid=args.pid,source_index_sha256=SOURCE_SHA,declared_function_boundary=False,
                discovery_type_proven=False,session_payloads_read=0,attempts=1)
    (args.output/'reader-local.bin').write_bytes(data)
    (args.output/'reader-local.json').write_text(json.dumps(meta,indent=2),'utf8')
    print(json.dumps({'status':'complete','bytes':len(data),'ranges':meta['ranges']}))


if __name__=='__main__': main()
