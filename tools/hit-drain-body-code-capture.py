"""One bounded read of the declared Drain successor, only in Ship.

Actual 51B prologue SHA67962e2f... proves fallthrough to 12A6F23;
its exception search also returned [12A6F23,12A7AC9). The known queue0
consumer call at 12A6FA3 pins this declared body. Reuse the tested private
metadata reader to revalidate it and its bounded unwind ancestry, not gaps.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('drain_body_session',
                                            ROOT / 'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = session.reader.REVISION = 'impact_queue_drain_body_v1'
session.TARGET_RVA = session.reader.TARGET_RVA = 0x12A6FA3
session.TARGET_PIN = session.reader.TARGET_PIN = 'e8980d0000'
session.reader.SOURCE_REFERENCE = (
    'actual drain prologue 67962e2f6efb3bb800a1e20858df7f5b1d3d099267f5b5f36281e7a7bc568e6c; '
    'exception record 0x408E444 [12A6F23,12A7AC9); '
    'HD2Runtime dcd996d research_event_combat.py queue0 call PIN')

if __name__ == '__main__':
    session.main()
