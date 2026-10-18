"""One Ship-only, read-only capture of the observed EXE Flow setter entry.

The target is explicitly helldivers2.exe, never an alias for game.dll. Reuse
the bounded RUNTIME_FUNCTION search/unwind ancestry reader with a private
profile. All process reads, including PE headers, the fresh entry PIN and
before/after Ship gates, share 8192B / 32 RPM / 2s soft limits. Declared code
is at most 4096B. No waiting, retry, native call, write or protection change.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'flow_exe_setter_declared_code_v1'
TARGET_MODULE = 'exe'
TARGET_NAME = 'World.set_flow_callback_object'
TARGET_RVA = 0x3F1560
TARGET_PIN = '48895c2408574883ec20ba0100000048'
EXE_IMAGE_SIZE = 0x39E8000
GAME_IMAGE_SIZE = 0x4744000
PE_OFFSET = 0x1E0
OPTIONAL_SIZE = 240
EXCEPTION_RVA = 0x31840A0
EXCEPTION_SIZE = 0x10E984
MAX_BYTES = 8192
MAX_READS = 32
MAX_SECONDS = 2.0
MAX_CODE_BYTES = 4096
INVENTORY = ROOT / 'dist/engine-bindings-live-0.4.21/engine_bindings.json'
INVENTORY_SHA = 'bd2d11bdda4245bd2a5aa541e38c0002a3049695e258f7d8ccba950c1c2d419b'
tail = runpy.run_path(str(ROOT / 'tools/hit-tail-code-capture.py'))
FINGERPRINT = dict(tail['FINGERPRINT'])


def validate_inventory(path=INVENTORY):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA:
        raise ValueError('FLOW_EXE_INVENTORY_CHANGED')
    inventory = json.loads(raw)['inventory']
    if (not inventory.get('ProfileVerified') or not inventory.get('identity_ready')
            or inventory['profile']['exe_sha'].lower() != FINGERPRINT['exe_sha']
            or inventory['profile']['game_sha'].lower() != FINGERPRINT['dll_sha']):
        raise ValueError('FLOW_EXE_INVENTORY_PROFILE')
    rows = [row for row in inventory['functions'] if row['name'] == TARGET_NAME]
    if (len(rows) != 1 or rows[0].get('module') != TARGET_MODULE
            or rows[0].get('status') != 'identified'
            or rows[0].get('rva') != TARGET_RVA or rows[0].get('hex') != TARGET_PIN):
        raise ValueError('FLOW_EXE_INVENTORY_PIN')
    return {'path': str(Path(path).resolve()), 'sha256': INVENTORY_SHA,
            'name': TARGET_NAME, 'module': TARGET_MODULE,
            'rva': TARGET_RVA, 'hex': TARGET_PIN}


def resolve_sources(pid, module_enumerator=None):
    """One existing read-only module snapshot, retaining both image identities."""
    if module_enumerator is None:
        from fire_code_windows import _modules
        module_enumerator = _modules
    modules = module_enumerator(pid)
    selected = {}
    for role, name in (('exe', 'helldivers2.exe'), ('game', 'game.dll')):
        matches = [item for item in modules if item['name'].casefold() == name]
        if len(matches) != 1:
            raise FileNotFoundError('FLOW_EXE_EXPECTS_EXACT_MODULE: ' + name)
        selected[role] = matches[0]
    return {role + '_' + key: selected[role][field]
            for role in ('exe', 'game')
            for key, field in (('base', 'base'), ('size', 'size'), ('path', 'path'))}


def validate_module(identity):
    for role, size in (('exe', EXE_IMAGE_SIZE), ('game', GAME_IMAGE_SIZE)):
        base = identity.get(role + '_base')
        if (type(base) is not int or base < 65536 or base % 4096
                or identity.get(role + '_size') != size
                or base + size >= 0x800000000000):
            raise ValueError('FLOW_EXE_MODULE_INVALID: ' + role)
    if not (0 < EXCEPTION_RVA < EXCEPTION_RVA + EXCEPTION_SIZE <= EXE_IMAGE_SIZE
            and EXCEPTION_SIZE % 12 == 0):
        raise ValueError('FLOW_EXE_EXCEPTION_PROFILE_INVALID')


class Budget:
    """A single read/query budget for Ship, EXE metadata, PIN and code."""

    def __init__(self, process, identity, clock=time.perf_counter):
        self.process, self.identity, self.clock = process, identity, clock
        self.started = clock()
        self.read_calls = self.query_calls = self.bytes_requested = self.bytes_returned = 0
        self.records = []

    def time_gate(self):
        if self.clock() - self.started >= MAX_SECONDS:
            raise ValueError('FLOW_EXE_TIME_BUDGET')

    def require_capacity(self, size, calls=1):
        self.time_gate()
        if (size <= 0 or self.read_calls + calls > MAX_READS
                or self.bytes_requested + size > MAX_BYTES):
            raise ValueError('FLOW_EXE_READ_BUDGET')

    def query(self, address):
        self.time_gate()
        if self.query_calls >= MAX_READS:
            raise ValueError('FLOW_EXE_QUERY_BUDGET')
        self.query_calls += 1
        return self.process.query(address)

    def read(self, address, size, purpose='ship'):
        if not 0 < size <= MAX_CODE_BYTES:
            raise ValueError('FLOW_EXE_READ_SIZE')
        self.require_capacity(size)
        self.read_calls += 1
        self.bytes_requested += size
        row = {'purpose': purpose, 'length': size}
        if purpose != 'ship':
            row.update(module=TARGET_MODULE, rva=address - self.identity['exe_base'])
        self.records.append(row)
        raw = self.process.read(address, size)
        row['returned'] = len(raw)
        self.bytes_returned += len(raw)
        if len(raw) != size:
            raise ValueError('FLOW_EXE_SHORT_READ')
        return raw

    def read_module(self, rva, size, purpose, executable=False):
        if not (0 <= rva < rva + size <= self.identity['exe_size']):
            raise ValueError('FLOW_EXE_OUTSIDE_TARGET_MODULE')
        self.require_capacity(size)
        address = self.identity['exe_base'] + rva
        region = self.query(address)
        protection = region['protect']
        allowed = (0x20, 0x40, 0x80) if executable else (2, 4, 8, 0x20, 0x40, 0x80)
        if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                and region['base'] <= address
                and address + size <= region['base'] + region['size']
                and not protection & 0x100 and protection & 0xFF in allowed):
            raise ValueError('FLOW_EXE_TARGET_REGION_UNREADABLE: ' + purpose)
        return self.read(address, size, purpose)

    def summary(self):
        return {'read_calls': self.read_calls, 'query_calls': self.query_calls,
                'bytes_requested': self.bytes_requested, 'bytes_returned': self.bytes_returned,
                'elapsed_ms': (self.clock() - self.started) * 1000,
                'max_reads': MAX_READS, 'max_bytes': MAX_BYTES,
                'soft_seconds': MAX_SECONDS, 'includes_ship_pe_pin_metadata_code': True}


def read_pe_declaration(budget):
    """Check the loaded EXE's exact pinned header declarations; no section scan."""
    dos = budget.read_module(0, 64, 'exe_header')
    if dos[:2] != b'MZ' or struct.unpack_from('<I', dos, 60)[0] != PE_OFFSET:
        raise ValueError('FLOW_EXE_DOS_PROFILE')
    nt = budget.read_module(PE_OFFSET, 24, 'exe_header')
    if (nt[:4] != b'PE\0\0' or struct.unpack_from('<H', nt, 4)[0] != 0x8664
            or struct.unpack_from('<H', nt, 20)[0] != OPTIONAL_SIZE):
        raise ValueError('FLOW_EXE_NT_PROFILE')
    optional = budget.read_module(PE_OFFSET + 24, OPTIONAL_SIZE, 'exe_header')
    exception = struct.unpack_from('<II', optional, 112 + 3 * 8)
    if (struct.unpack_from('<H', optional)[0] != 0x20B
            or struct.unpack_from('<I', optional, 56)[0] != EXE_IMAGE_SIZE
            or struct.unpack_from('<I', optional, 108)[0] < 4
            or exception != (EXCEPTION_RVA, EXCEPTION_SIZE)):
        raise ValueError('FLOW_EXE_OPTIONAL_PROFILE')
    return {'module': TARGET_MODULE, 'pe_offset': PE_OFFSET,
            'dos_hex': dos.hex(), 'nt_hex': nt.hex(), 'optional_hex': optional.hex(),
            'image_size': EXE_IMAGE_SIZE,
            'exception_directory': {'rva': EXCEPTION_RVA, 'size': EXCEPTION_SIZE,
                                    'entry_size': 12},
            'header_bytes_read': 64 + 24 + OPTIONAL_SIZE}


def private_reader():
    """Reuse the original algorithms without changing the frozen game profile."""
    spec = importlib.util.spec_from_file_location(
        '_flow_exe_metadata', ROOT / 'tools/recon_chat_code_capture.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, TARGET_RVA, TARGET_PIN
    reader.IMAGE_SIZE, reader.EXCEPTION_RVA, reader.EXCEPTION_SIZE = (
        EXE_IMAGE_SIZE, EXCEPTION_RVA, EXCEPTION_SIZE)
    reader.checked_metadata_read = lambda budget, rva, size: budget.read_module(
        rva, size, 'exception_record' if EXCEPTION_RVA <= rva < EXCEPTION_RVA + EXCEPTION_SIZE
        else 'unwind_metadata')
    return reader


def capture(budget, evidence):
    evidence['pe_declaration'] = read_pe_declaration(budget)
    fresh = budget.read_module(TARGET_RVA, len(bytes.fromhex(TARGET_PIN)), 'entry_pin', True)
    evidence['fresh_pin'] = {'module': TARGET_MODULE, 'rva': TARGET_RVA,
                             'hex': fresh.hex(), 'matched': fresh.hex() == TARGET_PIN}
    if fresh.hex() != TARGET_PIN:
        raise ValueError('FLOW_EXE_ENTRY_PIN_MISMATCH')
    reader, journal, nodes = private_reader(), [], []
    evidence.update(exception_records=journal, unwind_chain=nodes)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, n: reader.checked_metadata_read(budget, rva, n), nodes)
    selected = reader.ancestry_ranges(nodes)
    # Reserve the two after-Ship reads before requesting any declared code.
    budget.require_capacity(sum(length for _, _, length in selected) + 12, len(selected) + 2)
    chunks, ranges, offset = [], [], 0
    for index, (_, rva, length) in enumerate(selected):
        name = TARGET_NAME if rva <= TARGET_RVA < rva + length else 'unwind_parent_' + str(index)
        raw = budget.read_module(rva, length, 'declared_code', True)
        chunks.append(raw)
        ranges.append({'name': name, 'module': TARGET_MODULE, 'rva': rva,
                       'length': length, 'binary_offset': offset})
        offset += length
    binary = b''.join(chunks)
    target = next(row for row in ranges if row['rva'] <= TARGET_RVA < row['rva'] + row['length'])
    pin_offset = target['binary_offset'] + TARGET_RVA - target['rva']
    if binary[pin_offset:pin_offset + len(fresh)] != fresh:
        raise ValueError('FLOW_EXE_BODY_PIN_CHANGED')
    evidence.update(ranges=ranges, binary_pin_offset=pin_offset, code_bytes=len(binary),
                    boundary_kind='target_range_plus_bounded_unwind_ancestry',
                    declared_code_complete=True, all_sibling_fragments_captured=False,
                    logical_function_complete=False)
    return binary


def load_dependencies():
    deps = tail['load_dependencies']()
    deps['resolve_game'] = resolve_sources
    return deps


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_EXE_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': TARGET_MODULE,
                'target_name': TARGET_NAME, 'target_rva': TARGET_RVA, 'target_pin': TARGET_PIN,
                'complete': False, 'code_only': True, 'classification_ready': False,
                'contract_ready': False, 'native_written': False, 'native_called': False,
                'capture_attempted': False, 'attempts': 1}
    budget = None
    try:
        evidence['pin_source'] = validate_inventory()
        deps = dependencies if dependencies is not None else load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_EXE_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_EXE_EXPECTS_SHIP')
            evidence['capture_attempted'] = True
            raw = capture(budget, evidence)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_EXE_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_EXE_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'setter.bin', folder / 'setter.json'
        evidence.update(complete=True, captured_at=datetime.now(timezone.utc).isoformat(),
                        ship_reads=4, ship_bytes_read=24, budget=budget.summary(),
                        read_records=budget.records,
                        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        binary.write_bytes(raw)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION,
                  'json_path': str(report), 'binary_path': str(binary), 'sha256': evidence['sha256']}
        tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False,
                   'error': str(error), 'partial_binary_saved': False,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'setter.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
