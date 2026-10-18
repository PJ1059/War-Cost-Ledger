"""One read-only two-row cache check against the user-confirmed visible page.

No account sync, backend call, HUD search, retries, or native invocation.
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
REVISION = 'career_hidden_same_two_rows_v1'
REFERENCE_SHA = '6dc84d63eddee2136e1572fbaa7b6c5ccf8900bd213e21acbf71b25551e2b9fc'
TARGET_SHA = '73c9cde1528ef9803bf48ecdf9d0d12a3abe67cf26eb3dff554618c001cc1629'


def private_target():
    path = ROOT / 'tools/career-target-rows.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != TARGET_SHA:
        raise ValueError('CAREER_CACHE_TARGET_SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location('career_hidden_private_target', path)
    target = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(target)
    layout = target.layout

    def locate(budget):
        # Deliberate private copy of the frozen fixed locator. Actual alpha is
        # retained; a hidden panel is never labelled visible or synthesized.
        identity = budget.identity
        if identity['game_size'] != layout.IMAGE_SIZE or identity['game_base'] % 4096:
            raise ValueError('CAREER_CACHE_MODULE')
        context = budget.ptr(identity['game_base'] + layout.STATE_GLOBAL, image=True)
        if not context:
            return None, 'waiting_ship'
        if not layout.pointer(context):
            raise ValueError('CAREER_CACHE_STATE_POINTER')
        if budget.u32(context + layout.STATE_OFFSET) != 3:
            return None, 'waiting_ship'
        dispatch = budget.ptr(identity['game_base'] + layout.DISPATCH_GLOBAL, image=True)
        if not dispatch:
            return None, 'waiting_armory'
        if not layout.pointer(dispatch):
            raise ValueError('CAREER_CACHE_DISPATCH_POINTER')
        count = budget.u32(dispatch + layout.COUNT)
        if count > 64:
            raise ValueError('CAREER_CACHE_REGISTRY_COUNT')
        if count == 0:
            return None, 'waiting_armory'
        rows = budget.read(dispatch + layout.ROWS, count * layout.ROW_STRIDE)
        candidates = []
        for offset in range(0, len(rows), layout.ROW_STRIDE):
            controller, kind = struct.unpack_from('<QI', rows, offset)
            if kind != 224:
                continue
            if not layout.pointer(controller):
                raise ValueError('CAREER_CACHE_CONTROLLER_POINTER')
            panel = controller + layout.CAREER_PANEL
            raw_alpha = budget.read(panel + layout.CAREER_TRACK + 84, 4)
            alpha = struct.unpack('<f', raw_alpha)[0]
            if not 0 <= alpha <= 1.001:
                raise ValueError('CAREER_CACHE_ALPHA')
            at = panel + layout.CAREER_LIST
            header = budget.read(at, layout.HEADER_BYTES)
            flags = struct.unpack_from('<I', header)[0]
            gui_context = struct.unpack_from('<Q', header, layout.CONTEXT)[0]
            if not flags or not layout.pointer(gui_context):
                raise ValueError('CAREER_CACHE_LIST_HEADER')
            candidates.append({'state_context': context, 'dispatch': dispatch,
                               'controller': controller, 'panel': panel, 'list': at,
                               'gui_context': gui_context, 'header': header.hex(),
                               'alpha': alpha, 'alpha_raw_hex': raw_alpha.hex()})
        if len(candidates) > 1:
            raise ValueError('CAREER_CACHE_AMBIGUOUS_CONTROLLER')
        return (candidates[0], 'career_cache_owner') if candidates else (None, 'waiting_armory')

    # This layout module is created by the private import and is not registered
    # in sys.modules. Frozen target/collector imports elsewhere stay untouched.
    layout.locate = locate
    return target


def reference(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA:
        raise ValueError('CAREER_CACHE_REFERENCE_SHA')
    value = json.loads(raw)
    if value['status'] != 'complete' or value['game_pid'] != 48892:
        raise ValueError('CAREER_CACHE_REFERENCE_IDENTITY')
    return value


def compare_reference(target, expected, observed):
    if observed['identity'] != expected['identity']:
        raise ValueError('CAREER_CACHE_REFERENCE_MODULE')
    for suffix in ('before', 'after'):
        target.compare_owners(expected['owner_before'], observed['owner_' + suffix])
        target.compare_rows(expected['row_path_before'], expected['rows_before'],
                            observed['row_path_' + suffix], observed['rows_' + suffix])


def run(folder, *, reference_path, deps=None, clock=time.perf_counter):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_CACHE_OUTPUT_EXISTS')
    folder.mkdir(parents=True)

    def save(value):
        (folder / 'status.json').write_text(json.dumps(value, indent=2) + '\n', 'utf8')

    try:
        expected = reference(reference_path)
        target = private_target()
        deps = target.layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if pids != (expected['game_pid'],):
            raise ValueError('CAREER_CACHE_REFERENCE_PID')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        if identity != expected['identity']:
            raise ValueError('CAREER_CACHE_REFERENCE_MODULE')
        with deps['Process'](pid) as process:
            try:
                observed = target.capture(process, identity, clock)
            except target.NotVisible as paused:
                raise ValueError('CAREER_CACHE_' + paused.reason.upper()) from paused
        # All reference and fresh process/module checks precede any successful
        # evidence/status write. A failure is a one-shot failure, never a retry.
        compare_reference(target, expected, observed)
        final_identity = deps['resolve_game'](pid)
        deps['validate_identity'](final_identity, stamps)
        if final_identity != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('CAREER_CACHE_MODULE_CHANGED')
        observed.update(source_revision=REVISION,
                        checked_at=datetime.now(timezone.utc).isoformat(), game_pid=pid,
                        status='ui_cache_observed', ui_cache_observed=True,
                        reference_path=str(Path(reference_path).resolve()),
                        reference_sha256=REFERENCE_SHA, server_ready=False,
                        backend_ready=False, account_modified=False,
                        reference_owner_path_values_matched=True,
                        alpha_before=observed['owner_before']['alpha'],
                        alpha_after=observed['owner_after']['alpha'])
        path = folder / 'career-hidden-cache.json'
        path.write_text(json.dumps(observed, indent=2) + '\n', 'utf8')
        save({'status': 'ui_cache_observed', 'source_revision': REVISION,
              'json_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'active_read_bytes': observed['active_read_bytes'],
              'active_read_calls': observed['active_read_calls'],
              'alpha_before': observed['alpha_before'], 'alpha_after': observed['alpha_after'],
              'career_stats_ready': False, 'server_ready': False, 'backend_ready': False})
        return observed
    except Exception as error:
        save({'status': 'failed', 'source_revision': REVISION, 'error': str(error),
              'career_stats_ready': False, 'server_ready': False, 'backend_ready': False,
              'account_modified': False, 'native_written': False, 'native_called': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.output, reference_path=args.reference)
        print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_bytes',
                         'active_read_calls', 'alpha_before', 'alpha_after', 'server_ready', 'backend_ready')}))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
