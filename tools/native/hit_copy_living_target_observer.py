"""Freeze target life before the original hit consumer; pure profile generation.

The earlier profiles remain immutable. This extension only wraps their existing
type/source qualifier. A hit on a confirmed living enemy still commits after
that enemy dies or disappears; later contacts with its corpse do not qualify.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from hit_callable_profile import RelocCode

BASE = ROOT / 'docs/native-demolition-diagnostic-profile-v1.json'
BASE_SHA = 'd9625febd977dc7cfa80f05259b4e2ccd00e9789cec50363c6e72d7b84442476'
UNWIND = bytes.fromhex('010704000732037002600130')


def health_alive_code():
    """u32 alive(Health RCX, entity EDX), at most eight owned-table probes.

Health's descriptor is a pointer array, unlike EntityManager's inline array.
All layout constants match Runtime event_natives.health / event_world.lua.
Unknown, retired, reused and already-dead targets return zero. No damage amount
is inspected: a live target's blocked hit/reflection remains a valid contact.
"""
    c = RelocCode()
    c.emit('53 56 57 48 83 ec 20 48 89 ce 89 d7')
    c.emit('48 85 f6'); c.branch('0f 84', 'no')
    c.emit('85 ff'); c.branch('0f 84', 'no')
    c.emit('83 ff ff'); c.branch('0f 84', 'no')
    c.emit('8b 86 10 10 00 00 85 c0'); c.branch('0f 84', 'no')
    c.emit('3d 00 10 00 00'); c.branch('0f 87', 'no')
    c.emit('8b 96 20 10 00 00 39 c2'); c.branch('0f 87', 'no')
    c.emit('85 d2'); c.branch('0f 84', 'no')
    c.emit('44 8b 8e 38 10 00 00 45 85 c9'); c.branch('0f 84', 'no')
    c.emit('41 81 f9 00 00 01 00'); c.branch('0f 87', 'no')
    c.emit('44 89 c8 41 ff c9 44 85 c8'); c.branch('0f 85', 'no')
    c.emit('4c 8b 86 30 10 00 00 4d 85 c0'); c.branch('0f 84', 'no')
    c.emit('89 f8 0f af 86 40 10 00 00 44 21 c8 b9 08 00 00 00')
    c.label('probe')
    c.emit('41 8b 14 c0 39 fa'); c.branch('0f 84', 'found')
    c.emit('3b 96 3c 10 00 00'); c.branch('0f 84', 'no')
    c.emit('ff c0 44 21 c8 ff c9'); c.branch('0f 85', 'probe')
    c.branch('e9', 'no')
    c.label('found')
    c.emit('41 8b 5c c0 04 3b 9e 20 10 00 00'); c.branch('0f 83', 'no')
    c.emit('3b 9e 10 10 00 00'); c.branch('0f 83', 'no')
    c.emit('4c 8b 96 48 10 00 00 4d 85 d2'); c.branch('0f 84', 'no')
    c.emit('4d 8b 14 da 4d 85 d2'); c.branch('0f 84', 'no')
    c.emit('41 39 7a 08'); c.branch('0f 85', 'no')
    c.emit('4c 8b 9e 58 10 00 00 4d 85 db'); c.branch('0f 84', 'no')
    c.emit('48 69 c3 b8 01 00 00 41 83 bc 03 9c 01 00 00 02')
    c.branch('0f 83', 'no')
    # Recheck identity and table extents after the life read. Never carry an
    # entity's slot to another contact, frame or original damage-consumer call.
    c.emit('41 39 7a 08'); c.branch('0f 85', 'no')
    c.emit('4c 3b 9e 58 10 00 00'); c.branch('0f 85', 'no')
    c.emit('4c 3b 86 30 10 00 00'); c.branch('0f 85', 'no')
    c.emit('41 ff c1 44 3b 8e 38 10 00 00'); c.branch('0f 85', 'no')
    c.emit('3b 9e 20 10 00 00'); c.branch('0f 83', 'no')
    c.emit('4c 8b 86 48 10 00 00 4d 85 c0'); c.branch('0f 84', 'no')
    c.emit('4d 3b 14 d8'); c.branch('0f 85', 'no')
    c.emit('b8 01 00 00 00'); c.branch('e9', 'return')
    c.label('no'); c.emit('31 c0')
    c.label('return'); c.emit('48 83 c4 20 5f 5e 5b c3')
    return c


def qualifier_code():
    c = RelocCode()
    c.emit('56 57 48 83 ec 28 48 89 d6')
    c.call('qualifier_types')
    c.emit('a9 40 00 00 00'); c.branch('0f 84', 'return')
    c.address('48 b8', 'health_manager_global')
    c.emit('48 8b 38 48 89 f9 8b 56 2c'); c.call('health_alive')
    c.emit('85 c0'); c.branch('0f 84', 'dead_or_unknown')
    c.address('48 b8', 'health_manager_global')
    c.emit('48 3b 38'); c.branch('0f 84', 'return')
    c.label('dead_or_unknown')
    c.emit('81 66 58 bf ff ff ff c7 46 54 00 00 00 00')
    c.label('return'); c.emit('8b 46 58 48 83 c4 28 5f 5e c3')
    return c


def entry(name, code, unwind):
    raw = code.finish()
    return dict(name=name, code_hex=raw.hex(), relocations=code.relocations,
                unwind_hex=unwind.hex(), entry_offset=0, executable_length=len(raw))


def package():
    raw = BASE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('LIVING_TARGET_FROZEN_BASE_CHANGED')
    profile = copy.deepcopy(json.loads(raw))
    for item in profile['entries']:
        if item['name'] == 'qualifier':
            item['name'] = 'qualifier_types'
    profile['entries'] += [entry('health_alive', health_alive_code(), UNWIND),
                           entry('qualifier', qualifier_code(), bytes.fromhex('010603000642027001600000'))]
    profile['revision'] = 'copy_pending_living_target_observer_v1'
    profile['living_target_filter'] = dict(revision=1, health_manager_rva=0x3326688,
        max_records=4096, max_hash_capacity=65536, max_probes=8,
        record_stride=440, life_offset=412, alive_life_below=2,
        unknown_target_admitted=False, damage_amount_required=False,
        qualification_time='before_original_normal_consumer_or_reflection_writeback',
        commit_rechecks_life=False, preserves_killing_hit=True,
        base_profile_sha256=BASE_SHA)
    profile['count_contract'].update(target_alive_at_capture_required=True,
        dead_or_unknown_health_target_rejected=True, commit_does_not_recheck_target_life=True)
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package(), indent=2) + '\n', encoding='utf8')
    print(output.resolve())
