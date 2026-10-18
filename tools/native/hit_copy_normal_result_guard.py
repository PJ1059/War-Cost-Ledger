"""Pure normal-result guard profile; no Game or native API access.

The physical true tail remains a bounded diagnostic and original replay only.
It cannot replace a proven normal/AP tuple with an unverified ricochet result.
Diagnostic tags are private observer tags, never Game enums or ordinary hits.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PENDING_SHA = '95b7a98c4d1c1b7201049b9fc31af71a981f68c9e0d16db540955277240aef0e'
DIAGNOSTIC_SHA = '262c52c46c7f30be0a8f604f36068e18e8a41cbacc39d8dc77cfb9c89725f456'
DIAGNOSTIC_PROFILE_SHA = 'c3bf4a1961da5a6848a19a34d99e79b1800aa96bb93b9969412cc8f62e3be3f4'
for filename, wanted in [('hit_copy_pending_observer.py', PENDING_SHA),
                         ('hit_copy_tail_diagnostic.py', DIAGNOSTIC_SHA)]:
    if hashlib.sha256((HERE / filename).read_bytes()).hexdigest() != wanted:
        raise ValueError('NORMAL_RESULT_GUARD_FROZEN_SOURCE_CHANGED:' + filename)
import hit_copy_tail_diagnostic as D


def gateway():
    """Keep the old prolog/UW/replay, with diagnostic tag 4 as its sole observer.

    No ordinary lookup, raw_snapshot, phase 5 transition or publication exists
    in this gateway. The shared diagnostic helper writes only reserved scratch.
    """
    c = D.P.RelocCode()
    D.P.old.prolog(c)
    D.diagnose(c, D.CONTRACT['true_tag'])
    D.P.restore(c, 'physical_success')
    result = D.P.entry('physical_success', c, D.P.old.GATE_UNWIND)
    result.update(frame_allocation=D.P.old.FRAME_BYTES, frame_register='RBP',
                  original_parent_unwind_unchanged=True,
                  diagnostic_only_alt=False,
                  diagnostic_only_physical_success=True,
                  ordinary_pending_unchanged=True)
    return result


def package():
    original = D.package()
    # The frozen Windows artifact used CRLF; serialize that exact byte contract
    # rather than mistaking a text-newline difference for a source change.
    encoded = (json.dumps(original, indent=2) + '\n').replace('\n', '\r\n').encode('utf8')
    if hashlib.sha256(encoded).hexdigest() != DIAGNOSTIC_PROFILE_SHA:
        raise ValueError('NORMAL_RESULT_GUARD_FROZEN_PROFILE_CHANGED')
    profile = copy.deepcopy(original)
    profile['entries'] = [gateway() if e['name'] == 'physical_success' else e
                          for e in profile['entries']]
    profile['count_contract']['physical_success_overrides_normal'] = False
    profile['count_contract']['physical_success_publishes'] = False
    profile.update(revision='copy_pending_normal_result_guard_v1',
                   immutable_diagnostic_generator_sha=DIAGNOSTIC_SHA,
                   immutable_diagnostic_profile_sha=DIAGNOSTIC_PROFILE_SHA,
                   ricochet_producer_verified=False,
                   ordinary_physical_publish=False,
                   ordinary_physical_FIFO_publish=False,
                   physical_success_diagnostic_only=True,
                   ordinary_AP_classification_rules_unchanged=True,
                   ordinary_classification_rules_unchanged=False,
                   physical_success_keeps_normal_AP_pending=True,
                   owned_normal_guard_replay_verified=False)
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    path = parser.parse_args().output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(package(), indent=2) + '\n', encoding='utf8')
    print(path.resolve())
