"""Control bounded, manually triggered native-stat captures; never a full process dump."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import uuid

FOLDER = Path(os.environ['LOCALAPPDATA']) / 'HD2Runtime/mod_data'
STORE = FOLDER / 'mods_hd2_costs_war_cost_ledger.json'
REQUEST = FOLDER / 'ledger_probe_request.json'


def write_json(path, data):
    pending = path.with_name(path.name + '.tmp')
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(pending, path)


def require_closed():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq helldivers2.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, encoding='utf8', errors='replace', check=True)
    if 'helldivers2.exe' in result.stdout.lower():
        raise SystemExit('游戏运行时不能修改缓存中的设置。关闭游戏后再启用/停用探针。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'capture', 'status', 'diff'])
    parser.add_argument('--label', default='sample')
    parser.add_argument('--code', action='store_true', help='Read two small, known native code ranges once')
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    args = parser.parse_args()
    if args.action in ('enable', 'disable'):
        require_closed()
        FOLDER.mkdir(parents=True, exist_ok=True)
        data = json.loads(STORE.read_text(encoding='utf8')) if STORE.exists() else {}
        if not isinstance(data, dict):
            raise SystemExit('已有账目不是 JSON 对象，未改动。')
        if STORE.exists():
            backup = STORE.with_name(STORE.stem + '.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak.json')
            backup.write_bytes(STORE.read_bytes())
        data['probe_enabled'] = args.action == 'enable'
        write_json(STORE, data)
        print('探针下次启动时' + ('启用。' if data['probe_enabled'] else '停用。'))
    elif args.action == 'capture':
        data = json.loads(STORE.read_text(encoding='utf8')) if STORE.exists() else {}
        if data.get('probe_enabled') is not True:
            raise SystemExit('探针未启用；游戏关闭时先运行 enable，再启动游戏。')
        if REQUEST.exists():
            raise SystemExit('还有一条待采集命令；先用 status 检查。')
        if len(args.label.encode('utf8')) > 160:
            raise SystemExit('标签太长（最多 160 UTF-8 字节）。')
        request = {'id': uuid.uuid4().hex, 'label': args.label, 'include_code': args.code}
        write_json(REQUEST, request)
        print('已发送一次采集命令：' + str(FOLDER / ('ledger_probe_' + request['id'] + '.json')))
    elif args.action == 'status':
        data = json.loads(STORE.read_text(encoding='utf8')) if STORE.exists() else {}
        print(json.dumps({'enabled_on_next_start': data.get('probe_enabled', False),
            'pending': json.loads(REQUEST.read_text(encoding='utf8')) if REQUEST.exists() else None,
            'captures': [str(p) for p in sorted(FOLDER.glob('ledger_probe_*.json'), key=lambda p: p.stat().st_mtime)[-8:]]},
            ensure_ascii=False, indent=2))
    else:
        if not args.before or not args.after:
            parser.error('diff requires --before and --after')
        def entries(path):
            snapshot = json.loads(path.read_text(encoding='utf8'))
            if not snapshot.get('stats'):
                raise SystemExit('采集没有有效 stats：' + str(path))
            stats = snapshot['stats']
            out = {('main', item['key']): item for item in stats['main']}
            for source in stats['sources']:
                for item in source['entries']:
                    # Keep native blocks distinct; don’t merge unknown float/bool semantics.
                    out[(str(source['block']) + ':' + source['type'], item['key'])] = item
            return out
        before, after = entries(args.before), entries(args.after)
        changes = []
        for location in sorted(set(before) | set(after)):
            a, b = before.get(location), after.get(location)
            if a != b:
                changes.append({'location': location[0], 'key_hex': '%08X' % location[1], 'before': a, 'after': b})
        print(json.dumps(changes, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
