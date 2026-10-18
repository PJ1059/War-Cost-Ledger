"""One read-only loaded get_plugin_api lookup and16B prefix, no API call.

Only fixed GameDLL export directory39D4000/74B, internal tables/strings and
named ordinal1->4EEAD0. Packed original target bytes are provenance, never
the loaded PIN. Two complete snapshots share16KiB/24RPM-query/2s soft with
real Title2/Ship3/currentPID/EXE+Game identity gates. No arbitrary target,
body/unwind/table-object/heap/registry read, native call, write, retry or wait.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'game_named_plugin_export_locator_v1'
READER = ROOT / 'tools/hit-contact-forwarder-code-capture.py'
READER_SHA = '3cb34d65eabbbdd27a188f40e295117aad8c04aca7c9ab4282390f1cb998fc39'
SOURCE = ROOT / 'dist/game-plugin-export-source-20261013'
SOURCE_SHA = '76de5bc694410c5f09ab4bb34c3369f70ad9eba3fad30b44df977ba9b998489b'
EXPORT_SHA = '70394f181ed74a51a996deb4de13555bd35f069ec806da587e4e9cbea4388fd3'
EXPORT_RVA, EXPORT_SIZE = 0x39D4000, 74
TARGET_NAME, TARGET_RVA = 'get_plugin_api', 0x4EEAD0
IMAGE_SIZE = 0x4744000


def private_reader():
    if hashlib.sha256(READER.read_bytes()).hexdigest() != READER_SHA:
        raise ValueError('PLUGIN_LOCATOR_FROZEN_READER_CHANGED')
    spec = importlib.util.spec_from_file_location('_plugin_named_export_reader', READER)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.MAX_BYTES, reader.MAX_READS, reader.MAX_SECONDS = 16384, 24, 2.0
    return reader


def parse_export(raw):
    """All referenced strings and arrays must fit this one fixed74B directory."""
    if len(raw) != EXPORT_SIZE:
        raise ValueError('PLUGIN_LOCATOR_EXPORT_SIZE')
    fields = struct.unpack_from('<IIHHIIIIIII', raw)
    dll_name_rva, base, function_count, name_count, eat_rva, names_rva, ordinals_rva = fields[4:]
    def offset(rva, length):
        at = rva - EXPORT_RVA
        if not 0 <= at < at + length <= len(raw):
            raise ValueError('PLUGIN_LOCATOR_EXPORT_TABLE_OUTSIDE_DIRECTORY')
        return at
    def string(rva):
        at = offset(rva, 1)
        end = raw.find(b'\0', at)
        if end < 0:
            raise ValueError('PLUGIN_LOCATOR_EXPORT_UNTERMINATED_STRING')
        try:
            return raw[at:end].decode('ascii')
        except UnicodeDecodeError:
            raise ValueError('PLUGIN_LOCATOR_EXPORT_NAME_ENCODING') from None
    if (base, function_count, name_count) != (1, 1, 1) or string(dll_name_rva) != 'game.dll':
        raise ValueError('PLUGIN_LOCATOR_EXPORT_UNIQUE_PROFILE')
    name_rva = struct.unpack_from('<I', raw, offset(names_rva, 4))[0]
    ordinal_index = struct.unpack_from('<H', raw, offset(ordinals_rva, 2))[0]
    if string(name_rva) != TARGET_NAME or ordinal_index != 0:
        raise ValueError('PLUGIN_LOCATOR_EXPORT_NAME_OR_ORDINAL_CHANGED')
    target = struct.unpack_from('<I', raw, offset(eat_rva, 4))[0]
    if EXPORT_RVA <= target < EXPORT_RVA + EXPORT_SIZE:
        raise ValueError('PLUGIN_LOCATOR_EXPORT_FORWARDER_UNSUPPORTED')
    if target != TARGET_RVA:
        raise ValueError('PLUGIN_LOCATOR_EXPORT_TARGET_CHANGED')
    return {'name': TARGET_NAME, 'ordinal': base + ordinal_index, 'rva': target,
            'forwarder': False, 'all_tables_strings_inside_directory': True}


def validate_source(folder=SOURCE):
    meta_raw = (Path(folder) / 'source.json').read_bytes()
    raw = (Path(folder) / 'original-export.bin').read_bytes()
    if (hashlib.sha256(meta_raw).hexdigest() != SOURCE_SHA
            or hashlib.sha256(raw).hexdigest() != EXPORT_SHA):
        raise ValueError('PLUGIN_LOCATOR_STATIC_SOURCE_CHANGED')
    meta = json.loads(meta_raw)
    if ((meta['export_directory_rva'], meta['export_directory_size']) != (EXPORT_RVA, EXPORT_SIZE)
            or meta['named_exports'] != [{'name': TARGET_NAME, 'ordinal': 1, 'rva': TARGET_RVA}]
            or meta['export_binary_sha256'] != EXPORT_SHA or meta['exported_target_is_forwarder']
            or meta['original_getter_loaded_prefix_match_verified'] is not False):
        raise ValueError('PLUGIN_LOCATOR_STATIC_SOURCE_PROFILE')
    parse_export(raw)
    packed = (Path(folder) / 'original-getter-prefix.bin').read_bytes()
    if len(packed) != 64 or hashlib.sha256(packed).hexdigest() != meta['original_getter_sha256']:
        raise ValueError('PLUGIN_LOCATOR_PACKED_PROVENANCE_CHANGED')
    return {'directory': str(Path(folder).resolve()), 'metadata_sha256': SOURCE_SHA,
            'original_export_sha256': EXPORT_SHA, 'export_rva': EXPORT_RVA,
            'export_bytes': EXPORT_SIZE, 'name': TARGET_NAME, 'ordinal': 1, 'target_rva': TARGET_RVA,
            'original_packed_prefix_sha256': meta['original_getter_sha256'],
            'original_packed_bytes_used_as_pin': False}


def snapshot(budget):
    header = budget.read_module(0, 4096, 'game_pe_header')
    pe = struct.unpack_from('<I', header, 60)[0]
    if (header[:2] != b'MZ' or pe != 0x110 or header[pe:pe + 4] != b'PE\0\0'
            or struct.unpack_from('<H', header, pe + 4)[0] != 0x8664
            or struct.unpack_from('<H', header, pe + 6)[0] != 16
            or struct.unpack_from('<H', header, pe + 20)[0] != 240):
        raise ValueError('PLUGIN_LOCATOR_LOADED_PE_PROFILE')
    optional = pe + 24
    if (struct.unpack_from('<H', header, optional)[0] != 0x20B
            or struct.unpack_from('<I', header, optional + 56)[0] != IMAGE_SIZE
            or struct.unpack_from('<I', header, optional + 108)[0] < 1
            or struct.unpack_from('<II', header, optional + 112) != (EXPORT_RVA, EXPORT_SIZE)):
        raise ValueError('PLUGIN_LOCATOR_LOADED_EXPORT_DIRECTORY_CHANGED')
    directory = budget.read_module(EXPORT_RVA, EXPORT_SIZE, 'named_export_directory')
    named = parse_export(directory)
    # A changed EAT is refused above; no fallback/forwarded/new target is read.
    prefix = budget.read_module(named['rva'], 16, 'named_export_target_prefix', True)
    return header, directory, prefix, named


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('PLUGIN_LOCATOR_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'complete': False, 'target_module': 'game',
        'target_name': TARGET_NAME, 'target_rva': TARGET_RVA, 'allowed_capture_states': [2, 3],
        'named_lookup_only': True, 'prefix_bytes': 16, 'body_read': False, 'unwind_read': False,
        'function_signature_proven': False, 'plugin_table_contract_proven': False,
        'classification_ready': False, 'native_called': False, 'native_written': False,
        'heap_reads': 0, 'registry_reads': 0, 'capture_attempted': False, 'attempts': 1,
        'original_packed_bytes_used_as_pin': False, 'reader_source_sha256': READER_SHA}
    budget = None
    try:
        evidence['source'] = validate_source()
        reader = private_reader()
        deps = dependencies if dependencies is not None else reader.profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('PLUGIN_LOCATOR_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        reader.profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=reader.profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = reader.Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['state_before'] = before
            if before['state'] not in (2, 3):
                raise ValueError('PLUGIN_LOCATOR_EXPECTS_STATIC_TITLE_OR_SHIP')
            evidence['capture_attempted'] = True
            first = snapshot(budget)
            second = snapshot(budget)
            after = deps['ship_state'](budget, identity)
            evidence['state_after'] = after
            if first != second:
                raise ValueError('PLUGIN_LOCATOR_LOADED_SOURCE_CHANGED')
            if before != after:
                raise ValueError('PLUGIN_LOCATOR_STATIC_STATE_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('PLUGIN_LOCATOR_MODULE_CHANGED')
        budget.time_gate()
        header, directory, prefix, named = first
        binary, report = folder / 'plugin-export-prefix.bin', folder / 'plugin-export.json'
        evidence.update(complete=True, named_export=named, target_prefix_hex=prefix.hex(),
            prefix_before_after_match=True, source_gates_verified=True,
            loaded_header_sha256=hashlib.sha256(header).hexdigest(),
            loaded_export_directory_hex=directory.hex(), loaded_export_directory_sha256=hashlib.sha256(directory).hexdigest(),
            budget=budget.summary(), read_records=budget.records,
            binary_path=str(binary), sha256=hashlib.sha256(prefix).hexdigest(),
            captured_at=datetime.now(timezone.utc).isoformat())
        binary.write_bytes(prefix)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'json_path': str(report), 'binary_path': str(binary),
                  'sha256': evidence['sha256'], 'source_revision': REVISION}
        reader.profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'results_withheld': True,
                   'partial_binary_saved': False, 'error': str(error)}
        report = folder / 'plugin-export.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        raise


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
