"""Read-only summary of loader/runtime evidence and this mod's saved mission."""
import json
import os
from pathlib import Path

base = Path(os.environ['LOCALAPPDATA'])
logs = base / 'CowboyBingus' / 'Helldivers2' / 'Logs'
for name in ('BingusSharedLoader.log', 'HD2Runtime.log'):
    file = logs / name
    print(str(file))
    if not file.is_file():
        print('尚无日志')
        continue
    matches = [line for line in file.read_text(encoding='utf8', errors='replace').splitlines()
               if 'war_cost_ledger' in line or 'War Cost Ledger' in line]
    print('\n'.join(matches[-15:]) if matches else '未发现本 MOD 的加载/记账记录')
file = base / 'HD2Runtime' / 'mod_data' / 'mods_hd2_costs_war_cost_ledger.json'
print(str(file))
if file.is_file():
    print(json.dumps(json.loads(file.read_text(encoding='utf8')), ensure_ascii=False, indent=2))
else:
    print('尚无保存账目：未完成真实游戏验证。')
