"""Read the SDK's exact entity-map consumer PIN within its declared function.

Ship only, metadata/code <=8192B/32 reads, code ranges <=4096B, 2s soft limit.
No entity scan, native call, game write, hook or gameplay event observation.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hit_entity_map_private_capture',
                                            ROOT/'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = session.reader.REVISION = 'hit_entity_map_declared_code_v1'
session.TARGET_RVA = session.reader.TARGET_RVA = 0xFD9D50
session.TARGET_PIN = session.reader.TARGET_PIN = '4c8b1541224902'
session.reader.SOURCE_REFERENCE = (
    'HD2Runtime dcd996d domains/event_natives.lua wielder entity map PIN; '
    'runtime/event_world.lua entity_descriptor/entity_type; '
    'the PIN is an internal global load, not a callable entry or type guarantee')

if __name__ == '__main__':
    session.main()
