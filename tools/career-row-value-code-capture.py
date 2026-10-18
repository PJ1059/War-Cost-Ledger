"""Read only the actual Career list stat-id/value row setter, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_row_value_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_row_value_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x18E63F1, 'e8eae7ffff', 0x18E4BE0
worker.SOURCE_SHA = '238f2d4a4307188e16625b1c255b93fc9052c5b2aea0eb6089e51352ffa4f5b1'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual Career StatsFill successor SHA' + worker.SOURCE_SHA + ';18E63F1 ->18E4BE0; '
    'RCX=Career panel+9B8 actual list, EDX=1, R8D=panel+2FE08; stat ID meaning/owner/ready unproven; no call')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_ROW_VALUE_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
