"""One fixed GameDLL JMP candidate's declared body, read-only and immediate.

Frozen index source names only JMP13F76D5->13AC1F0. The loaded exception
table determines its actual containing declaration; no window-derived begin.
Only that <=4096B body plus bounded unwind metadata, <=8192B/64RPM/query.
All IO including two4096B headers/JMP/real Title2-or-Ship3 gates shares
16384B/96RPM/query/2s soft. No target/callee body, scope table, heap/registry,
execution, write, waiting, retry, or claim of logical function completeness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'game_contact_jmp_candidate_declared_code_v1'
CORE = ROOT / 'tools/flow-exe-entry-code-capture.py'
CORE_SHA = 'e6915df8b097cc7bd40afd303bdd288054b82aa40b98e944afb475ff583ca2c0'
if hashlib.sha256(CORE.read_bytes()).hexdigest() != CORE_SHA:
    raise ValueError('CONTACT_FORWARDER_FROZEN_CORE_CHANGED')
spec = importlib.util.spec_from_file_location('_contact_forwarder_source_reader', CORE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
SOURCE = ROOT / 'dist/hit-contact-registration-title-live-20261013-v1/references.json'
SOURCE_SHA = '3bcc1df6b4dc6a17c96ff0bb2e8a874c43d7aaf124d9c1010ef5c7a94075f7b5'
TARGET_RVA = 0x13F76D5
TARGET_PIN = 'e9164bfbff'
JMP_DESTINATION = 0x13AC1F0
IMAGE_SIZE = 0x4744000
PE_OFFSET = 0x110
EXCEPTION_RVA = 0x3FD340C
EXCEPTION_SIZE = 0x1BF57C
CODE_BEGIN, CODE_END = 0x1000, 0x2110A93
MAX_CODE_BYTES = 4096
MAX_DECLARATION_BYTES = 8192
MAX_DECLARATION_READS = 64
MAX_BYTES = 16384
MAX_READS = 96
MAX_SECONDS = 2.0
DECLARATION_PURPOSES = {'exception_record', 'unwind_metadata', 'declared_forwarder_code'}


def validate_source(path=SOURCE):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('CONTACT_FORWARDER_INDEX_SOURCE_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or meta.get('truncated') or not meta.get('source_gates_verified')
            or meta.get('target_module') != 'game' or meta.get('target_rva') != JMP_DESTINATION
            or meta.get('fingerprint') != profile.FINGERPRINT
            or meta['sections'][0] != {'index': 0, 'rva': CODE_BEGIN,
                'virtual_size': CODE_END - CODE_BEGIN, 'end_exclusive': CODE_END,
                'characteristics': 0x60000020, 'kind': 'code'}):
        raise ValueError('CONTACT_FORWARDER_INDEX_SOURCE_PROFILE')
    rows = [row for row in meta['candidates'] if row['rva'] == TARGET_RVA]
    if len(rows) != 1:
        raise ValueError('CONTACT_FORWARDER_SOURCE_CANDIDATE')
    row = rows[0]
    window = bytes.fromhex(row['window_hex'])
    at = TARGET_RVA - row['window_rva']
    if (row['module'] != 'game' or row['section_index'] != 0
            or row['reference_kind'] != 'byte_jmp_rel32' or row['target_rva'] != JMP_DESTINATION
            or row['match_hex'] != TARGET_PIN or row['match_length'] != 5
            or len(window) != row['window_bytes'] or at != row['match_offset'] or at < 0
            or window[at:at + 5].hex() != TARGET_PIN or window[at] != 0xE9
            or TARGET_RVA + 5 + struct.unpack_from('<i', window, at + 1)[0] != JMP_DESTINATION):
        raise ValueError('CONTACT_FORWARDER_SOURCE_OPCODE_RELATIVE_JMP')
    return {'path': str(Path(path).resolve()), 'sha256': SOURCE_SHA,
            'candidate_rva': TARGET_RVA, 'jmp_hex': TARGET_PIN,
            'relative_target_rva': JMP_DESTINATION, 'window_rva': row['window_rva'],
            'window_hex': row['window_hex'], 'instruction_boundary_verified': False,
            'registered_callback_proven': False}


class Budget(profile.Budget):
    """Same bounded adapter, explicit Game image and two independent caps."""
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        self.declaration_reads = self.declaration_queries = self.declaration_bytes = 0

    def time_gate(self):
        if self.clock() - self.started >= MAX_SECONDS:
            raise ValueError('CONTACT_FORWARDER_TIME_BUDGET')

    def require_capacity(self, size, calls=1):
        self.time_gate()
        if size <= 0 or self.read_calls + calls > MAX_READS or self.bytes_requested + size > MAX_BYTES:
            raise ValueError('CONTACT_FORWARDER_READ_BUDGET')

    def query(self, address):
        self.time_gate()
        if self.query_calls >= MAX_READS:
            raise ValueError('CONTACT_FORWARDER_QUERY_BUDGET')
        self.query_calls += 1
        return self.process.query(address)

    def read(self, address, size, purpose='ship'):
        if not 0 < size <= MAX_CODE_BYTES:
            raise ValueError('CONTACT_FORWARDER_READ_SIZE')
        self.require_capacity(size)
        declaration = purpose in DECLARATION_PURPOSES
        if declaration:
            if (self.declaration_reads >= MAX_DECLARATION_READS
                    or self.declaration_bytes + size > MAX_DECLARATION_BYTES):
                raise ValueError('CONTACT_FORWARDER_DECLARATION_READ_BUDGET')
            self.declaration_reads += 1
            self.declaration_bytes += size
        self.read_calls += 1
        self.bytes_requested += size
        row = {'purpose': purpose, 'length': size}
        if purpose != 'ship':
            row.update(module='game', rva=address - self.identity['game_base'])
        self.records.append(row)
        raw = self.process.read(address, size)
        row['returned'] = len(raw)
        self.bytes_returned += len(raw)
        if len(raw) != size:
            raise ValueError('CONTACT_FORWARDER_SHORT_READ')
        return raw

    def read_module(self, rva, size, purpose, executable=False):
        if not 0 <= rva < rva + size <= self.identity['game_size']:
            raise ValueError('CONTACT_FORWARDER_OUTSIDE_GAME_IMAGE')
        if executable and not CODE_BEGIN <= rva < rva + size <= CODE_END:
            raise ValueError('CONTACT_FORWARDER_OUTSIDE_DECLARED_CODE_SECTION')
        self.require_capacity(size)
        if purpose in DECLARATION_PURPOSES:
            if (self.declaration_reads + 1 > MAX_DECLARATION_READS
                    or self.declaration_queries + 1 > MAX_DECLARATION_READS
                    or self.declaration_bytes + size > MAX_DECLARATION_BYTES):
                raise ValueError('CONTACT_FORWARDER_DECLARATION_READ_BUDGET')
            self.declaration_queries += 1
        address = self.identity['game_base'] + rva
        region = self.query(address)
        protection = region['protect']
        allowed = (0x20, 0x40, 0x80) if executable else (2, 4, 8, 0x20, 0x40, 0x80)
        if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                and region['base'] <= address < address + size <= region['base'] + region['size']
                and not protection & 0x100 and protection & 0xFF in allowed):
            raise ValueError('CONTACT_FORWARDER_GAME_REGION_UNREADABLE: ' + purpose)
        return self.read(address, size, purpose)

    def summary(self):
        return {'read_calls': self.read_calls, 'query_calls': self.query_calls,
                'bytes_requested': self.bytes_requested, 'bytes_returned': self.bytes_returned,
                'elapsed_ms': (self.clock() - self.started) * 1000,
                'max_bytes': MAX_BYTES, 'max_reads': MAX_READS, 'max_queries': MAX_READS,
                'declaration_read_calls': self.declaration_reads,
                'declaration_query_calls': self.declaration_queries,
                'declaration_bytes_requested': self.declaration_bytes,
                'max_declaration_bytes': MAX_DECLARATION_BYTES,
                'max_declaration_reads_queries': MAX_DECLARATION_READS,
                'soft_seconds': MAX_SECONDS, 'includes_all_process_reads': True}


def inspect_header(budget):
    raw = budget.read_module(0, 4096, 'game_pe_header')
    pe = struct.unpack_from('<I', raw, 60)[0]
    if (raw[:2] != b'MZ' or pe != PE_OFFSET or raw[pe:pe + 4] != b'PE\0\0'
            or struct.unpack_from('<H', raw, pe + 4)[0] != 0x8664
            or struct.unpack_from('<H', raw, pe + 6)[0] != 16
            or struct.unpack_from('<H', raw, pe + 20)[0] != 240):
        raise ValueError('CONTACT_FORWARDER_GAME_PE_PROFILE')
    optional = pe + 24
    if (struct.unpack_from('<H', raw, optional)[0] != 0x20B
            or struct.unpack_from('<I', raw, optional + 56)[0] != IMAGE_SIZE
            or struct.unpack_from('<I', raw, optional + 108)[0] < 4
            or struct.unpack_from('<II', raw, optional + 136) != (EXCEPTION_RVA, EXCEPTION_SIZE)):
        raise ValueError('CONTACT_FORWARDER_EXCEPTION_PROFILE')
    first = optional + 240
    if (struct.unpack_from('<II', raw, first + 8) != (CODE_END - CODE_BEGIN, CODE_BEGIN)
            or struct.unpack_from('<I', raw, first + 36)[0] != 0x60000020):
        raise ValueError('CONTACT_FORWARDER_CODE_SECTION_PROFILE')
    return raw


def capture(budget, evidence):
    reader = profile.private_reader()
    reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, TARGET_RVA, TARGET_PIN
    reader.IMAGE_SIZE, reader.EXCEPTION_RVA, reader.EXCEPTION_SIZE = IMAGE_SIZE, EXCEPTION_RVA, EXCEPTION_SIZE
    reader.checked_metadata_read = lambda b, rva, n: b.read_module(rva, n,
        'exception_record' if EXCEPTION_RVA <= rva < EXCEPTION_RVA + EXCEPTION_SIZE else 'unwind_metadata')
    journal, nodes = [], []
    evidence.update(exception_records=journal, unwind_chain=nodes)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, n: reader.checked_metadata_read(budget, rva, n), nodes)
    # Only the actual containing declaration, never additional ancestry code.
    budget.require_capacity(end - begin + 4113, 5)
    raw = budget.read_module(begin, end - begin, 'declared_forwarder_code', True)
    offset = TARGET_RVA - begin
    if raw[offset:offset + 5].hex() != TARGET_PIN:
        raise ValueError('CONTACT_FORWARDER_BODY_JMP_CHANGED')
    evidence.update(ranges=[{'name': 'GameDLL_JMP13F76D5_containing_declaration',
        'module': 'game', 'rva': begin, 'length': end - begin, 'binary_offset': 0}],
        binary_jmp_offset=offset, code_bytes=len(raw), declared_code_complete=True,
        logical_function_complete=False, all_sibling_fragments_captured=False,
        boundary_kind='actual_containing_runtime_function_only',
        unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        additional_ancestry_code_read=False)
    return raw


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('CONTACT_FORWARDER_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': 'game', 'target_rva': TARGET_RVA,
        'jmp_destination_rva': JMP_DESTINATION, 'complete': False, 'code_only': True,
        'capture_purpose': 'STATIC_GAME_IMAGE_DECLARED_JMP_CANDIDATE_ONLY',
        'allowed_capture_states': [2, 3], 'api_identity_verified': False,
        'registered_callback_proven': False, 'classification_ready': False, 'contract_ready': False,
        'native_called': False, 'native_written': False, 'registry_reads': 0,
        'index_rescanned': False, 'extra_callee_reads': 0, 'attempts': 1,
        'capture_attempted': False, 'sampler_source_sha256': CORE_SHA}
    budget = None
    try:
        evidence['source'] = validate_source()
        deps = dependencies if dependencies is not None else profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('CONTACT_FORWARDER_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] not in (2, 3):
                raise ValueError('CONTACT_FORWARDER_EXPECTS_STATIC_TITLE_OR_SHIP')
            header = inspect_header(budget)
            pin = budget.read_module(TARGET_RVA, 5, 'fresh_jmp_pin', True)
            evidence['fresh_jmp_pin'] = {'rva': TARGET_RVA, 'hex': pin.hex(), 'matched': pin.hex() == TARGET_PIN}
            if pin.hex() != TARGET_PIN:
                raise ValueError('CONTACT_FORWARDER_FRESH_JMP_CHANGED')
            evidence['capture_attempted'] = True
            raw = capture(budget, evidence)
            header_after = inspect_header(budget)
            pin_after = budget.read_module(TARGET_RVA, 5, 'after_jmp_pin', True)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if header_after != header or pin_after != pin:
                raise ValueError('CONTACT_FORWARDER_SOURCE_CHANGED_DURING_CAPTURE')
            if before != after:
                raise ValueError('CONTACT_FORWARDER_STATIC_STATE_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CONTACT_FORWARDER_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'forwarder.bin', folder / 'forwarder.json'
        evidence.update(complete=True, budget=budget.summary(), read_records=budget.records,
            captured_at=datetime.now(timezone.utc).isoformat(), ship_reads=4, ship_bytes_read=24,
            loaded_header_sha256=hashlib.sha256(header).hexdigest(), fresh_gates_verified=True,
            exception_directory={'module': 'game', 'rva': EXCEPTION_RVA, 'size': EXCEPTION_SIZE,
                                 'entry_size': 12},
            binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        binary.write_bytes(raw)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
                  'binary_path': str(binary), 'sha256': evidence['sha256']}
        profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'error': str(error),
                   'partial_binary_saved': False, 'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'forwarder.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        profile.tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
