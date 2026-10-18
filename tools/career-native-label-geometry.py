"""Capture the two known first-row localized labels; read-only geometry."""
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('label_parent', ROOT/'tools/career-parent-snapshot.py')
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)

def capture(process, identity, clock):
    b = parent.Budget(process, identity, clock)
    owner, why = parent.layout.locate(b)
    if not owner:
        raise parent.NotVisible(why, b)
    parent.layout.verify_code(b)
    fixture = json.loads((ROOT/'tests/fixtures/career-visible-rows.json').read_text('utf8'))
    old_controller = fixture['identity']['controller']
    row = fixture['rows'][0]
    values = []
    for role in ('tag', 'value'):
        address = owner['controller'] + row[role]['address'] - old_controller
        raw = b.read(address, 256)
        info = parent.validate(raw, owner['gui_context'], owner['controller'] + row['address'] - old_controller)
        if info['kind'] != 7:
            raise ValueError('CAREER_LABEL_KIND_CHANGED')
        font = b.read(address+0x27C,60)
        values.append(dict(role=role, address=address, **info, geometry=parent.geometry(raw),
                           layer=struct.unpack_from('<H',raw,0xBC)[0], header_hex=raw.hex(),
                           font_hex=font.hex(), font_floats=struct.unpack_from('<ffff',font),
                           font_index=font[0x14], font_flags=struct.unpack_from('<I',font,0x24)[0],
                           font_resource=struct.unpack_from('<Q',font,0x2C)[0]))
    for item in values:
        if b.read(item['address'],256).hex() != item['header_hex']:
            raise ValueError('CAREER_LABEL_CHANGED')
    after, why = parent.layout.locate(b)
    if not after or after != owner:
        raise ValueError('CAREER_LABEL_OWNER_CHANGED')
    return dict(identity=identity, owner_before=owner, owner_after=after,
                labels=values, active_read_bytes=b.total['bytes'], active_read_calls=b.total['reads'],
                read_records=b.total['records'], headers_stable=True,
                nodes=values, native_called=False, native_written=False, account_modified=False)

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    parent.capture=capture
    result=parent.run(args.output)
    print(json.dumps({key:result[key] for key in ('status','game_pid','labels','active_read_bytes')},ensure_ascii=False))
