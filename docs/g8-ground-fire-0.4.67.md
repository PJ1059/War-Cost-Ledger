# 0.4.67 地火漏源诊断与修复

## Diagnosis

Synthetic replays reproduced three source-attribution gaps. Personal mission/account observations and raw diagnostic captures are excluded from the public source.

## 已稳定复现的三个缺口

1. **首次看见目标已经死亡。** 0.4.66允许这类目标通过原生本人击杀额度确认死亡，但区域来源分支又要求`damage_observed=true`，位置读取也要求已见过实际扣血。因此已有核验致死火元素的首见死亡仍永久未知。修复只允许`first_seen_dead + life=2 + kind=2 + element=1`进入原有区域匹配；不造活体时间、不建立可继承的伤害链，原生额度门槛不变。
2. **本人阵亡/换avatar清掉仍在燃烧的火区。** 先前每次life epoch变化都会清空所有爆炸上下文。新`life_changed(now)`只保留同一世界、同一本人peer中已观测的本地fire事件，保留原始事件时间、半径和截止时刻。普通爆炸上下文仍清除，目标伤害链仍受epoch约束；世界、peer变化或真实读数间隙仍全清。没有延长G-8的27秒窗口。
3. **等待增援时每轮重复开启“新生命”。** `poll_health`每100ms看见同一个死亡状态就调用`new_life()`；来源观察器随后每轮清掉尚待使用的原生击杀额度，尤其使无creditor/首见死亡无法完成归属。现在对Health/lifecycle死亡锁存一次，并与可能先到或后到的原生阵亡计数合并。未匹配的Health死亡计数可跨复活保留，迟到的旧计数不会再次清掉新avatar的来源链；真实复活/新avatar仍开始新epoch。阵亡总数和无法排序的成就连杀中断照常处理。

## 保留的证据限制

活体Health extension的kind/element仍不可靠；只能使用核验过的死亡`life=2`数据。G-8仍要求真实本人爆炸事件、目标位置、致死火元素、范围/时间以及本人creditor或既有原生本人击杀额度共同成立。明确的已知武器/敌方来源优先，不能因靠近G-8改归。首次看到旧尸体的初始基线仍不奖励。

10m取自原生爆炸外半径，是有界关联范围，不是真实地形火焰轮廓；27s是上一版记录的社区地火池报告推断窗口，不称作核验原生寿命。此次没有改大半径/时限，没有把所有火焰都归G-8。喷射类地火仍缺少核验创建者/落点链，原创建代码片段只证明位置/template/peer派生值，不能证明武器。

## 固定大小诊断

`state.kill_observer.ground_fire`与现有`last_mission.kill_observer`快照共用，只有固定数值字段，没有新增逐敌日志、坐标轨迹或无限增长的哈希表。数字为**解算尝试次数**，可能同一目标多次，不能当新增击杀。

| 字段组 | 用途 |
| --- | --- |
| `events_seen/local/foreign/uncredited/forwarded` | 精确G-8爆炸事件是否到达callback、本人归属是否存在、是否转交resolver |
| `event_mission_inactive/missing_source/missing_radius/not_local/rejected` | callback没有转交的原因 |
| `fire_contexts/g8_contexts/contexts_expired/contexts_evicted/life_fire_retained` | 火区是否建立、是否固定到期/达到64条缓存边界、跨生命保留 |
| `death_observations/death_cause_missing/fatal_nonfire/fatal_fire_attempts/first_dead_fire_attempts` | 是否收到可信致死火元素，是否首见死亡 |
| `known_source_kept/typed_source_kept/unreadable_fire` | 已知来源优先或同目标读取失败 |
| `no_fire_context/no_position/credit_rejected/typed_rejected/outside_area` | 区域解算缺失的关键条件 |
| `fire_matched/g8_matched` | 区域补源成功的尝试 |

`kill_observer.life_changes`是额外固定计数，用于确认等待增援不会每轮重置生命epoch。诊断不改变费用、击杀总数或原生历史。

## 回归证据

- `tests/test_g8_first_dead_067.lua`：纯resolver，首见fatal火死亡、固定时限、跨life与所有原有门槛。
- `tests/test_observer_g8_first_dead_067.lua`：真实游戏LuaJIT执行既有owned-memory Health fixture；首见/缺creditor/没有原生额度、非火、越界、缺位置、过期、旧基线、不同peer/世界、读间隙；跨本人epoch仍按原时限。
- `tests/test_addon_g8_first_dead_067.lua`：built addon公开爆炸事件到击杀提示、来源总数、敌人关联、火焰绶带、生涯保存/重载；本人阵亡和新avatar情况下保持原火区。
- `tests/test_addon_g8_death_wait_067.lua`：Health与原生阵亡计数任意先后、lifecycle重复死亡、增援等待的原生额度、迟到计数在复活之后、下一场重置，保留阵亡总数/成就中断。

三项原缺口均分别在修改前源码/回放上失败，记录于本地`g8-first-dead-before.log`、`g8-respawn-before.log`、`g8-death-wait-before.log`；修复后的相同输入通过。旧G-8、同目标连续链、空投仓/孢子自爆、原生预算及来源resolver回归保留。

这是离线有证据的缺口修复，尚不证明新版本实战能识别所有G-8地火死亡。下一局的固定聚合计数可区分事件缺失、元素缺失、范围和归属条件，避免再次只增加推断范围。

## English

Fix three reproducible ground-fire gaps without extending the existing G-8 radius or time window: first-seen exact fatal Health records can now use verified fire-area evidence; same-peer/same-world fire contexts survive an avatar death with their original expiry; repeated dead Health/lifecycle observations no longer reset the native local-kill credit queue every poll. Health death observations and delayed native death counters are merged, while revival still starts a new target-chain epoch.

Known sources remain authoritative. Fire inference still requires a local observed event, verified fatal fire element, real target position, bounded area/time and local creditor or the existing native local-kill quota. Live Health element bytes are never used. Old records are not rewritten. Fixed-size aggregate diagnostics distinguish missing events, cause/position/provenance failures and successful area matches; they are resolution attempts, not additional kills. Offline byte-fixture replays do not establish complete live-game coverage.
