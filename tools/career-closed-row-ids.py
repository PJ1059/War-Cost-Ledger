"""Once-only Armory catalog diagnostic: two stat IDs and locale labels.

Readable memory is not proof that the closed UI object is alive. This helper
does not read a backend provider, update statistics, or open any game UI.
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
_spec = importlib.util.spec_from_file_location('career_closed_private_layout', ROOT / 'tools/career-ui-snapshot.py')
layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout)
REVISION = 'career_closed_two_row_ids_v1'
MAX_BYTES, MAX_READS, SOFT_SECONDS = 8192, 64, 1.0
CATALOG, ARMORY_SLOT, BACKREF = 0x347CE38, 0x60, 0x28
BLOCK, CONSTRUCTED, PANEL, LIST = 0x4DAF8, 0x31C18, 0x4DC08, 0x9B8
FILLED_COUNT, FIRST_ROW, STRIDE = 0x2F0F4, 0x110, 0x1910
TAG, META = 0xA40, 0x18FC
LOCAL_USER, LOCAL_PEER = 0x347CEF0, 0xB398
ROWS = ((0, 'enemy_kills', 0xF68F08B2), (8, 'deaths', 0x32C9CF0D))
# Actual captured code, not hypothetical metadata or an interface name.
SOURCES = (
    {'path': 'dist/career-armory-enter-20261012-58f5e3a7/capture/drain.bin',
     'sha256': '0b60ac9427b42b76feaed6c9d1abea397d9e40857f68532f74c200f9ce22219a'},
    {'path': 'dist/career-row-value-20261012-09e6e39c/capture/drain.bin',
     'sha256': '0b798e6a1b323e31afa2b763449b9a500dbe168e947edf79bfdb51b650bfa2dd'},
    {'path': 'dist/career-panel-list-init-20261012-5f0d5e2a/capture/drain.bin',
     'sha256': '0b32a1a11119f7cb16f4761d2e6cf65ae97aba181bac646de24ef528378a3056'},
)
PINS = ((0x1495511, 'e82a03fcff'), (0x18E4BF7, '488d810c1a0000'),
        (0x18E58CB, '4981c610190000'))


class CaptureError(ValueError):
    def __init__(self, reason, evidence):
        super().__init__(reason)
        self.evidence = evidence


class Budget(layout.Budget):
    """One clock and cap for every PIN, Ship, peer, chain and data read."""
    def __init__(self, process, identity, clock=time.perf_counter, *, started=None):
        super().__init__(process, identity, clock)
        if started is not None:
            self.started = started

    def check_time(self):
        if self.clock() - self.started >= SOFT_SECONDS:
            raise ValueError('CAREER_CLOSED_SOFT_BUDGET')

    def gate(self, size):
        if self.total['bytes'] + size > MAX_BYTES or self.total['reads'] >= MAX_READS:
            raise ValueError('CAREER_CLOSED_TOTAL_BUDGET')
        self.check_time()

    def read(self, address, size, *, image=False, code=False):
        self.gate(size)
        if not 0 < size <= 4096 or not layout.pointer(address, False):
            raise ValueError('CAREER_CLOSED_ADDRESS_OR_SIZE')
        if code and not image:
            raise ValueError('CAREER_CLOSED_CODE_REQUIRES_IMAGE')
        if image and not self.identity['game_base'] <= address < address + size <= self.identity['game_base'] + layout.IMAGE_SIZE:
            raise ValueError('CAREER_CLOSED_OUTSIDE_MODULE')
        self.queries += 1
        region = self.process.query(address)
        self.check_time()
        protection = region['protect']
        allowed = ((0x20, 0x40, 0x80) if code else
                   (2, 4, 8, 0x20, 0x40, 0x80) if image else (2, 4, 8))
        if (region['state'] != 0x1000 or region['type'] != (0x1000000 if image else 0x20000)
                or protection & 0x100 or protection & 0xff not in allowed
                or not region['base'] <= address < address + size <= region['base'] + region['size']):
            raise ValueError('CAREER_CLOSED_UNREADABLE')
        self.gate(size)
        self.bytes += size; self.reads += 1
        self.total['bytes'] += size; self.total['reads'] += 1
        raw = self.process.read(address, size)
        self.total['records'].append({'address': address, 'length': size,
                                      'received': len(raw), 'raw_hex': raw.hex(),
                                      'image': image, 'code': code})
        if len(raw) != size:
            raise ValueError('CAREER_CLOSED_SHORT_READ')
        self.check_time()
        return raw


def checked_pointer(value, reason):
    if not layout.pointer(value):
        raise ValueError('CAREER_CLOSED_' + reason)
    return value


def kind(raw):
    return struct.unpack_from('<I', raw)[0] >> 18 & 15


def verify_code(budget):
    for rva, expected in PINS:
        wanted = bytes.fromhex(expected)
        if budget.read(budget.identity['game_base'] + rva, len(wanted), image=True, code=True) != wanted:
            raise ValueError('CAREER_CLOSED_CODE_PIN')


def ship(budget):
    context = checked_pointer(budget.ptr(budget.identity['game_base'] + layout.STATE_GLOBAL, image=True), 'STATE_POINTER')
    if budget.u32(context + layout.STATE_OFFSET) != 3:
        raise ValueError('CAREER_CLOSED_NOT_SHIP')
    return context


def locate(budget, state_context):
    base = budget.identity['game_base']
    local_user = checked_pointer(budget.ptr(base + LOCAL_USER, image=True), 'LOCAL_USER')
    peer = budget.read(local_user + LOCAL_PEER, 8)
    if peer == bytes(8):
        raise ValueError('CAREER_CLOSED_LOCAL_PEER')
    owner = checked_pointer(budget.ptr(base + CATALOG, image=True), 'CATALOG_POINTER')
    armory = checked_pointer(budget.ptr(owner + ARMORY_SLOT), 'ARMORY_POINTER')
    if budget.ptr(armory + BACKREF) != owner:
        raise ValueError('CAREER_CLOSED_BACKREF')
    block, panel = armory + BLOCK, armory + PANEL
    if budget.read(block + CONSTRUCTED, 1) != b'\x01':
        raise ValueError('CAREER_CLOSED_NOT_CONSTRUCTED')
    at = panel + LIST
    raw = budget.read(at, layout.HEADER_BYTES)
    child, _, parent, context = struct.unpack_from('<QQQQ', raw, layout.CHILD)
    if kind(raw) != 1 or not layout.pointer(context) or not layout.pointer(parent):
        raise ValueError('CAREER_CLOSED_LIST_HEADER')
    if child != at + FIRST_ROW:
        raise ValueError('CAREER_CLOSED_INLINE_FIRST_ROW')
    count = budget.u32(at + FILLED_COUNT)
    if not 1 <= count <= 30:
        raise ValueError('CAREER_CLOSED_FILLED_COUNT')
    if count <= ROWS[-1][0]:
        raise ValueError('CAREER_CLOSED_ROW8_NOT_FILLED')
    return {'state_context': state_context, 'local_user': local_user,
            'local_peer_hex': peer[::-1].hex().upper(), 'catalog_owner': owner,
            'armory': armory, 'block': block, 'panel': panel, 'list': at,
            'gui_context': context, 'filled_count': count, 'header_hex': raw.hex()}


def widget_header(budget, address, parent, context, expected_kind):
    raw = budget.read(address, layout.HEADER_BYTES)
    if kind(raw) != expected_kind or struct.unpack_from('<QQ', raw, layout.PARENT) != (parent, context):
        raise ValueError('CAREER_CLOSED_WIDGET_OWNER')
    return raw


def selected_rows(budget, owner):
    first = owner['list'] + FIRST_ROW
    path = [first]
    for index in range(1, 9):
        actual = budget.ptr(path[-1] + layout.NEXT)
        if actual != first + index * STRIDE:
            raise ValueError('CAREER_CLOSED_NEXT_ARRAY_MISMATCH')
        path.append(actual)
    rows = {}
    for index, role, key in ROWS:
        address = path[index]
        row_header = widget_header(budget, address, owner['list'], owner['gui_context'], 1)
        tag = address + TAG
        tag_header = widget_header(budget, tag, address, owner['gui_context'], 7)
        label = budget.u32(tag + layout.LABEL_START)
        if label != key:
            raise ValueError('CAREER_CLOSED_LABEL_MISMATCH')
        raw = budget.read(address + META, 8)
        stat_id, value_raw = struct.unpack('<II', raw)
        rows[role] = {'row_index': index, 'row_address': address,
                      'row_header_hex': row_header.hex(), 'tag_header_hex': tag_header.hex(),
                      'tag_address': tag, 'label_key': label, 'stat_id': stat_id,
                      'metadata_address': address + META, 'metadata_hex': raw.hex(),
                      'value_raw': value_raw, 'value_freshness_proven': False}
    if rows['enemy_kills']['stat_id'] == rows['deaths']['stat_id']:
        raise ValueError('CAREER_CLOSED_STAT_ID_AMBIGUOUS')
    return path, rows


def base_evidence(budget, identity):
    return {'source_revision': REVISION, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'identity': dict(identity), 'source_code_evidence': list(SOURCES),
            'active_read_bytes': budget.total['bytes'], 'active_read_calls': budget.total['reads'],
            'read_records': budget.total['records'], 'diagnostic_only': True,
            'liveness_proven': False, 'server_ready': False, 'backend_ready': False,
            'career_stats_ready': False, 'values_fresh': False, 'atomic': False,
            'account_modified': False, 'native_written': False, 'native_called': False,
            'limits': {'bytes': MAX_BYTES, 'reads': MAX_READS, 'soft_seconds': SOFT_SECONDS,
                       'soft_clock_scope': 'process_open_through_final_identity',
                       'soft_limit_preempts_blocking_os_calls': False}}


def capture(process, identity, clock=time.perf_counter, *, started=None):
    budget = Budget(process, identity, clock, started=started)
    partial = {}
    try:
        if identity['game_size'] != layout.IMAGE_SIZE or identity['game_base'] % 4096:
            raise ValueError('CAREER_CLOSED_MODULE')
        before_state = ship(budget)  # No code or catalog read outside Ship.
        verify_code(budget)
        before = locate(budget, before_state)
        partial['owner_before'] = before
        before_path, before_rows = selected_rows(budget, before)
        partial.update(row_path_before=before_path, rows_before=before_rows)
        after_state = ship(budget)
        verify_code(budget)
        after = locate(budget, after_state)
        partial['owner_after'] = after
        after_path, after_rows = selected_rows(budget, after)
        partial.update(row_path_after=after_path, rows_after=after_rows)
        if before != after or before_path != after_path or before_rows != after_rows:
            raise ValueError('CAREER_CLOSED_BEFORE_AFTER_CHANGED')
        budget.check_time()
        return {**base_evidence(budget, identity), **partial, 'pins_verified_twice': True,
                'stat_id_label_mapping': [{'row_index': index, 'role': role,
                                          'label_key': key, 'stat_id': after_rows[role]['stat_id']}
                                         for index, role, key in ROWS]}, budget
    except Exception as error:
        raise CaptureError(str(error), {**base_evidence(budget, identity), **partial,
                                       'status': 'failed', 'error': str(error)}) from error


def save_material(folder, value):
    binary = b''.join(bytes.fromhex(record['raw_hex']) for record in value.get('read_records', []))
    offset = 0
    for record in value.get('read_records', []):
        record['binary_offset'] = offset
        offset += record['received']
    (folder / 'drain.bin').write_bytes(binary)
    value.update(binary_sha256=hashlib.sha256(binary).hexdigest(), bytes_written=len(binary))
    path = folder / 'drain.json'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(folder, *, deps=None, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_CLOSED_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    budget, result = None, None
    pid = None
    try:
        deps = layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()  # Disk/path handshake precedes the read clock.
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('CAREER_CLOSED_EXPECTS_ONE_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        started = clock()
        with deps['Process'](pid) as process:
            result, budget = capture(process, identity, clock, started=started)
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CAREER_CLOSED_MODULE_OR_PID_CHANGED')
        budget.check_time()
        result.update(status='complete', game_pid=pid, elapsed_seconds=clock() - started)
        digest = save_material(folder, result)
        status = {key: result[key] for key in ('status', 'source_revision', 'game_pid',
                  'active_read_bytes', 'active_read_calls', 'liveness_proven', 'server_ready')}
        status.update(json_sha256=digest, binary_sha256=result['binary_sha256'])
        (folder / 'status.json').write_text(json.dumps(status, indent=2) + '\n', 'utf8')
        return result
    except Exception as error:
        evidence = error.evidence if isinstance(error, CaptureError) else result
        if evidence is not None:
            evidence.update(status='failed', error=str(error), game_pid=pid)
            evidence.pop('stat_id_label_mapping', None)
            save_material(folder, evidence)
        status = {'status': 'failed', 'source_revision': REVISION, 'error': str(error),
                  'game_pid': pid, 'diagnostic_only': True, 'liveness_proven': False,
                  'server_ready': False, 'career_stats_ready': False,
                  'account_modified': False, 'native_written': False, 'native_called': False}
        (folder / 'status.json').write_text(json.dumps(status, indent=2) + '\n', 'utf8')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.output)
        print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_bytes',
                          'active_read_calls', 'liveness_proven', 'server_ready')}))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
