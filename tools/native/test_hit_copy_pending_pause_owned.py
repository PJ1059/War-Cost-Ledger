"""One focused pause replay in this Python process; no Game access or old suite."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
from hit_bridge_owned import OwnedBridge, _Code
from test_hit_copy_pending_observer_owned import (
    Fixture, address, expect, record_dict, unchanged_snapshot,
    RETURN, COMMON_RCX, STACK_VALUES,
)

FROZEN = "95b7a98c4d1c1b7201049b9fc31af71a981f68c9e0d16db540955277240aef0e"
LABELS = ("contact_begin", "default_delta", "normal_final", "pause",
          "disabled_physical", "disabled_common_end", "resume", "new_begin")
# Reuse only the old owned caller construction. Its two custom-call positions
# bind this new owned control shim, never the producer's custom gateway. The
# shim calls pause while enabled, then resume while disabled, in this fixed
# single sequence. This keeps the original master RSP constant at all sites.
CALLER_ACTIONS = ("contact_begin", "default_delta", "normal_final", "custom_curve",
                  "physical_success", "contact_end", "custom_curve", "contact_begin")
SHIM_UNWIND = bytes.fromhex("010603000642027001600000")


def control_shim(fixture):
    c = _Code()
    c.emit("56 57 48 83 ec 28 48 b8 "
           + struct.pack("<Q", fixture.arena.address).hex(" ") + " 83 78 28 00")
    c.branch("0f 84", "resume")
    for reg, value in [("48 b9", fixture.b.base), ("48 ba", fixture.arena.address),
                       ("49 b8", fixture.b.epoch), ("49 b9", fixture.b.local_peer)]:
        c.emit(reg + " " + struct.pack("<Q", value).hex(" "))
    c.emit("49 bb " + struct.pack("<Q", fixture.addresses["pause"]).hex(" ") + " 41 ff d3")
    c.emit("48 89 44 24 20")
    c.emit("48 be " + struct.pack("<Q", fixture.arena.rows).hex(" ")
           + " 49 8b 7c 24 40 b9 00 0a 00 00 fc f3 48 a5")
    c.emit("48 be " + struct.pack("<Q", fixture.b.base).hex(" ")
           + " 49 8b 7c 24 48 b9 14 00 00 00 fc f3 48 a5")
    c.emit("48 8b 44 24 20"); c.branch("e9", "return")
    c.label("resume")
    for reg, value in [("48 b9", fixture.b.base), ("48 ba", fixture.arena.address),
                       ("49 b8", fixture.b.epoch), ("49 b9", fixture.b.local_peer)]:
        c.emit(reg + " " + struct.pack("<Q", value).hex(" "))
    c.emit("49 bb " + struct.pack("<Q", fixture.addresses["resume"]).hex(" ") + " 41 ff d3")
    c.label("return"); c.emit("48 83 c4 28 5f 5e c3")
    return fixture.b._procedure(c.finish(), ctypes.c_uint32, unwind=SHIM_UNWIND)


def main():
    destination = ROOT / "dist/hit-copy-pending-pause-owned-20261013-v1"
    destination.mkdir(parents=True, exist_ok=True)
    generator = ROOT / "tools/native/hit_copy_pending_observer.py"
    sha = hashlib.sha256(generator.read_bytes()).hexdigest()
    expect(sha == FROZEN, "Frozen pause candidate changed; focused replay withheld")
    import hit_copy_pending_observer as producer
    manifest = producer.package()
    report = {
        "status": "RUNNING", "group": "one_focused_pending_pause_case",
        "pid": os.getpid(), "generator_sha256": sha,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "Game_access": False, "external_process_enumeration": False,
        "Game_code_executed": False, "old_suite_executed": False,
        "gameplay_or_exception_safety_proven": False,
        "sequence": list(LABELS),
    }
    started = time.perf_counter()
    try:
        with OwnedBridge() as b:
            p = Fixture(b, manifest)
            for entry in manifest["entries"]:
                for rel in entry["relocations"]:
                    target = p.addresses[rel["address_key"]] + rel["addend"]
                    expect(any(base <= target < base + size
                               for base, size in b._allocation_sizes.items()),
                           f"Relocation escaped owned memory: {entry['name']}:{rel['address_key']}")
            rows_snapshot = b._allocate(32 * 640, executable=False)
            queue_snapshot = b._allocate(160, executable=False)
            config = (ctypes.c_uint64 * 10)(*list(p.config), rows_snapshot, queue_snapshot)
            p.config = config
            # The same case exercises every fixed row, including the tail.
            # Reserve the current thread's first probe for the real gateways.
            owners = []
            current_index = (p.row - p.arena.rows) // 640
            for i in range(32):
                row = p.arena.rows + i * 640
                owner = 0 if i == current_index else 0x71000000 + i
                ctypes.c_uint32.from_address(row + 96).value = owner
                owners.append(owner)
                if owner:
                    ctypes.c_uint32.from_address(row + 100).value = 3
                    ctypes.c_uint32.from_address(row + 88).value = 0x1FF
                    ctypes.c_uint64.from_address(row + 104).value = ctypes.addressof(p.hit)
                    ctypes.c_uint64.from_address(row + 624).value = ctypes.addressof(config)
                    ctypes.c_uint32.from_address(row + 112).value = 1
            owners[current_index] = int(b.kernel.GetCurrentThreadId())
            seed = b.record(target=1001, source=1002, contact_ordinal=0x7FFF,
                            native_branch=1, capture_flags=0x1FF, ap_delta=1)
            expect(b.publish(seed), "Owned seed FIFO record was not accepted")
            before = ctypes.string_at(b.base, 160)
            # This same case first checks both zero-result busy paths. A
            # failed lock acquisition owns nothing and must change nothing.
            ctypes.c_uint32.from_address(p.arena.address + 56).value = 1
            busy_gate = ctypes.string_at(p.arena.address, 64)
            busy_rows = ctypes.string_at(p.arena.rows, 32 * 640)
            busy_results = []
            for name in ("pause", "resume"):
                fn = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_uint64,
                                        ctypes.c_uint64)(p.addresses[name])
                result = int(fn(b.base, p.arena.address, b.epoch, b.local_peer))
                busy_results.append(result)
                expect(result == 0, f"Lock-busy {name} falsely returned success")
                expect(ctypes.string_at(p.arena.address, 64) == busy_gate
                       and ctypes.string_at(p.arena.rows, 32 * 640) == busy_rows
                       and ctypes.string_at(b.base, 160) == before,
                       f"Lock-busy {name} changed gate, pending rows or FIFO")
            report.update(lock_busy_returns=busy_results,
                          lock_busy_gate_rows_FIFO_unchanged=True)
            ctypes.c_uint32.from_address(p.arena.address + 56).value = 0
            shim = control_shim(p)
            p.addresses["custom_curve"] = address(shim)
            expect(address(shim) in b._procedures,
                   "Focused control shim escaped the owned procedure registry")
            runner = p.runner(CALLER_ACTIONS)
            runner(ctypes.addressof(config))
            raw = ctypes.string_at(p.output, 4096)
            count_trace = list(struct.unpack_from("<8I", raw, 0x1C0))
            flags_trace = list(struct.unpack_from("<8I", raw, 0x1E0))
            report.update(count_trace=count_trace, flags_trace=flags_trace,
                          all_native_targets_owned=True)
            expect(count_trace == [1] * 8, "Paused old normal result was delivered later")
            expect(flags_trace == [0, 0x9C, 0x1FF, 0, 0, 0, 0, 0],
                   "Pause did not clear pending capture flags before resume/new begin")
            expect(struct.unpack_from("<Q", raw, 0x198)[0] == 1
                   and struct.unpack_from("<Q", raw, 0x1B0)[0] == 1,
                   "Native pause/resume did not return success")
            expect(ctypes.string_at(queue_snapshot, 160) == before
                   and ctypes.string_at(b.base, 160) == before,
                   "Pause/resume changed FIFO, accepted/sequence, peer or epoch")
            cleared = ctypes.string_at(rows_snapshot, 32 * 640)
            for i, owner in enumerate(owners):
                base = i * 640
                expect(struct.unpack_from("<I", cleared, base + 96)[0] == owner,
                       f"Pause changed row owner {i}")
                for offset, width in [(100, 4), (88, 4), (104, 8), (624, 8), (112, 4)]:
                    expect(cleared[base + offset:base + offset + width] == bytes(width),
                           f"Pause failed to clear row {i} offset {offset}")
                expect(ctypes.c_uint32.from_address(p.arena.rows + base + 96).value == owner,
                       f"Resume/new begin changed row owner {i}")
            expect(ctypes.c_uint32.from_address(p.row + 100).value == 1
                   and p.arena.stats()["contact_counter"] == 2,
                   "New begin did not start a fresh ordinal after pause")
            expect(ctypes.c_uint32.from_address(p.arena.address + 40).value == 1
                   and ctypes.c_uint32.from_address(p.arena.address + 44).value == 0
                   and ctypes.c_uint32.from_address(p.arena.address + 56).value == 0,
                   "Resume left arena disabled, active or configuration-locked")
            expect(ctypes.c_uint64.from_address(p.arena.address + 8).value == b.epoch
                   and ctypes.c_uint64.from_address(p.arena.address + 16).value == b.local_peer,
                   "Pause changed arena peer or epoch")
            expect(config[7] == COMMON_RCX and p.damage[0x1C] == 0,
                   "Disabled gateways lost original common-MOV/physical-clear replay")
            unchanged_snapshot(raw, 1536, physical=True)
            unchanged_snapshot(raw, 2560)
            for i in (0, 2, 7):
                expect(struct.unpack_from("<Q", raw, 0x180 + i * 8)[0] == RETURN,
                       "Original begin/normal return value changed")
            expect(struct.unpack_from("<Q", raw, 96)[0] == 2
                   and struct.unpack_from("<Q", raw, 224)[0] == 1,
                   "Original begin/normal callee invocation count changed")
            expect(struct.unpack_from("<8Q", raw, 32) == STACK_VALUES
                   and struct.unpack_from("<8Q", raw, 160) == STACK_VALUES,
                   "Original begin/normal stack arguments changed")
            records = b.drain()
            expect(len(records) == 1 and records[0].sequence == 1
                   and records[0].contact_ordinal == 0x7FFF,
                   "Final FIFO did not contain only the original seed")
            report.update(status="PASS", records=[record_dict(r) for r in records],
                          fixed_32_rows_cleared=True, row_owners_preserved=True,
                          seed_FIFO_sequence_accepted_peer_epoch_preserved=True,
                          old_pending_never_submitted=True, new_begin_ordinal=2,
                          disabled_original_replay_preserved=True,
                          original_calls_returns_stack_arguments_preserved=True)
        report.update(owned_allocations_released=b.closed,
                      released_allocation_count=len(b._allocations))
    except Exception as error:
        report.update(status="FAIL", first_failure=f"{type(error).__name__}: {error}")
    report["elapsed_ms"] = (time.perf_counter() - started) * 1000
    out = destination / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(out),
                      "first_failure": report.get("first_failure")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
