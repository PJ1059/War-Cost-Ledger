"""One owned normal-result guard group, importing only frozen fixture helpers.

No old test main/group runs, Game lookup, remote memory access or Game code.
The guard's true-tail replay must preserve normal/AP pending bytes; only the
unchanged commit leaf may later publish the normal default-armour result.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/native'))
GENERATOR_SHA = 'bd7bbed22001e43711b0d66b5990867f21a7cfa760820844fc84df860bb6999e'
PROFILE_SHA = '3d7f0f02af32b05e46495a1fb192773ad866e2087622ab86e3d5f5ee056e5f35'
FIXTURE_SHA = 'f42d2f0f91d448f1b2df7227a79dd3f9528560135e09b3e6ced1992084ea90bc'


def main():
    for relative, wanted in [
        ('tools/native/hit_copy_normal_result_guard.py', GENERATOR_SHA),
        ('tools/native/test_hit_copy_tail_diagnostic_owned.py', FIXTURE_SHA),
        ('dist/hit-normal-result-guard-prepared-20261013-v1/profile.json', PROFILE_SHA),
    ]:
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != wanted:
            raise AssertionError('Frozen owned guard input changed: ' + relative)
    from hit_bridge_owned import OwnedBridge, Record
    from test_hit_copy_tail_diagnostic_owned import (
        Fixture, head, region, snapshot_with_pending, invoke, expect, record_dict)
    import hit_copy_normal_result_guard as producer
    manifest = producer.package()
    original = producer.D.package()
    report = dict(status='RUNNING', group='one_owned_normal_result_guard_group',
                  pid=os.getpid(), generator_sha256=GENERATOR_SHA,
                  profile_sha256=PROFILE_SHA, imported_fixture_sha256=FIXTURE_SHA,
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  Game_access=False, Game_code_executed=False,
                  external_process_enumeration=False, old_groups_executed=False,
                  gameplay_or_exception_safety_proven=False, cases=[])
    started = time.perf_counter()
    stage = 'profile_template_conservation'
    try:
        expect(manifest['revision'] == 'copy_pending_normal_result_guard_v1'
               and len(manifest['entries']) == 20 and len(manifest['sites']) == 7,
               'Guard interface is not the fixed twenty-entry seven-site profile')
        expect(manifest['sites'] == original['sites']
               and manifest['tail_diagnostic'] == original['tail_diagnostic']
               and manifest['data_tables'] == original['data_tables'],
               'Guard changed a site, diagnostic layout or qualification catalog')
        entries = {e['name']: e for e in manifest['entries']}
        old_entries = {e['name']: e for e in original['entries']}
        unchanged = [name for name in entries if name != 'physical_success']
        expect(all(entries[name] == old_entries[name] for name in unchanged),
               'Guard changed an entry other than the physical true-tail gateway')
        guarded = entries['physical_success']
        code = bytes.fromhex(guarded['code_hex'])
        expect(guarded['unwind_hex'] == old_entries['physical_success']['unwind_hex']
               and guarded['frame_allocation'] == old_entries['physical_success']['frame_allocation']
               and guarded['frame_register'] == 'RBP'
               and code[:14] == bytes.fromhex('555657488da424e0feffff4889e5')
               and code[-11:] == bytes.fromhex('488da5200100005f5e5dc3'),
               'Guard changed the original prolog, unwind frame or canonical epilog')
        expect({r['address_key'] for r in guarded['relocations']}
               == {'arena', 'tail_diagnostic'},
               'Guard retains an ordinary lookup, snapshot or publisher dependency')
        expect(manifest['ricochet_producer_verified'] is False
               and manifest['ordinary_physical_FIFO_publish'] is False
               and manifest['count_contract']['physical_success_overrides_normal'] is False,
               'Guard still certifies physical success as an ordinary ricochet producer')
        report.update(unchanged_entry_names=unchanged,
                      unchanged_site_and_diagnostic_contract=True,
                      canonical_prolog_epilog_and_UW_preserved=True,
                      physical_success_bytes=len(code))

        stage = 'owned_initialization'
        with OwnedBridge() as b:
            p = Fixture(b, manifest)
            for e in manifest['entries']:
                for rel in e['relocations']:
                    target = p.addresses[rel['address_key']] + rel['addend']
                    expect(any(base <= target < base + size
                               for base, size in b._allocation_sizes.items()),
                           f"Relocation escaped owned allocation: {e['name']}:{rel['address_key']}")
            report['all_native_targets_owned'] = True
            p.snapshots = [snapshot_with_pending(p, 0, 3584),
                           snapshot_with_pending(p, 512, 3760)]
            commit = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p,
                                       ctypes.c_void_p)(p.addresses['commit'])
            queue_bytes = b._allocation_sizes[b.base]
            cases = [
                ('begun_stays_begun', 5, ('contact_begin', 'physical_success'), 1, None),
                ('blocked_normal_survives_true_tail', 3,
                 ('contact_begin', 'default_delta', 'normal_final', 'physical_success'), 3, 'blocked'),
                ('equal_AP_normal_survives_true_tail', 4,
                 ('contact_begin', 'default_delta', 'normal_final', 'physical_success'), 3, 'penetration'),
                ('high_AP_normal_survives_true_tail', 5,
                 ('contact_begin', 'default_delta', 'normal_final', 'physical_success'), 3, 'full_penetration'),
                ('AP_stays_AP_then_normal_commits', 5,
                 ('contact_begin', 'default_delta', 'physical_success', 'normal_final'), 2, 'full_penetration'),
            ]
            for index, (stage, ap, actions, phase, expected_result) in enumerate(cases):
                p.defaults()
                p.floats[0] = ap
                caller = p.runner(actions)
                seed = b.record(target=1001, source=1002,
                                contact_ordinal=0x7000 + index,
                                native_branch=1, capture_flags=0x1FF, ap_delta=1)
                expect(b.publish(seed) == 1, 'Owned ordinary seed was not accepted')
                queue = ctypes.string_at(b.base, queue_bytes)
                raw = invoke(p, caller, alternative=False)
                before, after = raw[3584:3720], raw[3760:3896]
                expect(before == after,
                       stage + ': true-tail diagnostic changed ordinary raw/metadata/frame bytes')
                expect(struct.unpack_from('<I', after, 100)[0] == phase,
                       stage + ': true-tail changed pending phase')
                expect(ctypes.string_at(b.base, queue_bytes) == queue,
                       stage + ': true-tail changed ordinary FIFO before commit')
                expect(head(p) == dict(alt=0, true=1, claimed=1, mask=1, epoch=b.epoch),
                       stage + ': bounded true diagnostic sample was not preserved')
                sample = Record.from_buffer_copy(region(p)[1][0])
                expect(sample.native_branch == 4 and sample.projectile_generation == phase
                       and sample.capture_flags == 0x14B and sample.target_kind == 1,
                       stage + ': diagnostic tag/phase/qualification changed')
                case = dict(name=stage, status='CHECKING', pending_phase=phase,
                            pending_before_hex=before.hex(), pending_after_hex=after.hex(),
                            GP_XMM_MXCSR_and_original_5B_replay_preserved=True,
                            ordinary_FIFO_before_commit_byte_preserved=True,
                            diagnostic_sample=record_dict(sample))
                report['cases'].append(case)
                diag = region(p)
                committed = int(commit(p.arena.address, p.row))
                expect(region(p) == diag, stage + ': normal commit changed diagnostic slots')
                records = b.drain()
                expect(records and records[0].contact_ordinal == 0x7000 + index,
                       stage + ': original seed was lost or reordered')
                if expected_result is None:
                    expect(committed == 0 and len(records) == 1,
                           'Unfinished begun contact was fabricated into an ordinary hit')
                else:
                    expect(committed == 1 and len(records) == 2,
                           stage + ': original normal commit failed to produce one record')
                    r = records[1]
                    expect(r.native_branch == 1 and r.capture_flags == 0x1FF
                           and r.selected_ap == ap and r.armour == 4
                           and r.ap_delta == ap - 4 and r.effect_flags == 0
                           and r.creditor == b.local_peer and r.epoch == b.epoch
                           and r.target == 1001 and r.source == 1002,
                           stage + ': normal AP tuple was replaced or changed')
                    # Evidence for the existing decoder's three delta branches;
                    # this test does not execute the Lua decoder or Game logic.
                    result = ('blocked' if r.ap_delta < 0 else
                              'penetration' if r.ap_delta < 1 else 'full_penetration')
                    expect(result == expected_result, stage + ': wrong preserved AP result')
                    case.update(expected_decoder_result=result,
                                ordinary_record=record_dict(r))
                    expect(int(commit(p.arena.address, p.row)) == 0 and not b.drain(),
                           stage + ': spent normal contact committed twice')
                expect(all(r.native_branch != 2 for r in records),
                       stage + ': physical gateway emitted an ordinary branch 2 record')
                case['status'] = 'PASS'

            stage = 'diagnostic_cap_preserves_ordinary_FIFO'
            p.defaults()
            caller = p.runner(('contact_begin', 'physical_success'))
            seed = b.record(target=1001, source=1002, contact_ordinal=0x7FFF,
                            native_branch=1, capture_flags=0x1FF, ap_delta=1)
            expect(b.publish(seed) == 1, 'Bounded diagnostic seed was not accepted')
            queue = ctypes.string_at(b.base, queue_bytes)
            first_unclaimed = ctypes.string_at(p.arena.rows + 16 * 640 + 256, 96)
            full_slots = None
            for index in range(17):
                raw = invoke(p, caller, alternative=False)
                expect(raw[3584:3720] == raw[3760:3896],
                       'Repeated true-tail diagnostic changed begun pending bytes')
                expect(ctypes.string_at(b.base, queue_bytes) == queue,
                       'Repeated true-tail diagnostic changed ordinary FIFO')
                expected_count = min(index + 1, 16)
                expect(head(p) == dict(alt=0, true=index + 1, claimed=expected_count,
                                       mask=(1 << expected_count) - 1, epoch=b.epoch),
                       'True diagnostic lost trigger count or escaped sixteen slots')
                if index == 15:
                    full_slots = region(p)[1]
                elif index == 16:
                    expect(region(p)[1] == full_slots,
                           'Seventeenth true diagnostic overwrote a committed slot')
            expect(ctypes.string_at(p.arena.rows + 16 * 640 + 256, 96) == first_unclaimed,
                   'True diagnostic wrote outside the first sixteen row slots')
            samples = [Record.from_buffer_copy(raw) for raw in region(p)[1]]
            expect([r.sequence for r in samples] == list(range(1, 17))
                   and all(r.native_branch == 4 and r.projectile_generation == 1
                           for r in samples),
                   'Bounded diagnostic records changed their private tag/phase contract')
            records = b.drain()
            expect(len(records) == 1 and records[0].contact_ordinal == 0x7FFF,
                   'Diagnostic triggers entered the ordinary consumer')
            report.update(status='PASS', final_head=head(p),
                          normal_commit_record_count=4,
                          ordinary_branch_2_records=0,
                          diagnostic_cap_and_FIFO_conservation_verified=True,
                          first_unclaimed_slot_unchanged=True,
                          Lua_decoder_executed=False,
                          accepted_ordinary_records=b.stats()['accepted'])
        report.update(owned_allocations_released=b.closed,
                      released_allocation_count=len(b._allocations))
    except Exception as error:
        report.update(status='FAIL', first_failure_stage=stage,
                      first_failure=f'{type(error).__name__}: {error}')
    report['elapsed_ms'] = (time.perf_counter() - started) * 1000
    destination = ROOT / 'dist/hit-normal-result-guard-owned-20261013-v1'
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / 'report.json'
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                   encoding='utf8')
    print(json.dumps(dict(status=report['status'], report=str(out),
                         first_failure=report.get('first_failure')), ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
