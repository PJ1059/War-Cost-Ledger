"""One fixed CALL byte candidate, declaration-clipped read-only code windows.

Hard source: AB5FEF E8 -> 13AC1F0 and its preceding seven bytes. Capture
only PC-32..PC+5+16 clipped to the actual containing RUNTIME_FUNCTION and
that same declaration's first <=64 bytes, merged if they overlap. Large
declarations are metadata only; never read the whole AB5000 update body.
All process IO shares 24KiB / 32 RPM and query / 2s soft. No callee,
ancestor code, heap, registry, invocation, write, retries or UI input.
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
REVISION = 'game_world_update_contact_callsite_windows_v1'
FROZEN = ROOT / 'tools/hit-contact-forwarder-code-capture.py'
FROZEN_SHA = '3cb34d65eabbbdd27a188f40e295117aad8c04aca7c9ab4282390f1cb998fc39'
RECON = ROOT / 'tools/recon_chat_code_capture.py'
RECON_SHA = '797b5fcb45d391958e99e7e9305b56433efd20a5148645cb72b9993ed16dd675'
for pinned, digest in ((FROZEN, FROZEN_SHA), (RECON, RECON_SHA)):
    if hashlib.sha256(pinned.read_bytes()).hexdigest() != digest:
        raise ValueError('CONTACT_CALLSITE_FROZEN_HELPER_CHANGED: ' + pinned.name)
spec = importlib.util.spec_from_file_location('_contact_callsite_private_forwarder', FROZEN)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
SOURCE, SOURCE_SHA = frozen.SOURCE, frozen.SOURCE_SHA
TARGET_RVA = 0xAB5FEF
CALL_HEX = 'e8fc618f00'
CALL_DESTINATION = 0x13AC1F0
PIN_RVA = TARGET_RVA - 7
PIN_HEX = '498d8e307e4f04' + CALL_HEX
MAX_BYTES, MAX_READS, MAX_SECONDS = 24 * 1024, 32, 2.0
MAX_CODE_BYTES = 32 + 5 + 16 + 64


def validate_source(path=SOURCE):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('CONTACT_CALLSITE_INDEX_SOURCE_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or meta.get('truncated') or not meta.get('source_gates_verified')
            or meta.get('target_module') != 'game' or meta.get('target_rva') != CALL_DESTINATION
            or meta.get('fingerprint') != frozen.profile.FINGERPRINT
            or meta['sections'][0] != {'index': 0, 'rva': frozen.CODE_BEGIN,
                'virtual_size': frozen.CODE_END - frozen.CODE_BEGIN,
                'end_exclusive': frozen.CODE_END, 'characteristics': 0x60000020, 'kind': 'code'}):
        raise ValueError('CONTACT_CALLSITE_SOURCE_PROFILE')
    matches = [row for row in meta['candidates'] if row['rva'] == TARGET_RVA]
    if len(matches) != 1:
        raise ValueError('CONTACT_CALLSITE_SOURCE_CANDIDATE')
    row = matches[0]
    window = bytes.fromhex(row['window_hex'])
    at = TARGET_RVA - row['window_rva']
    if (row['module'] != 'game' or row['section_index'] != 0
            or row['reference_kind'] != 'byte_call_rel32'
            or row['target_rva'] != CALL_DESTINATION or row['match_hex'] != CALL_HEX
            or row['match_length'] != 5 or at != row['match_offset'] or at < 7
            or len(window) != row['window_bytes'] or window[at - 7:at + 5].hex() != PIN_HEX
            or TARGET_RVA + 5 + struct.unpack_from('<i', window, at + 1)[0] != CALL_DESTINATION):
        raise ValueError('CONTACT_CALLSITE_SOURCE_CALL_AND_PRECEDING_PIN')
    return {'path': str(Path(path).resolve()), 'sha256': SOURCE_SHA,
            'candidate_rva': TARGET_RVA, 'call_hex': CALL_HEX,
            'relative_target_rva': CALL_DESTINATION, 'pin_rva': PIN_RVA, 'pin_hex': PIN_HEX,
            'window_rva': row['window_rva'], 'window_hex': row['window_hex'],
            'instruction_boundary_verified': False, 'caller_entry_proven': False,
            'global_context_argument_proven': False, 'registered_callback_proven': False}


class Budget(frozen.Budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        # Only a private loaded module is changed; original frozen globals stay intact.
        frozen.MAX_BYTES, frozen.MAX_READS, frozen.MAX_SECONDS = MAX_BYTES, MAX_READS, MAX_SECONDS
        frozen.MAX_DECLARATION_READS = MAX_READS
        frozen.DECLARATION_PURPOSES = {'exception_record', 'unwind_metadata', 'callsite_windows'}
        super().__init__(process, identity, clock)


def capture(budget, evidence):
    reader = frozen.profile.private_reader()
    reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, TARGET_RVA, CALL_HEX
    reader.IMAGE_SIZE = frozen.IMAGE_SIZE
    reader.EXCEPTION_RVA, reader.EXCEPTION_SIZE = frozen.EXCEPTION_RVA, frozen.EXCEPTION_SIZE
    # This is only a span check for metadata. No ancestry_ranges/full-body capture.
    reader.MAX_FUNCTION_BYTES = frozen.CODE_END - frozen.CODE_BEGIN
    reader.checked_metadata_read = lambda b, rva, size: b.read_module(rva, size,
        'exception_record' if frozen.EXCEPTION_RVA <= rva < frozen.EXCEPTION_RVA + frozen.EXCEPTION_SIZE
        else 'unwind_metadata')
    journal, nodes = [], []
    evidence.update(exception_records=journal, unwind_chain=nodes)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    if not frozen.CODE_BEGIN <= begin <= PIN_RVA < TARGET_RVA + 5 <= end <= frozen.CODE_END:
        raise ValueError('CONTACT_CALLSITE_PIN_OUTSIDE_CURRENT_DECLARATION')
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    selected = [
        (max(begin, TARGET_RVA - 32), min(end, TARGET_RVA + 5 + 16), 'callsite_window'),
        (begin, min(end, begin + 64), 'declared_prefix')]
    merged = []
    for lo, hi, name in sorted(selected):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
            merged[-1][2].append(name)
        else:
            merged.append([lo, hi, [name]])
    size = sum(hi - lo for lo, hi, _ in merged)
    if size > MAX_CODE_BYTES:
        raise ValueError('CONTACT_CALLSITE_WINDOW_CODE_LIMIT')
    # Reserve both post headers/PIN/state reads and queries before any window.
    budget.require_capacity(size + 4096 + 12 + 12, len(merged) + 4)
    if budget.query_calls + len(merged) + 4 > MAX_READS:
        raise ValueError('CONTACT_CALLSITE_POST_QUERY_RESERVATION_BUDGET')
    chunks, ranges, offset = [], [], 0
    for lo, hi, names in merged:
        raw = budget.read_module(lo, hi - lo, 'callsite_windows', True)
        chunks.append(raw)
        ranges.append({'name': '+'.join(names), 'module': 'game', 'rva': lo,
                       'length': len(raw), 'binary_offset': offset})
        offset += len(raw)
    binary = b''.join(chunks)
    pin_range = next(row for row in ranges if row['rva'] <= PIN_RVA
        and PIN_RVA + 12 <= row['rva'] + row['length'])
    pin_offset = pin_range['binary_offset'] + PIN_RVA - pin_range['rva']
    if binary[pin_offset:pin_offset + 12].hex() != PIN_HEX:
        raise ValueError('CONTACT_CALLSITE_WINDOW_PIN_CHANGED')
    evidence.update(ranges=ranges, binary_pin_offset=pin_offset,
        binary_call_offset=pin_offset + 7, code_bytes=len(binary),
        requested_callsite_window={'rva': selected[0][0], 'length': selected[0][1] - selected[0][0]},
        requested_current_declaration_prefix={'rva': begin, 'length': selected[1][1] - begin},
        declared_code_complete=False, logical_function_complete=False,
        boundary_kind='two_windows_within_actual_containing_declaration_only',
        additional_ancestry_code_read=False, unwind_scope_tables_read=False,
        unwind_full_codes_captured=False, instruction_boundary_verified=False)
    return binary


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('CONTACT_CALLSITE_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': 'game', 'target_rva': TARGET_RVA,
        'call_destination_rva': CALL_DESTINATION, 'complete': False, 'code_only': True,
        'capture_purpose': 'STATIC_DECLARATION_CLIPPED_CONTACT_CALLSITE_WINDOWS_ONLY',
        'allowed_capture_states': [2, 3], 'caller_entry_proven': False,
        'global_context_argument_proven': False, 'registered_callback_proven': False,
        'classification_ready': False, 'contract_ready': False,
        'native_called': False, 'native_written': False, 'registry_reads': 0,
        'extra_callee_reads': 0, 'index_rescanned': False,
        'capture_attempted': False, 'attempts': 1,
        'frozen_wrapper_sha256': FROZEN_SHA, 'metadata_helper_sha256': RECON_SHA}
    budget = None
    try:
        evidence['source'] = validate_source()
        deps = dependencies if dependencies is not None else frozen.profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('CONTACT_CALLSITE_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        frozen.profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=frozen.profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] not in (2, 3):
                raise ValueError('CONTACT_CALLSITE_EXPECTS_STATIC_TITLE_OR_SHIP')
            header = frozen.inspect_header(budget)
            pin = budget.read_module(PIN_RVA, 12, 'fresh_call_and_preceding_pin', True)
            evidence['fresh_pin'] = {'rva': PIN_RVA, 'hex': pin.hex(), 'matched': pin.hex() == PIN_HEX}
            if pin.hex() != PIN_HEX:
                raise ValueError('CONTACT_CALLSITE_FRESH_PIN_CHANGED')
            evidence['capture_attempted'] = True
            raw = capture(budget, evidence)
            header_after = frozen.inspect_header(budget)
            pin_after = budget.read_module(PIN_RVA, 12, 'after_call_and_preceding_pin', True)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if header_after != header or pin_after != pin:
                raise ValueError('CONTACT_CALLSITE_SOURCE_CHANGED_DURING_CAPTURE')
            if before != after:
                raise ValueError('CONTACT_CALLSITE_STATIC_STATE_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CONTACT_CALLSITE_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'callsite.bin', folder / 'callsite.json'
        evidence.update(complete=True, budget=budget.summary(), read_records=budget.records,
            captured_at=datetime.now(timezone.utc).isoformat(), ship_reads=4, ship_bytes_read=24,
            loaded_header_sha256=hashlib.sha256(header).hexdigest(), fresh_gates_verified=True,
            exception_directory={'module': 'game', 'rva': frozen.EXCEPTION_RVA,
                'size': frozen.EXCEPTION_SIZE, 'entry_size': 12},
            binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        binary.write_bytes(raw)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION,
            'json_path': str(report), 'binary_path': str(binary), 'sha256': evidence['sha256']}
        frozen.profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'error': str(error),
                   'partial_binary_saved': False, 'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'callsite.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        frozen.profile.tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
