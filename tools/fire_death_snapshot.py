"""One bounded diagnostic DATA snapshot. No polling, writes or native calls.

Run only when explicitly invoked by the root: python -B tools/fire_death_snapshot.py
The captured corpses are observation material, never backfilled into kill/FIRE counts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import time
from datetime import datetime, timezone
import uuid

sys.dont_write_bytecode = True
import fire_code_capture as code_proof

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'dist/fire-controlled-playtest'
FIXED_PID = 61204
LIMIT = 65536
MAX_RECORDS, MAX_CANDIDATES = 64, 16
H_GLOBAL, H_HEADER, H_HEADER_SIZE = 0x3326688, 0x1010, 0x58
STRIDE, EXT_STRIDE = 0x1B8, 0x1C
LOCAL_USER, LOCAL_PEER = 0x347CEF0, 0xB398
SOURCE_META = ROOT / 'dist/fire-source-code/fire-code-20261011T055421Z-39817b24.json'
SOURCE_BIN_SHA = 'c58fc32a9158111ed1a0aa4cfc288232f360948b21870af5abb2ba806a6365ec'
CODE_META = ROOT / 'dist/fire-code-capture/fire-code-20261011T053231Z-893a9479.json'


def u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def u64(data, offset=0):
    return struct.unpack_from('<Q', data, offset)[0]


def pointer(value):
    if not isinstance(value, int) or not 0x10000 <= value <= 0x7FFFFFFFFFFF:
        raise ValueError('SNAPSHOT_BAD_POINTER')
    return value


def prove_saved_code():
    """Verify existing code packages on disk; never read live code again."""
    large = json.loads(CODE_META.read_text(encoding='utf8'))
    small = json.loads(SOURCE_META.read_text(encoding='utf8'))
    for meta, path, count, size in ((large, CODE_META, 18, 19328),
                                     (small, SOURCE_META, 16, 2704)):
        if (not meta.get('complete') or meta.get('game_pid') is None
                or len(meta.get('pins', [])) != count
                or not all(p.get('matched') is True for p in meta['pins'])
                or any(meta.get(k) != v for k, v in code_proof.FINGERPRINT.items())):
            raise ValueError('SNAPSHOT_SAVED_CODE_PROOF_MISMATCH')
        raw = path.with_suffix('.bin').read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != meta['binary_sha256']:
            raise ValueError('SNAPSHOT_SAVED_CODE_DIGEST_MISMATCH')
        if size == 19328:
            code_proof.verify_pins(raw)
        elif meta['binary_sha256'] != SOURCE_BIN_SHA:
            raise ValueError('SNAPSHOT_SOURCE_CODE_DIGEST_MISMATCH')
    if small.get('game_pid') != FIXED_PID or large['identity'] != small['identity']:
        raise ValueError('SNAPSHOT_SAVED_IDENTITY_MISMATCH')
    return small


def validate_identity(pid, actual, expected):
    if pid != FIXED_PID:
        raise ValueError('SNAPSHOT_FIXED_PID_MISMATCH')
    if actual != expected:
        raise ValueError('SNAPSHOT_MODULE_IDENTITY_MISMATCH')


def parse_header(raw):
    result = {'capacity': u32(raw), 'live': u32(raw, 0x10),
              'owned_bound': u32(raw, 0x14), 'descriptors': u64(raw, 0x38),
              'records': u64(raw, 0x48), 'ext': u64(raw, 0x50)}
    if not 0 < result['capacity'] <= 4096 or not 0 <= result['owned_bound'] <= result['live'] <= result['capacity']:
        raise ValueError('SNAPSHOT_HEADER_BOUNDS')
    for field in ('descriptors', 'records', 'ext'):
        pointer(result[field])
    return result


def capture(process, identity, pid=FIXED_PID, budget=LIMIT):
    """Inject a read/query adapter for fixtures. No other process operations."""
    if pid != FIXED_PID:
        raise ValueError('SNAPSHOT_FIXED_PID_MISMATCH')
    # The worst case is checked before the first read, not only after allocation.
    planned = MAX_RECORDS * (STRIDE + EXT_STRIDE + 8) + 224 + MAX_CANDIDATES * 96
    if budget > LIMIT or budget < planned:
        raise ValueError('SNAPSHOT_BUDGET_TOO_SMALL_OR_LARGE')
    binary, chunks = bytearray(), []

    def read(label, address, size):
        pointer(address)
        if size <= 0 or len(binary) + size > budget:
            raise ValueError('SNAPSHOT_READ_BUDGET')
        region = process.query(address)
        protect = region['protect']
        if (region['state'] != 0x1000 or protect & 0x100
                or protect & 0xFF not in (2, 4, 8, 0x20, 0x40, 0x80)
                or not region['base'] <= address
                or address + size > region['base'] + region['size']):
            raise ValueError('SNAPSHOT_REGION_UNREADABLE')
        start = time.perf_counter()
        raw = process.read(address, size)
        elapsed = (time.perf_counter() - start) * 1000
        if len(raw) != size:
            raise ValueError('SNAPSHOT_SHORT_READ')
        chunks.append({'label': label, 'address': address, 'length': size,
                       'binary_offset': len(binary), 'read_ms': elapsed})
        binary.extend(raw)
        return raw

    base = pointer(identity['game_base'])
    manager = pointer(u64(read('manager_before', base + H_GLOBAL, 8)))
    header_raw = read('header_before', manager + H_HEADER, H_HEADER_SIZE)
    header = parse_header(header_raw)
    user = pointer(u64(read('local_user_before', base + LOCAL_USER, 8)))
    peer_raw = read('local_peer_before', user + LOCAL_PEER, 8)
    peer = u64(peer_raw)
    if peer == 0:
        raise ValueError('SNAPSHOT_LOCAL_PEER_ZERO')
    count = min(header['live'], MAX_RECORDS)
    records = read('records_before', header['records'], count * STRIDE) if count else b''
    ext = read('ext_before', header['ext'], count * EXT_STRIDE) if count else b''
    descriptors = read('descriptor_pointers_before', header['descriptors'], count * 8) if count else b''
    candidates, eligible = [], 0
    for index in range(count):
        record = records[index * STRIDE:(index + 1) * STRIDE]
        if u32(record, 0x19C) != 2 or u64(record, 0x38) != peer:
            continue
        eligible += 1
        if len(candidates) >= MAX_CANDIDATES:
            continue
        descriptor_ptr = pointer(u64(descriptors, index * 8))
        descriptor_before = read(f'descriptor_{index}_before', descriptor_ptr, 24)
        cause_before = ext[index * EXT_STRIDE:(index + 1) * EXT_STRIDE]
        # Second observations of precisely the same indexed array fields.
        life_after = read(f'life_{index}_after', header['records'] + index * STRIDE + 0x19C, 4)
        creditor_after = read(f'creditor_{index}_after', header['records'] + index * STRIDE + 0x38, 8)
        descriptor_ptr_after = read(f'descriptor_pointer_{index}_after', header['descriptors'] + index * 8, 8)
        cause_after = read(f'ext_{index}_after', header['ext'] + index * EXT_STRIDE, EXT_STRIDE)
        descriptor_after = read(f'descriptor_{index}_after', descriptor_ptr, 24)
        owned = bool(u32(descriptor_before, 20) & 1)
        stable = (life_after == record[0x19C:0x1A0]
                  and creditor_after == record[0x38:0x40]
                  and u64(descriptor_ptr_after) == descriptor_ptr
                  and cause_after == cause_before and descriptor_after == descriptor_before)
        candidates.append({'index': index, 'descriptor_pointer': descriptor_ptr,
                           'type': f'{u64(descriptor_before):016X}',
                           'entity': u32(descriptor_before, 8), 'unit': u32(descriptor_before, 12),
                           'goid': u32(descriptor_before, 16), 'owned': owned,
                           'within_owned_bound': index < header['owned_bound'],
                           'life': 2, 'creditor': f'{peer:016X}',
                           'ext_kind': u32(cause_before), 'ext_element': u32(cause_before, 4),
                           'ext_life': u32(cause_before, 12), 'stable_fields': stable,
                           'stable': stable, 'killer_attribution_proven': False,
                           'enemy_type_confirmed': False})
    manager_after = u64(read('manager_after', base + H_GLOBAL, 8))
    header_after = read('header_after', manager + H_HEADER, H_HEADER_SIZE)
    user_after = u64(read('local_user_after', base + LOCAL_USER, 8))
    peer_after = read('local_peer_after', user + LOCAL_PEER, 8)
    globally_stable = (manager_after == manager and header_after == header_raw
                       and user_after == user and peer_after == peer_raw)
    for candidate in candidates:
        candidate['stable'] = candidate['stable_fields'] and globally_stable
    meta = {'revision': 'fire_death_data_once_v1', 'complete': True, 'atomic': False,
            'native_called': False, 'native_written': False, 'game_pid': pid,
            'identity': identity, 'budget': budget, 'bytes_planned_max': planned,
            'bytes_written': len(binary), 'chunks': chunks, 'header': header,
            'manager': manager, 'local_peer': f'{peer:016X}', 'header_identity_stable': globally_stable,
            'sampled_record_count': count, 'candidate_count': len(candidates),
            'eligible_local_creditor_deaths_first64': eligible,
            'candidate_limit': MAX_CANDIDATES, 'candidates': candidates,
            'coverage': 'limited; known first 64 health records only; at most 16 local-creditor deaths',
            'corpse_backfill': False, 'updates_ledger': False,
            'attribution_limit': 'Current creditor may change after death; stable fields are non-atomic observations.',
            'binary_sha256': hashlib.sha256(binary).hexdigest()}
    return bytes(binary), meta


def main():
    from fire_code_windows import Process, resolve_game
    proof = prove_saved_code()
    stamps = code_proof.fingerprints()  # Exact disk SHA256, no process memory reads.
    before = resolve_game(FIXED_PID)
    validate_identity(FIXED_PID, before, proof['identity'])
    code_proof.validate_identity(before, stamps)
    with Process(FIXED_PID) as process:
        raw, meta = capture(process, before)
    after = resolve_game(FIXED_PID)
    validate_identity(FIXED_PID, after, before)
    code_proof.validate_identity(after, stamps)
    meta.update(captured_at=datetime.now(timezone.utc).isoformat(),
                code_proof=str(SOURCE_META), exe_sha=proof['exe_sha'], dll_sha=proof['dll_sha'])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = 'fire-death-data-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    bin_path, json_path = OUTPUT / (stem + '.bin'), OUTPUT / (stem + '.json')
    with bin_path.open('xb') as target:
        target.write(raw)
    meta['binary_path'], meta['json_path'] = str(bin_path), str(json_path)
    with json_path.open('x', encoding='utf8') as target:
        json.dump(meta, target, ensure_ascii=False, indent=2)
    print(json.dumps({'status': 'complete', 'json_path': str(json_path),
                      'bytes_read': len(raw), 'candidates': meta['candidate_count'],
                      'atomic': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, struct.error) as error:
        print('Stopped without retry: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
