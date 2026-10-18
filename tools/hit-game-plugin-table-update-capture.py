"""Fixed plugin table200B twice and proved slot's80B code window, read-only.

Recalculate all11 RIP-LEA/RIP-store values from the frozen actual getter.
Current table+0x68 and all11 known stores must match currentGameBase+RVA
before reading4EE6C0..4EE710. Unknown table words are saved, never followed.
Original locator snapshots/state/PID/module gates surround these3 reads;
16KiB/24RPM-query/2s. Windows are not declarations/full functions/API fields.
No Game calls/writes,other table/provider/heap reads,UW,callee,loop or retry.
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
REVISION = 'game_plugin_known_table_update_window_v1'
FOLLOWUP = ROOT / 'tools/hit-game-plugin-entry-window-capture.py'
FOLLOWUP_SHA = '1f346fdce4b18d10dbc5bd4a9862eebb6ea6a8a7f5aa75d9ab24baeff851d8d8'
SOURCE = ROOT / 'dist/hit-game-plugin-entry-window-live-20261013-v1'
SOURCE_SHA = 'b62cdeb0c187392411c85d53a4d28c1fda76e150fc5a80c7616431fe946b69b9'
BINARY_SHA = '4c1c9fdfa8e26bba9bcc4743ee61af2f5bfefe229a2f7bf703b9bc44bcfa6118'
ANALYSIS_SHA = 'bb2feb2d2921dd9c5a1bbc7d89794025b9b389fcc6df9cacccd1f034c6d3e4e5'
GETTER_RVA, TABLE_RVA, TABLE_BYTES = 0x4EEAD0, 0x37CEB10, 200
UPDATE_RVA, UPDATE_BYTES, UPDATE_SLOT = 0x4EE6C0, 80, 0x68


def private_followup():
    if hashlib.sha256(FOLLOWUP.read_bytes()).hexdigest() != FOLLOWUP_SHA:
        raise ValueError('PLUGIN_TABLE_FROZEN_FOLLOWUP_CHANGED')
    spec = importlib.util.spec_from_file_location('_plugin_known_table_source', FOLLOWUP)
    followup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(followup)
    return followup


def validate_source(fingerprint, folder=SOURCE):
    meta_raw = (Path(folder) / 'plugin-entry-window.json').read_bytes()
    binary = (Path(folder) / 'plugin-entry-window.bin').read_bytes()
    analysis_raw = (Path(folder) / 'getter-analysis.json').read_bytes()
    if (hashlib.sha256(meta_raw).hexdigest() != SOURCE_SHA or len(binary) != 256
            or hashlib.sha256(binary).hexdigest() != BINARY_SHA
            or hashlib.sha256(analysis_raw).hexdigest() != ANALYSIS_SHA):
        raise ValueError('PLUGIN_TABLE_GETTER_SOURCE_CHANGED')
    meta, analysis = json.loads(meta_raw), json.loads(analysis_raw)
    if (not meta.get('complete') or not meta.get('source_gates_verified')
            or meta.get('window_rva') != GETTER_RVA or meta.get('window_bytes') != 256
            or meta.get('sha256') != BINARY_SHA or meta.get('fingerprint') != fingerprint
            or meta.get('declared_code_complete') is not False
            or meta.get('logical_function_complete') is not False
            or analysis.get('source_sha256') != BINARY_SHA or analysis.get('table_return_rva') != TABLE_RVA
            or analysis.get('interpreted_code_bytes') != 173 or len(analysis['stores']) != 11):
        raise ValueError('PLUGIN_TABLE_GETTER_SOURCE_PROFILE')
    # Fixed instruction forms are independently checked against captured code,
    # not inferred from instruction labels/field names in the analysis JSON.
    stores = []
    for i in range(11):
        at = 8 + i * 14
        if binary[at:at + 3] != b'\x48\x8d\x05' or binary[at + 7:at + 10] != b'\x48\x89\x05':
            raise ValueError('PLUGIN_TABLE_GETTER_LEA_STORE_OPCODE')
        value = GETTER_RVA + at + 7 + struct.unpack_from('<i', binary, at + 3)[0]
        slot = GETTER_RVA + at + 14 + struct.unpack_from('<i', binary, at + 10)[0]
        row = {'instruction_rva': GETTER_RVA + at + 7, 'slot_rva': slot,
               'value_rva': value, 'offset_from_return': slot - TABLE_RVA}
        if (row != analysis['stores'][i] or not 0 <= row['offset_from_return'] <= TABLE_BYTES - 8
                or row['offset_from_return'] % 8 or not 0x1000 <= value < 0x2110A93):
            raise ValueError('PLUGIN_TABLE_GETTER_LEA_STORE_ARITHMETIC')
        stores.append(row)
    at = 8 + 11 * 14
    if (binary[:8] != bytes.fromhex('85c90f85a2000000')
            or binary[at:at + 3] != b'\x48\x8d\x05'
            or GETTER_RVA + at + 7 + struct.unpack_from('<i', binary, at + 3)[0] != TABLE_RVA
            or binary[169:173] != bytes.fromhex('c333c0c3')
            or [row for row in stores if row['offset_from_return'] == UPDATE_SLOT][0]['value_rva'] != UPDATE_RVA):
        raise ValueError('PLUGIN_TABLE_GETTER_RETURN_OR_UPDATE_ARITHMETIC')
    return {'directory': str(Path(folder).resolve()), 'metadata_sha256': SOURCE_SHA,
            'binary_sha256': BINARY_SHA, 'analysis_sha256': ANALYSIS_SHA,
            'getter_rva': GETTER_RVA, 'table_rva': TABLE_RVA, 'table_bytes': TABLE_BYTES,
            'stores': stores, 'lea_store_arithmetic_rechecked': True,
            'update_slot_offset': UPDATE_SLOT, 'candidate_update_rva': UPDATE_RVA,
            'engine_sdk_field_names_proven': False, 'function_signature_proven': False}


def verify_known_slots(raw, base, stores):
    if len(raw) != TABLE_BYTES:
        raise ValueError('PLUGIN_TABLE_TABLE_SIZE')
    for row in stores:
        if struct.unpack_from('<Q', raw, row['offset_from_return'])[0] != base + row['value_rva']:
            raise ValueError(f"PLUGIN_TABLE_KNOWN_SLOT_CHANGED: +{row['offset_from_return']:#x}")
    if struct.unpack_from('<Q', raw, UPDATE_SLOT)[0] != base + UPDATE_RVA:
        raise ValueError('PLUGIN_TABLE_UPDATE_SLOT_CHANGED')


def run(output, dependencies=None, clock=time.perf_counter):
    followup = private_followup()
    locator = followup.private_locator()
    reader = locator.private_reader()
    locator.private_reader = lambda: reader
    old_source = locator.validate_source()
    actual_prefix = followup.validate_source(locator)
    source = validate_source(reader.profile.FINGERPRINT)
    locator.validate_source = lambda: {**source, 'actual_getter_prefix_source': actual_prefix,
                                      'original_export_provenance': old_source,
                                      'frozen_followup_sha256': FOLLOWUP_SHA}
    original_snapshot = locator.snapshot
    captured = {}
    def snapshot_with_fixed_table(budget):
        snapshot = original_snapshot(budget)
        if snapshot[2].hex() != followup.PIN_HEX:
            raise ValueError('PLUGIN_TABLE_ACTUAL_GETTER_PIN_CHANGED')
        if not captured:
            first = budget.read_module(TABLE_RVA, TABLE_BYTES, 'known_plugin_table_before')
            verify_known_slots(first, budget.identity['game_base'], source['stores'])
            code = budget.read_module(UPDATE_RVA, UPDATE_BYTES, 'candidate_update_fixed_code_window', True)
            second = budget.read_module(TABLE_RVA, TABLE_BYTES, 'known_plugin_table_after')
            if first != second:
                raise ValueError('PLUGIN_TABLE_CHANGED_DURING_UPDATE_WINDOW')
            captured.update(table=first, code=code)
        return snapshot
    locator.snapshot = snapshot_with_fixed_table
    status = locator.run(output, dependencies=dependencies, clock=clock)
    meta = json.loads(Path(status['json_path']).read_text('utf8'))
    folder = Path(output).resolve()
    binary, report = folder / 'plugin-table-update.bin', folder / 'plugin-table-update.json'
    raw = captured['table'] + captured['code']
    meta.update(source_revision=REVISION, capture_purpose='FIXED_KNOWN_PLUGIN_TABLE_AND_UPDATE_CANDIDATE_WINDOW',
        named_lookup_only=False, getter_rva=GETTER_RVA, table_rva=TABLE_RVA, table_bytes=TABLE_BYTES,
        target_rva=UPDATE_RVA, target_name='getter_store_0x68_code_candidate', code_window_bytes=UPDATE_BYTES,
        table_before_after_match=True, known_getter_stores_match_current_game_base=True,
        unknown_table_words_followed=False, table_qword_hex=[f'{v:016x}' for v in struct.unpack('<25Q', captured['table'])],
        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest(), lookup_json_path=status['json_path'],
        ranges=[{'kind': 'table', 'module': 'game', 'rva': TABLE_RVA, 'length': TABLE_BYTES, 'binary_offset': 0},
                {'kind': 'fixed_code_window', 'module': 'game', 'rva': UPDATE_RVA, 'length': UPDATE_BYTES, 'binary_offset': TABLE_BYTES}],
        declared_code_complete=False, logical_function_complete=False, pdata_read=False,
        boundary_kind='fixed80B_code_window_not_function_declaration', extra_callee_reads=0,
        engine_sdk_field_names_proven=False, plugin_table_contract_proven=False)
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
