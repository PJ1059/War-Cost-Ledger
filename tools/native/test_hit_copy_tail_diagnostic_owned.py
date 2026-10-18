"""One new owned tail-diagnostic group; no Game or previous test groups."""
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
from hit_bridge_owned import OwnedBridge, Record, _Code
from hit_physical_profile_owned import snapshot_code
from test_hit_copy_pending_observer_owned import Fixture, address, expect, record_dict

FROZEN = "262c52c46c7f30be0a8f604f36068e18e8a41cbacc39d8dc77cfb9c89725f456"
NORMAL_ALT = ("contact_begin", "default_delta", "normal_final", "physical_success")
TRUE_ONLY = ("contact_begin", "physical_success")


def head(p):
    raw = ctypes.string_at(p.arena.rows + 128, 32)
    alt, true, claimed, mask, epoch = struct.unpack("<QQIIQ", raw)
    return dict(alt=alt, true=true, claimed=claimed, mask=mask, epoch=epoch)


def region(p):
    return (ctypes.string_at(p.arena.rows + 128, 32),
            [ctypes.string_at(p.arena.rows + i * 640 + 256, 96) for i in range(16)])


def snapshot_with_pending(p, displacement, checkpoint):
    c = _Code(); snapshot_code(c, displacement)
    # Only MOVs after the existing snapshot: no stack, XMM or flag changes.
    # RAX/R10/R11 are restored from that same snapshot before returning.
    c.emit("48 b8 " + struct.pack("<Q", p.row).hex(" ")
           + " 49 ba " + struct.pack("<Q", p.output + checkpoint).hex(" "))
    for i in range(16):
        c.emit("4c 8b 98 " + struct.pack("<I", i * 8).hex(" ")
               + " 4d 89 9a " + struct.pack("<I", i * 8).hex(" "))
    c.emit("4c 8b 98 70 02 00 00 4d 89 9a 80 00 00 00")
    for register, opcode in [(10, "4c 8b 91"), (11, "4c 8b 99"), (0, "48 8b 81")]:
        c.emit(opcode + " " + struct.pack("<I", displacement + register * 8).hex(" "))
    c.emit("c3")
    return p.b._procedure(c.finish(), None, unwind=bytes.fromhex("01000000"))


def replay_preserved(p, raw, *, alternative):
    before, after = raw[1536:2048], raw[2048:2560]
    a, z = struct.unpack_from("<16Q", before), struct.unpack_from("<16Q", after)
    wanted_al = 0 if alternative else 1  # old caller executes XOR AL,1.
    expect(z[0] == (a[0] & ~0xFF) | wanted_al and a[1:] == z[1:],
           "Tail diagnostic changed GP state beyond the original replay")
    expect(before[160:416] == after[160:416], "Tail diagnostic changed XMM state")
    expect(before[136:140] == after[136:140], "Tail diagnostic changed full MXCSR")
    expect(after[128] & 0xC5 == (0x44 if alternative else 0) and after[129] == 0,
           "Original caller XOR flags changed")
    expect(p.damage[0x1C] == (1 if alternative else 0),
           "Tail diagnostic lost original DamageValues+1C replay")


def invoke(p, caller, *, alternative):
    ctypes.memset(p.output, 0, 4096)
    caller(ctypes.addressof(p.config))
    raw = ctypes.string_at(p.output, 4096)
    replay_preserved(p, raw, alternative=alternative)
    expect(ctypes.c_uint32.from_address(p.arena.address + 44).value == 0,
           "Tail gateway active count leaked")
    return raw


def control(p, name):
    fn = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_uint64, ctypes.c_uint64)(p.addresses[name])
    expect(fn(p.b.base, p.arena.address, p.b.epoch, p.b.local_peer) == 1,
           f"Owned {name} control failed")


def pause_resume_preserves_diag(p, queue):
    before = region(p)
    control(p, "pause")
    expect(region(p) == before, "Pause discarded diagnostic head/slots")
    expect(ctypes.string_at(p.b.base, 160) == queue, "Diagnostic pause changed ordinary FIFO")
    control(p, "resume")
    expect(region(p) == before, "Resume changed diagnostic head/slots")


def main():
    generator = ROOT / "tools/native/hit_copy_tail_diagnostic.py"
    sha = hashlib.sha256(generator.read_bytes()).hexdigest()
    expect(sha == FROZEN, "Frozen tail-diagnostic generator changed; run withheld")
    import hit_copy_tail_diagnostic as producer
    manifest = producer.package()
    expect(manifest["revision"] == "copy_pending_tail_diagnostic_v1"
           and len(manifest["entries"]) == 20 and len(manifest["sites"]) == 7,
           "Frozen diagnostic interface changed")
    expect(manifest["immutable_pending_generator_sha"]
           == "95b7a98c4d1c1b7201049b9fc31af71a981f68c9e0d16db540955277240aef0e",
           "Diagnostic profile changed ordinary pending generator")
    report = {
        "status": "RUNNING", "group": "one_owned_tail_diagnostic_group",
        "pid": os.getpid(), "generator_sha256": sha,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "Game_access": False, "Game_code_executed": False,
        "external_process_enumeration": False, "old_groups_executed": False,
        "gameplay_or_exception_safety_proven": False,
    }
    started = time.perf_counter(); stage = "owned_initialization"
    try:
        with OwnedBridge() as b:
            p = Fixture(b, manifest)
            for e in manifest["entries"]:
                for rel in e["relocations"]:
                    target = p.addresses[rel["address_key"]] + rel["addend"]
                    expect(any(base <= target < base + size
                               for base, size in b._allocation_sizes.items()),
                           f"Relocation escaped owned allocation: {e['name']}:{rel['address_key']}")
            report["all_native_targets_owned"] = True
            p.snapshots = [snapshot_with_pending(p, 0, 3584),
                           snapshot_with_pending(p, 512, 3760)]
            real_true = p.addresses["physical_success"]
            p.addresses["physical_success"] = p.addresses["physical_alt_tail"]
            alt_caller = p.runner(NORMAL_ALT)
            p.addresses["physical_success"] = real_true
            true_caller = p.runner(TRUE_ONLY)
            seed = b.record(target=1001, source=1002, contact_ordinal=0x7FFF,
                            native_branch=1, capture_flags=0x1FF, ap_delta=1)
            expect(b.publish(seed), "Owned ordinary seed was not accepted")
            queue = ctypes.string_at(b.base, 160)
            report["ordinary_seed_prefix_hex"] = queue.hex()

            stage = "alternative_tail_keeps_ordinary_pending"
            raw = invoke(p, alt_caller, alternative=True)
            pending_before, pending_after = raw[3584:3720], raw[3760:3896]
            expect(pending_before == pending_after,
                   "Alternative diagnostic changed ordinary record/metadata/frame")
            expect(struct.unpack_from("<I", pending_after, 100)[0] == 3
                   and struct.unpack_from("<I", pending_after, 88)[0] == 0x1FF,
                   "Alternative tail did not retain normal pending phase/flags")
            expect(ctypes.string_at(b.base, 160) == queue,
                   "Alternative diagnostic submitted to ordinary FIFO")
            expect(head(p) == dict(alt=1, true=0, claimed=1, mask=1, epoch=b.epoch),
                   "Alternative diagnostic head differs from its first sample")
            report.update(alt_pending_before_hex=pending_before.hex(),
                          alt_pending_after_hex=pending_after.hex(),
                          alt_replay_GP_XMM_MXCSR_preserved=True)
            pause_resume_preserves_diag(p, queue)

            stage = "true_tail_keeps_original_phase_transition"
            raw = invoke(p, true_caller, alternative=False)
            expect(struct.unpack_from("<I", raw, 3584 + 100)[0] == 1
                   and struct.unpack_from("<I", raw, 3760 + 100)[0] == 5,
                   "True tail changed the original begun-to-physical-pending transition")
            expect(ctypes.string_at(b.base, 160) == queue,
                   "Diagnostic true tail submitted before the ordinary commit boundary")
            expect(head(p) == dict(alt=1, true=1, claimed=2, mask=3, epoch=b.epoch),
                   "True diagnostic head differs from its second sample")
            report["true_replay_GP_XMM_MXCSR_preserved"] = True
            pause_resume_preserves_diag(p, queue)

            stage = "diagnostic_identity_filters"
            denied = []
            ordinary_counters = (b.stats()["dropped"], b.stats()["filtered"],
                                 p.arena.stats()["rejected"])
            for name, offset, ctype, value in [
                ("wrong_high_peer", 0x110, ctypes.c_uint64, b.local_peer ^ (1 << 32)),
                ("unknown_enemy", 0x20, ctypes.c_uint32, 9999),
                ("unsupported_source", 0x80, ctypes.c_uint32, 9999),
            ]:
                field = ctype.from_buffer(p.hit, offset); original = field.value
                before = head(p); slots_before = region(p)[1]
                field.value = value
                raw = invoke(p, alt_caller, alternative=True)
                after = head(p)
                expect(after == {**before, "alt": before["alt"] + 1}
                       and region(p)[1] == slots_before,
                       f"Diagnostic {name} gained a sample or changed existing slots")
                expect(raw[3584:3720] == raw[3760:3896],
                       f"Alternative {name} diagnostic modified ordinary pending fields")
                denied.append(dict(name=name, before=before, after=after))
                field.value = original
                pause_resume_preserves_diag(p, queue)
            expect((b.stats()["dropped"], b.stats()["filtered"],
                    p.arena.stats()["rejected"]) == ordinary_counters,
                   "Diagnostic rejections changed ordinary dropped/filtered/rejected counters")
            report["identity_rejections"] = denied

            stage = "seventeenth_valid_tail_stops_at_sixteen"
            first_unclaimed = ctypes.string_at(p.arena.rows + 16 * 640 + 256, 96)
            for i in range(15):
                before = head(p); old_slots = region(p)[1]
                invoke(p, alt_caller, alternative=True)
                after = head(p)
                wanted = min(before["claimed"] + 1, 16)
                expect(after == dict(alt=before["alt"] + 1, true=1,
                                     claimed=wanted, mask=(1 << wanted) - 1, epoch=b.epoch),
                       "Diagnostic sample reservation exceeded cap or lost count/mask")
                if before["claimed"] == 16:
                    expect(region(p)[1] == old_slots, "Seventeenth valid tail overwrote a sample")
                pause_resume_preserves_diag(p, queue)
            final_head = head(p)
            expect(final_head == dict(alt=19, true=1, claimed=16, mask=0xFFFF, epoch=b.epoch),
                   "Final counts do not include both tails and rejected diagnostic triggers")
            expect(ctypes.string_at(p.arena.rows + 16 * 640 + 256, 96) == first_unclaimed,
                   "Diagnostic record escaped its first sixteen row slots")
            samples = [Record.from_buffer_copy(raw) for raw in region(p)[1]]
            expect([r.sequence for r in samples] == list(range(1, 17))
                   and [r.native_branch for r in samples] == [3, 4] + [3] * 14,
                   "Diagnostic slot sequence/tail tags changed")
            expect([r.projectile_generation for r in samples] == [3, 1] + [3] * 14,
                   "Diagnostic generation is not the observed pending phase")
            expect(all(r.epoch == b.epoch and r.creditor == b.local_peer
                       and r.target == 1001 and r.source == 1002
                       and r.owner == 71 and r.projectile_slot == 17
                       and r.target_kind == 1 and r.capture_flags == 0x14B
                       and r.armour == 4 and r.damage == 22 for r in samples),
                   "Diagnostic raw identity/qualification/DP fields changed")
            expect(ctypes.string_at(b.base, 160) == queue,
                   "Diagnostic group altered ordinary seed FIFO/header")
            report.update(final_head=final_head, samples=[record_dict(r) for r in samples],
                          valid_tail_triggers=17, total_tail_triggers=20,
                          sample_cap_and_publication_mask_verified=True,
                          first_unclaimed_slot_unchanged=True,
                          pause_resume_preserve_diagnostic=True,
                          ordinary_FIFO_and_pending_preserved=True)

            stage = "existing_configure_clears_diagnostic"
            records = b.drain()
            expect(len(records) == 1 and records[0].sequence == 1
                   and records[0].contact_ordinal == 0x7FFF,
                   "Ordinary consumer did not receive only its original seed")
            report["ordinary_seed_record"] = record_dict(records[0])
            configure = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64,
                ctypes.c_uint32)(p.addresses["configure"])
            expect(configure(b.base, p.arena.address, b.epoch, b.local_peer, 1) == 1,
                   "Owned quiescent configure failed")
            expect(ctypes.string_at(p.arena.rows, 32 * 640) == bytes(32 * 640),
                   "Existing configure did not clear all diagnostic storage")
            report.update(status="PASS", configure_clears_diagnostic=True,
                          accepted_ordinary_records=b.stats()["accepted"])
        report.update(owned_allocations_released=b.closed,
                      released_allocation_count=len(b._allocations))
    except Exception as error:
        report.update(status="FAIL", first_failure_stage=stage,
                      first_failure=f"{type(error).__name__}: {error}")
    report["elapsed_ms"] = (time.perf_counter() - started) * 1000
    destination = ROOT / "dist/hit-copy-tail-diagnostic-owned-20261013-v1"
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(out),
                      "first_failure": report.get("first_failure")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
