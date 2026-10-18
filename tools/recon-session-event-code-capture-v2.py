"""Read the two exact RF ranges declared by the first session-writer sample.

The first attempt stopped after metadata: 3888 bytes plus its adjacent 670-byte
parent exceeded the generic 4096-byte aggregate limit. This version admits only
that exact 4558-byte span, still with the existing 8192-byte/32-read budget.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_recon_session_writer_v2', ROOT/'tools/recon-session-event-code-capture.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
reader = base.reader
reader.REVISION = 'recon_session_notice_known_writer_v2'
reader.MAX_FUNCTION_BYTES = 0x108431E - 0x1083150
KNOWN = (
    {'begin': 0x10833EE, 'end': 0x108431E, 'unwind_rva': 0x24D9CFC,
     'header': {'rva': 0x24D9CFC, 'raw_hex': '21100400'},
     'chain_entry': {'rva': 0x24D9D08, 'raw_hex': '50310801ee330801dc9c4d02'}},
    {'begin': 0x1083150, 'end': 0x10833EE, 'unwind_rva': 0x24D9CDC,
     'header': {'rva': 0x24D9CDC, 'raw_hex': '19260900'}},
)
original_ancestry = reader.unwind_ancestry


def exact_ancestry(initial, read_metadata, nodes):
    original_ancestry(initial, read_metadata, nodes)
    if nodes != list(KNOWN):
        raise ValueError('RECON_SESSION_DECLARED_RANGES_CHANGED')


reader.unwind_ancestry = exact_ancestry

if __name__ == '__main__':
    base.main()
