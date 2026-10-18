# 0.4.51 火焰、毒气与未知来源溯源

核对日期：2026-10-16。本轮只读检查实际账目、已有参考 MOD 和匹配构建代码材料，没有改写历史账户，也没有升级 Runtime。

## 实际未知数据来自哪里

本轮账户快照的第 34 局：1145 杀，原生按来源统计的明细合计 892，另有 253 没有原生武器来源。已识别的凝固汽油弹火力网 164 杀、G-8 焚烧弹 2 杀，与该局 `ignite=166` 对得上。说明已知火源没有漏名；这 253 杀没有附带逐目标的武器或元素记录，不能全称为火焰／毒气。

14 条既存死亡记录中，5 条在身体已移除后读取失败，5 条被旧规则拒绝为来源冲突，4 条归为自身。5 条冲突的完整 owner 类型分别已能映射为掠食追猎虫、狂暴武斗虫、吐酸泰坦、阿尔法指挥官、虫窝护卫。旧记录缺少当时 owner 实体和最终伤害元素，本轮不倒填或覆盖它们。

只读原始检查结果在本机忽略目录 `dist/combat-fixes-0.4.51/fire-gas-raw-account-review.json`，含账户 SHA、分局核对和失败原因计数。该文件可能包含本地会话信息，不随发布包分发。

## 采用已有原生死亡原因字段

匹配构建的 `health_cause_setter` 材料已在 2026-10-11 捕获，未执行该函数：

- `dist/fire-source-code/fire-code-20261011T055421Z-39817b24.bin`，SHA-256 `c58fc32a9158111ed1a0aa4cfc288232f360948b21870af5abb2ba806a6365ec`。
- 完整可达反汇编 `dist/fire-cause-setter.asm`，入口 `0x925D80`，返回 `0x925F08`。
- DLL SHA-256 `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E`。

该函数先核对 Health descriptor 的 owned 位，在 life 上升且新 life 为 2 时，把本次 kind、element 与 life 写到同索引的 extension。

| RVA | 固定字节 | 作用 |
| --- | --- | --- |
| `0x925E38` | `f6411401` | descriptor owned bit0 |
| `0x925E42` | `488b8360100000` | manager+0x1060 extension 指针 |
| `0x925E49` | `486bfe1c` | extension 步长 28 |
| `0x925E58` | `448974070c` | extension+12 写 life |
| `0x925E99` | `89040f` | extension+0 写 kind |
| `0x925EC9` | `89440f04` | extension+4 写 element |

`kind=2, element=1` 用作燃烧提示，`kind=2, element=5` 用作毒气提示，与参考 DeathSourceNotice 的死亡元素字典一致。kind=2 本身不是燃烧；例如 element=4 是流血，不补成火焰。owned 是 Health 模拟权威，击杀仍需走既有本人 creditor 或本人累计额度观察。

`kill-observer.lua` 只在实际被观察到的死亡上读取这段字段，输出：

```lua
damage_cause = {
  kind = 2, element = 1, life = 2,
  owned = true, current = true,
  source = 'native_health_extension'
}
```

需要上述 PIN、当前 descriptor 的完整实体与类型、owned 位、record life=extension life=2、前后相同的 extension 和 descriptor，以及当前索引仍指向同一 descriptor。每轮最多补充 8 次；初次 PIN 为 6 次／27 字节，每个成功候选最多 5 次／112 字节，总额外上限 46 次／923 字节，沿用 2ms 软时间预算。读取失败或预算不足只省略 `damage_cause`，不会丢掉已有击杀、改写费用或额外增加绶带。已经失去 Health 的尸体不会借用别的 extension。

`native-death-reader.lua` 为玩家死因读取相同的表，沿用原 96 次／4096 字节／2ms 软上限。`death-observer.lua` 可以保留“燃烧／毒气”伤害类型；未识别到攻击者时才将其作为环境死因，已有队友／自身／敌人身份仍保留。不声称取得了原生 fatal callback，也不由火焰武器定义猜测每次死亡。

## 修正错误的来源冲突

已有 ApplyDamage 代码证据显示，没有新 creditor 的伤害会保留旧 `Health.lastCreditor`；`lastOwner` 则记录本次 owner。Runtime 的伤害事件 attacker peer 也来自这个 creditor，不是第二个独立的攻击者证据。

因此，本轮仅在 owner 实体不是任何玩家 avatar、并且其完整类型精确映射为敌人时，优先保留该敌人身份，不因残留 creditor 而全部拒绝。实际 owner 是玩家 avatar 却与 creditor 不同、没有精确敌人 owner 时伤害 peer 与 creditor 不同，以及死亡后 owner／受害者身份变化，仍保留为冲突。旧历史的明确拒绝标记不回填。

同时给未来 `reader_failures` 增加最多 16 种原因计数和最近失败原因，避免只有一个总数、无法区分身体移除、预算和布局失败。

## 验证与实际边界

专项通过 38 组死因观察检查、14 组原生只读内存检查，以及完整生产 kill observer 的 PIN、owned、life、索引、读取变化和每轮 8 次上限检查。源测试只使用本进程拥有的合成内存。

重新运行 `tools/bench-kill-observer.py` 更新 `docs/kill-observer-performance.json`。128／1024／4096 活体的平均耗时约 0.020／0.184／1.018ms；4096 条记录的 p99 约 3.509ms，表明 2ms 是软预算，读大块内存和系统调度仍可超时。实际游戏 FPS、真实死亡字段覆盖率及火毒实战提示尚未验证。

无最终字段、非 owned、Health 已销毁或读取跨变更的死亡仍可能没有元素。武器来源提示仍是客户端近似配对；具体火焰武器名称与原生元素“火焰伤害／毒气伤害”有不同证据，不能用当前持枪或既有未知总差额制造历史明细。

## 后续定点核对：G-8 留下的地火

用户进一步指出多数现场未知来源来自 G-8 的地火。因此本轮另外核对了匹配构建的静态定义，并在仍运行的原任务做了两次固定本人统计读取，没有要求额外投雷或击杀。

静态链为 `5C14F27759DD3BE0` → `ExplosiveComponentData` record 23 的 +36 → `ExplosionType=32` → 当前 `ExplosionSettings` row 82。爆炸行 +4 是 `DamageInfoType=339`，直接爆炸伤害为 20/AP0；状态槽含 fire 强度 100，共享 fire 定义持续 3 秒。

地火另由该爆炸行 +96 的 `FireTemplate=4` 创建。此成员类型哈希 `0x1ABF81A2` 与当前类型库的 `FireTemplate` 精确一致，Filediver 的枚举将 4 命名为 `Massive`。+100 的 `StatusEffectTemplateType=0`，G-8 本体也没有独立的 Area／Fire 组件。+56 的 `D225FFDD7C602994` 是粒子特效路径，不是新的击杀武器资源；不能把它合并成“G-8 地火”来源哈希。

两份相隔约 0.2 秒的本人原生统计完全一致：G-8 来源有 `dealt_damage=2765`，没有 `dealt_kills` 条目；无来源主表有 `dealt_damage=23618, dealt_kills=60`。这证明现场确实出现了“G-8 伤害有来源、部分击杀没有具体武器来源”的数据形态，缺口不只是名称哈希。读取使用 13 条现成统计／玩家 PIN，合计 42,476 字节／52 次读取／约 256ms，账户未修改；本机材料为 `dist/combat-fixes-0.4.51/g8-fire-live-stat-snapshot.json`。

目前没有从公开 SDK 闭合“地火区域实例 → 原始 G-8 创建者”的逐区域字段，也没有本次 60 个主表击杀各自的原因。因此本版优先用当前目标自身的死亡元素显示“火焰伤害”，不把它们全部写成 G-8。进一步的合理近似可以复用既有统计读取：只有目标为本人的原生火焰死亡、近期本人 G-8 来源伤害发生增长时，才把该提示归给 G-8；整场累计伤害或当前携带 G-8 都不能单独触发这条关联。此近似尚未在本轮新增统计逻辑。
