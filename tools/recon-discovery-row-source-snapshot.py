"""One fixed 64-row snapshot with contemporaneous, bounded NAME attribution.

Keeps the original 64 KiB / 256-read limits. At most 8 discovery names are
resolved, each <=64B, against one stable four-person roster. No type10 reads.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_recon_discovery_combined_rows', ROOT / 'tools/recon-chat-row-child-descriptor-snapshot.py')
child = importlib.util.module_from_spec(spec); spec.loader.exec_module(child)
reader, layout = child.reader, child.reader.layout
MAX_NAMES, NAME_KEY, DISCOVERY_KEY = 8, 0x341F7711, 0x38237B81
ROSTER_GLOBAL, USER_GLOBAL, LOCAL_PEER = 0x347CED8, 0x347CEF0, 0xB398
STRING_BYTES, ROSTER_STRIDE = 64, 0xC0


def string(raw):
    end = raw.find(b'\0')
    if end < 0: return None, 'name_not_terminated_within64'
    try: return raw[:end].decode('utf8'), None
    except UnicodeDecodeError: return None, 'name_invalid_utf8'


class NameProbe:
    def __init__(self):
        self.attempts = 0
        self.pending = None
        self.players = []

    def start(self, budget):
        base = budget.identity['game_base']
        self.roster = budget.ptr(base + ROSTER_GLOBAL, image=True)
        self.user = budget.ptr(base + USER_GLOBAL, image=True)
        if not layout.pointer(self.roster) or not layout.pointer(self.user):
            raise ValueError('RECON_DISCOVERY_ROSTER_POINTER')
        self.local_peer = budget.read(self.user + LOCAL_PEER, 8)
        if self.local_peer == bytes(8): raise ValueError('RECON_DISCOVERY_LOCAL_PEER')
        self.raw = [budget.read(self.roster + i * ROSTER_STRIDE, 72) for i in range(4)]
        for i, raw in enumerate(self.raw):
            if raw[:8] == bytes(8): continue
            name, error = string(raw[8:])
            self.players.append({'slot': i, 'peer': raw[:8][::-1].hex().upper(), 'name': name,
                                 'name_error': error, 'local': raw[:8] == self.local_peer})

    def before_identity(self, budget, row):
        self.pending = None
        descriptor = row.get('descriptor')
        if not descriptor or not descriptor['discovery_template_match']: return
        out = row['discovery_source'] = {'resolved': False, 'type10_followed': False}
        args = descriptor['arguments']
        if descriptor['argument_count'] not in (2, 3) or not descriptor['layout_valid']:
            out['reason'] = 'unsupported_discovery_argument_count'; return
        names = [a for a in args if a['key'] == NAME_KEY]
        discoveries = [a for a in args if a['key'] == DISCOVERY_KEY]
        if len(names) != 1 or len(discoveries) != 1 or names[0]['type'] != 1:
            out['reason'] = 'unsupported_discovery_name_binding'; return
        pointer = names[0]['value_raw']
        if not layout.pointer(pointer, False):
            out['reason'] = 'invalid_name_pointer'; return
        if self.attempts >= MAX_NAMES:
            out['reason'] = 'eight_name_budget'; return
        self.attempts += 1
        raw = budget.read(pointer, STRING_BYTES)
        self.pending = {'pointer': pointer, 'raw': raw, 'row': row,
                        'descriptor': bytes.fromhex(row['descriptor_hex']),
                        'used_bytes': 8 + 24 * len(args)}

    def after_identity(self, budget, row):
        pending = self.pending
        if pending is None: return
        assert pending['row'] is row
        label = row['address'] + 272
        # Unused descriptor storage is not evidence. Recheck the exact template,
        # all declared typed parameters, count, and NAME bytes around the sample.
        prefix = budget.read(label, pending['used_bytes'])
        count = budget.read(label + 344, 1)
        raw = budget.read(pending['pointer'], STRING_BYTES)
        if (prefix != pending['descriptor'][:pending['used_bytes']]
            or count != pending['descriptor'][344:345] or raw != pending['raw']):
            raise ValueError('RECON_DISCOVERY_SOURCE_CHANGED_DURING_ROW')
        out = row['discovery_source']; name, error = string(raw)
        if error or not name:
            out['reason'] = error or 'name_empty'; return
        matches = [p for p in self.players if p['name'] == name]
        out.update(name=name, name_pointer=pending['pointer'], exact_match_count=len(matches))
        if len(matches) == 1:
            out.update(resolved=True, peer=matches[0]['peer'], local_player=matches[0]['local'],
                       reason='unique_current_roster_name')
        else:
            out['reason'] = 'ambiguous_roster_name' if matches else 'no_current_roster_name'
        self.pending = None

    def finish(self, budget):
        base = budget.identity['game_base']
        if (budget.ptr(base + ROSTER_GLOBAL, image=True) != self.roster
            or budget.ptr(base + USER_GLOBAL, image=True) != self.user
            or budget.read(self.user + LOCAL_PEER, 8) != self.local_peer
            or [budget.read(self.roster + i * ROSTER_STRIDE, 72) for i in range(4)] != self.raw):
            raise ValueError('RECON_DISCOVERY_ROSTER_CHANGED')


def snapshot(process, module, clock=time.perf_counter):
    probe = NameProbe()
    result = child.snapshot(process, module, clock=clock, name_probe=probe)
    result.update(source_revision='recon_fixed_rows_and_name_v1', roster=probe.players,
                  names_attempted=probe.attempts, maximum_name_reads=MAX_NAMES,
                  string_pointers_followed=probe.attempts, type10_followed=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    import fire_code_capture as guard
    child.source(); stamps = guard.fingerprints()
    if tuple(game_processes()) != (args.pid,): raise ValueError('RECON_DISCOVERY_PID_CHANGED')
    module = resolve_game(args.pid); guard.validate_identity(module, stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process: result = snapshot(process, module)
    final = resolve_game(args.pid); guard.validate_identity(final, stamps)
    if final != module: raise ValueError('RECON_DISCOVERY_MODULE_CHANGED')
    result.update(game_pid=args.pid, module=module)
    (args.output / 'rows.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'status': result['status'], 'mode': result['mode'], 'read_bytes': result['read_bytes'],
        'read_calls': result['read_calls'], 'elapsed_ms': result['elapsed_ms'],
        'sources': [{'row': r['index'], **r['discovery_source']} for r in result['rows'] if 'discovery_source' in r]}, ensure_ascii=False))


if __name__ == '__main__': main()
