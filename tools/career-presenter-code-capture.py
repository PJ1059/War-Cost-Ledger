"""Read the author's named PresenterManager::open code; never open a menu.

VPM GalacticMenuHotkey routes Armory through presenter5 and this actual-build
entry. Only its declared PE range/ancestry is captured to study initialization;
no Career data, UI heap, account, native call or game write is performed.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_armory_presenter_declared_code_v1'
TARGET_RVA = 0x14C0350
# Author's exact 16-byte prefix; its final 8b is not extended by guessing.
TARGET_PIN = '48895c24084889742410574883ec208b'
spec = importlib.util.spec_from_file_location('career_presenter_private_session',
                                             ROOT / 'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = REVISION
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = TARGET_RVA, TARGET_PIN
worker.session.reader.SOURCE_REFERENCE = (
    'VPM1762b06 GalacticMenuHotkey/src/galactic_menu_hotkey.lua:52,79,118,317,344-374; '
    'PresenterManager::open(manager,int,void*), Armory presenter5; no call or stats getter claim')
worker.session.reader.window_capture = worker.window_factory
worker.session.reader.capture = worker.body_capture


def verify_saved(meta, raw):
    if (meta['source_revision'] != REVISION or meta['target_rva'] != TARGET_RVA
            or meta['classification_ready'] is not False
            or meta['native_written'] is not False or meta['native_called'] is not False):
        raise ValueError('CAREER_PRESENTER_SAVED_PROFILE')
    worker.session.reader.verify_saved(meta, raw)


worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
