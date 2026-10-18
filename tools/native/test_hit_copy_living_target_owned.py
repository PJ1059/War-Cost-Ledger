"""Replay living/corpse hit qualification on this Python process's own pages.

No process enumeration, game-memory read/write, captured game-code execution,
installation or real account access. Existing frozen producer fixtures supply
the real ABI gateway/queue; only the new qualifier and Health tables are added.
"""
from __future__ import annotations
import argparse
import copy
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/native'))
sys.path.insert(0, str(ROOT / 'tests'))
import hit_copy_living_target_observer as producer
from hit_bridge_owned import OwnedBridge, Record
from test_hit_copy_pending_observer_owned import (
    Fixture, address, relocated, sentinel_code, sentinel_parameters)
from test_hit_copy_reflection_observer_owned import (
    ReflectionFixture, replay_preserved, REFLECTION_SITE)


class Health:
    def __init__(self, bridge):
        self.b = bridge
        self.manager = bridge._allocate(0x1060, executable=False)
        self.global_address = bridge._allocate(8, executable=False)
        self.buckets = bridge._allocate(16 * 8, executable=False)
        self.descriptors = bridge._allocate(2 * 8, executable=False)
        self.descriptor = bridge._allocate(24, executable=False)
        self.records = bridge._allocate(2 * 440, executable=False)
        self.reset()

    def put32(self, at, value):
        ctypes.c_uint32.from_address(at).value = value

    def put64(self, at, value):
        ctypes.c_uint64.from_address(at).value = value

    @property
    def life(self):
        return self.records + 412

    def reset(self):
        ctypes.memset(self.manager, 0, 0x1060)
        ctypes.memset(self.records, 0, 2 * 440)
        for index in range(16):
            ctypes.memmove(self.buckets + index * 8, struct.pack('<II', 0xffffffff, 0xffffffff), 8)
        self.put64(self.global_address, self.manager)
        for at, value in [(0x1010, 2), (0x1020, 1), (0x1038, 16),
                          (0x103c, 0xffffffff), (0x1040, 3)]:
            self.put32(self.manager + at, value)
        for at, value in [(0x1030, self.buckets), (0x1048, self.descriptors),
                          (0x1058, self.records)]:
            self.put64(self.manager + at, value)
        self.put64(self.descriptors, self.descriptor)
        self.put32(self.descriptor + 8, 1001)
        self.slot = (1001 * 3) & 15
        ctypes.memmove(self.buckets + self.slot * 8, struct.pack('<II', 1001, 0), 8)


def install_extension(p, manifest, health):
    """Bind new entries after the frozen fixture's original leaves exist."""
    p.addresses['health_manager_global'] = health.global_address
    p.addresses['qualifier_types'] = p.addresses['qualifier']
    entries = {entry['name']: entry for entry in manifest['entries']}
    for name in ('health_alive', 'qualifier'):
        entry = entries[name]
        fn = p.b._procedure(relocated(entry, p.addresses), ctypes.c_uint64,
                            unwind=bytes.fromhex(entry['unwind_hex']))
        p.functions[name] = fn
        p.addresses[name] = address(fn)
    # All original contact gateways retain their exact bytes/unwind. Rebind
    # only their existing qualifier call literal to the new owned wrapper.
    for name, entry in entries.items():
        if name == 'qualifier' or not any(r['address_key'] == 'qualifier' for r in entry['relocations']):
            continue
        fn = p.b._procedure(relocated(entry, p.addresses), ctypes.c_uint64,
                            unwind=bytes.fromhex(entry['unwind_hex']),
                            executable_length=entry['executable_length'])
        p.functions[name] = fn
        p.addresses[name] = address(fn)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    manifest = producer.package()
    base = json.loads(producer.BASE.read_text(encoding='utf8'))
    expected = {entry['name']: entry for entry in base['entries']}
    actual = {entry['name']: entry for entry in manifest['entries']}
    for name, entry in expected.items():
        mapped = dict(actual['qualifier_types'], name='qualifier') if name == 'qualifier' else actual[name]
        assert mapped == entry, 'Existing entry changed: ' + name
    assert manifest['sites'] == base['sites']
    assert manifest['count_contract']['commit_does_not_recheck_target_life']
    assert len(actual) == 26
    report = dict(status='RUNNING', game_access=False, game_code_executed=False,
                  external_process_enumeration=False, real_account_access=False,
                  original_gateways_and_commit_byte_identical=True, cases=[])
    # The old fixture executes only owned sentinels and simple declared leaves.
    # Captured demolition dispatch is intentionally excluded from this replay.
    fixture_manifest = copy.deepcopy(base)
    fixture_manifest['entries'] = [entry for entry in fixture_manifest['entries']
                                   if not entry['name'].startswith('demolition_')]
    try:
        with OwnedBridge() as bridge:
            p = Fixture(bridge, fixture_manifest)
            h = Health(bridge)
            install_extension(p, manifest, h)
            alive = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)(p.addresses['health_alive'])
            qualifier = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)(p.addresses['qualifier'])
            leaf_cases = [
                ('life_zero', lambda: h.put32(h.life, 0), 1),
                ('life_one', lambda: h.put32(h.life, 1), 1),
                ('corpse_life_two', lambda: h.put32(h.life, 2), 0),
                ('corpse_life_three', lambda: h.put32(h.life, 3), 0),
                ('invalid_life', lambda: h.put32(h.life, 0xffffffff), 0),
                ('unknown_entity', lambda: h.put32(h.buckets + h.slot * 8, 9999), 0),
                ('reused_descriptor', lambda: h.put32(h.descriptor + 8, 9999), 0),
                ('retired_health_index', lambda: h.put32(h.manager + 0x1020, 0), 0),
                ('invalid_record_capacity', lambda: h.put32(h.manager + 0x1010, 4097), 0),
                ('invalid_hash_capacity', lambda: h.put32(h.manager + 0x1038, 3), 0),
                ('missing_descriptor_array', lambda: h.put64(h.manager + 0x1048, 0), 0),
                ('missing_record_array', lambda: h.put64(h.manager + 0x1058, 0), 0),
                ('invalid_index', lambda: h.put32(h.buckets + h.slot * 8 + 4, 1), 0),
            ]
            for name, arrange, wanted in leaf_cases:
                h.reset(); arrange()
                assert alive(h.manager, 1001) == wanted, name
                record = bridge.record(target=1001, source=1002, capture_flags=0xBF)
                flags = qualifier(p.resolver.manager, ctypes.addressof(record))
                assert bool(flags & 0x40) == bool(wanted), name + ': shared normal/reflection qualifier'
                assert record.target_kind == wanted, name + ': target kind'
                assert flags & 0x100, name + ': source proof was changed'
                report['cases'].append(dict(name=name, result=wanted, status='PASS'))
            for depth in (7, 8):
                h.reset()
                for index in range(16):
                    ctypes.memmove(h.buckets + index * 8, struct.pack('<II', 2000 + index, 0), 8)
                ctypes.memmove(h.buckets + ((h.slot + depth) & 15) * 8, struct.pack('<II', 1001, 0), 8)
                assert alive(h.manager, 1001) == (1 if depth == 7 else 0)
                report['cases'].append(dict(name='bounded_hash_probe_' + str(depth + 1), status='PASS'))
            h.reset()
            assert alive(0, 1001) == 0 and alive(h.manager, 0) == 0 and alive(h.manager, 0xffffffff) == 0
            actions = ('contact_begin', 'default_delta', 'normal_final', 'contact_end')
            for life, ap in [(0, 3), (0, 4), (1, 5), (2, 5), (3, 3)]:
                p.defaults(); h.reset(); h.put32(h.life, life); p.floats[0] = ap
                records, trace, flags, raw = p.run(actions)
                assert len(records) == (1 if life < 2 else 0), (life, ap, trace)
                assert trace == [0, 0, 0, 1 if life < 2 else 0]
                sentinel_parameters(p, raw, actions)
                assert ctypes.c_uint32.from_address(p.output + 128 + 0x60).value == 1
                if records:
                    assert records[0].ap_delta == ap - 4 and records[0].capture_flags == 0x1ff
                report['cases'].append(dict(name=f'contact_life_{life}_AP_{ap}', status='PASS',
                                           accepted=len(records), original_consumer_called_once=True))
            # A real gateway freezes life BEFORE calling this owned original.
            # The sentinel then kills/removes the target before end() commits.
            normal_entry = actual['normal_final']
            original_normal = p.addresses['original_normal_final']
            for name, destination, value, opcode in [
                ('killing_hit', h.life, 2, 'c7 00 02 00 00 00'),
                ('killing_hit_removed_descriptor', h.descriptors, 0, '48 c7 00 00 00 00 00')]:
                p.defaults(); h.reset()
                code = sentinel_code()[:-11] + bytes.fromhex('48 b8') + struct.pack('<Q', destination) + bytes.fromhex(opcode) + sentinel_code()[-11:]
                original = bridge._procedure(code, ctypes.c_uint64, unwind=bytes.fromhex('01000000'))
                p.addresses['original_normal_final'] = address(original)
                gateway = bridge._procedure(relocated(normal_entry, p.addresses), ctypes.c_uint64,
                    unwind=bytes.fromhex(normal_entry['unwind_hex']), executable_length=normal_entry['executable_length'])
                p.addresses['normal_final'] = address(gateway)
                records, trace, flags, raw = p.run(actions)
                assert len(records) == 1 and trace == [0, 0, 0, 1], name
                assert records[0].capture_flags == 0x1ff and records[0].ap_delta == 1
                sentinel_parameters(p, raw, actions)
                # A second fresh contact with the now-dead/removed target is rejected.
                p.arena.reset_after_owned_calls_return()
                records, trace, _, _ = p.run(actions)
                assert not records, name + ': later corpse contact counted'
                report['cases'].append(dict(name=name, status='PASS', first_hit=1, later_corpse_hit=0))
            p.addresses['original_normal_final'] = original_normal
            # Exercise the actual reflection gateway in its proven caller
            # frame as well, including a normal killing hit that dies before
            # the later reflection branch performs its fresh qualification.
            p = ReflectionFixture(bridge, fixture_manifest)
            h = Health(bridge)
            install_extension(p, manifest, h)
            reflection_actions = ('contact_begin', REFLECTION_SITE, 'contact_end')
            for life in (0, 1, 2, 3):
                p.reflection_defaults(); h.reset(); h.put32(h.life, life)
                runner = p.runner(reflection_actions)
                runner(ctypes.addressof(p.config))
                raw = ctypes.string_at(p.output, 4096)
                replay_preserved(p, raw)
                records = bridge.drain()
                assert len(records) == (1 if life < 2 else 0)
                if records:
                    assert records[0].native_branch == 2
                report['cases'].append(dict(name=f'fresh_reflection_life_{life}', status='PASS',
                    accepted=len(records), GP_XMM_MXCSR_preserved=True))
            for name, destination, opcode in [
                ('normal_killing_hit_late_reflection', h.life, 'c7 00 02 00 00 00'),
                ('normal_removed_descriptor_late_reflection', h.descriptors, '48 c7 00 00 00 00 00')]:
                p.reflection_defaults(); h.reset()
                code = sentinel_code()[:-11] + bytes.fromhex('48 b8') + struct.pack('<Q', destination) + bytes.fromhex(opcode) + sentinel_code()[-11:]
                original = bridge._procedure(code, ctypes.c_uint64, unwind=bytes.fromhex('01000000'))
                p.addresses['original_normal_final'] = address(original)
                gateway = bridge._procedure(relocated(normal_entry, p.addresses), ctypes.c_uint64,
                    unwind=bytes.fromhex(normal_entry['unwind_hex']), executable_length=normal_entry['executable_length'])
                p.addresses['normal_final'] = address(gateway)
                runner = p.runner(('contact_begin', 'default_delta', 'normal_final', REFLECTION_SITE, 'contact_end'))
                runner(ctypes.addressof(p.config))
                raw = ctypes.string_at(p.output, 4096)
                replay_preserved(p, raw)
                assert raw[2816:2960] == raw[3072:3216], name + ': late failed reflection changed frozen normal'
                records = bridge.drain()
                assert len(records) == 1 and records[0].native_branch == 1
                report['cases'].append(dict(name=name, status='PASS', accepted=1, branch=1,
                    frozen_normal_preserved=True, GP_XMM_MXCSR_preserved=True))
            report.update(status='PASS', owned_allocations=len(bridge._allocations))
        report['owned_allocations_released'] = bridge.closed
    except Exception as error:
        report.update(status='FAIL', first_failure=f'{type(error).__name__}: {error}')
    report['profile_sha256'] = hashlib.sha256(json.dumps(manifest, indent=2).encode() + b'\n').hexdigest()
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=report['status'], cases=len(report['cases']),
                         first_failure=report.get('first_failure'), report=str((output / 'report.json').resolve()))))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
