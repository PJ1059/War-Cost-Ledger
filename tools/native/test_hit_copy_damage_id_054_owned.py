"""Execute the derived DamageInfo gateways on owned Win64 code/data only.

No game process, game code execution, installed files, accounts or live tests.
The actual generated machine code is bound to sentinel consumers and the same
native queue, living-target tables and qualifier leaves as the old fixture.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/native'))
sys.path.insert(0, str(ROOT / 'tests'))
import hit_copy_damage_id_054_observer as producer
import hit_entity_resolver_owned as resolver_module
from hit_bridge_owned import OwnedBridge
from test_hit_copy_pending_observer_owned import (
    Fixture, address, relocated, sentinel_parameters, unchanged_snapshot)
from test_hit_copy_reflection_observer_owned import ReflectionFixture, replay_preserved
from test_hit_copy_living_target_owned import Health
from test_hit_copy_vehicle_source_owned import fixture_profile


def install(p, manifest, health):
    p.addresses['health_manager_global'] = health.global_address
    p.addresses['qualifier_types'] = p.addresses['qualifier']
    entries = {e['name']: e for e in manifest['entries']}
    for name in ('health_alive', 'qualifier_prior', 'qualifier'):
        e = entries[name]
        fn = p.b._procedure(relocated(e, p.addresses), ctypes.c_uint64,
                            unwind=bytes.fromhex(e['unwind_hex']),
                            executable_length=e['executable_length'])
        p.functions[name] = fn; p.addresses[name] = address(fn)
    for name, e in entries.items():
        if name in ('health_alive', 'qualifier_prior', 'qualifier') or name.startswith('demolition_'):
            continue
        if name not in ('contact_begin', 'reflection_writeback') and not any(r['address_key'] == 'qualifier' for r in e['relocations']):
            continue
        fn = p.b._procedure(relocated(e, p.addresses), ctypes.c_uint64,
                            unwind=bytes.fromhex(e['unwind_hex']),
                            executable_length=e['executable_length'])
        p.functions[name] = fn; p.addresses[name] = address(fn)


class DamageFixture(Fixture):
    def runner(self, actions):
        return damage_runner(self, super().runner, actions)


class DamageReflectionFixture(ReflectionFixture):
    def runner(self, actions, **options):
        return damage_runner(self, super().runner, actions, reflection=True, **options)


def damage_runner(p, parent, actions, reflection=False, **options):
    original = p.b._procedure
    needle = b'\x49\xbb' + struct.pack('<Q', p.addresses['contact_begin']) + b'\x41\xff\xd3'
    def bind(raw, *args, **kwargs):
        if 'contact_begin' in actions:
            if raw.count(needle) != actions.count('contact_begin'):
                raise AssertionError('Owned fixed contact_begin caller shape changed')
            # The historical fixture uses R14 as a convenience parent pointer.
            # The real caller instead supplies a 0xC8 projectile hit record.
            # This owned adaptation passes that actual ABI input without an
            # extra CALL/frame, then restores the fixture's parent convenience.
            before = b'\x49\xbe' + struct.pack('<Q', p.pool)
            after = b'' if reflection else bytes.fromhex('4c 8d b4 24 80 fb ff ff')
            if p.mutate_after_begin is not None:
                after = bytes.fromhex('41 c7 46 0c') + struct.pack('<I', p.mutate_after_begin) + after
            raw = raw.replace(needle, before + needle + after)
        return original(raw, *args, **kwargs)
    p.b._procedure = bind
    try:
        return parent(actions, **options)
    finally:
        p.b._procedure = original


def make_fixture(bridge, manifest, reflection=False):
    cls = DamageReflectionFixture if reflection else DamageFixture
    p = frozen_resolver_fixture(cls, bridge, fixture_profile(manifest))
    p.pool = bridge._allocate(200, executable=False)
    p.mutate_after_begin = None
    h = Health(bridge)
    install(p, manifest, h)
    return p, h


def frozen_resolver_fixture(cls, bridge, manifest):
    # The historical helper's dynamic catalog was pinned to 91 sources. This
    # fixture explicitly replays the immutable profile, including its 3 reviewed
    # tank sources, rather than allowing a newly expanded catalog to alter it.
    saved = resolver_module.catalog
    tables = manifest['data_tables']
    resolver_module.catalog = lambda: ([int(x, 16) for x in tables['enemy_types']],
                                       [int(x, 16) for x in tables['source_types']],
                                       {'source': 'frozen owned fixture profile'})
    try:
        return cls(bridge, manifest)
    finally:
        resolver_module.catalog = saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'docs/native-hit-damage-id-profile-v1.json',
                        help='Profile under test; default replays the immutable .54 producer')
    parser.add_argument('--catalog', type=Path, help='Also require exact whitelist equality to this reviewed catalog')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    historical_path = ROOT / 'docs/native-hit-damage-id-profile-v1.json'
    historical_bytes = historical_path.read_bytes()
    assert hashlib.sha256(historical_bytes).hexdigest() == '2c5abff2c8b8606d0c413cafe546fbd53c7ebcadd17aeafc35e22a6f342e7754'
    historical = json.loads(historical_bytes)
    manifest = json.loads(args.profile.read_text(encoding='utf8'))
    selected_ids = [int(value, 16) for value in manifest['data_tables']['damage_info_types']]
    assert manifest == producer.package(selected_ids), 'Profile must exactly reproduce from its own audited whitelist'
    if args.catalog:
        catalog = json.loads(args.catalog.read_text(encoding='utf8'))
        assert selected_ids == producer.audited_ids(catalog), 'Profile whitelist differs from the selected catalog'
    historical_ids = {int(value, 16) for value in historical['data_tables']['damage_info_types']}
    added_ids = sorted(set(selected_ids) - historical_ids)
    assert historical_ids <= set(selected_ids), 'An expanded profile may not discard historical audited IDs'
    assert manifest['abi'] == 1 and manifest['record_bytes'] == 96 and manifest['arena_capacity'] == 32
    assert len(manifest['data_tables']['source_types']) == 94
    assert manifest['damage_id_extension']['attribution_only_hit_count'] == 0
    base = json.loads(producer.BASE.read_text(encoding='utf8'))
    old = {e['name']: e for e in base['entries']}
    for e in manifest['entries']:
        if e['name'] == 'qualifier_prior':
            assert dict(e, name='qualifier') == old['qualifier']
        elif e['name'] not in ('contact_begin', 'reflection_writeback', 'qualifier'):
            assert e == old[e['name']], 'Unrelated native entry changed: ' + e['name']
    assert manifest['sites'] == base['sites']
    assert manifest['living_target_filter'] == base['living_target_filter']
    report = dict(status='RUNNING', game_access=False, game_code_executed=False,
                  installed_files_accessed=False, account_access=False,
                  legacy_profiles_unchanged=True, ABI=1, record_bytes=96, cases=[])
    actions = ('contact_begin', 'default_delta', 'normal_final', 'contact_end')
    for unknown in (False, True):
        with OwnedBridge() as bridge:
            p, h = make_fixture(bridge, manifest)
            contact_cases = [
                ('AC8_direct', 202, 0, 0, 5, 1, None),
                ('shared_fragments', 189, 0, 0, 5, 1, None),
                ('raw_ID_is_not_relabelled', 0xffffffff, 0, 0, 5, int(not unknown), None),
                ('zero_ID_is_not_known', 0, 0, 0, 5, int(not unknown), None),
                ('blocked_is_still_blocked', 202, 0, 0, 3, 1, None),
                ('same_ap_is_penetration', 202, 0, 0, 4, 1, None),
                ('other_peer', 202, 0, 1 << 32, 5, 0, None),
                ('zero_creditor', 202, 0, bridge.local_peer, 5, 0, None),
                ('corpse', 202, 2, 0, 5, 0, None),
                ('unmapped_ID', 4095, 0, 0, 5, int(not unknown), None),
                ('frozen_ID_before_pool_changes', 202, 0, 0, 5, 1, 189),
            ]
            # Every newly admitted ID is executed through the actual generated
            # Win64 gateway for both known-source and attribution-only inputs.
            # No Lua-only table lookup stands in for native admission.
            contact_cases.extend((f'new_audited_damage_{native_id}', native_id, 0, 0, 5, 1, None)
                                 for native_id in added_ids)
            for name, damage_id, life, peer_delta, ap, count, mutation in contact_cases:
                p.defaults(); h.reset(); h.put32(h.life, life)
                p.resolver.insert(1002, 0x4D1C334D294DFA97 if unknown else p.source, 1)
                ctypes.c_uint64.from_buffer(p.hit, 0x110).value = bridge.local_peer ^ peer_delta
                ctypes.c_uint32.from_address(p.pool + 12).value = damage_id
                p.floats[0] = ap; p.mutate_after_begin = mutation
                records, trace, _, raw = p.run(actions)
                assert len(records) == count, (unknown, name, len(records), trace)
                sentinel_parameters(p, raw, actions)
                unchanged_snapshot(raw, 512, default_delta=ap - 4)
                if records:
                    r = records[0]
                    assert r.projectile_generation == damage_id, (name, r.projectile_generation)
                    assert r.capture_flags & 512
                    assert bool(r.capture_flags & 1024) == unknown
                    assert r.native_branch == 1 and r.ap_delta == ap - 4
                    assert r.creditor == bridge.local_peer and r.target == 1001 and r.source == 1002
                report['cases'].append(dict(source='unmapped_avatar' if unknown else 'legacy_known',
                                            name=name, records=len(records), actual_damage_id=damage_id))
            # A second begin must clear/re-capture the ID, not keep the old
            # generation word. Its pending first row commits before the reset.
            p.defaults(); h.reset(); p.resolver.insert(1002, p.source, 1)
            ctypes.c_uint32.from_address(p.pool + 12).value = 202
            p.mutate_after_begin = 189
            pair = ('contact_begin', 'default_delta', 'normal_final',
                    'contact_begin', 'default_delta', 'normal_final', 'contact_end')
            records, _, _, _ = p.run(pair)
            assert [r.projectile_generation for r in records] == [202, 189]
            report['cases'].append(dict(name='next_begin_recaptures_current_ID', source=unknown, IDs=[202, 189]))
    for unknown in (False, True):
        with OwnedBridge() as bridge:
            p, h = make_fixture(bridge, manifest, reflection=True)
            for normal_first in (False, True):
                for name, damage_id, life, peer_delta, wanted in [
                    ('reflection_keeps_same_contact_ID', 202, 0, 0, 1),
                    ('reflection_unknown_ID', 4095, 0, 0, int(not unknown)),
                    ('reflection_other_peer', 202, 0, 1 << 32, 0),
                    ('reflection_corpse', 202, 2, 0, 0),
                ]:
                    p.reflection_defaults(); h.reset(); h.put32(h.life, life)
                    p.resolver.insert(1002, 0x4D1C334D294DFA97 if unknown else p.source, 1)
                    ctypes.c_uint64.from_buffer(p.hit, 0x110).value = bridge.local_peer ^ peer_delta
                    ctypes.c_uint32.from_address(p.pool + 12).value = damage_id
                    sequence = ('contact_begin',) + (('default_delta', 'normal_final') if normal_first else ()) + ('reflection_writeback', 'contact_end')
                    runner = p.runner(sequence); runner(ctypes.addressof(p.config))
                    raw = ctypes.string_at(p.output, 4096); records = bridge.drain()
                    assert len(records) == wanted, ('reflection', unknown, normal_first, name, len(records))
                    if records:
                        r = records[0]
                        assert r.native_branch == 2 and r.projectile_generation == damage_id and r.capture_flags & 512
                        assert bool(r.capture_flags & 1024) == unknown
                    replay_preserved(p, raw)
                    report['cases'].append(dict(name=name, unknown=unknown,
                                                normal_first=normal_first, records=len(records)))
    # Historical producer stays byte-identical and must not claim validity.
    with OwnedBridge() as bridge:
        p = frozen_resolver_fixture(Fixture, bridge, fixture_profile(base))
        from test_hit_copy_living_target_owned import install_extension
        h = Health(bridge); install_extension(p, base, h)
        records, _, _, _ = p.run(actions)
        assert len(records) == 1 and records[0].projectile_generation == 0 and not records[0].capture_flags & 512
    report['cases'].append(dict(name='old_producer_unchanged_without_ID_flag', status='PASS'))
    report['status'] = 'PASS'
    report['profile_sha256'] = hashlib.sha256(args.profile.read_bytes()).hexdigest()
    report['damage_info_count'] = len(selected_ids)
    report['added_damage_info_ids_executed'] = added_ids
    report['historical_profile_sha256'] = hashlib.sha256(historical_bytes).hexdigest()
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('PASS concrete native DamageInfo capture: ' + str(len(report['cases'])) + ' owned cases; ABI/transport unchanged')


if __name__ == '__main__':
    main()
