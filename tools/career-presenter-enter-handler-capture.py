"""Read the proven registry enter-handler call, no call/UI/account operation."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_presenter_enter_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_presenter_enter_handler_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x14C07BD, 'e8be48ffff', 0x14B5080
worker.SOURCE_SHA = '2f9e55042f43931957df15a1c5945ab74b3a8f8180959cf4531c1eb3eac00678'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual idle init SHA' + worker.SOURCE_SHA + ';14C07BD ->14B5080; '
    'RCX=presenter manager+D8, EDX=requested presenter5, R8=original extra; no Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)

# Reuse exact bounded capture/clock accounting, but mark this actual E8 honestly.
old_capture = worker.capture
def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta


def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_PRESENTER_ENTER_BRANCH')
    probe.base_verify(meta, raw)


worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
