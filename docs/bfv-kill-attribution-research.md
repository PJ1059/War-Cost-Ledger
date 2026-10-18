# BFV Kill Feedback 技术核对（0.4.40）

核对日期：2026-10-14。来源是用户提供的 BFV Kill Feedback v1.6.1 ZIP，以及 [Nexus 作者页](https://www.nexusmods.com/helldivers2/mods/16927)。仅静态解包，没有执行、修改或安装该 MOD。

## 实际能力

该包使用 Stingray Lua / LuaJIT，经 Bingus Shared Loader 启动；击杀数据依赖 HD2Runtime 0.28.1 以上的事件接口。音效采用 LuaJIT FFI 调用 Windows winmm，图案、声音及多语言名称内嵌在单个约 31.7 MB 的 Lua 资源中。Ledger 已使用 HD2Runtime 0.30.3，不需要增加这些显示、音效依赖。

两类数据必须分开：

| 数据 | BFV 使用的 Runtime 接口 | 可证明的内容 |
| --- | --- | --- |
| 敌人身份、死亡和归属 | `entity_killed` | 哪个实体死亡、游戏把击杀归给哪个玩家；不含逐敌人的武器字段 |
| 武器／手雷／战备杀敌数 | `player_kill_credited.sources` | 10 Hz 采样间隔内，每个来源增加了多少击杀；不能精确关联到某个敌人 |
| 命中反馈 | `entity_damaged`，并记录已死亡目标 | 有效生命值变化；不会仅根据聚合命中统计把尸体当作新目标 |

BFV 将死亡队列与来源批次按顺序用于显示。一个批次恰好只有一个来源、且来源数等于总击杀增长时，显示该来源；多个来源时显示混合。缺失来源时 BFV 的文字使用“持续伤害”，但数据本身只证明来源未知，Ledger 不采用这一推断，也不把聚合来源绑定到某个重型／巨型单位。

## Ledger 的最小接入

Ledger 已在 `poll_stats` 中读取同一份 `stat_breakdown` 原生来源统计，将 `KILLS` 保存在 `state.weapon_stats[type].kills`。重型／巨型绶带使用独立的存活到死亡观察及敌人哈希目录；两条路径各自计数。

新增 `src/kill-source-attribution.lua` 是独立实现的官方事件适配器：

- 规范化 `player_kill_credited` 为单来源／混合来源／未知来源批次，保留已知来源类型、数量和未知数量。
- `per_victim=false`，不生成逐敌人的武器映射，不更改原有账单、武器总数或绶带计数。
- 只接受本地玩家事件；使用已有 `SOURCE_NAMES` 中文名称；限制来源列表至 64 项，拒绝数值不一致的批次。
- `subscribe(hd2.events, MOD_ID, callback)` 使用固定事件订阅 ID。任务开始时调用 `reset()`，需要时将 `latest` 与现有 `state.weapon_stats`／分类击杀数据并列核对。不能再把该批次累加到已有武器或总击杀，避免重复计数。

`tests/test_kill_source_attribution.lua` 在游戏自带 LuaJIT 中通过；覆盖单来源、混合、字段缺失、未知类型、重复类型合并、来源数量失配、本地玩家门槛、队列上限及订阅回调。此测试不代表实战事件已验收。

## 静态证据

ZIP SHA-256：`60870291adfaf7fdbb2eac045bd547af87f6cd10a39fc96dfb5c09761f8581a2`。

只读解包的资源：Lua `93E5D0431533CBC9`，资源类型 `A14E8DFA2CD117E2`。原始包、解出的源码及资源清单保存在被 Git 忽略的 `dist/bfv-weapon-attribution-0.4.40/`。

源码定位：2711–2715（批次与单个死亡的区别）、2915–2999（顺序合并及来源选择）、4950–4972（尸体／生命值门槛）、5026–5074（击杀和统计入口）、5138–5147、5226–5278（官方事件订阅）。

Runtime 官方参考：`examples/projects/PlayerKillCreditedExample/README.md`、`runtime/event_sources.lua` 299–365、`docs/event-scripting.md` 的 Source attribution 章节。官方文档同样明确区分逐实体归属与按来源统计。

## 来源边界

Nexus 页面要求复用资产或修改该文件先征得作者同意，且不允许转载原文件。Ledger 不复制 BFV 的 Lua、音频、图案或名称表，不新增 BFV 依赖；适配器依据已有 HD2Runtime 的公开接口独立实现。BFV 包只用于本机只读技术核对。
