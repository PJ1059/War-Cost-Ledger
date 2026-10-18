"""One Ship-only read of one proven Armory switch table slot, not UI/stat data."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_screen2_target_slot_v1'
SOURCE_SHA = '9480213fe1765759f41589b1f3c918d87f00424c7992ba1eb425dbc373e921b1'
CALLER, CALL_PIN = 0x149544E, 'e82d000000'
SWITCH, SWITCH_PIN = 0x14954EC, '418b8c9e44664901'
SLOT, SELECTOR = 0x1496648, 1
spec = importlib.util.spec_from_file_location('career_screen2_slot_private',
                                             ROOT / 'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = session.reader.REVISION = REVISION
session.reader.MAX_BYTES, session.reader.MAX_READS = 17, 3

PROFILES = (('screen_selector_caller', CALLER, bytes.fromhex(CALL_PIN)),
            ('screen_selector_switch', SWITCH, bytes.fromhex(SWITCH_PIN)),
            ('screen2_target_slot', SLOT, None))
windows = []
for name, rva, pin in PROFILES:
    length = len(pin) if pin is not None else 4
    window = session.reader.window_capture(((name, rva, length),))
    window.PINS = ((rva, pin.hex()),) if pin is not None else ()
    windows.append(window)


def capture(process, identity, clock=time.perf_counter, evidence=None):
    budget = session.reader.Budget(process, identity, clock)
    parts, ranges, chunks, pins = [], [], [], []
    offset = 0
    for window in windows:
        raw, meta = window.capture(budget, identity, sleep=lambda _: None)
        parts.append(raw)
        ranges.extend(dict(r, binary_offset=r['binary_offset'] + offset) for r in meta['ranges'])
        chunks.extend(meta['chunks']);pins.extend(meta['pins'])
        offset += len(raw)
    binary = b''.join(parts)
    target = struct.unpack_from('<I', binary, 13)[0]
    if not 0 < target < identity['game_size']:
        raise ValueError('CAREER_SCREEN2_TARGET_OUTSIDE_IMAGE')
    meta.update(source_revision=REVISION, bytes_planned=17, bytes_written=17,
                source_binary_sha256=SOURCE_SHA, ranges=ranges, chunks=chunks, pins=pins,
                binary_sha256=hashlib.sha256(binary).hexdigest(), budget=budget.summary(),
                selector=SELECTOR, table_rva=0x1496644, slot_rva=SLOT,
                target_rva=target, target_executed=False, code_only=True,
                statistics_read=False, career_stats_ready=False,
                classification_ready=False, complete_stream=False)
    return binary, meta


def verify_saved(meta, raw):
    expected = [{'name': name, 'rva': rva, 'length': len(pin) if pin is not None else 4,
                 'binary_offset': offset} for (name, rva, pin), offset in zip(PROFILES, (0, 5, 13))]
    if (len(raw) != 17 or raw[:5] != bytes.fromhex(CALL_PIN)
            or raw[5:13] != bytes.fromhex(SWITCH_PIN)
            or meta['ranges'] != expected or meta['source_revision'] != REVISION
            or meta['source_binary_sha256'] != SOURCE_SHA
            or meta['selector'] != 1 or meta['slot_rva'] != SLOT
            or meta['target_rva'] != struct.unpack_from('<I', raw, 13)[0]
            or not 0 < meta['target_rva'] < session.reader.IMAGE_SIZE
            or meta['sha256'] != hashlib.sha256(raw).hexdigest()
            or meta['statistics_read'] is not False or meta['career_stats_ready'] is not False
            or meta['target_executed'] is not False
            or meta['native_written'] is not False or meta['native_called'] is not False
            or meta['budget']['read_calls'] != 3 or meta['budget']['bytes_requested'] != 17
            or meta['budget']['bytes_returned'] != 17):
        raise ValueError('CAREER_SCREEN2_SAVED_PROFILE')


session.reader.capture = capture

def run(output, dependencies=None):
    status = session.run(output, dependencies)
    meta = json.loads(Path(status['json_path']).read_text('utf8'))
    raw = Path(status['binary_path']).read_bytes()
    verify_saved(meta, raw)
    return status


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
