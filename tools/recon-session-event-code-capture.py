"""Capture only the known native session-notice writer's declared code ranges.

The 58-byte source PIN is the game's host-left system notice, not a discovery
event. This one-shot read establishes the shared session event representation;
it neither reads chat messages nor emits reconnaissance awards.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('external/VanillaPlusMegapack/components/BetterLobbyManagement/src/game.lua')
TARGET_RVA = 0x10834ED
TARGET_PIN = '83b91cc20a00030f85c7000000e8d1c32c00488b15ea993f0284db41b90700000041be04000000450f45ce33f68b8238f80100488b8aa8b30000'
CAPTURE_SCOPE = 'known_host_left_session_notice_writer'
spec = importlib.util.spec_from_file_location('_recon_session_event_code_reader', ROOT/'tools/recon_chat_code_capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
reader.REVISION = 'recon_session_notice_known_writer_v1'
reader.TARGET_RVA = TARGET_RVA
reader.TARGET_PIN = TARGET_PIN
reader.SOURCE_REFERENCE = str(SOURCE) + ':75'


def verify_source():
    raw = SOURCE.read_bytes()
    block = re.search(r"rva = 0x10834ed, name = 'host-left check', bytes =(.+?)\},", raw.decode('utf8'), re.S)
    if not block:
        raise ValueError('RECON_SESSION_SOURCE_PIN_MISSING')
    pin = bytes(int(v) for v in re.findall(r'\\(\d+)', block.group(1)))
    if pin.hex() != TARGET_PIN:
        raise ValueError('RECON_SESSION_SOURCE_PIN_CHANGED')
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/recon-session-event-code-live-20261013-v1')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source_sha = verify_source()
    stamps = reader.profile.fingerprints()
    if args.check:
        print(json.dumps({'status': 'disk_checked', 'source_sha256': source_sha,
                          'target_rva': TARGET_RVA, 'pin_bytes': len(bytes.fromhex(TARGET_PIN)),
                          'max_code_bytes': reader.MAX_FUNCTION_BYTES, 'max_read_bytes': reader.MAX_BYTES,
                          'max_reads': reader.MAX_READS, 'game_reads': 0}))
        return
    if not args.pid:
        parser.error('--pid is required unless --check is used')
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    if tuple(game_processes()) != (args.pid,):
        raise ValueError('RECON_SESSION_GAME_PID_CHANGED')
    identity = resolve_game(args.pid)
    reader.profile.validate_identity(identity, stamps)
    evidence = {}
    args.output.mkdir(exist_ok=False)
    try:
        with Process(args.pid) as process:
            binary, meta = reader.capture(process, identity, evidence=evidence)
        final = resolve_game(args.pid)
        reader.profile.validate_identity(final, stamps)
        if final != identity:
            raise ValueError('RECON_SESSION_MODULE_CHANGED')
        reader.verify_saved(meta, binary)
        meta.update(game_pid=args.pid, source_sha256=source_sha, source_pin=TARGET_PIN,
                    attempts=1, semantic_scope=CAPTURE_SCOPE,
                    discovery_event_type_proven=False, session_payloads_read=0)
        (args.output/'writer.bin').write_bytes(binary)
        (args.output/'writer.json').write_text(json.dumps(meta, indent=2), encoding='utf8')
        print(json.dumps({'status': 'complete', 'bytes': len(binary), 'ranges': meta['ranges'],
                          'budget': meta['budget'], 'discovery_event_type_proven': False}))
    except Exception as error:
        (args.output/'failure.json').write_text(json.dumps({'error': str(error), 'evidence': evidence,
                              'game_pid': args.pid, 'source_sha256': source_sha}, indent=2), encoding='utf8')
        raise


if __name__ == '__main__':
    main()
