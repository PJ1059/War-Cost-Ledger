"""Recheck only the two observed Career total rows; no HUD/list search or sync."""
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
spec = importlib.util.spec_from_file_location('career_target_private_layout', ROOT / 'tools/career-ui-snapshot.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
REVISION = 'career_two_observed_rows_v1'
MAX_BYTES, MAX_READS, SOFT_SECONDS = 8192, 64, 1.0
TAG_OFFSET, VALUE_OFFSET, COUNT_KEY = 0xA40, 0x1390, 0xAB2A7B35
ROWS = ((0, 'enemy_kills', 0xF68F08B2), (8, 'deaths', 0x32C9CF0D))


class NotVisible(Exception):
    def __init__(self, reason, budget):
        self.reason, self.bytes, self.reads = reason, budget.bytes, budget.reads
        super().__init__('CAREER_TARGET_' + reason.upper())


class Budget(layout.Budget):
    """All before/after/PIN/data reads share one immutable fixed session cap."""
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)

    def gate(self, size):
        if self.total['bytes'] + size > MAX_BYTES or self.total['reads'] >= MAX_READS:
            raise ValueError('CAREER_TARGET_TOTAL_BUDGET')
        if self.clock() - self.started >= SOFT_SECONDS:
            raise ValueError('CAREER_TARGET_SOFT_BUDGET')


def links(header):
    return header[layout.CHILD:layout.CONTEXT + 8]


def kind(header):
    return struct.unpack_from('<I', header)[0] >> 18 & 15


def header(budget, address, parent, context, expected_kind):
    raw = budget.read(address, layout.HEADER_BYTES)
    actual_parent, actual_context = struct.unpack_from('<QQ', raw, layout.PARENT)
    if kind(raw) != expected_kind or actual_parent != parent or actual_context != context:
        raise ValueError('CAREER_TARGET_WIDGET_IDENTITY')
    return raw


def descriptor(budget, address, expected_key, *, count_value=False):
    # This single fixed descriptor read includes count+616 and the one expected
    # 24-byte record. No other argument pointer or text buffer is followed.
    raw = budget.read(address + layout.LABEL_START, layout.LABEL_BYTES)
    key, count = struct.unpack_from('<I', raw)[0], raw[344]
    if key != expected_key or count != (1 if count_value else 0):
        raise ValueError('CAREER_TARGET_LABEL_OR_COUNT')
    result = {'address': address, 'key': key, 'count': count, 'raw_hex': raw.hex()}
    if count_value:
        arg_key, arg_type, value = struct.unpack_from('<IIQ', raw, 8)
        if arg_key != COUNT_KEY or arg_type != 4 or value >= 0x80000000:
            raise ValueError('CAREER_TARGET_OBSERVED_ARGUMENT_CHANGED')
        result.update(argument_key=arg_key, argument_type=arg_type,
                      value_raw=value, candidate_nonnegative32=value,
                      argument_tail_hex=raw[24:32].hex(), numeric_type_verified=False)
    return result


def selected_rows(budget, owner):
    root = bytes.fromhex(owner['header'])
    if kind(root) != 1:
        raise ValueError('CAREER_TARGET_LIST_KIND')
    first = struct.unpack_from('<Q', root, layout.CHILD)[0]
    if not layout.pointer(first):
        raise ValueError('CAREER_TARGET_FIRST_ROW')
    addresses, path = {0: first}, [first]
    current = first
    for index in range(1, 9):
        current = budget.ptr(current + layout.NEXT)
        if not layout.pointer(current) or current in path:
            raise ValueError('CAREER_TARGET_ROW_CHAIN')
        path.append(current)
        addresses[index] = current
    rows = {}
    for index, name, label_key in ROWS:
        address = addresses[index]
        row_header = header(budget, address, owner['list'], owner['gui_context'], 1)
        tag, value = address + TAG_OFFSET, address + VALUE_OFFSET
        tag_header = header(budget, tag, address, owner['gui_context'], 7)
        value_header = header(budget, value, address, owner['gui_context'], 7)
        rows[name] = {'row_index': index, 'row_address': address,
                      'row_header_hex': row_header.hex(),
                      'tag_header_hex': tag_header.hex(), 'value_header_hex': value_header.hex(),
                      'tag': descriptor(budget, tag, label_key),
                      'value': descriptor(budget, value, 0x2BAA24A7, count_value=True)}
    return path, rows


def compare_owners(before, after):
    for key in ('state_context', 'dispatch', 'controller', 'panel', 'list', 'gui_context'):
        if before[key] != after[key]:
            raise ValueError('CAREER_TARGET_OWNER_CHANGED')
    if links(bytes.fromhex(before['header'])) != links(bytes.fromhex(after['header'])):
        raise ValueError('CAREER_TARGET_LIST_REBUILT')


def compare_rows(before_path, before, after_path, after):
    if before_path != after_path:
        raise ValueError('CAREER_TARGET_ROW_CHAIN_CHANGED')
    for name in before:
        old, new = before[name], after[name]
        for field in ('row_header_hex', 'tag_header_hex', 'value_header_hex'):
            a, b = bytes.fromhex(old[field]), bytes.fromhex(new[field])
            if kind(a) != kind(b) or links(a) != links(b):
                raise ValueError('CAREER_TARGET_ROW_REBUILT')
        for field in ('tag', 'value'):
            keys = ('address', 'key', 'count') if field == 'tag' else ('address', 'key', 'count', 'argument_key', 'argument_type', 'value_raw')
            if any(old[field][key] != new[field][key] for key in keys):
                raise ValueError('CAREER_TARGET_VALUE_CHANGED')


def capture(process, identity, clock=time.perf_counter):
    budget = Budget(process, identity, clock)
    before, reason = layout.locate(budget)
    if before is None:
        raise NotVisible(reason, budget)
    layout.verify_code(budget)
    before_path, before_rows = selected_rows(budget, before)
    after, reason = layout.locate(budget)
    if after is None:
        raise ValueError('CAREER_TARGET_PAGE_CLOSED')
    compare_owners(before, after)
    after_path, after_rows = selected_rows(budget, after)
    compare_rows(before_path, before_rows, after_path, after_rows)
    return {'source_revision': REVISION, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'identity': identity, 'owner_before': before, 'owner_after': after,
            'row_path_before': before_path, 'row_path_after': after_path,
            'rows_before': before_rows, 'rows_after': after_rows,
            'active_read_bytes': budget.total['bytes'], 'active_read_calls': budget.total['reads'],
            'read_records': budget.total['records'], 'pins_verified': True,
            'parent_context_tag_argument_stable': True, 'atomic': False,
            'diagnostic_only': True, 'career_stats_ready': False,
            'numeric_type_verified': False, 'locator_instruction_pin_verified': False,
            'account_modified': False, 'native_written': False, 'native_called': False,
            'limits': {'bytes': MAX_BYTES, 'reads': MAX_READS, 'soft_seconds': SOFT_SECONDS}}


def run(folder, *, wait=False, deps=None, sleep=time.sleep, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_TARGET_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    waiting = {'polls': 0, 'bytes': 0, 'reads': 0}
    def save(value):
        (folder / 'status.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    try:
        deps = layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        while True:
            pids = tuple(deps['game_processes']())
            if not pids and wait:
                save({'status': 'waiting_game', 'source_revision': REVISION, 'waiting': waiting})
                sleep(2); continue
            if len(pids) != 1:
                raise ValueError('CAREER_TARGET_EXPECTS_ONE_GAME')
            pid = pids[0]
            try:
                identity = deps['resolve_game'](pid)
            except FileNotFoundError:
                if not wait:raise
                save({'status': 'waiting_module', 'source_revision': REVISION, 'waiting': waiting})
                sleep(2); continue
            deps['validate_identity'](identity, stamps)
            try:
                with deps['Process'](pid) as process:
                    result = capture(process, identity, clock)
            except NotVisible as paused:
                waiting['polls'] += 1; waiting['bytes'] += paused.bytes; waiting['reads'] += paused.reads
                if not wait:raise
                save({'status': paused.reason, 'source_revision': REVISION, 'waiting': waiting})
                sleep(2); continue
            final_identity = deps['resolve_game'](pid)
            deps['validate_identity'](final_identity, stamps)
            if final_identity != identity or tuple(deps['game_processes']()) != (pid,):
                raise ValueError('CAREER_TARGET_MODULE_CHANGED')
            result.update(game_pid=pid, waiting=waiting, status='complete')
            path = folder / 'career-rows.json'
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
            save({'status': 'complete', 'source_revision': REVISION, 'json_path': str(path),
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'active_read_bytes': result['active_read_bytes'],
                  'active_read_calls': result['active_read_calls'], 'career_stats_ready': False})
            return result
    except Exception as error:
        save({'status': 'failed', 'source_revision': REVISION, 'error': str(error),
              'waiting': waiting, 'career_stats_ready': False, 'account_modified': False,
              'native_written': False, 'native_called': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--wait-for-career', action='store_true')
    args = parser.parse_args()
    try:
        result = run(args.output, wait=args.wait_for_career)
        print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_bytes', 'active_read_calls', 'career_stats_ready')}))
    except (ValueError, OSError, NotVisible) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
