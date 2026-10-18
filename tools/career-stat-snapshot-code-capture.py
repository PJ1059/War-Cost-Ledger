"""Read only the actual Career data snapshot getter body, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_stat_snapshot_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_stat_snapshot_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x18E62DC, 'e8cfbfe6ff', 0x17522B0
worker.SOURCE_SHA = 'e9ec6b03305d1a69e50d7a9b5c735eff511404d61ccb1a3c9e0d16437da97880'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual StatsFill entry SHA' + worker.SOURCE_SHA + ';18E62DC ->17522B0; '
    'RCX=ownedstackdestination, return copied9F0bytes byCareer UI; unknownsnapshotfields/owner/ready; no call')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_STAT_SNAPSHOT_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
