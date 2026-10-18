"""Read the registered per-frame callback's proven tail declaration once.

The captured 4EE6FE JMP reaches 173BAB0 with RCX=Game+33262F0. Its
semantic role is unknown. Reuse the existing bounded Ship-only reader;
never invoke the function, alter Game, wait, or follow additional callees.
"""
from pathlib import Path
import hashlib
import importlib.util
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'dist/hit-game-plugin-table-update-live-20261013-v1/plugin-table-update.bin'
SOURCE_SHA = '03b3fd1cd3459fb3c3d6eb71e47a806dd2376ccd7f36dbc1f60f606bd446f546'
CALLER, CALL_PIN, CALLEE = 0x4EE6FE, 'e9add32401', 0x173BAB0

raw = SOURCE.read_bytes()
if (len(raw) != 280 or hashlib.sha256(raw).hexdigest() != SOURCE_SHA
        or raw[262:267].hex() != CALL_PIN
        or CALLER + 5 + struct.unpack_from('<i', raw, 263)[0] != CALLEE
        or raw[246:253].hex() != '488d0dfb7be302'):
    raise ValueError('CAREER_PLUGIN_TAIL_SOURCE_CHANGED')

spec = importlib.util.spec_from_file_location('_career_plugin_tail_private',
    ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_plugin_update_tail_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = CALLER, CALL_PIN, CALLEE
worker.SOURCE_SHA = SOURCE_SHA
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = CALLEE, ''
worker.session.reader.SOURCE_REFERENCE = (
    'Frozen registered plugin +68 callback SHA' + SOURCE_SHA
    + '; actual JMP4EE6FE ->173BAB0; RCX=Game+33262F0. '
    + 'No frontend, UI-update, provider, or signature claim.')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', CALLER, 5),))
worker.caller_window.PINS = ((CALLER, CALL_PIN),)

if __name__ == '__main__':
    worker.main()
