"""One new reflection observer group, on this process's owned code/data only.

The parent frame follows the captured contact prolog: RBP = parent RSP + 100h.
No Game code is executed and no previous native group/main is called.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/native'))
from hit_bridge_owned import OwnedBridge, Record, _Code
from hit_physical_profile_owned import snapshot_code
from test_hit_copy_pending_observer_owned import (
    Fixture, address, expect, record_dict, COMMON_RCX, RETURN, STACK_VALUES)

GENERATOR_SHA = '4dc86b00a6a3611aa444c5a4005e825fdd66e0f43fee34da57bcb56253176193'
PROFILE_SHA = '0facfa5122ee9dc334b31b4eebd48fc87dd6248f06484e728c85b5e064ef83ca'
FIXTURE_SHA = '5dbc869ce4f3bda135a4279e5c57aa279b5bf53e2b73db5b838aba4db6029aa3'
FRAME_BYTES = 0x2A08
CALLER_RBP = 0x100
HIT_AT = CALLER_RBP + 0x580
DAMAGE_AT = CALLER_RBP + 0x3E0
SAVED_XMM_AT = 0x2600
SAVED_MXCSR_AT = 0x26A0
REFLECTION_SITE = 'reflection_writeback'


def stack_xmm(c, register, offset, *, store):
    c.emit(('44 ' if register >= 8 else '') + ('0f 29 ' if store else '0f 28 ')
           + bytes([0x84 | ((register & 7) << 3), 0x24]).hex(' ') + ' '
           + struct.pack('<I', offset).hex(' '))


def snapshot_leaf(p, displacement, checkpoint):
    c = _Code(); snapshot_code(c, displacement)
    c.emit('48 b8 ' + struct.pack('<Q', p.row).hex(' ')
           + ' 49 ba ' + struct.pack('<Q', p.output + checkpoint).hex(' '))
    for source, destination in [(i * 8, i * 8) for i in range(16)] + [(624, 128), (632, 136)]:
        c.emit('4c 8b 98 ' + struct.pack('<I', source).hex(' ')
               + ' 4d 89 9a ' + struct.pack('<I', destination).hex(' '))
    for register, opcode in [(10, '4c 8b 91'), (11, '4c 8b 99'), (0, '48 8b 81')]:
        c.emit(opcode + ' ' + struct.pack('<I', displacement + register * 8).hex(' '))
    c.emit('c3')
    return p.b._procedure(c.finish(), None, unwind=bytes.fromhex('01000000'))


class ReflectionFixture(Fixture):
    def __init__(self, bridge, manifest):
        super().__init__(bridge, manifest)
        self.context = bridge._allocate(32768, executable=False)
        self.slot = 3
        self.flight = self.context + 0x3040 + self.slot * 0x70
        self.xmm_state = bridge._allocate(256, executable=False)
        self.config = (ctypes.c_uint64 * 11)(*self.config, self.context,
                                            self.xmm_state, self.slot)
        self.snapshots = [snapshot_leaf(self, 0, 2816), snapshot_leaf(self, 512, 3072)]
        self.reflection_defaults()

    def reflection_defaults(self):
        self.defaults()
        ctypes.memmove(self.flight, struct.pack('<4f', 4, 7, 9, 11), 16)
        bits = [0x3F000000 + i * 0x1000 for i in range(64)]
        bits[32] = struct.unpack('<I', struct.pack('<f', 5))[0]
        ctypes.memmove(self.xmm_state, struct.pack('<64I', *bits), 256)

    def runner(self, actions, *, frame_offset=0, wrong_slot=False):
        """One stable caller frame; mutations are inline MOVs between sites."""
        expect(len(actions) <= 10, 'Reflection caller exceeds ten owned actions')
        expect(frame_offset in (0, 16), 'Only the fixed wrong-parent deviation is allowed')
        c = _Code(); unwind_codes = []
        for register, opcode in [(3, '53'), (5, '55'), (6, '56'), (7, '57'),
                                 (12, '41 54'), (13, '41 55'),
                                 (14, '41 56'), (15, '41 57')]:
            c.emit(opcode); unwind_codes.append(bytes([len(c.code), register << 4]))
        for allocation in (0x1000, 0x1000, 0xA08):
            c.emit('48 81 ec ' + struct.pack('<I', allocation).hex(' '))
            unwind_codes.append(bytes([len(c.code), 1]) + struct.pack('<H', allocation // 8))
            c.emit('84 04 24')  # Touch each newly owned stack page, no Game helper.
        for register in range(6, 16):
            offset = SAVED_XMM_AT + (register - 6) * 16
            stack_xmm(c, register, offset, store=True)
            unwind_codes.append(bytes([len(c.code), (register << 4) | 8])
                                + struct.pack('<H', offset // 16))
        prolog_size = len(c.code)
        expect(prolog_size < 256, 'Owned caller prolog does not fit UW byte offsets')
        codes = b''.join(reversed(unwind_codes))
        slots = len(codes) // 2
        unwind = bytes([1, prolog_size, slots, 0]) + codes
        if slots & 1:
            unwind += bytes(2)
        c.emit('0f ae 9c 24 ' + struct.pack('<I', SAVED_MXCSR_AT).hex(' '))
        c.emit('49 89 cc 48 8d ac 24 00 01 00 00 '
               '48 8d 9c 24 ' + struct.pack('<I', HIT_AT).hex(' '))
        # Copy fixture inputs into their real contact-frame locations.
        c.emit('49 8b 74 24 08 48 89 df b9 23 00 00 00 fc f3 48 a5')
        c.emit('49 8b 74 24 10 48 8d bc 24 '
               + struct.pack('<I', DAMAGE_AT).hex(' ')
               + ' b9 09 00 00 00 f3 a5')
        c.emit('4d 8b 7c 24 40 49 8b 44 24 50 48 89 45 a8')
        c.emit('48 b8 ' + struct.pack('<Q', COMMON_RCX).hex(' ')
               + ' 48 89 85 c0 24 00 00')
        for i, value in enumerate(STACK_VALUES):
            c.emit('48 b8 ' + struct.pack('<Q', value).hex(' ')
                   + ' 48 89 84 24 ' + struct.pack('<I', 0x20 + i * 8).hex(' '))
        for i, action in enumerate(actions):
            if isinstance(action, tuple):
                _, offset, width, value = action
                expect(action[0] == 'mutate' and width in (4, 8)
                       and 0 <= offset <= 0x110,
                       'Only a fixed HitInfo MOV mutation is allowed')
                if width == 8:
                    c.emit('48 b8 ' + struct.pack('<Q', value).hex(' ')
                           + ' 48 89 83 ' + struct.pack('<I', offset).hex(' '))
                else:
                    c.emit('c7 83 ' + struct.pack('<I', offset).hex(' ')
                           + ' ' + struct.pack('<I', value).hex(' '))
                continue
            if action in ('contact_begin', 'normal_final', 'custom_curve'):
                area = {'contact_begin': 0, 'normal_final': 128, 'custom_curve': 256}[action]
                c.emit('49 8b 0c 24 48 8d 89 ' + struct.pack('<I', area).hex(' '))
                if action == 'normal_final':
                    c.emit('48 8d 94 24 ' + struct.pack('<I', DAMAGE_AT).hex(' ')
                           + ' 49 89 d8 49 8b 44 24 20')
                else:
                    c.emit('48 89 da 49 b8 88 99 aa bb cc dd ee ff')
                c.emit('49 b9 11 22 33 44 55 66 77 88')
            elif action == 'default_delta':
                c.emit('4d 8b 54 24 18 f3 41 0f 10 02 f3 45 0f 10 12 '
                       'f3 45 0f 10 4a 04 4d 8b 54 24 30 41 0f ae 12')
            elif action == REFLECTION_SITE:
                c.emit('c6 85 fc 03 00 00 00 '
                       '48 8b 45 a8 48 6b c0 70 '
                       '49 8d bc 07 40 30 00 00 4d 8b 54 24 48')
                for register in range(16):
                    c.emit(('45 ' if register >= 8 else '41 ') + '0f 10 '
                           + bytes([0x82 | ((register & 7) << 3)]).hex()
                           + ' ' + struct.pack('<I', register * 16).hex(' '))
                c.emit('4d 8b 54 24 30 41 0f ae 12 '
                       '49 8b 0c 24 48 8d 89 00 06 00 00')
                if wrong_slot:
                    # RDI still points at slot3; only the saved current index differs.
                    c.emit('48 c7 45 a8 04 00 00 00')
                if frame_offset:
                    # Original RBP/HI/DP remain valid; only actual parent RSP differs.
                    c.emit('48 8d 64 24 f0')
                c.emit('49 bb ' + struct.pack('<Q', self.addresses[action]).hex(' '))
                c.emit('ff 15 02 00 00 00 eb 08 '
                       + struct.pack('<Q', address(self.snapshots[0])).hex(' '))
            elif action == 'contact_end':
                pass
            else:
                raise AssertionError('Unknown owned reflection action: ' + action)
            c.emit('49 bb ' + struct.pack('<Q', self.addresses[action]).hex(' ')
                   + ' 41 ff d3')
            if action == REFLECTION_SITE:
                c.emit('ff 15 02 00 00 00 eb 08 '
                       + struct.pack('<Q', address(self.snapshots[1])).hex(' '))
                if frame_offset:
                    c.emit('48 8d 64 24 10')
                if wrong_slot:
                    c.emit('48 c7 45 a8 03 00 00 00')
            elif action == 'contact_end':
                c.emit('49 89 4c 24 38')
            else:
                c.emit('49 8b 14 24 48 89 82 '
                       + struct.pack('<I', 0x180 + i * 8).hex(' '))
            c.emit('48 b8 ' + struct.pack('<Q', self.b.base).hex(' ')
                   + ' 8b 40 1c 49 8b 14 24 89 82 '
                   + struct.pack('<I', 0x1C0 + i * 4).hex(' '))
        c.emit('0f ae 94 24 ' + struct.pack('<I', SAVED_MXCSR_AT).hex(' '))
        for register in range(6, 16):
            stack_xmm(c, register, SAVED_XMM_AT + (register - 6) * 16, store=False)
        c.emit('48 81 c4 ' + struct.pack('<I', FRAME_BYTES).hex(' ')
               + ' 41 5f 41 5e 41 5d 41 5c 5f 5e 5d 5b c3')
        return self.b._procedure(c.finish(), None, ctypes.c_void_p, unwind=unwind)


def replay_preserved(p, raw, *, snan=False, frame_offset=0, queue_base=0):
    before, after = raw[1536:2048], raw[2048:2560]
    left, right = struct.unpack_from('<16Q', before), struct.unpack_from('<16Q', after)
    expect(left == right, 'Reflection gateway changed an original GP register')
    expect(left[5] == left[4] + 8 + CALLER_RBP + frame_offset,
           'Owned parent RBP does not match captured prolog RBP=parentRSP+100h')
    expect(left[3] == left[5] + 0x580 and left[15] == p.context
           and left[7] == p.context + 0x3040 + p.slot * 0x70,
           'Owned HI/context/flight inputs do not match the real contact frame')
    expect(before[128:130] == after[128:130], 'ADDSS changed arithmetic flags')
    lane = 160 + 8 * 16
    expect(before[160:lane] == after[160:lane]
           and before[lane + 4:416] == after[lane + 4:416],
           'Reflection gateway changed another XMM register or upper lane')
    bits = struct.unpack_from('<I', after, lane)[0]
    old_mxcsr = struct.unpack_from('<I', before, 136)[0]
    new_mxcsr = struct.unpack_from('<I', after, 136)[0]
    if snan:
        expect(bits & 0x7FC00000 == 0x7FC00000,
               'Original ADDSS did not quiet the supplied signaling NaN')
        expect(new_mxcsr == old_mxcsr | 1,
               'Gateway lost the original ADDSS invalid sticky bit')
    else:
        expect(struct.unpack_from('<f', after, lane)[0] == 9,
               'Original ADDSS XMM8,[RDI] was missing or executed more than once')
        expect(new_mxcsr == old_mxcsr, 'Reflection changed full post-ADDSS MXCSR')
    expect(struct.unpack_from('<I', raw, 0x1C0)[0] == queue_base,
           'Begin unexpectedly published an unfinished contact')
    expect(p.config[7] == COMMON_RCX,
           'Common end lost MOV RCX,[original RBP+24C0] replay')
    expect(ctypes.c_uint32.from_address(p.arena.address + 44).value == 0,
           'Reflection gateway active count leaked')
    return dict(parent_RSP=left[4] + 8, parent_RBP=left[5],
                HI=left[3], DP=left[5] + 0x3E0,
                context=left[15], flight=left[7],
                XMM8_after_bits=bits, MXCSR_before=old_mxcsr,
                MXCSR_after=new_mxcsr)


def main():
    for relative, wanted in [
        ('tools/native/hit_copy_reflection_observer.py', GENERATOR_SHA),
        ('dist/native-copy-reflection-observer-owned-20261014-v1/profile.json', PROFILE_SHA),
        ('tools/native/test_hit_copy_pending_observer_owned.py', FIXTURE_SHA),
    ]:
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != wanted:
            raise AssertionError('Frozen reflection owned input changed: ' + relative)
    import hit_copy_reflection_observer as producer
    manifest = producer.package()
    report = dict(status='RUNNING', group='one_owned_reflection_observer_group',
                  pid=os.getpid(), generator_sha256=GENERATOR_SHA,
                  profile_sha256=PROFILE_SHA, imported_fixture_sha256=FIXTURE_SHA,
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  Game_access=False, Game_code_executed=False,
                  external_process_enumeration=False, old_groups_executed=False,
                  gameplay_or_exception_safety_proven=False, cases=[])
    produced = bytearray()
    started = time.perf_counter()
    stage = 'profile_template_contract'
    try:
        expect(manifest['revision'] == 'copy_pending_reflection_observer_v1'
               and len(manifest['entries']) == 21 and len(manifest['sites']) == 8,
               'Reflection profile is not the fixed 21-entry, 8-site interface')
        entry = next(e for e in manifest['entries'] if e['name'] == REFLECTION_SITE)
        expect(entry['code_hex'].startswith('f3440f5807')
               and entry['unwind_hex'] == '01130605130310012400087007600650',
               'Reflection original ADDSS or post-original unwind +5 contract changed')
        stage = 'owned_initialization'
        with OwnedBridge() as b:
            p = ReflectionFixture(b, manifest)
            report.update(epoch=b.epoch, local_peer=b.local_peer)
            for e in manifest['entries']:
                for rel in e['relocations']:
                    target = p.addresses[rel['address_key']] + rel['addend']
                    expect(any(base <= target < base + size
                               for base, size in b._allocation_sizes.items()),
                           f"Relocation escaped owned allocation: {e['name']}:{rel['address_key']}")
            report['all_native_targets_owned'] = True
            normal = ('contact_begin', 'default_delta', 'normal_final')
            reflect_end = (REFLECTION_SITE, 'contact_end', 'contact_end')
            cases = [
                ('normal_blocked', normal + ('contact_end', 'contact_end'), 'normal', ('ap', 3)),
                ('normal_equal_penetration', normal + ('contact_end', 'contact_end'), 'normal', ('ap', 4)),
                ('normal_full_penetration', normal + ('contact_end', 'contact_end'), 'normal', ('ap', 5)),
                ('normal_then_reflection_one_record', normal + reflect_end, 'reflection', None),
                ('fresh_reflection_without_normal', ('contact_begin',) + reflect_end, 'reflection', None),
                ('AP_only_fresh_reflection_no_AP_proof', ('contact_begin', 'default_delta')
                 + reflect_end, 'reflection', None),
                ('custom_and_force_normal_then_reflection', ('contact_begin', 'custom_curve', 'normal_final')
                 + reflect_end, 'reflection', 'custom_force'),
                ('repeat_reflection_same_contact', normal + (REFLECTION_SITE,) + reflect_end, 'reflection', None),
                ('wrong_parent_RSP_preserves_normal', normal + reflect_end, 'normal', 'wrong_parent'),
                ('wrong_saved_slot_preserves_normal', normal + reflect_end, 'normal', 'wrong_slot'),
                ('fresh_wrong_full_peer', ('contact_begin',) + reflect_end, None,
                 (0x110, 8, b.local_peer ^ (1 << 40))),
                ('fresh_enemy_not_admitted', ('contact_begin',) + reflect_end, None, (0x20, 4, 0)),
                ('fresh_source_not_admitted', ('contact_begin',) + reflect_end, None, (0x80, 4, 0)),
                ('fresh_owner_zero', ('contact_begin',) + reflect_end, None, (0x100, 4, 0)),
                ('fresh_owner_invalid', ('contact_begin',) + reflect_end, None, (0x100, 4, 0xFFFFFFFF)),
                ('fresh_kind_rejected', ('contact_begin',) + reflect_end, None, (0, 4, 2)),
                ('normal_target_tuple_changed', normal + (('mutate', 0x20, 4, 1003),)
                 + reflect_end, 'normal', None),
                ('normal_source_tuple_changed', normal + (('mutate', 0x80, 4, 1004),)
                 + reflect_end, 'normal', None),
                ('normal_owner_tuple_changed', normal + (('mutate', 0x100, 4, 72),)
                 + reflect_end, 'normal', None),
                ('normal_kind_tuple_changed', normal + (('mutate', 0, 4, 1),)
                 + reflect_end, 'normal', None),
                ('normal_node_tuple_changed', normal + (('mutate', 0x24, 4, 0x456),)
                 + reflect_end, 'normal', None),
                ('normal_part_hash_tuple_changed', normal + (('mutate', 0x7C, 4, 0x789),)
                 + reflect_end, 'normal', None),
                ('normal_armour_tuple_changed', normal + (('mutate', 0x50, 4, 0x40A00000),)
                 + reflect_end, 'normal', None),
                ('original_ADDSS_snan_post_MXCSR', ('contact_begin',) + reflect_end,
                 'reflection', 'snan'),
            ]
            p.resolver.insert(1003, p.enemy, 2)
            p.resolver.insert(1004, p.source, 3)
            for stage, actions, expected, change in cases:
                p.reflection_defaults()
                # Match real default AP factor branches before producing any record.
                ctypes.c_float.from_buffer(p.damage, 4).value = 1
                expected_ap = 5
                if change == 'snan':
                    ctypes.c_uint32.from_address(p.xmm_state + 128).value = 0x7F800001
                elif change == 'custom_force':
                    p.hit[0x73] = 1
                    p.projectile[0xFC] = 1
                elif change in ('wrong_parent', 'wrong_slot'):
                    pass
                elif change and change[0] == 'ap':
                    expected_ap = change[1]
                    p.floats[0] = expected_ap
                    ctypes.c_float.from_buffer(p.damage, 4).value = {
                        3: 0, 4: 0.65, 5: 1}[expected_ap]
                elif change:
                    offset, width, value = change
                    ctypes.memmove(ctypes.addressof(p.hit) + offset,
                                   struct.pack('<Q' if width == 8 else '<I', value), width)
                rejected_before = p.arena.stats()['rejected']
                frame_offset = 16 if change == 'wrong_parent' else 0
                caller = p.runner(actions, frame_offset=frame_offset,
                                  wrong_slot=change == 'wrong_slot')
                caller(ctypes.addressof(p.config))
                raw = ctypes.string_at(p.output, 4096)
                if REFLECTION_SITE in actions:
                    state = replay_preserved(p, raw, snan=change == 'snan',
                                             frame_offset=frame_offset)
                    if expected in (None, 'normal'):
                        expect(raw[2816:2960] == raw[3072:3216],
                               stage + ': rejected/conflicting reflection changed ordinary row or metadata')
                    if change in ('wrong_parent', 'wrong_slot'):
                        expect(p.arena.stats()['rejected'] == rejected_before + 1,
                               stage + ': original frame/slot guard did not reject exactly once')
                else:
                    state = None
                    expect(p.config[7] == COMMON_RCX,
                           'Normal common end lost original RCX replay')
                records = b.drain()
                expect(len(records) == int(expected is not None),
                       stage + ': contact count differs or duplicate end published again')
                queue_trace = list(struct.unpack_from('<' + 'I' * len(actions), raw, 0x1C0))
                first_end = actions.index('contact_end')
                expect(all(value == 0 for value in queue_trace[:first_end])
                       and queue_trace[first_end:] == [int(expected is not None)] * 2,
                       stage + ': pending contact published early or common end repeated it')
                if records:
                    record = records[0]
                    expect(record.native_branch == (2 if expected == 'reflection' else 1)
                           and record.target == 1001 and record.source == 1002
                           and record.owner == 71 and record.attack_kind == 0
                           and record.creditor == b.local_peer and record.epoch == b.epoch
                           and record.target_kind == 1,
                           stage + ': record used a changed tuple or lacks personal enemy proof')
                    if 'normal_final' in actions and 'default_delta' in actions:
                        expect(record.selected_ap == expected_ap and record.armour == 4
                               and record.ap_delta == expected_ap - 4,
                               stage + ': reflection/fallback lost the normal AP snapshot')
                    if 'normal_final' not in actions:
                        expect(record.capture_flags & 0x94 == 0,
                               stage + ': fresh reflection borrowed unfinished AP or curve proof')
                    if change == 'custom_force':
                        expect(record.effect_flags == 7 and record.capture_flags & 0x30 == 0x30,
                               'Reflection lost frozen custom-curve and force effect/proof bits')
                    expect(record.capture_flags & 0x143 == 0x143,
                           stage + ': emitted record lacks direct/full-peer/enemy/source proofs')
                    if REFLECTION_SITE in actions:
                        expect(record.contact_ordinal == struct.unpack_from('<I', raw, 2816 + 40)[0]
                               == struct.unpack_from('<I', raw, 3072 + 40)[0],
                               stage + ': reflection/fallback replaced the existing contact ordinal')
                report['cases'].append(dict(name=stage, status='PASS',
                    expected_branch=expected, preserved_machine_state=state,
                    pending_before_hex=raw[2816:2960].hex() if state else None,
                    pending_after_hex=raw[3072:3216].hex() if state else None,
                    records=[record_dict(r) for r in records],
                    queue_trace=queue_trace))
            report.update(validation_cases_passed=True, original_ADDSS_exactly_once=True,
                          original_GP_XMM_and_full_MXCSR_preserved=True,
                          real_parent_frame_relation_verified=True,
                          normal_reflection_merge_and_fresh_identity_verified=True)
        report.update(owned_allocations_released=b.closed,
                      released_allocation_count=len(b._allocations))
        stage = 'one_configure_continuous_five_record_delivery'
        # configure preserves accepted/sequence by design. Use one fresh owned
        # transport for the continuous deliverable, without editing its counters.
        with OwnedBridge(epoch=report['epoch'], local_peer=report['local_peer']) as b:
            p = ReflectionFixture(b, manifest)
            configure = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64,
                ctypes.c_uint32)(p.addresses['configure'])
            expect(configure(b.base, p.arena.address, b.epoch, b.local_peer, 1) == 1,
                   'Continuous native configure failed')
            delivery = [
                ('blocked', 3, 0, normal + ('contact_end', 'contact_end')),
                ('penetration', 4, 0.65, normal + ('contact_end', 'contact_end')),
                ('full_penetration', 5, 1, normal + ('contact_end', 'contact_end')),
                ('reflection_only', 5, 1, ('contact_begin',) + reflect_end),
                ('normal_then_reflection', 5, 1, normal + reflect_end),
            ]
            delivery_trace = []
            ordinals = []
            for index, (name, ap, factor, actions) in enumerate(delivery):
                stage = 'continuous_delivery_' + name
                # No defaults/reset/configure or drain within these five contacts.
                ctypes.memset(p.output, 0, 4096)
                p.config[7] = 0
                p.floats[0] = ap
                ctypes.c_float.from_buffer(p.damage, 4).value = factor
                caller = p.runner(actions)
                caller(ctypes.addressof(p.config))
                raw = ctypes.string_at(p.output, 4096)
                if REFLECTION_SITE in actions:
                    replay_preserved(p, raw, queue_base=index)
                trace = list(struct.unpack_from('<' + 'I' * len(actions), raw, 0x1C0))
                first_end = actions.index('contact_end')
                expect(trace[:first_end] == [index] * first_end
                       and trace[first_end:] == [index + 1] * 2,
                       name + ': continuous queue did not gain exactly one contact')
                ordinals.append(ctypes.c_uint32.from_address(p.row + 40).value)
                delivery_trace.append(dict(name=name, queue_trace=trace,
                                           contact_ordinal=ordinals[-1]))
            stage = 'continuous_single_native_drain'
            records = b.drain()  # The only drain in the continuous delivery.
            expect(len(records) == 5 and b.stats()['count'] == 0
                   and b.stats()['accepted'] == 5,
                   'Continuous native queue did not drain exactly five records')
            expect([r.sequence for r in records] == [1, 2, 3, 4, 5]
                   and [r.contact_ordinal for r in records] == ordinals
                   and len(set(ordinals)) == 5,
                   'Continuous sequences/ordinals are not unique and monotonic')
            expect([r.native_branch for r in records] == [1, 1, 1, 2, 2]
                   and all(r.epoch == b.epoch and r.creditor == b.local_peer
                           for r in records),
                   'Continuous records changed branch, epoch or full peer')
            for r, ap, factor in zip(records[:3], (3, 4, 5), (0, 0.65, 1)):
                expect(r.selected_ap == ap and r.armour == 4 and r.ap_delta == ap - 4
                       and r.factor == ctypes.c_float(factor).value,
                       'Continuous default AP/damage factor tuple is inconsistent')
            expect(records[3].capture_flags & 0x94 == 0,
                   'Reflection-only delivery borrowed AP proof')
            expect(records[4].selected_ap == 5 and records[4].armour == 4
                   and records[4].ap_delta == 1 and records[4].factor == 1,
                   'Normal/reflection delivery lost its default AP factor1 tuple')
            produced.extend(b''.join(ctypes.string_at(ctypes.addressof(r), 96) for r in records))
            report.update(status='PASS', continuous_native_configure_calls=1,
                          continuous_native_drain_calls=1,
                          continuous_delivery_trace=delivery_trace,
                          continuous_records=[record_dict(r) for r in records],
                          continuous_queue_stats=b.stats())
        report.update(continuous_owned_allocations_released=b.closed,
                      continuous_released_allocation_count=len(b._allocations))
    except Exception as error:
        report.update(status='FAIL', first_failure_stage=stage,
                      first_failure=f'{type(error).__name__}: {error}')
    report['elapsed_ms'] = (time.perf_counter() - started) * 1000
    destination = ROOT / 'dist/native-copy-reflection-observer-owned-20261014-v1'
    destination.mkdir(parents=True, exist_ok=True)
    raw_path = destination / 'owned-records.bin'
    raw_path.write_bytes(produced)
    report.update(native_drained_records=len(produced) // 96,
                  owned_records_path=str(raw_path),
                  owned_records_sha256=hashlib.sha256(produced).hexdigest(),
                  owned_records_only_native_commit_and_drain=True,
                  owned_records_reset_case_bytes_excluded=True)
    out = destination / 'report.json'
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                   encoding='utf8')
    print(json.dumps(dict(status=report['status'], report=str(out),
                         first_failure=report.get('first_failure')), ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
