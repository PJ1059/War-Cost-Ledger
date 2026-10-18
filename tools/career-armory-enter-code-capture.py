"""Read the actual screen2 Armory-object enter call, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_armory_enter_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_armory_enter_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x1495511, 'e82a03fcff', 0x1455840
worker.SOURCE_SHA = '9480213fe1765759f41589b1f3c918d87f00424c7992ba1eb425dbc373e921b1'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen2 branch SHA' + worker.SOURCE_SHA + ';actual table proof e6fbfc98f0b93a33d6aca4a5b60948e6fa585f515b3803955ebe8868523419b0 selects149550A;1495511 ->1455840; '
    'RCX=[[347CE38]+60] Armory object, RDX=screen stack owner; no call/Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_ARMORY_ENTER_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
