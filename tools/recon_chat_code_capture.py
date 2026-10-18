"""One read-only chat-history consumer capture after a normal game launch.

This is an interface diagnostic, not a chat receiver or a reconnaissance count.
It never sends chat, starts the game, installs a MOD, or executes game code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid

import fire_code_capture as profile

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'recon_chat_history_code_v2'
TARGET_RVA = 0x1097A7C
TARGET_PIN = '8b87949500008b8f90950000'
IMAGE_SIZE = 0x4744000
EXCEPTION_RVA = 0x3FD340C
EXCEPTION_SIZE = 0x1BF57C
ENTRY_SIZE = 12  # Windows x64 RUNTIME_FUNCTION: Begin, End, UnwindInfo RVA.
MAX_TABLE_READS = 20
MAX_CHAIN_NODES = 4
MAX_UNWIND_CODES = 64
MAX_FUNCTION_BYTES = 4096
MAX_BYTES = 8192
MAX_READS = 32
MAX_SECONDS = 2.0  # Checked between IO calls; an OS call cannot be interrupted.
SOURCE_REFERENCE = ('CowboyBingus-VanillaPlusMegapack-1762b06/'
                    'components/BetterLobbyManagement/src/chat.lua:34-41')


class Budget:
    """One-query/one-read adapter sharing a single capture-wide hard budget."""

    def __init__(self, process, identity, clock=time.perf_counter):
        self.process, self.identity, self.clock = process, identity, clock
        self.started = clock()
        self.read_calls = self.query_calls = self.bytes_requested = self.bytes_returned = 0

    def time_gate(self):
        if self.clock() - self.started >= MAX_SECONDS:
            raise ValueError('RECON_CODE_TIME_BUDGET')

    def read_gate(self, size):
        self.time_gate()
        if (not 0 < size <= 4096 or self.read_calls >= MAX_READS
                or self.bytes_requested + size > MAX_BYTES):
            raise ValueError('RECON_CODE_READ_BUDGET')

    def query(self, address):
        self.time_gate()
        if self.query_calls >= MAX_READS:
            raise ValueError('RECON_CODE_QUERY_BUDGET')
        self.query_calls += 1
        return self.process.query(address)

    def read(self, address, size):
        self.read_gate(size)
        base, image_size = self.identity['game_base'], self.identity['game_size']
        if not base <= address or address + size > base + image_size:
            raise ValueError('RECON_CODE_OUTSIDE_MODULE')
        self.read_calls += 1
        self.bytes_requested += size
        raw = self.process.read(address, size)
        self.bytes_returned += len(raw)
        if len(raw) != size:
            raise ValueError('RECON_CODE_SHORT_READ')
        return raw

    def summary(self):
        return {'read_calls': self.read_calls, 'query_calls': self.query_calls,
                'bytes_requested': self.bytes_requested, 'bytes_returned': self.bytes_returned,
                'elapsed_ms': (self.clock() - self.started) * 1000,
                'max_reads': MAX_READS, 'max_bytes': MAX_BYTES,
                'soft_seconds': MAX_SECONDS}


def validate_module(identity):
    base, size = identity['game_base'], identity['game_size']
    if (not isinstance(base, int) or base < 65536 or base % 4096
            or size != IMAGE_SIZE or EXCEPTION_RVA + EXCEPTION_SIZE > size):
        raise ValueError('RECON_CODE_MODULE_INVALID')


def checked_metadata_read(budget, rva, size):
    address = budget.identity['game_base'] + rva
    budget.read_gate(size)
    region = budget.query(address)
    protection = region['protect']
    if not (region['state'] == 0x1000 and region['type'] == 0x1000000
            and region['base'] <= address
            and address + size <= region['base'] + region['size']
            and not protection & 0x100
            and protection & 0xff in (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)):
        raise ValueError('RECON_CODE_EXCEPTION_REGION_UNREADABLE')
    return budget.read(address, size)


def table_read(budget, index):
    return checked_metadata_read(budget, EXCEPTION_RVA + index * ENTRY_SIZE, ENTRY_SIZE)


def check_unwind_header(raw):
    if len(raw) != 4 or raw[0] & 7 not in (1, 2) or raw[0] >> 3 & ~7:
        raise ValueError('RECON_CODE_UNWIND_FORMAT_UNKNOWN')
    flags = raw[0] >> 3
    if flags & 4 and flags != 4:
        raise ValueError('RECON_CODE_UNWIND_FLAGS_MIXED')
    if raw[2] > MAX_UNWIND_CODES:
        raise ValueError('RECON_CODE_UNWIND_CODES_LIMIT')
    return flags


def validate_runtime_entry(begin, end, unwind):
    if not (0 < begin < end <= IMAGE_SIZE and 0 < unwind < IMAGE_SIZE):
        raise ValueError('RECON_CODE_EXCEPTION_ENTRY_INVALID')
    if unwind % 4 or unwind + 4 > IMAGE_SIZE:
        raise ValueError('RECON_CODE_UNWIND_ADDRESS_INVALID')
    if end - begin > MAX_FUNCTION_BYTES:
        raise ValueError(f'RECON_CODE_FUNCTION_TOO_LARGE: {begin:#x}..{end:#x}')


def unwind_ancestry(initial, read_metadata, nodes):
    """Read only declared ancestry, never sibling records or unproved gaps.

    For V1/V2, the chained RUNTIME_FUNCTION follows the DWORD-aligned array
    of 2-byte UNWIND_CODE slots. We locate it; we do not simulate unwinding.
    """
    current, seen_entries, seen_unwind, frame = initial, set(), set(), None
    for level in range(MAX_CHAIN_NODES):
        begin, end, unwind = current
        validate_runtime_entry(begin, end, unwind)
        if current in seen_entries or unwind in seen_unwind:
            raise ValueError('RECON_CODE_UNWIND_CYCLE')
        seen_entries.add(current); seen_unwind.add(unwind)
        node = {'begin': begin, 'end': end, 'unwind_rva': unwind}
        nodes.append(node)
        raw = read_metadata(unwind, 4)
        node['header'] = {'rva': unwind, 'raw_hex': raw.hex()}
        flags = check_unwind_header(raw)
        if frame is not None and raw[3] != frame:
            raise ValueError('RECON_CODE_UNWIND_FRAME_MISMATCH')
        frame = raw[3]
        if not flags & 4:
            return
        if level + 1 == MAX_CHAIN_NODES:
            raise ValueError('RECON_CODE_UNWIND_DEPTH_LIMIT')
        chain_rva = unwind + 4 + 2 * ((raw[2] + 1) & ~1)
        if chain_rva % 4 or chain_rva + ENTRY_SIZE > IMAGE_SIZE:
            raise ValueError('RECON_CODE_CHAIN_ADDRESS_INVALID')
        chained = read_metadata(chain_rva, ENTRY_SIZE)
        if len(chained) != ENTRY_SIZE:
            raise ValueError('RECON_CODE_SHORT_READ')
        current = struct.unpack('<III', chained)
        node['chain_entry'] = {'rva': chain_rva, 'raw_hex': chained.hex()}
    raise ValueError('RECON_CODE_UNWIND_DEPTH_LIMIT')


def ancestry_ranges(nodes):
    merged = []
    for begin, end in sorted({(node['begin'], node['end']) for node in nodes}):
        if merged and begin <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([begin, end])
    if sum(end - begin for begin, end in merged) > MAX_FUNCTION_BYTES:
        raise ValueError('RECON_CODE_CHAIN_CODE_BYTES_LIMIT')
    return tuple(('chat_history_consumer' if begin <= TARGET_RVA < end
                  else 'chat_history_unwind_parent_' + str(index), begin, end - begin)
                 for index, (begin, end) in enumerate(merged))


def find_function(budget, journal):
    """Binary search only the fixed exception table, not the image/code pages."""
    lo, hi = 0, EXCEPTION_SIZE // ENTRY_SIZE
    for _ in range(MAX_TABLE_READS):
        if lo >= hi:
            break
        index = (lo + hi) // 2
        raw = table_read(budget, index)
        begin, end, unwind = struct.unpack('<III', raw)
        journal.append({'index': index, 'rva': EXCEPTION_RVA + index * ENTRY_SIZE,
                        'raw_hex': raw.hex(), 'begin': begin, 'end': end,
                        'unwind_rva': unwind})
        if not (0 < begin < end <= IMAGE_SIZE and 0 < unwind < IMAGE_SIZE):
            raise ValueError('RECON_CODE_EXCEPTION_ENTRY_INVALID')
        if TARGET_RVA < begin:
            hi = index
        elif TARGET_RVA >= end:
            lo = index + 1
        else:
            if TARGET_RVA + len(bytes.fromhex(TARGET_PIN)) > end:
                raise ValueError('RECON_CODE_PIN_OUTSIDE_FUNCTION')
            if end - begin > MAX_FUNCTION_BYTES:
                raise ValueError(f'RECON_CODE_FUNCTION_TOO_LARGE: {begin:#x}..{end:#x}')
            return begin, end
    raise ValueError('RECON_CODE_FUNCTION_NOT_FOUND')


def window_capture(ranges):
    """Reuse the proven fixed-window reader without mutating its FIRE globals."""
    spec = importlib.util.spec_from_file_location('_recon_fixed_window', profile.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REVISION = REVISION
    module.RANGES = ranges
    module.PINS = ((TARGET_RVA, TARGET_PIN),)
    module.TOTAL_BYTES = sum(length for _, _, length in ranges)
    return module


def capture(process, identity, clock=time.perf_counter, evidence=None):
    validate_module(identity)
    budget, journal = Budget(process, identity, clock), []
    evidence = {} if evidence is None else evidence
    evidence.update(exception_records=journal, source_revision=REVISION,
                    target_rva=TARGET_RVA, native_written=False, native_called=False)
    try:
        begin, end = find_function(budget, journal)
        evidence.update(function_begin=begin, function_end=end)
        nodes = []
        evidence['unwind_chain'] = nodes
        unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                        lambda rva, size: checked_metadata_read(budget, rva, size), nodes)
        ranges = ancestry_ranges(nodes)
        evidence['selected_ranges'] = ranges
        reader = window_capture(ranges)
        binary, meta = reader.capture(budget, identity, sleep=lambda _: None)
        meta.update(exception_directory={'rva': EXCEPTION_RVA, 'size': EXCEPTION_SIZE,
                                         'entry_size': ENTRY_SIZE},
                    exception_records=journal, unwind_chain=nodes,
                    function_begin=begin, function_end=end,
                    boundary_kind='target_range_plus_bounded_unwind_ancestry',
                    all_sibling_fragments_captured=False, logical_function_complete=False,
                    source_reference=SOURCE_REFERENCE, target_rva=TARGET_RVA,
                    diagnostic_only=True, chat_messages_read=0, recon_events_emitted=0)
        return binary, meta
    finally:
        evidence['budget'] = budget.summary()
        if 'meta' in locals():
            meta['budget'] = evidence['budget']


def verify_saved(meta, binary):
    if (not meta.get('complete') or meta.get('source_revision') != REVISION
            or any(meta.get(k) != v for k, v in profile.FINGERPRINT.items())):
        raise ValueError('RECON_CODE_CACHE_PROFILE')
    lo, hi, found = 0, EXCEPTION_SIZE // ENTRY_SIZE, None
    records = meta['exception_records']
    if not 1 <= len(records) <= MAX_TABLE_READS:
        raise ValueError('RECON_CODE_CACHE_SEARCH')
    for record in records:
        index = (lo + hi) // 2
        if (found is not None or lo >= hi or record['index'] != index
                or record['rva'] != EXCEPTION_RVA + index * ENTRY_SIZE):
            raise ValueError('RECON_CODE_CACHE_SEARCH')
        raw = bytes.fromhex(record['raw_hex'])
        if len(raw) != ENTRY_SIZE:
            raise ValueError('RECON_CODE_CACHE_SEARCH')
        begin, end, unwind = struct.unpack('<III', raw)
        if not (0 < begin < end <= IMAGE_SIZE and 0 < unwind < IMAGE_SIZE):
            raise ValueError('RECON_CODE_CACHE_SEARCH')
        if TARGET_RVA < begin:
            hi = index
        elif TARGET_RVA >= end:
            lo = index + 1
        else:
            found = (begin, end)
    if found != (meta['function_begin'], meta['function_end']):
        raise ValueError('RECON_CODE_CACHE_BOUNDARY')
    begin, end = found
    if not 0 < end - begin <= MAX_FUNCTION_BYTES:
        raise ValueError('RECON_CODE_CACHE_BOUNDARY')
    saved_nodes = meta['unwind_chain']
    if not 1 <= len(saved_nodes) <= MAX_CHAIN_NODES:
        raise ValueError('RECON_CODE_CACHE_UNWIND')
    recorded_reads = []
    for node in saved_nodes:
        recorded_reads.append((node['header'], 4))
        if 'chain_entry' in node:
            recorded_reads.append((node['chain_entry'], ENTRY_SIZE))
    iterator = iter(recorded_reads)
    def saved_read(rva, size):
        try:
            item, expected_size = next(iterator)
        except StopIteration:
            raise ValueError('RECON_CODE_CACHE_UNWIND') from None
        raw = bytes.fromhex(item['raw_hex'])
        if item['rva'] != rva or expected_size != size or len(raw) != size:
            raise ValueError('RECON_CODE_CACHE_UNWIND')
        return raw
    nodes = []
    unwind_ancestry((begin, end, unwind), saved_read, nodes)
    if nodes != saved_nodes or next(iterator, None) is not None:
        raise ValueError('RECON_CODE_CACHE_UNWIND')
    reader = window_capture(ancestry_ranges(nodes))
    offset, expected_ranges = 0, []
    for name, rva, length in reader.RANGES:
        expected_ranges.append({'name': name, 'rva': rva, 'length': length, 'binary_offset': offset})
        offset += length
    if meta['ranges'] != expected_ranges:
        raise ValueError('RECON_CODE_CACHE_RANGES')
    reader.verify_pins(binary)
    if hashlib.sha256(binary).hexdigest() != meta['binary_sha256']:
        raise ValueError('RECON_CODE_CACHE_HASH')
    if (meta['budget']['read_calls'] > MAX_READS
            or meta['budget']['bytes_requested'] > MAX_BYTES):
        raise ValueError('RECON_CODE_CACHE_BUDGET')


def saved_complete(folder):
    try:
        status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        if status.get('status') != 'complete':
            return None
        meta_path, bin_path = Path(status['json_path']), Path(status['binary_path'])
        if meta_path.parent.resolve() != folder.resolve() or bin_path.parent.resolve() != folder.resolve():
            return None
        meta = json.loads(meta_path.read_text(encoding='utf8'))
        with bin_path.open('rb') as source:
            binary = source.read(MAX_FUNCTION_BYTES + 1)
        verify_saved(meta, binary)
        return status
    except (OSError, ValueError, KeyError, TypeError, struct.error):
        return None


def wait_and_capture(folder, stamps=None):
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes

    stamps = profile.fingerprints() if stamps is None else stamps
    profile.write_status(folder, {'status': 'waiting_game', 'sampler_pid': os.getpid(),
                                 'updated_at': profile.utc_now(), 'source_revision': REVISION,
                                 'max_bytes': MAX_BYTES, 'timeout_seconds': None,
                                 'chat_messages_read': 0, 'recon_events_emitted': 0})
    while True:
        pids = game_processes()
        if not pids:
            time.sleep(2)
            continue
        if len(pids) != 1:
            raise ValueError('RECON_CODE_MULTIPLE_GAME_PROCESSES')
        pid = pids[0]
        try:
            initial = resolve_game(pid)
        except FileNotFoundError:
            time.sleep(2)
            continue
        profile.validate_identity(initial, stamps)
        validate_module(initial)
        profile.write_status(folder, {'status': 'waiting_loaded_code', 'sampler_pid': os.getpid(),
                                     'game_pid': pid, 'updated_at': profile.utc_now()})
        time.sleep(20)  # No RPM before the unpacking/startup delay.
        if pid not in game_processes():
            continue
        evidence = {}
        try:
            identity = resolve_game(pid)
            profile.validate_identity(identity, stamps)
            if identity != initial:
                raise ValueError('RECON_CODE_MODULE_CHANGED')
            with Process(pid) as process:
                binary, meta = capture(process, identity, evidence=evidence)
            final = resolve_game(pid)
            profile.validate_identity(final, stamps)
            if identity != final:
                raise ValueError('RECON_CODE_MODULE_CHANGED')
            stem = 'recon-chat-code-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            bin_path, meta_path = folder / (stem + '.bin'), folder / (stem + '.json')
            meta.update(game_pid=pid, attempts=1, binary_path=str(bin_path), json_path=str(meta_path))
            with bin_path.open('xb') as target:
                target.write(binary)
            with meta_path.open('x', encoding='utf8') as target:
                json.dump(meta, target, ensure_ascii=False, indent=2)
            result = {'status': 'complete', 'sampler_pid': os.getpid(), 'game_pid': pid,
                      'updated_at': profile.utc_now(), 'binary_path': str(bin_path),
                      'json_path': str(meta_path), 'bytes_written': len(binary),
                      'bytes_read': meta['budget']['bytes_returned'],
                      'chat_messages_read': 0, 'recon_events_emitted': 0}
            profile.write_status(folder, result)
            return result
        except Exception as error:
            profile.write_status(folder, {'status': 'failed', 'sampler_pid': os.getpid(),
                                         'game_pid': pid, 'attempts': 1, 'error': str(error),
                                         'updated_at': profile.utc_now(), 'evidence': evidence})
            raise  # No retries or larger/partial fallback windows.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/recon-chat-code-v2')
    parser.add_argument('--check', action='store_true', help='Check disk build only; no waiting/game reads.')
    args = parser.parse_args()
    if args.check:
        profile.fingerprints()
        print(json.dumps({'status': 'local_build_matches', 'target_rva': TARGET_RVA,
                          'max_function_bytes': MAX_FUNCTION_BYTES, 'max_bytes': MAX_BYTES,
                          'max_reads': MAX_READS, 'table_reads': MAX_TABLE_READS,
                          'chain_nodes': MAX_CHAIN_NODES, 'max_unwind_codes': MAX_UNWIND_CODES,
                          'soft_seconds': MAX_SECONDS, 'pins': 1}))
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        stamps = profile.fingerprints()
        old = saved_complete(args.output)
        if old:
            print('Already complete: ' + old['json_path'])
            return 0
        result = wait_and_capture(args.output, stamps=stamps)
        print('Complete: ' + result['json_path'])
        return 0
    except KeyboardInterrupt:
        profile.write_status(args.output, {'status': 'cancelled', 'updated_at': profile.utc_now()})
        return 130
    except Exception as error:
        try:
            previous = json.loads((args.output / 'status.json').read_text(encoding='utf8'))
        except (OSError, ValueError):
            previous = {}
        if not (previous.get('status') == 'failed' and previous.get('sampler_pid') == os.getpid()
                and previous.get('error') == str(error)):
            profile.write_status(args.output, {'status': 'failed', 'updated_at': profile.utc_now(), 'error': str(error)})
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
