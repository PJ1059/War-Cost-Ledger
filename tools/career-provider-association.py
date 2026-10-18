"""One read-only association sample of a visible personal Career page.

No wait loop, provider/getter invocation, UI action, account write or sync.
The 44-byte candidate is retained without following any reference inside it.
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
REVISION = 'career_visible_provider_association_v1'
MAX_BYTES, MAX_IO, SOFT_SECONDS = 8192, 96, 1.0
LOCAL_USER, LOCAL_PEER, UI_PEER = 0x347CEF0, 0xB398, 0x7F6D8
MODE, COPY, COPY_BYTES = 0x2FE04, 0x2FE08, 44
CANDIDATE, CANDIDATE_FIELDS = 0x347CDD8, 0x14C
FILLED_COUNT, ROW_META = 0x2F0F4, 0x18FC
ROW_FIELD = {1: 0, 2: 0x14, 4: 0x18, 5: 0x1C}
HELPERS = (
    ('tools/career-target-rows.py', '73c9cde1528ef9803bf48ecdf9d0d12a3abe67cf26eb3dff554618c001cc1629'),
    ('tools/career-ui-snapshot.py', '5b16c3ca6550e6c717f4245dce5aabcbf2890ac08e0fcc8de667afe0930a0fe6'),
)
# Actual frozen BIN bodies; offsets come from their saved drain ranges.
SOURCES = (
    ('dist/career-armory-view-init-20261012-8a8b50c3/capture/drain.bin',
     '4ab9fe08c4d409637872f9f6926b73a0906ad8d53292023bd32c1100a7990257', 0x1455C30, 2855, 5),
    ('dist/career-panel-init-20261012-8223909e/capture/drain.bin',
     '390516011461495dd7e09f4e106c980c00df00861385a47299d3fef6d7babcff', 0x18EDCA0, 597, 5),
    ('dist/career-panel-list-init-20261012-5f0d5e2a/capture/drain.bin',
     '0b32a1a11119f7cb16f4761d2e6cf65ae97aba181bac646de24ef528378a3056', 0x18E52B0, 2139, 5),
    ('dist/career-stat-fill-body-20261012-f2168643/capture/drain.bin',
     '238f2d4a4307188e16625b1c255b93fc9052c5b2aea0eb6089e51352ffa4f5b1', 0x18E62B0, 406, 5),
    ('dist/career-row-value-20261012-09e6e39c/capture/drain.bin',
     '0b798e6a1b323e31afa2b763449b9a500dbe168e947edf79bfdb51b650bfa2dd', 0x18E4BE0, 94, 5),
    ('dist/career-local-profile-20261012-nextship/capture/drain.bin',
     '68523d1281b7b8bc55c50763d3fe2e6ee56749b28aa09062245d863affdb2bdb', 0x19A6990, 109, 5),
)
PINS = (
    (0x1456522, '498d8ff8da0400e872774900'),
    (0x18EDD80, '488d8f10010000'),
    (0x18EDDCA, 'e8e174ffff'),
    (0x18E5ACA, 'e8e1070000'),
    (0x18E62F4, '488b05dd6ab901'),
    (0x18E62FB, '0f10804c010000'),
    (0x18E63CD, '83bf04fe020001'),
    (0x18E4C24, '44898419101a0000'),
    (0x19A69C6, '488991c0190000'),
)
for relative, expected in HELPERS:
    if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
        raise ValueError('CAREER_ASSOCIATION_HELPER_CHANGED')
spec = importlib.util.spec_from_file_location('career_association_private_target', ROOT / HELPERS[0][0])
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)
layout = target.layout


def validate_source():
    bodies = []
    for path, expected, begin, length, offset in SOURCES:
        raw = (ROOT / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected or offset + length > len(raw):
            raise ValueError('CAREER_ASSOCIATION_SOURCE_CHANGED')
        bodies.append((begin, raw[offset:offset + length]))
    for rva, pin in PINS:
        wanted = bytes.fromhex(pin)
        if not any(begin <= rva and rva + len(wanted) <= begin + len(raw)
                   and raw[rva - begin:rva - begin + len(wanted)] == wanted
                   for begin, raw in bodies):
            raise ValueError('CAREER_ASSOCIATION_SOURCE_PIN')
    return [{'path': path, 'sha256': sha} for path, sha, *_ in SOURCES]


class Budget(layout.Budget):
    """Independent whole-capture cap; no old reader globals are changed."""
    def __init__(self, process, identity, clock=time.perf_counter, *, started=None):
        super().__init__(process, identity, clock)
        if started is not None:
            self.started = started

    def check_time(self):
        elapsed = self.clock() - self.started
        if not 0 <= elapsed < SOFT_SECONDS:
            raise ValueError('CAREER_ASSOCIATION_SOFT_BUDGET')

    def gate(self, size):
        if (self.total['bytes'] + size > MAX_BYTES
                or self.total['reads'] >= MAX_IO or self.queries > MAX_IO):
            raise ValueError('CAREER_ASSOCIATION_TOTAL_BUDGET')
        self.check_time()

    def read(self, address, size, *, image=False, code=False):
        if self.queries >= MAX_IO:
            raise ValueError('CAREER_ASSOCIATION_TOTAL_BUDGET')
        raw = super().read(address, size, image=image, code=code)
        self.check_time()
        return raw


def pointer(value, reason):
    if not layout.pointer(value):
        raise ValueError('CAREER_ASSOCIATION_' + reason)
    return value


def verify_code(budget):
    layout.verify_code(budget)
    for rva, pin in PINS:
        wanted = bytes.fromhex(pin)
        if budget.read(budget.identity['game_base'] + rva, len(wanted), image=True, code=True) != wanted:
            raise ValueError('CAREER_ASSOCIATION_CODE_PIN')


def association(budget, owner, rows):
    base = budget.identity['game_base']
    user = pointer(budget.ptr(base + LOCAL_USER, image=True), 'LOCAL_USER')
    peer = budget.read(user + LOCAL_PEER, 8)
    ui_peer = budget.read(owner['controller'] + UI_PEER, 8)
    if peer == bytes(8) or peer != ui_peer:
        raise ValueError('CAREER_ASSOCIATION_NOT_LOCAL_PEER')
    count = budget.u32(owner['list'] + FILLED_COUNT)
    if not 9 <= count <= 30:
        raise ValueError('CAREER_ASSOCIATION_FILLED_COUNT')
    panel_raw = budget.read(owner['panel'] + MODE, 4 + COPY_BYTES)
    candidate = pointer(budget.ptr(base + CANDIDATE, image=True), 'CANDIDATE_POINTER')
    candidate_raw = budget.read(candidate + CANDIDATE_FIELDS, COPY_BYTES)
    row_fields = {}
    for name, row in rows.items():
        raw = budget.read(row['row_address'] + ROW_META, 8)
        row_id, value = struct.unpack('<II', raw)
        mapped = ROW_FIELD.get(row_id)
        item = {'metadata_address': row['row_address'] + ROW_META,
                'metadata_hex': raw.hex(), 'row_id': row_id, 'stored_value_u32': value,
                'display_value_u64': row['value']['value_raw'],
                'stored_equals_display': value == row['value']['value_raw'],
                'mode_one_branch_field_offset': mapped}
        if mapped is not None:
            item.update(panel_field_u32=struct.unpack_from('<I', panel_raw, 4 + mapped)[0],
                        candidate_field_u32=struct.unpack_from('<I', candidate_raw, mapped)[0])
        row_fields[name] = item
    return {'local_user': user, 'local_peer_hex': peer[::-1].hex().upper(),
            'ui_peer_address': owner['controller'] + UI_PEER, 'ui_peer_hex': ui_peer[::-1].hex().upper(),
            'filled_count': count, 'mode_address': owner['panel'] + MODE,
            'mode_u32': struct.unpack_from('<I', panel_raw)[0], 'panel_mode_and_copy_hex': panel_raw.hex(),
            'candidate_global_rva': CANDIDATE, 'candidate_address': candidate,
            'candidate_fields_address': candidate + CANDIDATE_FIELDS, 'candidate_hex': candidate_raw.hex(),
            'panel_copy_equals_candidate': panel_raw[4:] == candidate_raw,
            'copy_different_dword_offsets': [i for i in range(0, COPY_BYTES, 4)
                if panel_raw[4 + i:8 + i] != candidate_raw[i:i + 4]],
            'rows': row_fields}


def capture(process, identity, clock=time.perf_counter, *, started=None):
    budget = Budget(process, identity, clock, started=started)
    before, reason = layout.locate(budget)
    if before is None:
        raise target.NotVisible(reason, budget)
    verify_code(budget)
    before_path, before_rows = target.selected_rows(budget, before)
    first = association(budget, before, before_rows)
    after, reason = layout.locate(budget)
    if after is None:
        raise ValueError('CAREER_ASSOCIATION_PAGE_CLOSED')
    target.compare_owners(before, after)
    verify_code(budget)
    after_path, after_rows = target.selected_rows(budget, after)
    target.compare_rows(before_path, before_rows, after_path, after_rows)
    second = association(budget, after, after_rows)
    if first != second:
        raise ValueError('CAREER_ASSOCIATION_FIELDS_CHANGED')
    budget.check_time()
    return {'source_revision': REVISION, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'identity': identity, 'owner_before': before, 'owner_after': after,
            'row_path_before': before_path, 'row_path_after': after_path,
            'rows_before': before_rows, 'rows_after': after_rows,
            'association_before': first, 'association_after': second,
            'active_read_bytes': budget.bytes, 'active_read_calls': budget.reads,
            'active_query_calls': budget.queries, 'read_records': budget.total['records'],
            'pins_verified_twice': True, 'fields_stable_twice': True, 'visible_local_page_verified': True,
            'candidate_owner_verified': False, 'candidate_career_semantics_verified': False,
            'provider_refresh_verified': False, 'mode_enum_verified': False,
            'career_stats_ready': False, 'atomic': False, 'diagnostic_only': True,
            'account_modified': False, 'native_written': False, 'native_called': False,
            'limits': {'bytes': MAX_BYTES, 'rpm': MAX_IO, 'queries': MAX_IO, 'soft_seconds': SOFT_SECONDS,
                       'clock_scope': 'process_open_through_final_identity',
                       'soft_limit_preempts_blocking_os_calls': False}}


def native_creation_tick(pid, process_factory):
    # Same metadata-only API as the existing fixed Career tools, using 0x410.
    import ctypes
    from ctypes import wintypes
    with process_factory(pid) as process:
        fn = process._kernel.GetProcessTimes
        fn.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        fn.restype = wintypes.BOOL
        values = [wintypes.FILETIME() for _ in range(4)]
        if not fn(process._require_open(), *(ctypes.byref(value) for value in values)):
            raise ctypes.WinError(ctypes.get_last_error())
        return values[0].dwHighDateTime << 32 | values[0].dwLowDateTime


def run(folder, *, pid, deps=None, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_ASSOCIATION_OUTPUT_EXISTS')
    if type(pid) is not int or pid <= 0:
        raise ValueError('CAREER_ASSOCIATION_EXPLICIT_PID_REQUIRED')
    source = validate_source()
    folder.mkdir(parents=True)
    def save(value):
        (folder / 'status.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    try:
        deps = layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        if tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CAREER_ASSOCIATION_EXPECTS_AUTHORIZED_SINGLE_PID')
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        started = clock()
        creation = deps.get('process_creation_tick', lambda p: native_creation_tick(p, deps['Process']))
        before_tick = creation(pid)
        with deps['Process'](pid) as process:
            result = capture(process, identity, clock, started=started)
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if (final != identity or tuple(deps['game_processes']()) != (pid,)
                or creation(pid) != before_tick):
            raise ValueError('CAREER_ASSOCIATION_PROCESS_OR_MODULE_CHANGED')
        elapsed = clock() - started
        if not 0 <= elapsed < SOFT_SECONDS:
            raise ValueError('CAREER_ASSOCIATION_SOFT_BUDGET')
        result.update(status='complete', game_pid=pid, process_creation_time_filetime=before_tick,
                      source_code_evidence=source, elapsed_ms=elapsed * 1000)
        path = folder / 'association.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
        save({'status': 'complete', 'source_revision': REVISION, 'json_path': str(path),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'active_read_calls': result['active_read_calls'], 'active_query_calls': result['active_query_calls'],
              'active_read_bytes': result['active_read_bytes'], 'career_stats_ready': False})
        return result
    except Exception as error:
        save({'status': 'failed', 'source_revision': REVISION, 'error': str(error),
              'career_stats_ready': False, 'account_modified': False, 'native_written': False, 'native_called': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pid', required=True, type=int)
    args = parser.parse_args()
    try:
        result = run(args.output, pid=args.pid)
        print(json.dumps({key: result[key] for key in
            ('status', 'game_pid', 'active_read_calls', 'active_query_calls', 'active_read_bytes', 'career_stats_ready')}))
    except (ValueError, OSError, target.NotVisible) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
