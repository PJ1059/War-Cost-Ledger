"""Read the named UILabel string-format writer once in Ship, never call it.

VPM1762b06 proves this build/PIN; numeric argument types and Career values
remain unknown. Reuse the one-shot Ship waiter and bounded metadata reader.
No Career cache, UI heap, account update, game write or native call.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_string_format_declared_code_v1'
TARGET_RVA = 0x143C950
TARGET_PIN = '40534883ec20488bd94881c110010000'
spec = importlib.util.spec_from_file_location('career_format_wait_session',
                                            ROOT / 'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = REVISION
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = TARGET_RVA, TARGET_PIN
worker.session.reader.SOURCE_REFERENCE = (
    'VanillaPlusMegapack1762b06 components/ModOptionsMenu/src/native.lua set_string_arg; '
    'career-provider-research-20261012/static-read-contract.json')
# This target has its own byte PIN in the declared body. It uses the original
# bounded capture, not the impact caller prefix or an empty callee PIN.
worker.session.reader.window_capture = worker.window_factory
worker.session.reader.capture = worker.body_capture


def verify_saved(meta, raw):
    if (meta['source_revision'] != REVISION or meta['target_rva'] != TARGET_RVA
            or meta['classification_ready'] is not False
            or meta['native_written'] is not False or meta['native_called'] is not False):
        raise ValueError('CAREER_FORMAT_SAVED_PROFILE')
    worker.session.reader.verify_saved(meta, raw)


worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
