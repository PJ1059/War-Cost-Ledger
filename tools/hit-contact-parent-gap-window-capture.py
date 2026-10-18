"""One fixed168B gap window after byte-exact current parent104, read-only.

Private frozen parent sampler retains both locator snapshots and original
caller/record before+after checks. Its single parent104 read is compared to
the frozen actual source; only then read13AC258..13AC300 once. Total16KiB/
24RPM-query/2s; no pdata search/chain/callee/newfield/heap/rest-body/API calls,
writes,wait/retry. Gap extent is a fixed window, not a declaration/function.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'contact_parent104_to_saved_owner_prefix_gap168_v1'
PARENT_TOOL = ROOT / 'tools/hit-contact-parent-fragment-capture.py'
PARENT_TOOL_SHA = 'dfad6281f878697bc8179a87d4fbbbd1a83b95f6806d8216855da32fb0176549'
SOURCE = ROOT / 'dist/hit-contact-parent-fragment-live-20261013-v1'
SOURCE_SHA = '571075ffd72f94df74c9a70e1f75edd165ece8b0eaa88d366146ad2bd7312527'
PARENT_BIN_SHA = '407a416a17c2b5153b9f81e0261d63e04ac67b05ee4eb557bc493342021ff118'
GAP_RVA, GAP_END, GAP_BYTES = 0x13AC258, 0x13AC300, 168


def private_parent():
    if hashlib.sha256(PARENT_TOOL.read_bytes()).hexdigest() != PARENT_TOOL_SHA:
        raise ValueError('PARENT_GAP_FROZEN_TOOL_CHANGED')
    spec = importlib.util.spec_from_file_location('_parent_gap_private_sampler', PARENT_TOOL)
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    return parent


def validate_source(fingerprint, folder=SOURCE):
    raw = (Path(folder) / 'parent104.json').read_bytes()
    binary = (Path(folder) / 'parent104.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != SOURCE_SHA or len(binary) != 104
            or hashlib.sha256(binary).hexdigest() != PARENT_BIN_SHA):
        raise ValueError('PARENT_GAP_FROZEN_ACTUAL_SOURCE_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or not meta.get('source_gates_verified')
            or not meta.get('record_before_after_match') or not meta.get('caller_before_after_match')
            or not meta.get('declared_code_complete') or meta.get('logical_function_complete') is not False
            or meta.get('declared_begin') != 0x13AC1F0 or meta.get('declared_end') != GAP_RVA
            or meta.get('code_bytes') != 104 or meta.get('sha256') != PARENT_BIN_SHA
            or meta.get('fingerprint') != fingerprint or meta.get('target_module') != 'game'
            or meta.get('target_prefix_hex') != binary[:16].hex()):
        raise ValueError('PARENT_GAP_FROZEN_ACTUAL_SOURCE_PROFILE')
    return binary, {'directory': str(Path(folder).resolve()), 'metadata_sha256': SOURCE_SHA,
                    'parent_binary_sha256': PARENT_BIN_SHA, 'parent_declared_begin': 0x13AC1F0,
                    'parent_declared_end': GAP_RVA, 'gap_rva': GAP_RVA, 'gap_bytes': GAP_BYTES,
                    'gap_end_exclusive': GAP_END, 'logical_function_complete': False}


def run(output, dependencies=None, clock=time.perf_counter):
    parent = private_parent()
    followup = parent.private_followup()
    locator = followup.private_locator()
    reader = locator.private_reader()
    fresh_expected, source = validate_source(reader.profile.FINGERPRINT)
    BaseBudget = reader.Budget
    captured = {}
    class GapBudget(BaseBudget):
        def read_module(self, rva, size, purpose, executable=False):
            raw = super().read_module(rva, size, purpose, executable)
            if purpose == 'fixed_declared_parent104':
                if rva != parent.PARENT_RVA or size != 104 or raw != fresh_expected:
                    raise ValueError('PARENT_GAP_FRESH_PARENT104_CHANGED')
                captured['gap'] = super().read_module(GAP_RVA, GAP_BYTES, 'fixed_gap168_code_window', True)
            return raw
    reader.Budget = GapBudget
    locator.private_reader = lambda: reader
    followup.private_locator = lambda: locator
    parent.private_followup = lambda: followup
    status = parent.run(output, dependencies=dependencies, clock=clock)
    meta = json.loads(Path(status['json_path']).read_text('utf8'))
    folder = Path(output).resolve()
    binary, report = folder / 'parent-gap168.bin', folder / 'parent-gap168.json'
    raw = captured['gap']
    meta.update(source_revision=REVISION, capture_purpose='SINGLE_FIXED_PARENT_TO_OWNER_PREFIX_GAP_WINDOW',
        gap_source=source, frozen_parent_tool_sha256=PARENT_TOOL_SHA,
        fresh_parent_binary_path=status['binary_path'], fresh_parent_json_path=status['json_path'],
        fresh_parent_declared_begin=meta.pop('declared_begin'), fresh_parent_declared_end=meta.pop('declared_end'),
        fresh_parent_prefix_hex=meta['target_prefix_hex'], target_prefix_hex=raw[:16].hex(),
        target_rva=GAP_RVA, target_name='fixed_gap_window_13AC258_13AC300', code_bytes=GAP_BYTES,
        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest(),
        ranges=[{'module': 'game', 'rva': GAP_RVA, 'length': GAP_BYTES, 'binary_offset': 0}],
        fresh_parent104_exact=True, gap_window_read_once=True, gap_end_exclusive=GAP_END,
        declared_code_complete=False, logical_function_complete=False,
        boundary_kind='fixed168B_gap_window_not_declaration')
    binary.write_bytes(raw)
    report.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf8')
    result = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
              'binary_path': str(binary), 'sha256': meta['sha256']}
    reader.profile.tail['write_status'](folder, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
