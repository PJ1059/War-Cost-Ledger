"""One read-only check of hidden Career rows on the normal Armory landing page.

Diagnostic output only: no stats synchronization, UI operations or native calls.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('landing_private_locator', ROOT / 'tools/career-hidden-cache-check.py')
hidden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hidden)
REVISION = 'career_armory_landing_hidden_rows_v1'


def presenter(budget, layout):
    ui = budget.ptr(budget.identity['game_base'] + 0x347CE28, image=True)
    user = budget.ptr(budget.identity['game_base'] + 0x347CEF0, image=True)
    if not layout.pointer(ui) or not layout.pointer(user):
        raise ValueError('LANDING_CONTEXT_UNAVAILABLE')
    raw = budget.read(ui + 0x4288 + 12, 32)
    current, depth = struct.unpack_from('<I', raw)[0], struct.unpack_from('<I', raw, 28)[0]
    if not 1 <= depth <= 5:
        raise ValueError('LANDING_PRESENTER_DEPTH')
    top = struct.unpack_from('<I', raw, 8 + (depth - 1) * 4)[0]
    peer = struct.unpack('<Q', budget.read(user + 0xB398, 8))[0]
    if current != 5 or top != 5 or peer == 0:
        raise ValueError('LANDING_ARMORY_NOT_ACTIVE')
    return {'ui': ui, 'current': current, 'depth': depth, 'top': top, 'local_user': user,
            'local_peer': f'{peer:016X}'}


def capture(process, identity, clock=time.perf_counter):
    target = hidden.private_target()
    layout = target.layout
    budget = target.Budget(process, identity, clock)
    first_presenter = presenter(budget, layout)
    before, reason = layout.locate(budget)
    if before is None:
        raise ValueError('LANDING_' + reason.upper())
    if before['alpha'] > .05:
        raise ValueError('LANDING_DETAIL_PAGE_VISIBLE')
    layout.verify_code(budget)
    first = struct.unpack_from('<Q', bytes.fromhex(before['header']), layout.CHILD)[0]
    filled = budget.u32(before['list'] + 0x2F0F4)
    if filled > 30:
        raise ValueError('LANDING_FILLED_COUNT')
    if first == 0 or filled < 9:
        old_path, old_rows = [], {}
    else:
        if first != before['list'] + 0x110:
            raise ValueError('LANDING_FIRST_ROW_SLOT')
        old_path, old_rows = target.selected_rows(budget, before)
    after, reason = layout.locate(budget)
    if after is None:
        raise ValueError('LANDING_OWNER_REMOVED')
    target.compare_owners(before, after)
    if before['alpha_raw_hex'] != after['alpha_raw_hex']:
        raise ValueError('LANDING_ALPHA_CHANGED')
    after_first = struct.unpack_from('<Q', bytes.fromhex(after['header']), layout.CHILD)[0]
    after_filled = budget.u32(after['list'] + 0x2F0F4)
    if after_filled != filled:
        raise ValueError('LANDING_ROWS_FILLING')
    if after_first == 0 or after_filled < 9:
        new_path, new_rows = [], {}
    else:
        new_path, new_rows = target.selected_rows(budget, after)
    target.compare_rows(old_path, old_rows, new_path, new_rows)
    if presenter(budget, layout) != first_presenter:
        raise ValueError('LANDING_PRESENTER_CHANGED')
    status = 'candidate_rows_unverified' if new_rows else 'empty_rows' if first == 0 else 'rows_not_filled'
    return {'source_revision': REVISION, 'status': status, 'filled_count': filled,
            'captured_at': datetime.now(timezone.utc).isoformat(), 'identity': identity,
            'presenter': first_presenter, 'owner_before': before, 'owner_after': after,
            'row_path_before': old_path, 'row_path_after': new_path,
            'rows_before': old_rows, 'rows_after': new_rows,
            'active_read_bytes': budget.total['bytes'], 'active_read_calls': budget.total['reads'],
            'read_records': budget.total['records'], 'diagnostic_only': True,
            'career_stats_ready': False, 'account_modified': False,
            'native_written': False, 'native_called': False,
            'limits': {'bytes': target.MAX_BYTES, 'reads': target.MAX_READS, 'soft_seconds': target.SOFT_SECONDS}}


def run(folder, *, deps=None, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('LANDING_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    try:
        target = hidden.private_target()
        deps = target.layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('LANDING_EXPECTS_ONE_GAME')
        identity = deps['resolve_game'](pids[0])
        deps['validate_identity'](identity, stamps)
        with deps['Process'](pids[0]) as process:
            result = capture(process, identity, clock)
        final = deps['resolve_game'](pids[0])
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != pids:
            raise ValueError('LANDING_MODULE_CHANGED')
        result['game_pid'] = pids[0]
        path = folder / 'landing-rows.json'
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        status = {'status': result['status'], 'source_revision': REVISION,
                  'json_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'active_read_bytes': result['active_read_bytes'], 'active_read_calls': result['active_read_calls'],
                  'career_stats_ready': False, 'account_modified': False, 'native_written': False, 'native_called': False}
        (folder / 'status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
        return status
    except Exception as error:
        (folder / 'status.json').write_text(json.dumps({'status': 'failed', 'source_revision': REVISION,
            'error': str(error), 'career_stats_ready': False, 'account_modified': False,
            'native_written': False, 'native_called': False}, indent=2), encoding='utf-8')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
