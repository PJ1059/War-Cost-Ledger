"""Read only the published text_font_set entry's fixed first 512 bytes.

Uses the existing visible Career/PID/module gates; never follows a callee,
reads a font resource, calls native code, or modifies the game.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('font_entry_base', ROOT/'tools/career-text-render-entry-snapshot.py')
entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
REVISION = 'career_text_font_set_fixed_512_v1'
RVA, LENGTH = 0x11F7340, 512
PREFIX = bytes.fromhex('48895c2408488974241048897c241841564883ec30')


def capture(process, identity, source, clock=time.perf_counter, tail_source=None, **unused):
    if source.get('status') != 'complete' or not source.get('headers_stable'):
        raise ValueError('CAREER_FONT_SOURCE_INCOMPLETE')
    if any(identity.get(k) != v for k, v in source['identity'].items()):
        raise ValueError('CAREER_FONT_MODULE_CHANGED')
    b = entry.Budget(process, identity, clock)
    before, why = entry.layout.locate(b)
    if not before: raise entry.parent.NotVisible(why, b)
    keys = ('controller', 'list', 'panel', 'gui_context', 'state_context', 'dispatch')
    if any(before[k] != source['owner_before'][k] for k in keys):
        raise ValueError('CAREER_FONT_OWNER_CHANGED')
    entry.layout.verify_code(b)
    entry_at = identity['game_base'] + RVA
    if b.read(entry_at, len(PREFIX), image=True, code=True) != PREFIX:
        raise ValueError('CAREER_FONT_ENTRY_PIN')
    rva, length, entry_pin = RVA, LENGTH, None
    if tail_source is not None:
        prior = tail_source.get('entry', {})
        if (tail_source.get('status') != 'complete' or tail_source.get('stage') != 'text_font_set'
                or tail_source.get('identity') != identity or prior.get('rva') != RVA
                or prior.get('length') != LENGTH or tail_source.get('game_pid') != source['game_pid']):
            raise ValueError('CAREER_FONT_TAIL_SOURCE')
        entry_pin = bytes.fromhex(prior['hex'])
        if len(entry_pin) != LENGTH or not entry_pin.startswith(PREFIX) or hashlib.sha256(entry_pin).hexdigest() != prior['sha256']:
            raise ValueError('CAREER_FONT_TAIL_SOURCE_BYTES')
        if b.read(entry_at, LENGTH, image=True, code=True) != entry_pin:
            raise ValueError('CAREER_FONT_TAIL_ENTRY_CHANGED')
        rva, length = 0x11F753F, 0xE7
    at = identity['game_base'] + rva
    raw = b.read(at, length, image=True, code=True)
    after, why = entry.layout.locate(b)
    if not after or any(after[k] != before[k] for k in keys):
        raise ValueError('CAREER_FONT_PAGE_CHANGED')
    if b.read(at, length, image=True, code=True) != raw:
        raise ValueError('CAREER_FONT_CODE_CHANGED')
    if entry_pin is not None and b.read(entry_at, LENGTH, image=True, code=True) != entry_pin:
        raise ValueError('CAREER_FONT_TAIL_ENTRY_CHANGED')
    return dict(status='complete', source_revision=REVISION,
        captured_at=datetime.now(timezone.utc).isoformat(), identity=identity,
        owner_before=before, owner_after=after, stage='text_font_set_tail' if entry_pin else 'text_font_set',
        validated_entry_sha256=hashlib.sha256(entry_pin).hexdigest() if entry_pin else None,
        entry=dict(module='game', address=at, rva=rva, length=length,
                   sha256=hashlib.sha256(raw).hexdigest(), hex=raw.hex()),
        active_read_bytes=b.total['bytes'], active_read_calls=b.total['reads'],
        active_query_calls=b.queries, read_records=b.total['records'],
        code_stable=True, native_called=False, native_written=False, account_modified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True); p.add_argument('--output', required=True)
    p.add_argument('--tail', action='store_true', help='Only 0x11F753F..0x11F7626, retaining the prior 512-byte entry PIN')
    p.add_argument('--entry-source', help='Completed text-font-set 512-byte snapshot; required with --tail')
    a = p.parse_args()
    if a.tail != bool(a.entry_source): p.error('--tail requires --entry-source, and vice versa')
    prior = json.loads(Path(a.entry_source).read_text('utf8')) if a.tail else None
    entry.capture = lambda *args, **kwargs: capture(*args, tail_source=prior, **kwargs)
    try: print(json.dumps(entry.run(a.source, a.output)))
    except (ValueError, OSError, entry.parent.NotVisible) as e: p.exit(1, str(e)+'\n')
