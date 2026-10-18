"""Read only the proven presenter5 -> screen2 tail target.

Actual14B5080 table14B59D4[4]=14B515C then14B5178 e93330f8ff
->14381B0. RCX=[347CE38], EDX=2, R8=originalextra. No Stats getter
claim, native call, UI opening, heap or account operation.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_armory_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_armory_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x14B5178, 'e93330f8ff', 0x14381B0
worker.SOURCE_SHA = 'cb2c3703cbf685427ba9f6cb7432aae7b423c89ca025650b06e36208f902ca24'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual presenter5 table14B59D4[4]=14B515C; SHA' + worker.SOURCE_SHA +
    ';14B5178 ->14381B0; RCX=[347CE38], EDX=2, R8=original extra; no Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)

capture, verify_saved = probe.capture, probe.verify_saved

if __name__ == '__main__':
    worker.main()
