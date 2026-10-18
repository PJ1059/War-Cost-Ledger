"""Follow actual string-storage branch2C0 ->2D8 within declared sibling.

Fresh143C960 ->143A1B0 retained. Only the existing declared fragment and its
bounded unwind ancestry; no actual Career widgets or account values.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('format_output_session',
                                             ROOT/'tools/career-format-helper-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_format_storage_output_v3'
worker.session.reader.TARGET_RVA = 0x143A2D8
worker.session.reader.SOURCE_REFERENCE = (
    'Actual274B helper SHA2cacbe9e8dca9f0b404c05cbb9cf72ef9185871a07f8d5de343787ef903936d1; '
    '143A2C0 jne143A2D8; declared[143A2D8,143A2F1); original143C960 ->143A1B0 PIN')

if __name__ == '__main__':
    worker.main()
