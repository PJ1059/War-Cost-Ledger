"""One static loaded GameDLL reference index for declared parent13AC1F0.

Ship is required by default; explicit --allow-title-screen also permits stable
TitleScreen2. This samples only static images, not World/physics/provider data.

Only section0code + section1declaredROdata. Code E8/E9 rel32 and48/4C RIP-LEA
must compute exacttarget; code/data qwords match actualgameBase+target. All
are byte candidates, not instruction-boundary/registration/coverage proof.
48MiB/256RPM/query/2s soft, <=256KiB chunks, combined64 windows<=64B, no full
binary, EXE/othersection/heap/registry/string scan, execution/writes or retry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'game_contact_parent_reference_index_v2'
CORE = ROOT / 'tools/flow-exe-entry-code-capture.py'
CORE_SHA = 'e6915df8b097cc7bd40afd303bdd288054b82aa40b98e944afb475ff583ca2c0'
if hashlib.sha256(CORE.read_bytes()).hexdigest() != CORE_SHA:
    raise ValueError('CONTACT_INDEX_FROZEN_READER_CHANGED')
spec = importlib.util.spec_from_file_location('_contact_index_sources', CORE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
SOURCE = ROOT / 'dist/hit-contact-registration-source-20261013'
SOURCE_SHA = '3c9bc9170c33da803d5a1c7b1042d2e64c86f28e7dcb1b7e977f83ecb44b719f'
HEADER_META_SHA = 'e7f9a8a3a2af4d560e097d8907ee627d23bf1a7ed234a661e6e8142c2771bc37'
HEADER_SHA = '6fe3be049b62483f08ee614a63b067148bbb3dbf9dc7b40712150a4bcb6078e8'
TARGET_RVA = 0x13AC1F0
PIN_RVA = 0x13AC345
PIN_HEX = '498dbf4030000048c1e3054d8db740d0'
SECTIONS = ({'index': 0, 'rva': 0x1000, 'virtual_size': 34667155,
             'end_exclusive': 0x2110A93, 'characteristics': 0x60000020, 'kind': 'code'},
            {'index': 1, 'rva': 0x2111000, 'virtual_size': 5417484,
             'end_exclusive': 0x263BA0C, 'characteristics': 0x40000040, 'kind': 'declared_ro_data'})
MAX_BYTES = 48 * 1024 * 1024
MAX_READS = 256
MAX_SECONDS = 2.0
CHUNK_BYTES = 256 * 1024
TAIL_BYTES = 63
MAX_CANDIDATES = 64


def validate_sources():
    source_raw = (SOURCE / 'source-evidence.json').read_bytes()
    header_meta = (SOURCE / 'pe-header.json').read_bytes()
    header = (SOURCE / 'game-pe-header.bin').read_bytes()
    if (hashlib.sha256(source_raw).hexdigest() != SOURCE_SHA
            or hashlib.sha256(header_meta).hexdigest() != HEADER_META_SHA
            or len(header) != 4096 or hashlib.sha256(header).hexdigest() != HEADER_SHA):
        raise ValueError('CONTACT_INDEX_STATIC_SOURCE_CHANGED')
    source = json.loads(source_raw)
    if (source['target_module'] != 'game' or source['target_rva'] != TARGET_RVA
            or not source['target_is_declared_chained_parent_entry']
            or source['fingerprint'] != profile.FINGERPRINT):
        raise ValueError('CONTACT_INDEX_SOURCE_PROFILE')
    for name in ('owner_prefix', 'unwind'):
        record = source[name]
        folder = Path(record['directory'])
        raw, meta = (folder / 'drain.bin').read_bytes(), (folder / 'drain.json').read_bytes()
        if (hashlib.sha256(raw).hexdigest() != record['binary_sha256']
                or hashlib.sha256(meta).hexdigest() != record['metadata_sha256']):
            raise ValueError('CONTACT_INDEX_SAVED_PACKAGE_CHANGED')
        if name == 'owner_prefix':
            at = source['fresh_pin']['binary_offset']
            if raw[at:at + 16].hex() != PIN_HEX:
                raise ValueError('CONTACT_INDEX_PREFIX_PIN_SOURCE')
        else:
            chain = source['unwind']['chain']
            for i, node in enumerate(chain):
                complete = node['complete_unwind']
                at, size = complete['binary_offset'], complete['length']
                if raw[at:at + size].hex() != complete['raw_hex']:
                    raise ValueError('CONTACT_INDEX_UNWIND_SOURCE')
                if i + 1 < len(chain):
                    actual = struct.unpack('<III', bytes.fromhex(node['chain_entry']['raw_hex']))
                    expected = tuple(chain[i + 1][k] for k in ('begin', 'end', 'unwind_rva'))
                    if actual != expected:
                        raise ValueError('CONTACT_INDEX_UNWIND_CHAIN_SOURCE')
            if chain[-1]['begin'] != TARGET_RVA:
                raise ValueError('CONTACT_INDEX_PARENT_SOURCE')
    return {'directory': str(SOURCE.resolve()), 'source_sha256': SOURCE_SHA,
            'pe_metadata_sha256': HEADER_META_SHA, 'header_sha256': HEADER_SHA,
            'target_rva': TARGET_RVA, 'parent_entry_declared': True,
            'owner_prefix': source['owner_prefix'], 'unwind': source['unwind'],
            'different_saved_pid_same_build': True, 'registered_callback_proven': False}


class Budget:
    """Explicit Game image bounds; existing Ship adapter shares these counters."""
    def __init__(self, process, identity, clock=time.perf_counter):
        self.process, self.identity, self.clock = process, identity, clock
        self.started = clock()
        self.read_calls = self.query_calls = self.bytes_requested = self.bytes_returned = 0
        self.records = []

    def time_gate(self):
        if self.clock() - self.started >= MAX_SECONDS:
            raise ValueError('CONTACT_INDEX_TIME_BUDGET')

    def require_capacity(self, size, calls=1):
        self.time_gate()
        if size <= 0 or self.read_calls + calls > MAX_READS or self.bytes_requested + size > MAX_BYTES:
            raise ValueError('CONTACT_INDEX_READ_BUDGET')

    def query(self, address):
        self.time_gate()
        if self.query_calls >= MAX_READS:
            raise ValueError('CONTACT_INDEX_QUERY_BUDGET')
        self.query_calls += 1
        return self.process.query(address)

    def read(self, address, size, purpose='ship'):
        if not 0 < size <= CHUNK_BYTES:
            raise ValueError('CONTACT_INDEX_READ_SIZE')
        self.require_capacity(size)
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
            raise ValueError('CONTACT_INDEX_SHORT_READ')
        return raw

    def image_read(self, rva, size, purpose, executable=False):
        if not 0 <= rva < rva + size <= self.identity['game_size']:
            raise ValueError('CONTACT_INDEX_OUTSIDE_GAME_IMAGE')
        self.require_capacity(size)
        address = self.identity['game_base'] + rva
        region = self.query(address)
        check_region(region, address, size, executable)
        return self.read(address, size, purpose)

    def summary(self):
        return {'read_calls': self.read_calls, 'query_calls': self.query_calls,
                'bytes_requested': self.bytes_requested, 'bytes_returned': self.bytes_returned,
                'elapsed_ms': (self.clock() - self.started) * 1000,
                'max_bytes': MAX_BYTES, 'max_reads': MAX_READS, 'max_queries': MAX_READS,
                'soft_seconds': MAX_SECONDS, 'includes_all_process_reads': True}


def check_region(region, address, size, executable=False):
    protection = region['protect']
    allowed = (0x20, 0x40, 0x80) if executable else (2, 4, 8, 0x20, 0x40, 0x80)
    if not (region['state'] == 0x1000 and region['type'] == 0x1000000
            and not protection & 0x100 and protection & 0xFF in allowed
            and region['base'] <= address < address + size <= region['base'] + region['size']):
        raise ValueError('CONTACT_INDEX_IMAGE_REGION_UNREADABLE')


def inspect_header(budget):
    raw = budget.image_read(0, 4096, 'game_pe_header')
    pe = struct.unpack_from('<I', raw, 60)[0]
    if (raw[:2] != b'MZ' or pe != 0x110 or raw[pe:pe + 4] != b'PE\0\0'
            or struct.unpack_from('<H', raw, pe + 4)[0] != 0x8664
            or struct.unpack_from('<H', raw, pe + 6)[0] != 16
            or struct.unpack_from('<H', raw, pe + 20)[0] != 240):
        raise ValueError('CONTACT_INDEX_GAME_PE_PROFILE')
    optional = pe + 24
    if (struct.unpack_from('<H', raw, optional)[0] != 0x20B
            or struct.unpack_from('<I', raw, optional + 56)[0] != profile.GAME_IMAGE_SIZE):
        raise ValueError('CONTACT_INDEX_GAME_IMAGE_PROFILE')
    first = optional + 240
    for selected in SECTIONS:
        at = first + 40 * selected['index']
        size, rva = struct.unpack_from('<II', raw, at + 8)
        flags = struct.unpack_from('<I', raw, at + 36)[0]
        if (rva, size, flags) != (selected['rva'], selected['virtual_size'], selected['characteristics']):
            raise ValueError('CONTACT_INDEX_SELECTED_SECTION_PROFILE')
    return raw


def byte_matches(buffer, buffer_rva, kind, absolute):
    """Only approved raw forms; no disassembly or instruction-boundary claim."""
    def relative(prefix, length, displacement_at, name, modrm=False):
        at = buffer.find(prefix)
        while at >= 0:
            if (at + length <= len(buffer) and (not modrm or buffer[at + 2] & 0xC7 == 5)
                    and buffer_rva + at + length + struct.unpack_from('<i', buffer, at + displacement_at)[0] == TARGET_RVA):
                yield at, length, name
            at = buffer.find(prefix, at + 1)
    def pointers():
        at = buffer.find(absolute)
        while at >= 0:
            yield at, 8, 'byte_absolute_qword'
            at = buffer.find(absolute, at + 1)
    streams = [pointers()]
    if kind == 'code':
        streams += [relative(b'\xe8', 5, 1, 'byte_call_rel32'),
                    relative(b'\xe9', 5, 1, 'byte_jmp_rel32'),
                    relative(b'\x48\x8d', 7, 3, 'byte_rip_lea', True),
                    relative(b'\x4c\x8d', 7, 3, 'byte_rip_lea', True)]
    return heapq.merge(*streams)


def stream_index(budget, sections, evidence):
    rows, seen = [], set()
    absolute = struct.pack('<Q', budget.identity['game_base'] + TARGET_RVA)
    payload_reads = payload_bytes = 0
    evidence['stream'] = {'payload_bytes': 0, 'payload_reads': 0, 'candidate_count': 0}
    for selected in sections:
        if selected.get('index') not in (0, 1):
            raise ValueError('CONTACT_INDEX_SCOPE_CHANGED')
        approved = SECTIONS[selected['index']]
        start, end, kind = selected['rva'], selected['end_exclusive'], selected['kind']
        if (start != approved['rva'] or not start < end <= approved['end_exclusive']
                or kind != approved['kind'] or selected['characteristics'] != approved['characteristics']):
            raise ValueError('CONTACT_INDEX_SCOPE_CHANGED')
        cursor, minimum_new_rva, tail = start, start, b''
        while cursor < end:
            address = budget.identity['game_base'] + cursor
            region = budget.query(address)
            size = min(CHUNK_BYTES, end - cursor, region['base'] + region['size'] - address)
            if size <= 0:
                raise ValueError('CONTACT_INDEX_REGION_GAP')
            check_region(region, address, size, kind == 'code')
            # Reserve final header4096B, PIN16B and Ship12B /4RPM.
            budget.require_capacity(size + 4124, 1 + 4)
            raw = budget.read(address, size, 'game_' + kind + '_index_payload')
            payload_reads += 1
            payload_bytes += len(raw)
            evidence['stream'].update(payload_bytes=payload_bytes, payload_reads=payload_reads)
            buffer, buffer_rva = tail + raw, cursor - len(tail)
            block_end = cursor + len(raw)
            last = block_end == end
            for at, length, reference_kind in byte_matches(buffer, buffer_rva, kind, absolute):
                rva = buffer_rva + at
                key = (rva, reference_kind)
                if rva < minimum_new_rva or key in seen:
                    continue
                if not last and rva + length + 32 > block_end:
                    continue
                if len(rows) == MAX_CANDIDATES:
                    evidence['stream'].update(candidate_count=len(rows), truncated=True, limit_rva=rva)
                    return {'complete': False, 'truncated': True, 'reason': 'COMBINED_CANDIDATE_LIMIT',
                            'candidates': rows, 'payload_bytes': payload_bytes, 'payload_reads': payload_reads,
                            'stopped_section_index': selected['index'], 'scanned_end_exclusive': block_end}
                lo, hi = max(start, rva - 16), min(end, rva + length + 32)
                if not buffer_rva <= lo < hi <= block_end:
                    raise ValueError('CONTACT_INDEX_CONTEXT_UNAVAILABLE')
                window = buffer[lo - buffer_rva:hi - buffer_rva]
                if len(window) > 64:
                    raise ValueError('CONTACT_INDEX_WINDOW_LIMIT')
                rows.append({'module': 'game', 'section_index': selected['index'], 'rva': rva,
                             'reference_kind': reference_kind, 'match_hex': buffer[at:at + length].hex(),
                             'target_rva': TARGET_RVA, 'match_length': length,
                             'window_rva': lo, 'window_hex': window.hex(), 'window_bytes': len(window),
                             'match_offset': rva - lo, 'boundary_truncated': lo != rva - 16 or hi != rva + length + 32,
                             'slot_alignment_mod8': rva % 8,
                             'instruction_boundary_verified': False, 'registration_proven': False,
                             'semantic_status': 'BYTE_CANDIDATE_ONLY'})
                seen.add(key)
                evidence['stream']['candidate_count'] = len(rows)
            minimum_new_rva = block_end if last else max(start, block_end - 39)
            tail = buffer[-TAIL_BYTES:]
            cursor = block_end
            budget.time_gate()
    return {'complete': True, 'truncated': False, 'reason': 'TWO_FIXED_SECTIONS_COMPLETE',
            'candidates': rows, 'payload_bytes': payload_bytes, 'payload_reads': payload_reads}


def run(output, dependencies=None, clock=time.perf_counter, allow_title_screen=False):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('CONTACT_INDEX_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    allowed_states = [2, 3] if allow_title_screen else [3]
    evidence = {'source_revision': REVISION, 'complete': False, 'source_gates_verified': False,
                'allowed_capture_states': allowed_states, 'allow_title_screen': bool(allow_title_screen),
                'capture_purpose': 'STATIC_GAME_IMAGE_REFERENCE_INDEX_ONLY',
                'target_module': 'game', 'target_rva': TARGET_RVA, 'sections': list(SECTIONS),
                'registered_callback_proven': False, 'classification_ready': False,
                'native_called': False, 'native_written': False, 'registry_reads': 0,
                'whole_binary_saved': False, 'scanning_attempted': False, 'attempts': 1,
                'excluded': ['EXE scanning', 'other GameDLL sections', 'heap/registry/string scanning'],
                'negative_result_limited_to_selected_reference_forms_and_sections': True}
    budget = None
    try:
        evidence['source'] = validate_sources()
        deps = dependencies if dependencies is not None else profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('CONTACT_INDEX_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] not in allowed_states:
                raise ValueError('CONTACT_INDEX_EXPECTS_ALLOWED_STATIC_STATE' if allow_title_screen
                                 else 'CONTACT_INDEX_EXPECTS_SHIP')
            pin_before = budget.image_read(PIN_RVA, 16, 'contact_prefix_pin', True)
            if pin_before.hex() != PIN_HEX:
                raise ValueError('CONTACT_INDEX_PREFIX_PIN_CHANGED')
            header_before = inspect_header(budget)
            evidence['scanning_attempted'] = True
            indexed = stream_index(budget, SECTIONS, evidence)
            pin_after = budget.image_read(PIN_RVA, 16, 'contact_prefix_pin', True)
            header_after = inspect_header(budget)
            if pin_after != pin_before or header_after != header_before:
                raise ValueError('CONTACT_INDEX_LOADED_SOURCE_CHANGED')
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('CONTACT_INDEX_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CONTACT_INDEX_MODULE_CHANGED')
        budget.time_gate()
        evidence.update(indexed, source_gates_verified=True,
                        fresh_pin={'rva': PIN_RVA, 'hex': pin_before.hex(), 'before_after_match': True},
                        loaded_header_sha256=hashlib.sha256(header_before).hexdigest(),
                        captured_at=datetime.now(timezone.utc).isoformat(), budget=budget.summary(),
                        read_records=budget.records, chunk_bytes=CHUNK_BYTES, tail_bytes=TAIL_BYTES,
                        combined_candidate_limit=MAX_CANDIDATES)
        report = folder / ('references.json' if indexed['complete'] else 'references.truncated.json')
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete' if indexed['complete'] else 'truncated',
                  'source_revision': REVISION, 'json_path': str(report),
                  'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
        profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'source_gates_verified': False,
                   'error': str(error), 'results_withheld': True, 'failed_at': datetime.now(timezone.utc).isoformat()}
        failure.pop('candidates', None)
        report = folder / 'references.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        profile.tail['write_status'](folder, {**failure, 'json_path': str(report)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-title-screen', action='store_true',
                        help='Also allow stable TitleScreen2 for this static image index; Mission4 stays refused.')
    args = parser.parse_args()
    try:
        result = run(args.output, allow_title_screen=args.allow_title_screen)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] != 'complete':
            raise SystemExit(2)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
