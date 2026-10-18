"""Read only the known chat-box-send PIN's RF and bounded declared ancestry."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('external/VanillaPlusMegapack/components/BetterLobbyManagement/src/chat.lua')
TARGET_RVA=0x186025D
TARGET_PIN='488b0d8cccc1014c8d87d41600004881c118c40000e8e97283ff'
spec=importlib.util.spec_from_file_location('_recon_hud_bounded_session',ROOT/'tools/recon_chat_code_capture.py')
session=importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION='recon_chat_hud_known_handler_v2'
session.TARGET_RVA=TARGET_RVA
session.TARGET_PIN=TARGET_PIN
session.SOURCE_REFERENCE=str(SOURCE)+':28'
session.MAX_CHAIN_NODES=6
_ancestry=session.unwind_ancestry
_prior=json.loads((ROOT/'dist/recon-chat-hud-handler-live-20261013-v1/failure.json').read_text(encoding='utf8'))['evidence']['unwind_chain']
def checked_ancestry(initial,read_metadata,nodes):
    _ancestry(initial,read_metadata,nodes)
    if len(nodes)<4: raise ValueError('RECON_CHAT_KNOWN_ANCESTRY_CHANGED')
    for previous,current in zip(_prior,nodes):
        for key,value in previous.items():
            if current.get(key)!=value: raise ValueError('RECON_CHAT_KNOWN_ANCESTRY_CHANGED')
session.unwind_ancestry=checked_ancestry

def verify_source():
    text=SOURCE.read_text(encoding='utf8')
    match=re.search(r"rva = 0x186025d, name = 'chat box send', bytes =\s*'([^']+)'",text)
    if not match: raise ValueError('RECON_CHAT_SOURCE_PIN_MISSING')
    raw=bytes(int(s) for s in re.findall(r'\\(\d+)',match.group(1)))
    if raw.hex()!=TARGET_PIN: raise ValueError('RECON_CHAT_SOURCE_PIN_CHANGED')
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',required=True,type=int)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/recon-chat-hud-handler-live-20261013-v2')
    args=parser.parse_args()
    from fire_code_windows import Process,resolve_game
    from probe_session import game_processes
    source_sha=verify_source()
    if tuple(game_processes())!=(args.pid,): raise ValueError('RECON_CHAT_GAME_PID_CHANGED')
    stamps=session.profile.fingerprints()
    identity=resolve_game(args.pid)
    session.profile.validate_identity(identity,stamps)
    evidence={}
    args.output.mkdir(exist_ok=False)
    try:
        with Process(args.pid) as process:
            data,meta=session.capture(process,identity,evidence=evidence)
        final=resolve_game(args.pid)
        session.profile.validate_identity(final,stamps)
        if final!=identity: raise ValueError('RECON_CHAT_MODULE_CHANGED')
        session.verify_saved(meta,data)
        meta.update(game_pid=args.pid,source_sha256=source_sha,source_pin=TARGET_PIN,attempts=1)
        (args.output/'handler.bin').write_bytes(data)
        (args.output/'handler.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
        print(json.dumps({'status':'complete','bytes':len(data),'ranges':meta['ranges'],'budget':meta['budget']}))
    except Exception as e:
        (args.output/'failure.json').write_text(json.dumps({'error':str(e),'evidence':evidence,'game_pid':args.pid,'source_sha256':source_sha},indent=2),encoding='utf8')
        raise

if __name__=='__main__': main()
