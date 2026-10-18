"""Read the known screen stack lazy-constructor call, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_constructor_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_constructor_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x14381D0, 'e80bfaffff', 0x1437BE0
worker.SOURCE_SHA = '868d16b58632f45583db4131fdc51fe18a5c176f67380c74009c794604a10924'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen stack entry SHA' + worker.SOURCE_SHA + ';14381D0 ->1437BE0 only when owner+889=0; '
    'RCX=screen stack owner [347CE38], EDX=screen2 retained; no initialization invocation/Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_SCREEN_CONSTRUCTOR_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
