"""Final read-only status setter tail and switch table supplement; explicit PID.

One fresh activation callsite PIN then one 2336-byte candidate tail. Total
2341 bytes in exactly two reads, no retry or native call. No gameplay data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('status_code_helpers', ROOT / 'tools/status-code-capture.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
FINGERPRINT = helpers.FINGERPRINT
REVISION = 'status_setter_tail_code_v1'
IMAGE_SIZE = 0x4744000
PINS = ((0x69A76B, 'e8d07affff', 0x692240),)
RANGES = (('effective_toggle_tail_and_switch_tables_candidate', 0x693640, 0x920),)
PIN_BYTES = sum(len(bytes.fromhex(raw)) for _, raw, _ in PINS)
BODY_BYTES = sum(n for _, _, n in RANGES)
TOTAL_BYTES = PIN_BYTES + BODY_BYTES
MAX_CHUNK = 4096
PARENT_JSON = ROOT / 'dist/status-setter-code/status-setter-code-20261011T105022Z-031537b1.json'
PREFIX_SHA = '5d4dde47ad336a652ca5dd59019c418fe3a1b163b4c84f01ba2e903cfe98d63f'
PREFIX_REFERENCES = (
    (0x6925DE, '0fb68402143f6900', 'type_byte_map', 0x693F14),
    (0x6925E6, '8b8c82b43e6900', 'switch_rva_table', 0x693EB4),
    (0x6926E8, '0f844b150000', 'common_tail_branch', 0x693C39),
    (0x6926FD, 'e944150000', 'common_tail_branch', 0x693C46),
)


def range_plan():
    offset, result = PIN_BYTES, []
    for name, rva, n in RANGES:
        result.append({'name': name, 'rva': rva, 'length': n, 'binary_offset': offset,
                       'function_extent_verified': False, 'independent_body_pin_count': 0})
        offset += n
    return result


def pin_plan():
    offset, result = 0, []
    for rva, raw, target in PINS:
        n = len(bytes.fromhex(raw))
        result.append({'rva': rva, 'length': n, 'binary_offset': offset, 'target': target})
        offset += n
    return result


def verify_pins(binary):
    if len(binary) != TOTAL_BYTES:
        raise ValueError('STATUS_SETTER_TAIL_LENGTH_MISMATCH')
    results = []
    for plan, (_, expected, _) in zip(pin_plan(), PINS):
        start, n = plan['binary_offset'], plan['length']
        actual = binary[start:start + n]
        if actual != bytes.fromhex(expected):
            raise ValueError('STATUS_SETTER_TAIL_CALLSITE_CHANGED:' + hex(plan['rva']))
        displacement = int.from_bytes(actual[1:], 'little', signed=True)
        if actual[0] != 0xE8 or plan['rva'] + 5 + displacement != plan['target']:
            raise ValueError('STATUS_SETTER_TAIL_CALLEE_CHANGED')
        results.append({**plan, 'matched': True})
    return results


def verify_parent_material():
    """Disk-only proof of caller PIN and table/branch references in real caches."""
    original_spec = importlib.util.spec_from_file_location('status_setter_prefix_proof', ROOT / 'tools/status-setter-code-capture.py')
    original = importlib.util.module_from_spec(original_spec)
    original_spec.loader.exec_module(original)
    first = original.verify_parent_material()
    meta = json.loads(PARENT_JSON.read_text(encoding='utf8'))
    raw = PARENT_JSON.with_suffix('.bin').read_bytes()
    if (meta.get('binary_sha256') != PREFIX_SHA or hashlib.sha256(raw).hexdigest() != PREFIX_SHA
            or len(raw) != 5722 or meta.get('source_revision') != original.REVISION
            or meta.get('ranges') != original.range_plan()
            or any(meta.get(k) != v for k, v in FINGERPRINT.items())):
        raise ValueError('STATUS_SETTER_TAIL_TAIL_PARENT_MATERIAL_CHANGED')
    original.verify_pins(raw)
    references = []
    for rva, expected, kind, target in PREFIX_REFERENCES:
        window = next(w for w in meta['ranges'] if w['rva'] <= rva < w['rva'] + w['length'])
        at = window['binary_offset'] + rva - window['rva']
        instruction = raw[at:at + len(bytes.fromhex(expected))]
        if instruction != bytes.fromhex(expected):
            raise ValueError('STATUS_SETTER_TAIL_TAIL_PARENT_REFERENCE_CHANGED')
        actual_target = int.from_bytes(instruction[-4:], 'little', signed=False) if kind != 'common_tail_branch' else rva + len(instruction) + int.from_bytes(instruction[-4:], 'little', signed=True)
        if actual_target != target:
            raise ValueError('STATUS_SETTER_TAIL_TAIL_PARENT_TARGET_CHANGED')
        references.append({'rva': rva, 'raw': expected, 'kind': kind, 'target': target})
    return {'json_path': str(PARENT_JSON), 'binary_sha256': PREFIX_SHA,
            'original_callsite_proof': first, 'verified_prefix_references': references,
            'tail_start': 0x693640, 'tail_end_exclusive': 0x693F60}


def capture(process, identity, sleep=time.sleep):
    base = identity['game_base']
    if base < 65536 or base % 4096 or identity['game_size'] != IMAGE_SIZE:
        raise ValueError('STATUS_SETTER_TAIL_MODULE_INVALID')
    chunks, output = [], bytearray()
    plan = [(row['rva'], row['length'], 'fresh_callsite') for row in pin_plan()]
    for name, rva, n in RANGES:
        for offset in range(0, n, MAX_CHUNK):
            plan.append((rva + offset, min(MAX_CHUNK, n - offset), name))
    assert sum(n for _, n, _ in plan) == TOTAL_BYTES == 2341 and len(plan) == 2
    sleep(2)  # Short scheduling gate only; it does not assert a safe/idle game frame.
    started_at = datetime.now(timezone.utc).isoformat()
    for index, (rva, n, name) in enumerate(plan):
        address = base + rva
        started = time.perf_counter()
        region = process.query(address)
        if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                and region['base'] <= address and address + n <= region['base'] + region['size']
                and not region['protect'] & 0x100 and region['protect'] & 0xff in (0x20, 0x40, 0x80)):
            raise ValueError('STATUS_SETTER_TAIL_REGION_UNREADABLE:' + hex(rva))
        raw = process.read(address, n)
        if len(raw) != n:
            raise ValueError('STATUS_SETTER_TAIL_SHORT_READ:' + hex(rva))
        output.extend(raw)
        chunks.append({'name': name, 'rva': rva, 'length': n, 'binary_offset': len(output) - n,
                       'read_ms': (time.perf_counter() - started) * 1000})
        if index < len(PINS) and raw != bytes.fromhex(PINS[index][1]):
            raise ValueError('STATUS_SETTER_TAIL_CALLSITE_CHANGED:' + hex(rva))
        if index + 1 < len(plan):
            sleep(0.1)
    binary = bytes(output)
    pins = verify_pins(binary)
    return binary, {'source_revision': REVISION, **FINGERPRINT, 'identity': dict(identity),
        'purpose': 'effective_status_setter_common_tail_and_type_switch_code_diagnosis',
        'started_at': started_at, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'code_only': True, 'complete': True, 'atomic': False,
        'native_written': False, 'native_called': False, 'process_access_mask': 0x410,
        'layout_ready': False, 'success_count_available': False, 'ship_state_verified': False,
        'attempts': 1, 'soft_read_gate_seconds': 2, 'bytes_planned': TOTAL_BYTES,
        'bytes_written': len(binary), 'code_reads': len(chunks), 'ranges': range_plan(),
        'pins': pins, 'chunks': chunks, 'binary_sha256': hashlib.sha256(binary).hexdigest(),
        'limitations': ['Fresh activation caller PIN establishes only the original setter start; prefix references are verified from the saved real sample.',
                       'Candidate body endings are not verified function boundaries.',
                       'No active target records, sender identities, gameplay events or FPS evidence are captured.']}


def saved_complete(folder):
    try:
        status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        meta_path, binary_path = Path(status['json_path']), Path(status['binary_path'])
        if (status.get('status') != 'complete' or meta_path.parent.resolve() != folder.resolve()
                or binary_path.parent.resolve() != folder.resolve()):
            return None
        meta = json.loads(meta_path.read_text(encoding='utf8'))
        if (not meta.get('complete') or meta.get('source_revision') != REVISION
                or meta.get('ranges') != range_plan()
                or any(meta.get(k) != v for k, v in FINGERPRINT.items())):
            return None
        with binary_path.open('rb') as source:
            raw = source.read(TOTAL_BYTES + 1)
        verify_pins(raw)
        if hashlib.sha256(raw).hexdigest() != meta.get('binary_sha256'):
            return None
        return status
    except (OSError, ValueError, KeyError, TypeError):
        return None


def once(pid, folder):
    stamps, parent = helpers.fingerprints(), verify_parent_material()
    cached = saved_complete(folder)
    if cached:
        return cached
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    if type(pid) is not int or pid <= 0 or tuple(game_processes()) != (pid,):
        raise ValueError('STATUS_SETTER_TAIL_EXACT_PID_REQUIRED')
    identity = resolve_game(pid)
    helpers.validate_identity(identity, stamps)
    if identity['game_size'] != IMAGE_SIZE:
        raise ValueError('STATUS_SETTER_TAIL_MODULE_INVALID')
    with Process(pid) as process:
        binary, meta = capture(process, identity)
    final = resolve_game(pid)
    helpers.validate_identity(final, stamps)
    if final != identity or tuple(game_processes()) != (pid,):
        raise ValueError('STATUS_SETTER_TAIL_MODULE_CHANGED')
    stem = 'status-setter-tail-code-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    binary_path, meta_path = folder / (stem + '.bin'), folder / (stem + '.json')
    meta.update(game_pid=pid, parent_material=parent, binary_path=str(binary_path), json_path=str(meta_path))
    with binary_path.open('xb') as target:
        target.write(binary)
    with meta_path.open('x', encoding='utf8') as target:
        json.dump(meta, target, ensure_ascii=False, indent=2)
    status = {'status': 'complete', 'source_revision': REVISION, 'game_pid': pid,
              'binary_path': str(binary_path), 'json_path': str(meta_path),
              'bytes_written': len(binary), 'code_reads': 2}
    helpers.write_status(folder, status)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/status-setter-tail-code')
    parser.add_argument('--check', action='store_true', help='Disk fingerprints and original caller proof only.')
    parser.add_argument('--self-test', action='store_true', help='Isolated fixtures only; no game enumeration or read.')
    args = parser.parse_args(argv)
    if args.self_test:
        import unittest
        test_spec = importlib.util.spec_from_file_location('setter_tests', ROOT / 'tests/test_status_setter_tail_code_capture.py')
        tests = importlib.util.module_from_spec(test_spec)
        test_spec.loader.exec_module(tests)
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        return 0 if result.wasSuccessful() else 1
    if args.check:
        helpers.fingerprints()
        parent = verify_parent_material()
        print(json.dumps({'status': 'local_build_and_prefix_material_match', 'source_revision': REVISION,
                          'bytes_planned': TOTAL_BYTES, 'code_reads': 2, 'process_access_mask': 0x410,
                          'fresh_callsite_pins': pin_plan(), 'ranges': range_plan(),
                          'parent_material': parent, 'layout_ready': False, 'success_count_available': False}))
        return 0
    if args.pid is None:
        parser.error('--pid is required for the one-shot live capture')
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = once(args.pid, args.output)
        print(json.dumps(result))
        return 0
    except Exception as error:
        helpers.write_status(args.output, {'status': 'failed', 'source_revision': REVISION,
                                          'game_pid': args.pid, 'attempts': 1, 'error': str(error)})
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
