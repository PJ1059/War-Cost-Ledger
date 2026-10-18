"""Replay tank direct contacts using only owned memory and sentinel consumers.

No game process, game code execution, accounts or installation. Proves the
old source gate excludes these resources and the extension admits them only
with the existing exact creditor and living-hostile checks.
"""
from __future__ import annotations
import argparse
import copy
import ctypes
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/native'))
sys.path.insert(0, str(ROOT / 'tests'))
import hit_copy_vehicle_source_observer as producer
from hit_bridge_owned import OwnedBridge
from test_hit_copy_pending_observer_owned import Fixture
from test_hit_copy_living_target_owned import Health, install_extension


def fixture_profile(profile):
    # The original sentinel fixture already supplies the scalar native leaves.
    # Strip captured destruction code and install the life wrapper explicitly.
    base = json.loads((ROOT / 'docs/native-demolition-diagnostic-profile-v1.json').read_text())
    base['entries'] = [e for e in base['entries'] if not e['name'].startswith('demolition_')]
    qualifier = next(e for e in profile['entries'] if e['name'] == 'qualifier_types')
    base['entries'] = [dict(copy.deepcopy(qualifier), name='qualifier') if e['name'] == 'qualifier'
                       else e for e in base['entries']]
    base['data_tables'] = copy.deepcopy(profile['data_tables'])
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    manifest = producer.package()
    base = json.loads(producer.BASE.read_text())
    assert manifest == json.loads((ROOT / 'docs/native-hit-vehicle-source-profile-v1.json').read_text())
    old_entries = {e['name']: e for e in base['entries']}
    for e in manifest['entries']:
        if e['name'] != 'qualifier_types':
            assert e == old_entries[e['name']], 'Unrelated executable entry changed: ' + e['name']
        else:
            old = old_entries[e['name']]
            assert {k: v for k, v in e.items() if k != 'code_hex'} == {k: v for k, v in old.items() if k != 'code_hex'}
            changes = [i for i, (a, b) in enumerate(zip(bytes.fromhex(e['code_hex']), bytes.fromhex(old['code_hex']))) if a != b]
            assert len(changes) == 1, 'Only source-count immediate may change'
    assert manifest['sites'] == base['sites'] and manifest['living_target_filter'] == base['living_target_filter']
    cases = []
    actions = ('contact_begin', 'default_delta', 'normal_final', 'contact_end')
    for profile, expected in [(base, 0), (manifest, 1)]:
        with OwnedBridge() as bridge:
            p = Fixture(bridge, fixture_profile(profile))
            h = Health(bridge)
            install_extension(p, profile, h)
            for resource in producer.SOURCES:
                p.resolver.insert(1002, int(resource, 16), 1)
                for name, life, peer_delta, source_valid, count in [
                    ('local_living', 0, 0, True, expected),
                    ('other_player', 0, 1 << 32, True, 0),
                    ('zero_creditor', 0, bridge.local_peer, True, 0),
                    ('corpse', 2, 0, True, 0),
                    ('unknown_source', 0, 0, False, 0),
                ]:
                    p.defaults(); h.reset(); h.put32(h.life, life)
                    p.resolver.insert(1002, int(resource, 16) if source_valid else 0x0123456789ABCDEF, 1)
                    ctypes.c_uint64.from_buffer(p.hit, 0x110).value = bridge.local_peer ^ peer_delta
                    records, trace, _, _ = p.run(actions)
                    assert len(records) == count, (expected, resource, name, len(records), trace)
                    if records:
                        assert records[0].creditor == bridge.local_peer and records[0].capture_flags == 0x1ff
                        assert records[0].ap_delta == 1 and records[0].native_branch == 1
                    cases.append(dict(profile='extended' if expected else 'old', source=resource, case=name, hits=len(records)))
    report = dict(status='PASS', game_access=False, game_code_executed=False,
                  original_gateways_peer_commit_life_checks_byte_identical=True, cases=cases)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS tank source extension: exact source table, one-byte count change, ' + str(len(cases)) + ' owned native contact cases')


if __name__ == '__main__':
    main()
