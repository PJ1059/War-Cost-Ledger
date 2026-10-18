"""Cross-test owned x64 records through HD2's real LuaJIT and ribbon model.

This opens no game process and installs no connector. Native fields/flags here
are controlled fixtures, not observed gameplay. Queue bytes themselves are
produced by the owned machine-code publisher and drain, without Lua encoding.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from test import run_lua
from hit_bridge_owned import OwnedBridge, RECORD_SIZE
from hit_entity_resolver_owned import OwnedEntityResolver


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    peer, epoch = 0xFEDCBA9876543210, 7
    with OwnedBridge(capacity=8, epoch=epoch, local_peer=peer) as bridge:
        resolver=OwnedEntityResolver(bridge)
        resolver.insert(123,resolver.enemies[0],0)
        resolver.insert(42,0xC12A34F375BD5A87,1)
        common = dict(target=123, source=42, owner=99, attack_kind=987,
                      target_kind=0, capture_flags=0xBF, native_branch=1,
                      selected_ap=4.0, armour=3.0)
        def publish(**fields):
            record=bridge.record(**fields)
            resolver.qualify(record)
            return bridge.publish(record)
        for delta, factor in [(-1.0, 0.0), (0.0, .65), (1.0, 1.0)]:
            assert publish(**common, ap_delta=delta,factor=factor, damage=0) == 1
        reflected = dict(common, capture_flags=3, native_branch=2,
                         selected_ap=float("nan"), armour=float("nan"))
        assert publish(**reflected, ap_delta=float("nan")) == 1
        assert publish(**common, ap_delta=-1.0, factor=0) == 1
        unproved = dict(common, source=789)
        assert publish(**unproved, ap_delta=1.0) == 1
        other = dict(common, creditor=peer + 1)
        assert publish(**other) == 2
        # These two consume capacity. The third must explicitly report a drop.
        for _ in range(2):
            assert publish(**unproved) == 1
        assert publish(**common) == 0
        stats = bridge.stats()
        records = bridge.drain(64)
        assert len(records) == 8 and stats["dropped"] == 1 and stats["filtered"] == 1
        assert [r.sequence for r in records] == list(range(1, 9))
        raw = b"".join(ctypes.string_at(ctypes.addressof(r), RECORD_SIZE) for r in records)
        assert bridge.drain(64) == []
    binary = output / "owned-records.bin"
    binary.write_bytes(raw)
    run_lua(ROOT / "tests/test_native_hit_pipeline.lua", ROOT / "src/native-hit-feedback.lua",
            ROOT / "src/hit-feedback.lua",
            Path("external/HD2Runtime"),
            binary)
    sources = [Path(__file__), ROOT / "tools/native/hit_bridge_owned.py",
               ROOT / "tools/native/hit_entity_resolver_owned.py",
               ROOT / "tests/test_native_hit_pipeline.lua", ROOT / "src/native-hit-feedback.lua",
               ROOT / "src/hit-feedback.lua"]
    report = dict(status="PASS", origin="owned_process_fixture_not_game", game_reads=0,
                  game_writes=0, connector_installed=False, record_count=8, record_bytes=96,
                  binary_sha256=hashlib.sha256(raw).hexdigest(), native_stats=stats,
                  expected_classes=dict(blocked=2, penetration=1, full_penetration=1, ricochet=1),
                  partial=True, unclassified=3,
                  native_type_catalog_evidence=resolver.evidence,
                  files={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sources})
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(dict(status="PASS", report=str(output / "verification.json"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
