"""Bounded, read-only Career-list diagnostic; never synchronises an account.

Wait for the user's visible Career page in Ship, then traverse only its known
list. Work resumes in small slices; no HUD-root/heap search or native call.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_visible_list_snapshot_v1'
IMAGE_SIZE = 0x4744000
DISPATCH_GLOBAL, COUNT, ROWS, ROW_STRIDE = 0x3326E68, 5740, 5744, 16
CAREER_PANEL, CAREER_LIST, CAREER_TRACK = 0x4DC08, 2488, 195256
STATE_GLOBAL, STATE_OFFSET = 0x3326340, 705052
HEADER_BYTES, CHILD, NEXT, PARENT, CONTEXT = 256, 0xE0, 0xE8, 0xF0, 0xF8
LABEL_START, LABEL_BYTES = 272, 345
MAX_NODES_PER_SLICE, SLICE_BYTES, SLICE_READS, SLICE_SECONDS = 32, 8192, 64, .010
# Registry/PIN preflight runs in this external helper, outside a game frame.
# Its fixed small address plan has a separate clock; row work stays at 10ms.
GATE_SECONDS = .100
TOTAL_BYTES, TOTAL_READS, MAX_DEPTH, STRING_BYTES = 65536, 512, 8, 64
PINS = ((0x143C950, '40534883ec20488bd94881c110010000'),
        (0x143A1BA, '440fb69958010000'),
        (0x143A1E3, '4c8d0440423954c108'),
        (0x143A212, 'c744242401000000'))
# Real game locale IDs; a COUNT template alone never identifies Career totals.
LABELS = {0x32C9CF0D: 'deaths', 0xF68F08B2: 'enemy_kills',
          0x927DD715: 'career_title', 0x2BAA24A7: 'count_template',
          0xC67C7FAF: 'count_template'}


class SliceFull(Exception):
    def __init__(self):
        super().__init__('CAREER_UI_SLICE_BUDGET')


def pointer(value, aligned=True):
    return 65536 <= value < 0x800000000000 and (not aligned or value % 8 == 0)


class Budget:
    def __init__(self, process, identity, clock=time.perf_counter, total=None,
                 seconds=SLICE_SECONDS):
        self.process, self.identity, self.clock = process, identity, clock
        self.started, self.seconds = clock(), seconds
        self.total = total if total is not None else {'bytes': 0, 'reads': 0, 'records': []}
        self.bytes = self.reads = self.queries = 0

    def gate(self, size):
        if self.total['bytes'] + size > TOTAL_BYTES or self.total['reads'] >= TOTAL_READS:
            raise ValueError('CAREER_UI_TOTAL_BUDGET')
        if (self.bytes + size > SLICE_BYTES or self.reads >= SLICE_READS
                or self.clock() - self.started >= self.seconds):
            raise SliceFull()

    def read(self, address, size, *, image=False, code=False):
        self.gate(size)
        if not 0 < size <= 4096 or not pointer(address, False):
            raise ValueError('CAREER_UI_ADDRESS_OR_SIZE')
        if image and not self.identity['game_base'] <= address < address + size <= self.identity['game_base'] + IMAGE_SIZE:
            raise ValueError('CAREER_UI_OUTSIDE_MODULE')
        self.queries += 1
        region = self.process.query(address)
        protect = region['protect']
        allowed = (0x20, 0x40, 0x80) if code else (2, 4, 8, 0x20, 0x40, 0x80)
        if (region['state'] != 0x1000 or protect & 0x100 or protect & 0xff not in allowed
                or image and region['type'] != 0x1000000
                or not region['base'] <= address < address + size <= region['base'] + region['size']):
            raise ValueError('CAREER_UI_UNREADABLE')
        self.gate(size)
        self.bytes += size; self.reads += 1
        self.total['bytes'] += size; self.total['reads'] += 1
        raw = self.process.read(address, size)
        if len(raw) != size:
            raise ValueError('CAREER_UI_SHORT_READ')
        self.total['records'].append({'address': address, 'length': size, 'raw_hex': raw.hex()})
        return raw

    def u32(self, address, **options):
        return struct.unpack('<I', self.read(address, 4, **options))[0]

    def ptr(self, address, **options):
        return struct.unpack('<Q', self.read(address, 8, **options))[0]


def verify_code(budget):
    for rva, pin in PINS:
        if budget.read(budget.identity['game_base'] + rva, len(bytes.fromhex(pin)), image=True, code=True) != bytes.fromhex(pin):
            raise ValueError('CAREER_UI_CODE_PIN')


def locate(budget):
    """Author-known inline Career list; no controller-wide scan."""
    identity = budget.identity
    if identity['game_size'] != IMAGE_SIZE or identity['game_base'] % 4096:
        raise ValueError('CAREER_UI_MODULE')
    context = budget.ptr(identity['game_base'] + STATE_GLOBAL, image=True)
    if not context:
        return None, 'waiting_ship'
    if not pointer(context):
        raise ValueError('CAREER_UI_STATE_POINTER')
    if budget.u32(context + STATE_OFFSET) != 3:
        return None, 'waiting_ship'
    dispatch = budget.ptr(identity['game_base'] + DISPATCH_GLOBAL, image=True)
    if not dispatch:
        return None, 'waiting_armory'
    if not pointer(dispatch):
        raise ValueError('CAREER_UI_DISPATCH_POINTER')
    count = budget.u32(dispatch + COUNT)
    if count > 64:
        raise ValueError('CAREER_UI_REGISTRY_COUNT')
    if count == 0:
        return None, 'waiting_armory'
    rows = budget.read(dispatch + ROWS, count * ROW_STRIDE)
    controllers = []
    for offset in range(0, len(rows), ROW_STRIDE):
        controller, kind = struct.unpack_from('<QI', rows, offset)
        if kind != 224:
            continue
        if not pointer(controller):
            raise ValueError('CAREER_UI_CONTROLLER_POINTER')
        panel = controller + CAREER_PANEL
        alpha = struct.unpack('<f', budget.read(panel + CAREER_TRACK + 84, 4))[0]
        if not .95 < alpha <= 1.001:
            continue
        at = panel + CAREER_LIST
        header = budget.read(at, HEADER_BYTES)
        flags = struct.unpack_from('<I', header)[0]
        gui_context = struct.unpack_from('<Q', header, CONTEXT)[0]
        if not flags or not pointer(gui_context):
            raise ValueError('CAREER_UI_LIST_HEADER')
        controllers.append({'state_context': context, 'dispatch': dispatch,
                            'controller': controller, 'panel': panel, 'list': at,
                            'gui_context': gui_context, 'header': header.hex()})
    if len(controllers) > 1:
        raise ValueError('CAREER_UI_AMBIGUOUS_CONTROLLER')
    return (controllers[0], 'visible_career') if controllers else (None, 'waiting_career')


def label_descriptor(budget, address):
    raw = budget.read(address + LABEL_START, LABEL_BYTES)
    key = struct.unpack_from('<I', raw)[0]
    count = raw[344]
    if count > 14:
        return {'label_key': key, 'count': count, 'arguments': [], 'valid': False,
                'reason': 'argument_count_above14'}
    args = []
    for index in range(count):
        offset = 8 + 24 * index
        arg_key, kind, value = struct.unpack_from('<IIQ', raw, offset)
        item = {'key': arg_key, 'type': kind, 'value_raw': value,
                'tail_hex': raw[offset + 16:offset + 24].hex()}
        if kind == 1 and pointer(value, False):
            text = budget.read(value, STRING_BYTES)
            nul = text.find(b'\0')
            if nul >= 0:
                try:
                    item['text'] = text[:nul].decode('utf8')
                except UnicodeDecodeError:
                    item['text_error'] = 'invalid_utf8'
            else:
                item['text_error'] = 'string_limit'
        elif kind == 1:
            item['text_error'] = 'invalid_pointer'
        # All other types are retained, never guessed as a statistic.
        args.append(item)
    return {'label_key': key, 'role': LABELS.get(key), 'count': count,
            'arguments': args, 'valid': True, 'numeric_type_proven': False}


class Cursor:
    """Only this Career list, with row ancestry retained across slices."""
    def __init__(self, owner):
        self.owner = owner
        child = struct.unpack_from('<Q', bytes.fromhex(owner['header']), CHILD)[0]
        self.pending = [(child, owner['list'], child, 1)] if child else []
        self.seen, self.nodes, self.labels = set(), [], []

    def step(self, budget, owner):
        for key in ('state_context', 'dispatch', 'controller', 'list', 'gui_context'):
            if owner[key] != self.owner[key]:
                raise ValueError('CAREER_UI_OWNER_CHANGED')
        if bytes.fromhex(owner['header'])[CHILD:CONTEXT + 8] != bytes.fromhex(self.owner['header'])[CHILD:CONTEXT + 8]:
            raise ValueError('CAREER_UI_LIST_REBUILT')
        visited = 0
        while self.pending and visited < MAX_NODES_PER_SLICE:
            node, parent, row, depth = self.pending[-1]
            if not pointer(node) or node in self.seen or depth > MAX_DEPTH:
                raise ValueError('CAREER_UI_TREE_IDENTITY')
            # Do not advance the cursor until a node's reads finish.
            header = budget.read(node, HEADER_BYTES)
            flags = struct.unpack_from('<I', header)[0]
            child, sibling, actual_parent, context = struct.unpack_from('<QQQQ', header, CHILD)
            if not flags or actual_parent != parent or context != owner['gui_context']:
                raise ValueError('CAREER_UI_NODE_OWNER')
            kind = flags >> 18 & 15
            item = {'address': node, 'parent': parent, 'row': row, 'depth': depth,
                    'kind': kind, 'header_hex': header.hex()}
            # Read only exact locale-tag candidates; no numeric search in memory.
            key = budget.u32(node + LABEL_START)
            descriptor = None
            if key in LABELS:
                descriptor = label_descriptor(budget, node)
                if descriptor['label_key'] != key:
                    raise ValueError('CAREER_UI_LABEL_CHANGED')
                final_header = budget.read(node, HEADER_BYTES)
                if (final_header[CHILD:CONTEXT + 8] != header[CHILD:CONTEXT + 8]
                        or struct.unpack_from('<I', final_header)[0] >> 18 & 15 != kind):
                    raise ValueError('CAREER_UI_NODE_CHANGED')
                descriptor.update(address=node, parent=parent, row=row, kind=kind,
                                  widget_type_proven=(kind == 8))
            self.pending.pop(); self.seen.add(node)
            self.nodes.append(item); visited += 1
            if descriptor is not None:
                self.labels.append(descriptor)
            if sibling:
                self.pending.append((sibling, parent, sibling if depth == 1 else row, depth))
            if child:
                self.pending.append((child, node, row, depth + 1))
        return not self.pending


def dependencies():
    import sys
    sys.path.insert(0, str(ROOT / 'tools'))
    from fire_code_windows import Process, resolve_game, game_processes
    profile = runpy.run_path(str(ROOT / 'tools/fire_code_capture.py'))
    return {**profile, 'Process': Process, 'resolve_game': resolve_game,
            'game_processes': game_processes}


def run(folder, *, wait=False, deps=None, sleep=time.sleep, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_UI_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    total = {'bytes': 0, 'reads': 0, 'records': []}
    cursor, selected_pid, pins_pid = None, None, None
    waiting = {'polls': 0, 'bytes': 0, 'reads': 0}
    soft_yields = {'readiness': 0, 'pins': 0, 'final_gate': 0}
    def save(value):
        (folder / 'status.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    try:
        deps = dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        while True:
            pids = tuple(deps['game_processes']())
            if len(pids) != 1:
                if not pids and wait and cursor is None:
                    save({'status': 'waiting_game', 'source_revision': REVISION, **waiting})
                    sleep(2); continue
                raise ValueError('CAREER_UI_EXPECTS_ONE_GAME')
            pid = pids[0]
            try:
                identity = deps['resolve_game'](pid)
            except FileNotFoundError:
                if not wait or cursor is not None:
                    raise
                save({'status': 'waiting_module', 'source_revision': REVISION, **waiting})
                sleep(2); continue
            deps['validate_identity'](identity, stamps)
            if selected_pid is not None and selected_pid != pid:
                raise ValueError('CAREER_UI_PID_CHANGED')
            with deps['Process'](pid) as process:
                readiness = Budget(process, identity, clock, total if cursor is not None else None,
                                   seconds=GATE_SECONDS)
                try:
                    owner, reason = locate(readiness)
                except SliceFull:
                    soft_yields['readiness'] += 1
                    if cursor is None:
                        waiting['polls'] += 1
                        waiting['bytes'] += readiness.bytes; waiting['reads'] += readiness.reads
                    save({'status': 'yield_readiness', 'source_revision': REVISION,
                          'waiting': waiting, 'soft_yields': soft_yields,
                          'active_read_bytes': total['bytes'], 'active_read_calls': total['reads']})
                    if not wait:
                        raise ValueError('CAREER_UI_READINESS_SOFT_YIELD')
                    sleep(2 if cursor is None else .25)
                    continue
                if owner is None:
                    if cursor is not None:
                        raise ValueError('CAREER_UI_PAGE_CLOSED')
                    waiting['polls'] += 1
                    waiting['bytes'] += readiness.bytes; waiting['reads'] += readiness.reads
                    if not wait:
                        raise ValueError('CAREER_UI_' + reason.upper())
                    save({'status': reason, 'source_revision': REVISION, **waiting})
                else:
                    selected_pid = pid
                    if cursor is None:
                        # First visible-page gate was read before the active session
                        # existed. Retain/count those exact reads as active evidence.
                        total['bytes'] += readiness.bytes
                        total['reads'] += readiness.reads
                        total['records'].extend(readiness.total['records'])
                    if pins_pid != pid:
                        pins = Budget(process, identity, clock, total, seconds=GATE_SECONDS)
                        try:
                            verify_code(pins); pins_pid = pid
                        except SliceFull:
                            soft_yields['pins'] += 1
                            save({'status': 'yield_pins', 'source_revision': REVISION,
                                  'soft_yields': soft_yields, 'active_read_bytes': total['bytes'],
                                  'active_read_calls': total['reads']})
                            if not wait:
                                raise ValueError('CAREER_UI_PINS_SOFT_YIELD')
                            sleep(.25)
                            continue
                    if cursor is None:
                        cursor = Cursor(owner)
                    budget = Budget(process, identity, clock, total)
                    try:
                        done = cursor.step(budget, owner)
                    except SliceFull:
                        done = False
                    final_gate = Budget(process, identity, clock, total, seconds=GATE_SECONDS)
                    try:
                        final_owner, final_reason = locate(final_gate)
                    except SliceFull:
                        soft_yields['final_gate'] += 1
                        save({'status': 'yield_final_gate', 'source_revision': REVISION,
                              'soft_yields': soft_yields, 'nodes': len(cursor.nodes),
                              'active_read_bytes': total['bytes'], 'active_read_calls': total['reads']})
                        if not wait:
                            raise ValueError('CAREER_UI_FINAL_GATE_SOFT_YIELD')
                        sleep(.25)
                        continue
                    if final_reason != 'visible_career' or any(final_owner[key] != owner[key] for key in ('controller', 'list', 'gui_context', 'state_context')):
                        raise ValueError('CAREER_UI_FINAL_OWNER_CHANGED')
            if owner is None:
                sleep(2); continue
            if done:
                final_identity = deps['resolve_game'](pid)
                deps['validate_identity'](final_identity, stamps)
                if final_identity != identity or tuple(deps['game_processes']()) != (pid,):
                    raise ValueError('CAREER_UI_MODULE_CHANGED')
                evidence = {'status': 'complete', 'source_revision': REVISION,
                            'captured_at': datetime.now(timezone.utc).isoformat(),
                            'game_pid': pid, 'identity': identity, 'owner': cursor.owner,
                            'nodes': cursor.nodes, 'labels': cursor.labels, 'waiting': waiting,
                            'soft_yields': soft_yields,
                            'active_read_bytes': total['bytes'], 'active_read_calls': total['reads'],
                            'read_records': total['records'], 'diagnostic_only': True,
                            'career_stats_ready': False, 'account_modified': False,
                            'native_written': False, 'native_called': False,
                            'numeric_types': None,
                            'atomic': False,
                            'locator_source': 'VPM ClickableScrollbars author-known static layout',
                            'locator_instruction_pin_verified': False,
                            'label_layout_pins_verified': pins_pid == pid,
                            'normal_label_kind_verified': False,
                            'limits': {'nodes_per_work_slice': MAX_NODES_PER_SLICE,
                                       'bytes_per_budget': SLICE_BYTES,
                                       'reads_per_budget': SLICE_READS,
                                       'soft_seconds_per_budget': SLICE_SECONDS,
                                       'external_gate_soft_seconds_per_budget': GATE_SECONDS,
                                       'active_bytes': TOTAL_BYTES, 'active_reads': TOTAL_READS}}
                path = folder / 'career-list.json'
                path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
                save({key: evidence[key] for key in ('status', 'source_revision', 'active_read_bytes', 'active_read_calls', 'career_stats_ready') } | {'json_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                return evidence
            save({'status': 'reading_career_rows', 'source_revision': REVISION,
                  'nodes': len(cursor.nodes), 'pending': len(cursor.pending),
                  'active_read_bytes': total['bytes'], 'active_read_calls': total['reads']})
            sleep(.25)
    except Exception as error:
        if total['records']:
            # Preserve incomplete local evidence; never make a failed read or
            # partially rebuilt list a successful statistic.
            (folder / 'incomplete.json').write_text(json.dumps({
                'source_revision': REVISION, 'complete': False, 'error': str(error),
                'read_records': total['records'],
                'nodes': cursor.nodes if cursor else [],
                'labels': cursor.labels if cursor else [],
                'career_stats_ready': False}, ensure_ascii=False, indent=2) + '\n', 'utf8')
        save({'status': 'failed', 'source_revision': REVISION, 'error': str(error),
              'waiting': waiting, 'soft_yields': soft_yields,
              'active_read_bytes': total['bytes'],
              'active_read_calls': total['reads'], 'career_stats_ready': False,
              'account_modified': False, 'native_written': False, 'native_called': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--wait-for-career', action='store_true')
    args = parser.parse_args()
    try:
        result = run(args.output, wait=args.wait_for_career)
        print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_bytes', 'active_read_calls', 'career_stats_ready')}, ensure_ascii=False))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
