"""Read one declared local-peer UI callee; never invoke it or classify it as a provider.

Actual Armory-block initializer calls 19A6990 from 18EDEE8. The caller
passes block+30220 and a local peer identity; its callee's role is unknown.
Reuse the fixed 4K code / 8K 32-read / 2-second PE and Ship capture limits.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_local_profile_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_local_peer_ui_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x18EDEE8, 'e8a38a0b00', 0x19A6990
worker.SOURCE_SHA = '390516011461495dd7e09f4e106c980c00df00861385a47299d3fef6d7babcff'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual Armory block initializer SHA' + worker.SOURCE_SHA + ';18EDEE8 ->19A6990; '
    'RCX=block+30220=Armory+7DD18, RDX=QWORD [[game+347CEF0]+B398] local peer identity; '
    'R8=R9=0, stack+20 lowbyte0; callee role and ABI unknown; no native call or provider claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture


def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta


def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_LOCAL_PROFILE_BRANCH')
    probe.base_verify(meta, raw)


worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
