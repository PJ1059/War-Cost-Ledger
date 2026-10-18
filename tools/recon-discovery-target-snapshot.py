"""One fixed native discovery snapshot, resolving type10 locale keys.

The first real 2026-10-16 capture rejected the tail-pointer hypothesis:
low32 0x1166A22E is exactly the game's Light Nest locale key, while upper32
varies independently. This corrected reader never dereferences DISCOVERY.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_recon_target_source', ROOT / 'tools/recon-discovery-row-source-snapshot.py')
source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
source.MAX_NAMES = 4
POI_KEYS = {0x01F261DE, 0xD5BD7333, 0xDD55D46A}
LOCALE_FILES = {'zh': '0x353194c702a3c234.strings.json', 'en': '0x18056969d61dbfe9.strings.json'}


def locale_names():
    folder = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'mod-research/task-layout/full-ui-20261011/strings'
    return {lang: {row['Key']: row['Value'] for row in json.loads((folder / filename).read_text('utf8'))['Items']}
            for lang, filename in LOCALE_FILES.items()}


def target_info(descriptor, names):
    args = descriptor.get('arguments', [])
    selected = [a for a in args if a['key'] == source.DISCOVERY_KEY and a['type'] == 10]
    if len(selected) != 1: return None
    raw = bytes.fromhex(selected[0]['tail_hex'])
    key, upper = struct.unpack('<II', raw)
    return {'representation': 'locale_key_u32_at_tail_plus16', 'locale_key': key,
            'locale_key_hex': f'{key:08X}', 'ignored_upper_u32': upper,
            'names': {lang: values.get(key) for lang, values in names.items()},
            'point_of_interest': key in POI_KEYS, 'candidate_pointers_followed': 0,
            'native_type_dispatch_code_proven': False}


class TargetProbe(source.NameProbe):
    def __init__(self):
        super().__init__(); self.names = locale_names(); self.targets = 0

    def before_identity(self, budget, row):
        super().before_identity(budget, row)
        descriptor = row.get('descriptor')
        if not descriptor or not descriptor['discovery_template_match']: return
        target = target_info(descriptor, self.names)
        if target is not None:
            row['discovery_target'] = target; self.targets += 1


def snapshot(process, module, clock=time.perf_counter):
    probe = TargetProbe()
    result = source.child.snapshot(process, module, clock=clock, name_probe=probe)
    result.update(source_revision='recon_fixed_type10_locale_key_v2', roster=probe.players,
                  names_attempted=probe.attempts, target_keys_parsed=probe.targets,
                  candidate_pointers_followed=0, target_events_emitted=0)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    import fire_code_capture as guard
    source.child.source(); stamps = guard.fingerprints()
    if tuple(game_processes()) != (args.pid,): raise ValueError('RECON_TARGET_PID_CHANGED')
    module = resolve_game(args.pid); guard.validate_identity(module, stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process: result = snapshot(process, module)
    final = resolve_game(args.pid); guard.validate_identity(final, stamps)
    if final != module or tuple(game_processes()) != (args.pid,): raise ValueError('RECON_TARGET_CONTEXT_CHANGED')
    result.update(game_pid=args.pid, module=module)
    (args.output / 'rows.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'status': result['status'], 'mode': result['mode'], 'read_bytes': result['read_bytes'],
        'read_calls': result['read_calls'], 'elapsed_ms': result['elapsed_ms'],
        'sources': [{'row': row['index'], 'source': row.get('discovery_source'),
                     'target': row.get('discovery_target')} for row in result['rows']
                    if row.get('discovery_target')]}, ensure_ascii=False))


if __name__ == '__main__': main()
