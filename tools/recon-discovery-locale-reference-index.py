"""One Ship-only exact discovery locale-ID index in Game's fixed code0.

Keep only <=64 candidate windows, never a full image or gameplay/chat data.
Raw four-byte ID hits are candidates, not instruction or discovery proof.
The frozen reader enforces 48MiB, 256 reads/queries and 2 seconds, with
identity/build/PIN/PE/Ship checks before and after; no writes or execution.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'recon_discovery_locale_reference_index_v1'
INDEX = ROOT / 'tools/hit-contact-registration-index.py'
INDEX_SHA = '3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
LOCALE_IDS = (0x92871A58, 0xCD539459)
SOURCES = (
    ('dist/mod-research/task-layout/full-ui-20261011/strings/0x353194c702a3c234.strings.json',
     '77102338e1a47417a4eb2ea3f01da991e409530a406daa8cef074135cc13e876',
     ('<i=1>#NAME</i>已发现#DISCOVERY', '<c=#PLAYER_COLOR>#NAME</c>已发现#DISCOVERY')),
    ('dist/mod-research/task-layout/full-ui-20261011/strings/0x18056969d61dbfe9.strings.json',
     '7d4c49729c3cbc390a8d6fa9f0c1a77e6e093a03b0349a96df99521cf519d0f8',
     ('<i=1>#NAME</i> discovered #DISCOVERY', '<c=#PLAYER_COLOR>#NAME</c> discovered #DISCOVERY')),
)


def validate_locale_sources():
    proven = []
    for relative, expected_sha, expected_text in SOURCES:
        raw = (ROOT / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise ValueError('RECON_LOCALE_SOURCE_CHANGED')
        source = json.loads(raw)
        records = [row for row in source['Items'] if row['Key'] in LOCALE_IDS]
        expected = dict(zip(LOCALE_IDS, expected_text))
        if len(records) != 2 or {r['Key']: r['Value'] for r in records} != expected:
            raise ValueError('RECON_LOCALE_ID_OR_TEMPLATE_CHANGED')
        proven.append({'path': relative, 'sha256': expected_sha,
                       'language': source['Language'], 'records': records})
    return {'locale_sources': proven, 'locale_ids': list(LOCALE_IDS),
            'templates_verified_in_two_languages': True,
            'runtime_producer_proven': False, 'discoverer_peer_proven': False}


def byte_matches(buffer, buffer_rva, kind, absolute):
    if kind != 'code':
        raise ValueError('RECON_LOCALE_INDEX_CODE_ONLY')

    def matches(value):
        needle = struct.pack('<I', value)
        at = buffer.find(needle)
        while at >= 0:
            yield at, 4, f'byte_locale_id_{value:#x}'
            at = buffer.find(needle, at + 1)
    return heapq.merge(*(matches(value) for value in LOCALE_IDS))


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError('RECON_LOCALE_FROZEN_INDEX_CHANGED')
    spec = importlib.util.spec_from_file_location('_recon_locale_private_index', INDEX)
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    old_source = index.validate_sources()
    locale_source = validate_locale_sources()
    frozen_stream = index.stream_index
    index.REVISION = REVISION
    index.SECTIONS = index.SECTIONS[:1]
    # Retain the frozen reader's source-proven 16B code PIN as a build gate.
    # TARGET_RVA is only the unused absolute-match adapter input here.
    index.TARGET_RVA = 0
    index.byte_matches = byte_matches
    index.validate_sources = lambda: {**locale_source,
        'frozen_index_sha256': INDEX_SHA,
        'old_source_validated_before_private_override': True,
        'old_code_pin_provenance': old_source,
        'target_kind': 'EXACT_LOCALE_ID_BYTES_ONLY'}

    def stream(budget, sections, evidence):
        evidence.pop('target_rva', None)
        evidence.update(capture_purpose='STATIC_DISCOVERY_LOCALE_ID_INDEX_ONLY',
                        locale_ids=list(LOCALE_IDS), target_kind='EXACT_LOCALE_ID_BYTES_ONLY',
                        runtime_producer_proven=False, discoverer_peer_proven=False,
                        excluded=['other image sections', 'heap/chat/string scan',
                                  'candidate follow-up', 'writes or Game code execution'])
        result = frozen_stream(budget, sections, evidence)
        for row in result['candidates']:
            row.pop('target_rva', None)
            row['locale_id'] = struct.unpack('<I', bytes.fromhex(row['match_hex']))[0]
            row['locale_id_hex'] = f"{row['locale_id']:#x}"
            row['runtime_producer_proven'] = False
        if result['complete']:
            result['reason'] = 'SINGLE_FIXED_CODE0_COMPLETE'
        return result
    index.stream_index = stream
    return index


def run(output, expected_pid, dependencies=None, clock=time.perf_counter):
    index = private_index()
    deps = dependencies if dependencies is not None else index.profile.load_dependencies()
    deps = dict(deps)
    original_pids = deps['game_processes']
    if not isinstance(expected_pid, int) or expected_pid <= 0:
        raise ValueError('RECON_LOCALE_EXPECTED_PID_REQUIRED')

    def exact_pid():
        pids = tuple(original_pids())
        if pids != (expected_pid,):
            raise ValueError('RECON_LOCALE_CURRENT_PID_CHANGED')
        return pids
    deps['game_processes'] = exact_pid
    return index.run(output, dependencies=deps, clock=clock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output, args.pid)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] != 'complete':
            raise SystemExit(2)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
