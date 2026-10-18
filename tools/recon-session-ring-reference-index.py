"""One fixed-code0 reference index for the proven session record-base offset.

Only retained short windows are saved. A byte match is not an instruction or a
discovery event. Uses the existing build/Ship/PIN checks and bounded indexer.
"""
from pathlib import Path
import argparse
import hashlib
import heapq
import importlib.util
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'recon_session_ring_base_reference_index_v3'
# v2 hit the 64-window cap before UI code because each producer repeats the
# slot-index offset. Keep the same scope/cap, narrow to the record base only.
OFFSETS = (0x1F038,)
INDEX = ROOT/'tools/hit-contact-registration-index.py'
INDEX_SHA = '3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
SOURCE = ROOT/'dist/recon-session-event-code-live-20261013-v2/writer.bin'
PIN_RVA = 0x108351A
LAYOUT_PIN = '8b8238f80100488b8aa8b30000448bc049c1e005ffc0898238f80100'
# The frozen index reader has an exact 16-byte build gate.
PIN_HEX = bytes.fromhex(LAYOUT_PIN)[:16].hex()


def validate_source():
    raw = SOURCE.read_bytes()
    offset = PIN_RVA - 0x1083150
    if len(raw) != 4558 or raw[offset:offset+len(bytes.fromhex(LAYOUT_PIN))].hex() != LAYOUT_PIN:
        raise ValueError('RECON_SESSION_RING_SOURCE_CHANGED')
    # Check the same sampled block establishes the record base, peer and type.
    expected = bytes.fromhex('49898c1040f001000f57c0488b0df52d2a0245898c1038f00100')
    if raw[0x1083541-0x1083150:0x1083541-0x1083150+len(expected)] != expected:
        raise ValueError('RECON_SESSION_RING_RECORD_SOURCE_CHANGED')
    return {'writer_source': str(SOURCE), 'sha256': hashlib.sha256(raw).hexdigest(),
            'record_base_offset': OFFSETS[0], 'next_slot_offset': 0x1F838,
            'discovery_type_proven': False}


def byte_matches(buffer, buffer_rva, kind, absolute):
    if kind != 'code': raise ValueError('RECON_SESSION_RING_CODE_ONLY')
    def hits(value):
        needle = struct.pack('<I', value)
        at = buffer.find(needle)
        while at >= 0:
            yield at, 4, f'byte_ring_offset_{value:#x}'
            at = buffer.find(needle, at+1)
    return heapq.merge(*(hits(value) for value in OFFSETS))


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError('RECON_SESSION_RING_FROZEN_INDEX_CHANGED')
    spec = importlib.util.spec_from_file_location('_session_ring_index', INDEX)
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    index.validate_sources()
    source = validate_source()
    original_stream = index.stream_index
    index.REVISION, index.SECTIONS = REVISION, index.SECTIONS[:1]
    index.TARGET_RVA = 0
    index.PIN_RVA, index.PIN_HEX = PIN_RVA, PIN_HEX
    index.byte_matches = byte_matches
    index.validate_sources = lambda: source
    def stream(budget, sections, evidence):
        evidence.pop('target_rva', None)
        evidence.update(capture_purpose='SESSION_RING_STATIC_CODE_REFERENCES',
                        offsets=list(OFFSETS), discovery_type_proven=False,
                        excluded=['heap', 'chat text', 'game calls', 'writes', 'candidate followups'])
        result = original_stream(budget, sections, evidence)
        for row in result['candidates']:
            row.pop('target_rva', None)
            row['offset'] = struct.unpack('<I', bytes.fromhex(row['match_hex']))[0]
        return result
    index.stream_index = stream
    return index


def run(output, pid, dependencies=None, clock=time.perf_counter):
    index = private_index()
    deps = dict(dependencies if dependencies is not None else index.profile.load_dependencies())
    original = deps['game_processes']
    def exact_pid():
        pids = tuple(original())
        if pids != (pid,): raise ValueError('RECON_SESSION_RING_PID_CHANGED')
        return pids
    deps['game_processes'] = exact_pid
    return index.run(output, dependencies=deps, clock=clock)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.pid), ensure_ascii=False, indent=2))
