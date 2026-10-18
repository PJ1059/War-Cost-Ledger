"""Single bounded read-only capture of the visible Career list's nearby parents.

Reads no statistic rows, text buffers or descendant trees. This diagnoses a
possible native collection-panel parent; it does not mount, call, or write UI.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_parent_private_layout', ROOT / 'tools/career-ui-snapshot.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
REVISION = 'career_three_parents_adjacent_headers_v1'
PARENT_OFFSET = 0x4E4B0  # Exact parent of +0x4E5C0 in saved visible-row evidence.
MAX_BYTES, MAX_READS, MAX_QUERIES, SOFT_SECONDS = 16384, 64, 64, 1.0
MAX_ANCESTORS, MAX_ADJACENT, MAX_HEADERS = 3, 12, 16


class NotVisible(Exception):
    def __init__(self, reason, budget):
        self.reason, self.bytes, self.reads = reason, budget.bytes, budget.reads
        super().__init__('CAREER_PARENT_' + reason.upper())


class Budget(layout.Budget):
    def gate(self, size):
        if self.total['bytes'] + size > MAX_BYTES or self.total['reads'] >= MAX_READS:
            raise ValueError('CAREER_PARENT_TOTAL_BUDGET')
        # A query occurs immediately before the second gate in read().
        if self.queries > MAX_QUERIES:
            raise ValueError('CAREER_PARENT_QUERY_BUDGET')
        if self.clock() - self.started >= SOFT_SECONDS:
            raise ValueError('CAREER_PARENT_SOFT_BUDGET')

    def read(self, address, size, **options):
        if self.queries >= MAX_QUERIES:
            raise ValueError('CAREER_PARENT_QUERY_BUDGET')
        return super().read(address, size, **options)


def unpack(raw):
    flags = struct.unpack_from('<I', raw)[0]
    child, following, parent, context = struct.unpack_from('<QQQQ', raw, layout.CHILD)
    return {'kind': flags >> 18 & 15, 'flags': flags, 'child': child,
            'next': following, 'parent': parent, 'gui_context': context}


def validate(raw, context, parent=None):
    fields = unpack(raw)
    if not fields['flags'] or not fields['kind'] or fields['gui_context'] != context:
        raise ValueError('CAREER_PARENT_WIDGET_IDENTITY')
    if parent is not None and fields['parent'] != parent:
        raise ValueError('CAREER_PARENT_CHILD_OWNERSHIP')
    for field in ('child', 'next', 'parent'):
        if fields[field] and not layout.pointer(fields[field]):
            raise ValueError('CAREER_PARENT_WIDGET_LINK')
    return fields


def geometry(raw):
    # These are the established 256B widget-header geometry offsets. They are
    # raw local/matrix observations; no unproved screen-space mapping is used.
    fields = {'width_at24': 0x24, 'height_at28': 0x28,
              'matrix64': 0x64, 'matrix68': 0x68, 'matrix6c': 0x6C,
              'matrix74': 0x74, 'matrix78': 0x78, 'matrix7c': 0x7C,
              'matrix84': 0x84, 'matrix88': 0x88, 'matrix8c': 0x8C,
              'translation94': 0x94, 'translation98': 0x98, 'translation9c': 0x9C}
    result = {name: struct.unpack_from('<f', raw, offset)[0] for name, offset in fields.items()}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError('CAREER_PARENT_NONFINITE_GEOMETRY')
    return result


def capture(process, identity, clock=time.perf_counter):
    budget = Budget(process, identity, clock)
    before, reason = layout.locate(budget)
    if before is None:
        raise NotVisible(reason, budget)
    layout.verify_code(budget)
    context = before['gui_context']
    nodes = {}
    def remember(address, raw, relation, parent=None):
        if address in nodes:
            if parent is not None and nodes[address]['parent'] != parent:
                raise ValueError('CAREER_PARENT_MULTIPLE_PARENTS')
            return nodes[address]
        if len(nodes) >= MAX_HEADERS:
            raise ValueError('CAREER_PARENT_HEADER_LIMIT')
        item = {'address': address, 'controller_offset': address - before['controller'],
                'relation': relation, 'header_hex': raw.hex(), **validate(raw, context, parent),
                'geometry': geometry(raw)}
        nodes[address] = item
        return item
    first = remember(before['list'], bytes.fromhex(before['header']), 'known_career_list')
    if first['kind'] != 1 or first['parent'] != before['controller'] + PARENT_OFFSET:
        raise ValueError('CAREER_PARENT_KNOWN_LIST_PARENT')
    ancestors, current = [], first['parent']
    for depth in range(1, MAX_ANCESTORS + 1):
        if not current:
            break
        if current in nodes:
            raise ValueError('CAREER_PARENT_ANCESTOR_CYCLE')
        item = remember(current, budget.read(current, layout.HEADER_BYTES), 'ancestor_' + str(depth))
        ancestors.append(current)
        current = item['parent']
    chains, adjacent_count = [], 0
    for parent in ancestors:
        chain, seen = {'parent': parent, 'children': [], 'truncated': False}, set()
        current = nodes[parent]['child']
        while current:
            if current in seen:
                raise ValueError('CAREER_PARENT_SIBLING_CYCLE')
            seen.add(current)
            if current not in nodes:
                if adjacent_count >= MAX_ADJACENT or len(nodes) >= MAX_HEADERS:
                    chain.update(truncated=True, next_unread=current)
                    break
                item = remember(current, budget.read(current, layout.HEADER_BYTES), 'adjacent', parent)
                adjacent_count += 1
            else:
                item = nodes[current]
                if item['parent'] != parent:
                    raise ValueError('CAREER_PARENT_CHILD_OWNERSHIP')
            chain['children'].append(current)
            current = item['next']
        chains.append(chain)
    after, reason = layout.locate(budget)
    if after is None:
        raise ValueError('CAREER_PARENT_PAGE_CLOSED')
    for key in ('state_context', 'dispatch', 'controller', 'panel', 'list', 'gui_context'):
        if before[key] != after[key]:
            raise ValueError('CAREER_PARENT_OWNER_CHANGED')
    for address, item in nodes.items():
        raw = bytes.fromhex(after['header']) if address == after['list'] else budget.read(address, layout.HEADER_BYTES)
        validate(raw, context, item['parent'])
        # Require all measured headers to stay exact. Transition/animation can
        # invalidate this diagnostic; a later single capture may retry settled UI.
        if raw.hex() != item['header_hex']:
            raise ValueError('CAREER_PARENT_HEADER_CHANGED')
    return {'source_revision': REVISION, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'identity': identity, 'owner_before': before, 'owner_after': after,
            'ancestors': ancestors, 'ancestor_limit_reached': bool(ancestors and nodes[ancestors[-1]]['parent']),
            'chains': chains, 'nodes': list(nodes.values()), 'adjacent_count': adjacent_count,
            'active_read_bytes': budget.total['bytes'], 'active_read_calls': budget.total['reads'],
            'active_query_calls': budget.queries, 'read_records': budget.total['records'],
            'pins_verified': True, 'headers_stable': True, 'atomic': False,
            'diagnostic_only': True, 'native_parent_mount_verified': False,
            'screen_geometry_verified': False, 'personal_account_verified': False,
            'account_modified': False, 'native_written': False, 'native_called': False,
            'limits': {'bytes': MAX_BYTES, 'reads': MAX_READS, 'queries': MAX_QUERIES,
                       'soft_seconds': SOFT_SECONDS, 'ancestors': MAX_ANCESTORS,
                       'adjacent': MAX_ADJACENT, 'unique_headers': MAX_HEADERS}}


def run(folder, *, deps=None, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_PARENT_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    def save(value):
        (folder / 'status.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    try:
        deps = layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('CAREER_PARENT_EXPECTS_ONE_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        with deps['Process'](pid) as process:
            result = capture(process, identity, clock)
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CAREER_PARENT_MODULE_CHANGED')
        result.update(game_pid=pid, status='complete')
        path = folder / 'career-parents.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
        save({'status': 'complete', 'source_revision': REVISION, 'json_path': str(path),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'active_read_bytes': result['active_read_bytes'],
              'active_read_calls': result['active_read_calls'], 'headers': len(result['nodes']),
              'native_parent_mount_verified': False})
        return result
    except Exception as error:
        save({'status': 'not_visible' if isinstance(error, NotVisible) else 'failed',
              'source_revision': REVISION, 'error': str(error), 'account_modified': False,
              'native_written': False, 'native_called': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.output)
        print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_bytes', 'active_read_calls', 'active_query_calls')}))
    except (ValueError, OSError, NotVisible) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
