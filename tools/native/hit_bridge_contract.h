/* Owned-process prototype ABI; no gameplay producer/installer is implemented.
 * Uses published structural research from HD2Runtime by SkyeShade:
 * https://github.com/SkyeShade/HD2Runtime
 * Record fields are a proposed observation contract, not native game offsets.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

/* Proposed OBSERVER enums, never native game enums. */
enum HD2HitObserverBranchV1 {
    HD2_HIT_BRANCH_UNKNOWN = 0,
    HD2_HIT_BRANCH_NORMAL_FINAL = 1,
    HD2_HIT_BRANCH_PHYSICAL_SUCCESS = 2
};
enum HD2HitObserverCaptureV1 {
    HD2_HIT_DIRECT_VERIFIED = 0x01,
    HD2_HIT_FULL_PEER_VERIFIED = 0x02,
    HD2_HIT_SELECTED_AP_VERIFIED = 0x04,
    HD2_HIT_ARMOUR_VERIFIED = 0x08,
    HD2_HIT_DEFAULT_CUSTOM_KNOWN = 0x10,
    HD2_HIT_FINAL_FORCE_KNOWN = 0x20,
    HD2_HIT_TARGET_HOSTILE_VERIFIED = 0x40,
    HD2_HIT_AP_DELTA_VERIFIED = 0x80,
    HD2_HIT_SUPPORTED_MODE_VERIFIED = 0x100
};
enum HD2HitObserverEffectV1 {
    HD2_HIT_FORCE_HITINFO = 0x01,
    HD2_HIT_FORCE_PROJECTILE = 0x02,
    HD2_HIT_CUSTOM_CURVE = 0x04
};
enum HD2HitObserverTargetV1 {
    HD2_HIT_TARGET_UNKNOWN = 0,
    HD2_HIT_TARGET_HOSTILE = 1
};

typedef struct HD2HitObservationV1 {
    uint64_t sequence;              /* queue assigns, never taken from game */
    uint64_t epoch;
    uint64_t creditor;
    uint64_t projectile_context;
    uint32_t projectile_slot;
    uint32_t projectile_generation; /* requires producer proof; zero if absent */
    uint32_t contact_ordinal;       /* producer contact identity, not victim dedup */
    uint32_t target;
    uint32_t source;
    uint32_t owner;
    uint32_t effect_flags;          /* forced/custom paths must remain explicit */
    uint32_t native_branch;         /* proved branch identity, not AL alone */
    float selected_ap;
    float armour;
    float factor;
    float damage;
    uint32_t attack_kind;
    uint32_t target_kind;           /* unknown allowed; enemy-only not inferred */
    uint32_t capture_flags;         /* per-field validity */
    float ap_delta;                /* native f32 SUBSS result, only with validity */
} HD2HitObservationV1;

/* All following functions are proposal names, not current Runtime exports.
 * Publish is constant work, no Lua/heap/file/system calls on contact.
 * Drain copies <=64 records per call on the Lua update thread.
 * Overflow or contention increments dropped; completeness must then be false.
 * Creditor comparison must use uint64 or two uint32 halves, never a Lua double.
 */
uint32_t hd2_hit_publish_owned(void *bridge, const HD2HitObservationV1 *record);
uint32_t hd2_hit_drain_owned(void *bridge, HD2HitObservationV1 *out, uint32_t limit);

/* The owned normal-final replay snapshots observed register args before native
 * processing, then restores incoming RSP/GPRs/XMM0..5 and tail-jumps to an owned
 * original. A tail transfer preserves all extra stack arguments and opaque
 * RAX/XMM returns; this does not provide a live hook or full native signature.
 * HitInfo offsets witnessed in the matching actual code: creditor +110,
 * owner +100, target +20, armour +50, kind +00, force byte +73.
 * DamageValues final amount +00 and armour factor +04 are copied as raw bits.
 * Effective selected AP/custom curve/hostility are context validity
 * requirements, never inferred from factor by this replay wrapper. The
 * certified 13AD88B caller profile can copy ProjectileInfo+FC bit0 from
 * entry RAX; ordinary FFI callers never enable this profile.
 * A canonical CALL wrapper follows Windows x64 ABI: incoming arithmetic flags
 * are volatile (original ProduceDamage SUBs RSP before using conditions), DF=0
 * is required; original callee's returned flags/results pass directly back.
 * The AP-stage owned CALL fixture is not an inline game trampoline and has
 * not proved live EFLAGS/MXCSR preservation for the original MOVSS site.
 */

#if defined(__cplusplus)
static_assert(sizeof(HD2HitObservationV1) == 96, "observation ABI size");
static_assert(offsetof(HD2HitObservationV1, creditor) == 16, "creditor ABI");
static_assert(offsetof(HD2HitObservationV1, selected_ap) == 64, "AP ABI");
#endif
