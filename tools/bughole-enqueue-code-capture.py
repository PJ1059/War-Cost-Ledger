"""One fixed 352B destruction-enqueue source window, Ship only.

Reuse the private fixed-window reader and existing PID/module/fingerprint/native
Ship gates. Two six-byte upstream source PIN reads surround the single window.
No arbitrary target/size CLI, metadata search, callee/field follow, write, call,
gameplay action, wait or retry. This is not a destruction event or credit proof.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'tools/hit-queue-consumer-code-capture.py'
FROZEN_SHA = '9e807430d0fad375456b20022209d16ea4fe491da0c28e0fd915c06e3b7cca8e'
READER = ROOT / 'tools/recon_chat_code_capture.py'
READER_SHA = '797b5fcb45d391958e99e7e9305b56433efd20a5148645cb72b9993ed16dd675'
SOURCE = ROOT / 'dist/career-stats-source-audit/upstream/domains/event_natives.lua'
SOURCE_SHA = 'ddb3f08f9c81d2894aa394e60056054bf5c85c78e85e7f9089ea007dbd652e97'
REVISION = 'bughole_destruction_enqueue_fixed352_v1'
BEGIN, SIZE = 0x13E15C0, 352
PIN_RVA, PIN_HEX = 0x13E163D, '0f8dd6000000'
EXPECTED_PID = 67988

for path, expected in ((FROZEN, FROZEN_SHA), (READER, READER_SHA), (SOURCE, SOURCE_SHA)):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('BUGHOLE_FROZEN_SOURCE_CHANGED:' + str(path))
source_text = SOURCE.read_text('utf8')
source_pin = '["label"]="a stage only grows",["rva"]=' + str(PIN_RVA) + ',["hex"]="' + PIN_HEX + '"'
if source_pin not in source_text:
    raise ValueError('BUGHOLE_UPSTREAM_STAGE_PIN_MISSING')
if PIN_RVA + 6 + struct.unpack('<i', bytes.fromhex(PIN_HEX)[2:])[0] != 0x13E1719:
    raise ValueError('BUGHOLE_UPSTREAM_BRANCH_TARGET')

spec = importlib.util.spec_from_file_location('_bughole_fixed_enqueue_session', FROZEN)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = REVISION


def capture(process, identity, clock=time.perf_counter, evidence=None):
    session.reader.validate_module(identity)
    budget = session.reader.Budget(process, identity, clock)
    raw_parts, ranges, chunks = [], [], []
    for name, rva, size in (('enqueue_stage_pin_before', PIN_RVA, 6),
                            ('enqueue_fixed352', BEGIN, SIZE),
                            ('enqueue_stage_pin_after', PIN_RVA, 6)):
        reader = session.reader.window_capture(((name, rva, size),))
        reader.PINS = ((PIN_RVA, PIN_HEX),)
        raw, metadata = reader.capture(budget, identity, sleep=lambda _: None)
        raw_parts.append(raw)
        ranges.extend(dict(item, binary_offset=item['binary_offset'] + sum(map(len, raw_parts[:-1])))
                      for item in metadata['ranges'])
        chunks.extend(metadata['chunks'])
    raw = b''.join(raw_parts)
    if raw[:6] != raw[-6:] or raw[6 + PIN_RVA - BEGIN:12 + PIN_RVA - BEGIN] != raw[:6]:
        raise ValueError('BUGHOLE_STAGE_PIN_CHANGED_INSIDE_WINDOW')
    budget.time_gate()
    metadata = {'source_revision': REVISION, 'complete': True, 'code_only': True,
                'candidate_only': True, 'classification_ready': False,
                'native_written': False, 'native_called': False,
                'destruction_credit_proven': False, 'complete_stream': False,
                'logical_function_complete': False, 'declared_code_complete': False,
                'boundary_kind': 'fixed352B_window_not_function_declaration',
                'source_reference': 'SkyeShade/HD2Runtime ab5b843f836e88bef4139513b539c2b22cc3336f '
                                    'scripts/research_event_destruction.py enqueue 0x13E15C0; '
                                    'cached event_natives.lua a-stage-only-grows PIN',
                'source_sha256': SOURCE_SHA, 'frozen_session_sha256': FROZEN_SHA,
                'frozen_reader_sha256': READER_SHA,
                'body_rva': BEGIN, 'body_length': SIZE, 'body_binary_offset': 6,
                'pin_rva': PIN_RVA, 'pin_hex': PIN_HEX, 'pin_before_after_match': True,
                'code_window_read_once': True, 'extra_callee_reads': 0, 'pdata_read': False,
                'ranges': ranges, 'chunks': chunks, 'code_bytes_read': len(raw),
                'read_calls': len(chunks), 'budget': budget.summary(),
                'binary_sha256': hashlib.sha256(raw).hexdigest()}
    if evidence is not None:
        evidence.update(metadata)
    return raw, metadata


def run(output, dependencies=None):
    deps = dict(dependencies if dependencies is not None else session.tail['load_dependencies']())
    enumerate_game = deps['game_processes']
    def expected_game():
        pids = tuple(enumerate_game())
        if pids != (EXPECTED_PID,):
            raise ValueError('BUGHOLE_EXPECTED_CURRENT_PID:' + str(pids))
        return pids
    deps['game_processes'] = expected_game
    session.reader.capture = capture
    return session.run(output, dependencies=deps)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
