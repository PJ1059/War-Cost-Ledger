"""One fixed256B window at named get_plugin_api, not a declared/full body.

Private frozen locator snapshots are unchanged. Between their two header/
export/prefix snapshots, read only GameDLL4EEAD0..4EEBD0 after the actual16B
PIN matches. All reads share16384B/24RPM-query/2s with realTitle2/Ship3 and
currentPID/modules/fingerprints. No pdata,callee,table-object,heap,registry,
execution/write,loop/retry/wait or arbitrary RVA/size CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'game_named_plugin_entry_fixed_window_v1'
LOCATOR = ROOT / 'tools/hit-game-plugin-export-locator.py'
LOCATOR_SHA = '82346fce9dec9a84d7af88e556fd448bf3f1893cf6c48888baa7f00b2b8a3ded'
SOURCE = ROOT / 'dist/hit-game-plugin-export-live-20261013-v1'
SOURCE_SHA = 'd9245f9950f04bbf19b3e26baccddf0d44a01a749cf5c12688dc57be40588c82'
PREFIX_SHA = 'e075e66a47e17e42a204687015dc6f1ade02930770855e8e2bd2387be17a42d5'
TARGET_RVA, WINDOW_BYTES = 0x4EEAD0, 256
PIN_HEX = '85c90f85a2000000488d0581f6ffff48'


def private_locator():
    if hashlib.sha256(LOCATOR.read_bytes()).hexdigest() != LOCATOR_SHA:
        raise ValueError('PLUGIN_WINDOW_FROZEN_LOCATOR_CHANGED')
    spec = importlib.util.spec_from_file_location('_plugin_fixed_entry_locator', LOCATOR)
    locator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(locator)
    return locator


def validate_source(locator, folder=SOURCE):
    raw = (Path(folder) / 'plugin-export.json').read_bytes()
    prefix = (Path(folder) / 'plugin-export-prefix.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != SOURCE_SHA or len(prefix) != 16
            or hashlib.sha256(prefix).hexdigest() != PREFIX_SHA or prefix.hex() != PIN_HEX):
        raise ValueError('PLUGIN_WINDOW_LIVE_SOURCE_CHANGED')
    meta = json.loads(raw)
    reader = locator.private_reader()
    if (not meta.get('complete') or not meta.get('source_gates_verified')
            or not meta.get('prefix_before_after_match') or meta.get('target_module') != 'game'
            or meta.get('target_name') != 'get_plugin_api' or meta.get('target_rva') != TARGET_RVA
            or meta.get('target_prefix_hex') != PIN_HEX or meta.get('sha256') != PREFIX_SHA
            or meta.get('fingerprint') != reader.profile.FINGERPRINT
            or meta.get('loaded_export_directory_sha256') != locator.EXPORT_SHA
            or locator.parse_export(bytes.fromhex(meta['loaded_export_directory_hex'])) != meta['named_export']):
        raise ValueError('PLUGIN_WINDOW_LIVE_SOURCE_PROFILE')
    return {'directory': str(Path(folder).resolve()), 'metadata_sha256': SOURCE_SHA,
            'prefix_sha256': PREFIX_SHA, 'name': 'get_plugin_api', 'target_module': 'game',
            'target_rva': TARGET_RVA, 'pin_hex': PIN_HEX,
            'function_signature_proven': False, 'plugin_table_contract_proven': False}


def run(output, dependencies=None, clock=time.perf_counter):
    locator = private_locator()
    reader = locator.private_reader()
    locator.private_reader = lambda: reader
    old_source = locator.validate_source()
    source = validate_source(locator)
    locator.validate_source = lambda: {**source, 'original_export_provenance': old_source,
                                      'frozen_locator_sha256': LOCATOR_SHA}
    original_snapshot = locator.snapshot
    captured = {}
    def snapshot_with_fixed_window(budget):
        current = original_snapshot(budget)
        if current[2].hex() != PIN_HEX:
            raise ValueError('PLUGIN_WINDOW_ACTUAL_ENTRY_PIN_CHANGED')
        if not captured:
            # One window, strictly between the two existing complete snapshots.
            window = budget.read_module(TARGET_RVA, WINDOW_BYTES, 'fixed_named_entry_code_window', True)
            if window[:16].hex() != PIN_HEX:
                raise ValueError('PLUGIN_WINDOW_PREFIX_CHANGED_INSIDE_WINDOW')
            captured['window'] = window
        return current
    locator.snapshot = snapshot_with_fixed_window
    # No result/code-window BIN is saved unless the original locator's full
    # second snapshot, realphase/currentPID/module/fingerprint gates all pass.
    status = locator.run(output, dependencies=dependencies, clock=clock)
    meta = json.loads(Path(status['json_path']).read_text('utf8'))
    folder = Path(output).resolve()
    binary, report = folder / 'plugin-entry-window.bin', folder / 'plugin-entry-window.json'
    raw = captured['window']
    meta.update(source_revision=REVISION, capture_purpose='FIXED_NAMED_ENTRY_CODE_WINDOW_ONLY',
        named_lookup_only=False, fixed_named_lookup_followup=True,
        window_rva=TARGET_RVA, window_bytes=WINDOW_BYTES, window_end_exclusive=TARGET_RVA + WINDOW_BYTES,
        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest(),
        snapshot_prefix_binary_path=status['binary_path'], lookup_json_path=status['json_path'],
        code_bytes=WINDOW_BYTES, binary_entry_offset=0,
        ranges=[{'module': 'game', 'rva': TARGET_RVA, 'length': WINDOW_BYTES, 'binary_offset': 0}],
        declared_code_complete=False, logical_function_complete=False,
        boundary_kind='fixed256B_window_not_function_declaration', pdata_read=False,
        code_window_read_once=True, extra_callee_reads=0)
    binary.write_bytes(raw)
    report.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf8')
    result = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
              'binary_path': str(binary), 'sha256': meta['sha256']}
    reader.profile.tail['write_status'](folder, result)
    return result


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
