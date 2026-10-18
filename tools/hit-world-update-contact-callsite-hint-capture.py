"""Fixed-record hint for the same AB5FEF declaration-clipped CALL windows.

The failed v1 packet is only a location hint, never a completed capture.
Replace binary search with a fresh exact 12B containing record read, fresh
bounded unwind metadata, and a second identical record read. Original PE,
12B CALL/predecessor PIN, state/context/PID/module pre/post gates remain.
No larger window or budget: <=117B code, 24KiB/32RPM-query/2s soft.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / 'tools/hit-world-update-contact-callsite-capture.py'
V1_SHA = 'a46b04f2851687fd719a7162f1ecf3bb183e833f2b07f0df6f4d25280ce6ec67'
if hashlib.sha256(V1.read_bytes()).hexdigest() != V1_SHA:
    raise ValueError('CONTACT_CALLSITE_HINT_FROZEN_V1_CHANGED')
spec = importlib.util.spec_from_file_location('_contact_callsite_hint_private_v1', V1)
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
REVISION = 'game_world_update_contact_callsite_windows_v2_record_hint'
HINT = ROOT / 'dist/hit-world-update-contact-callsite-live-20261013-v1/callsite.incomplete.json'
HINT_SHA = 'd10d1173c966133ae3edeca1d57d74adcc36518714cc8bd0d6f21086b5521550'
HINT_INDEX = 43772
HINT_RVA = v1.frozen.EXCEPTION_RVA + HINT_INDEX * 12
HINT_BYTES = bytes.fromhex('5450ab00d662ab003c6e4a02')
DECL_BEGIN, DECL_END, UNWIND_RVA = struct.unpack('<III', HINT_BYTES)


def validate_hint(path=HINT):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != HINT_SHA:
        raise ValueError('CONTACT_CALLSITE_HINT_PARTIAL_SOURCE_CHANGED')
    meta = json.loads(raw)
    matches = [row for row in meta.get('exception_records', []) if row.get('index') == HINT_INDEX]
    expected = {'index': HINT_INDEX, 'rva': HINT_RVA, 'raw_hex': HINT_BYTES.hex(),
                'begin': DECL_BEGIN, 'end': DECL_END, 'unwind_rva': UNWIND_RVA}
    if (meta.get('status') != 'failed' or meta.get('complete') is not False
            or meta.get('partial_binary_saved') is not False
            or meta.get('error') != 'CONTACT_FORWARDER_READ_BUDGET'
            or meta.get('source_revision') != 'game_world_update_contact_callsite_windows_v1'
            or meta.get('target_module') != 'game' or meta.get('target_rva') != v1.TARGET_RVA
            or meta.get('call_destination_rva') != v1.CALL_DESTINATION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or meta.get('source', {}).get('sha256') != v1.SOURCE_SHA
            or len(matches) != 1 or matches[0] != expected
            or meta.get('function_begin') != DECL_BEGIN or meta.get('function_end') != DECL_END
            or not v1.frozen.CODE_BEGIN <= DECL_BEGIN <= v1.PIN_RVA
                < v1.TARGET_RVA + 5 <= DECL_END <= v1.frozen.CODE_END
            or HINT_RVA + 12 > v1.frozen.EXCEPTION_RVA + v1.frozen.EXCEPTION_SIZE):
        raise ValueError('CONTACT_CALLSITE_HINT_PARTIAL_PROFILE')
    return {'path': str(Path(path).resolve()), 'sha256': HINT_SHA,
            'source_complete': False, 'location_hint_only': True,
            'record_index': HINT_INDEX, 'record_rva': HINT_RVA,
            'record_hex': HINT_BYTES.hex(), 'fresh_record_and_unwind_required': True}


_original_source = v1.validate_source
_original_reader = v1.frozen.profile.private_reader
_original_capture = v1.capture


def validate_source():
    source = _original_source()
    source['record_location_hint'] = validate_hint()
    source['hint_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    source['frozen_v1_wrapper_sha256'] = V1_SHA
    return source


def private_reader():
    reader = _original_reader()

    def find_function(budget, journal):
        raw = budget.read_module(HINT_RVA, 12, 'exception_record')
        if raw != HINT_BYTES:
            raise ValueError('CONTACT_CALLSITE_HINT_FRESH_RECORD_CHANGED')
        begin, end, unwind = struct.unpack('<III', raw)
        reader.validate_runtime_entry(begin, end, unwind)
        if not begin <= v1.PIN_RVA < v1.TARGET_RVA + 5 <= end:
            raise ValueError('CONTACT_CALLSITE_HINT_RECORD_DOES_NOT_CONTAIN_PIN')
        journal.append({'index': HINT_INDEX, 'rva': HINT_RVA, 'raw_hex': raw.hex(),
            'begin': begin, 'end': end, 'unwind_rva': unwind,
            'selection': 'fresh_fixed_record_from_partial_location_hint'})
        return begin, end

    reader.find_function = find_function
    return reader


def capture(budget, evidence):
    evidence.update(record_hint_only=True, binary_search_performed=False,
                    fixed_record_verified_before_after=False)
    raw = _original_capture(budget, evidence)
    after = budget.read_module(HINT_RVA, 12, 'exception_record')
    evidence['fixed_record_after'] = {'index': HINT_INDEX, 'rva': HINT_RVA, 'raw_hex': after.hex()}
    if after != HINT_BYTES:
        raise ValueError('CONTACT_CALLSITE_HINT_RECORD_CHANGED_DURING_CAPTURE')
    evidence['fixed_record_verified_before_after'] = True
    return raw


# All changes apply only to this independently loaded private v1 instance.
v1.REVISION = REVISION
v1.validate_source = validate_source
v1.frozen.profile.private_reader = private_reader
v1.capture = capture


def run(output, dependencies=None, clock=time.perf_counter):
    return v1.run(output, dependencies, clock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
