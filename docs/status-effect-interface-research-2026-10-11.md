# 点燃／中毒成功施加接口研究 · 2026-10-11

本轮向目标侧的**当前有效状态**继续追踪，新增了状态查询入口、实际施加入口、毒气持续区域路线及下一步反汇编范围。当前仍没有可交付的原生成功施加计数：敌人状态实例的 active、instigator、结束／刷新字段尚未取得结构证据。本轮只读源码、SDK、磁盘游戏文件和已有采集状态，仅新增本文；没有启用新地址读取、调用 `hd2.status.apply`、修改游戏状态、启动游戏或部署 MOD。

## 1. 来源与本机材料

核对时上游默认分支 `master` 的 tree SHA 仍为 `dcd996daca2573443956c07252c55c2d86dd0320`。本地 Runtime 0.30.3 源码目录：

`external/HD2Runtime`

下文源码行号均指这个提交中的实际文件行号。对 `research_event_actions.py`、`research_avatar_fields.py`、`research_status_susceptibility.py`、`runtime/event_world.lua`、`domains/event_natives.lua`、`docs/events.md`、`docs/custom-stratagems.md` 和 `sdk/StatusEffectCatalog.json`，逐字节与 GitHub raw primary 来源核对一致。

本机磁盘文件匹配 SDK 的 build `F5FEE03DCFDB`／Steam build `25480438`：

| 文件 | 本轮实读 SHA256 |
| --- | --- |
| `G:/SteamLibrary/steamapps/common/Helldivers 2/data/game/game.dll` | `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` |
| `G:/SteamLibrary/steamapps/common/Helldivers 2/bin/helldivers2.exe` | `F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06` |

但匹配磁盘哈希不等于获得了运行后的代码。只读 PE 节表显示 `game.dll` 有 `.winlice`／`.boot` 节；上游也明确磁盘 DLL／EXE 加壳。`QueueStatusRequest` 的 RVA `0x129F170` 不在其对应节的磁盘正文范围内；`0x699E40` 与 `0x69B1F0` 对应的磁盘字节不能作为上游运行时函数的已解包指令。没有运行加壳文件或任何第三方解包软件。

本轮检查以下目录未发现 `.hd2snap`：本地研究源码树、`external/hd2-integration-research`、`external/HD2Runtime`。预期快照目录中的现有 `control/status.txt` 记录 `runtime_version=0.30.3`、`captures=0`、`end=1`，只证明以前启动过采集控制且已结束，不能充当内存快照。依据：[上游 build profile](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/schemas/build_profile.json#L6)、[解包图像的研究前提](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_state.py#L4)。

## 2. 点燃／中毒的原生身份

这里的“中毒”按玩家毒气效果处理。目录中的同名变体是不同原生状态，展示计数时归为同一类别；混乱是毒气的伴随效果，不额外记一次中毒。`appliedBy` 是目录中哪些攻击配置使用这个状态，**不是运行中某个敌人的施加玩家**。

| 展示类别 | semanticId／本 build 原生 type | 定义持续时间 | 目录证据 |
| --- | --- | --- | --- |
| 点燃 | `fire`／5 | 3 s | 玩家燃烧弹药、喷火、激光以及火焰战备等使用 |
| 点燃 | `burning_heavy`／32 | 1 s | 飞鹰凝固汽油弹、轨道汽油弹、EAT-700 使用 |
| 中毒 | `gas`／42；`gas_2`／43 | 6／10 s | 前者含毒气战备与 G-4；后者为 TX-41 |
| 中毒伴随，合并去重 | `gas_confusion`／44；`gas_confusion_2`／45 | 5／9 s | 与相应毒气使用者一致，没有持续伤害定义 |
| 暂不纳入 | 独立 `poison` | 6 s | `appliedBy=[]`、`slotUsers=0`、`attachTier=other_system`，目录标为实验性 |

不增加未经证明的 `burning` 别名。`poison_vulnerability` 是另一个系统状态，也不当作玩家毒气成功次数。数字 type 只对上述 build 有效，身份应以表中类型自带名称重新核对；SDK 明示不同 build 会改编号。定义持续时间不是敌人实际剩余时间，不能用“施加请求时间＋3秒”伪造熄灭。

来源：[状态目录 fire](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/sdk/StatusEffectCatalog.json#L154)、[heavy](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/sdk/StatusEffectCatalog.json#L843)、[gas 至 confusion_2](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/sdk/StatusEffectCatalog.json#L1139)、[独立 poison](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/sdk/StatusEffectCatalog.json#L1792)、[native type allowlist 的生成](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/generate_event_natives.py#L365)、[编号会变化](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_status_effects.py#L16)。

## 3. 新找到的目标侧路线

### 3.1 当前状态查询，不需要数申请

`scripts/research_avatar_fields.py:97–98` 证明原生 stamina 更新把 `stim_stamina` type `0x1A` 交给 `0x69B1F0` 查询；`:125–126` 的移动更新对 `death_march` type `0x3B` 也调用同一入口。它是目前最小的 **has-status 候选入口**：反汇编其函数体，可找出实体到状态实例的映射与当前有效状态判定，从而避免依赖每帧即清空的申请队列。

这个证明只覆盖两处调用及作者标注的“has status”，没有公开该函数的完整参数、状态集合偏移、返回位含义、敌人是否走同一布局或施加者字段。**不直接执行原生函数**；下一步只从快照解包代码重建它读取的链。`scripts/research_booster_native.py:144` 另列出 `0x69AEC0` 为状态相关候选 callee，但没有证明它是删除、结束或刷新，不给它提前命名。

来源：[has-status 调用证据](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_avatar_fields.py#L91)、[第二处查询](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_avatar_fields.py#L120)、[其它状态 callee](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_booster_native.py#L144)。

### 3.2 阈值与刷新实际入口

已知全局状态管理器是 `[game.dll+0x3326620]`。申请 `0x129F170` 会检查目标有状态实例及 `0x6994F0` 的接收条件；世界更新 `0x13F7D5E → 0x12A6EF0` 消费，路由 `0x129F2A0` 用 `0xB894B0` 判断目标是否由本机拥有：本机所有则调用 **`ApplyStatusEffect 0x699E40`**，否则 `0xBEBDE0` 发给拥有目标的机器。

`0x699E40` 是下一步应定位“累积量是否跨阈值、首次有效状态写入、刷新是否改计时或归属”的函数体。上游文本确定申请量是 buildup，达到目标门槛才触发，重复施加通常刷新，仅 `poison_vulnerability` 叠层；但生成的 pin 表没有公开这些状态实例成员的读写指令。请求已发出、`hd2.status.apply` 返回 requested 或命中攻击带 fire 配置，均不足以当成功事件。没有把这些写接口接入本项目。

来源：[请求与消费 pins](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_actions.py#L405)、[实际 ApplyStatusEffect、阈值与刷新语义](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/docs/events.md#L462)。

### 3.3 毒气云每 tick 的施加不是新中毒

上游轨道毒气路线补足了此前只研究队列的缺口：炮弹 197 → 爆炸 82。爆炸伤害处理 `0x13C29E0` 在引爆时一次施加 `gas` 与 `gas_confusion`；爆炸再经 `0x13CD320` 建立 template 16 的持续区域，15秒内反复走 `0x6963E0 → 0x13CF3E0 / 0x13CE680 → 0x696820 → 0x699E40`，随落差权重继续施加两个状态。

因此中毒不能数爆炸次数、云内伤害 tick、两个状态之和或申请量。`0x13CC050` 是**区域本身**的到期路线，不等于敌人 `gas`／`gas_confusion` 已结束；离开云后的敌人仍需读自己的状态周期。这个持续区域是记录而非敌方实体，也不能拿它的创建次数冒充中毒敌人数。

归属尤其仍有缺口：`proof/GasEatExample/README.md:113–114` 区分了火箭／爆炸击杀归属和毒气云 DoT instigator，后者明确未追踪。不能从爆炸的 creditor、最后受伤者、当前手持毒气武器或云的来源名称推断这次敌人状态归本人。

来源：[原生毒气链](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/docs/custom-stratagems.md#L1721)、[云体归属缺口](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/proof/GasEatExample/README.md#L109)。

### 3.4 敌人配置中的 susceptibility 不等于运行中状态

`StatusEffectReceiverComponentData` 是敌人类型配置，46,600 字节，含8个 zone；每个 zone 有33个、步长176字节的 susceptibility 配置。条目 `+140` 是 susceptibility type，`+144/+148` 是一对值，`+168/+172` 是倍率候选值。作者比较了不同敌人，证明这对值随目标类型变化；名字被裁掉，尚不知道哪个条目对应火、气，也不知道二元值是门槛、时间或抵抗。

不能把这里的二元值当“当前剩余时间”，也不能把 susceptibility type 当 StatusEffectType 直接索引。它提供反汇编 `0x6994F0`／`0x699E40` 的结构核对点；先追读写，再赋予语义。来源：[目标接收配置原始布局及未知项](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_status_susceptibility.py#L6)。

## 4. 每个字段的可用程度

“已知参考”指上游固定 build 的公开源码证据，不等于本项目已经在游戏中读到。所有新增读取应保持关闭，直到本机运行后图像的字段链和指令字节取得证明。

| 要读的项目 | 已知参考／当前能力 | 必须补的证据 |
| --- | --- | --- |
| 敌方身份 | 本项目 `src/kill-observer.lua:69–83` 已有 health 哈希遍历、entity ID、descriptor pointer、type 缓存 | 新状态读取复用同一身份；generation 尚无原生字段证明，不能把离线接口提供的 generation 说成已找到游戏字段 |
| 实体是否存活 | 同一次 health 记录可读 life；原生 descriptor 可提供 unit／goid／owned | 敌方阵营来自已有类型表；本机 owned 不等于“本人施加” |
| 当前有效状态 | `[game+0x3326620]` 管理器；`0x69B1F0` 查询候选 | entity→实例 map、总量／容量、实例 stride、active bits／状态集合、zone 合并规则全部未知 |
| 原生状态 type | 5、32、42–45 与语义名称已有 allowlist 证据 | 本机表携带 type／名称与固定 build 一致；不得向函数传未知编号 |
| 累积与触发 | 申请目标 `+0`、type `+4`、buildup `+0x14`；`0x699E40` 处理候选 | 目标当前 buildup 的位置、实际阈值位置、成功分支和抵抗／免疫返回值未知 |
| 施加玩家 | 申请函数第5参数是 u32 instigator；stun 自有调用传实体 | 队列中的 instigator 存储偏移未公开 pin；状态实例是否持有它、首次／刷新会否覆盖、实体→owner／peer 的链待追；云体 DoT 明确未追踪 |
| 周期开始 | 没有已公开开始序号或时间字段 | `0x699E40` 首次写 active 与开始字段；是否有自增 epoch／状态实例 ID 待追 |
| 刷新 | 上游语义说明一般刷新 | timer 延长规则、是否更新 instigator、刷新序号／周期 ID 是否改变待追 |
| 周期结束 | `0x13CC050` 只证明持续区域到期；`0x69AEC0` 仅是候选 | 敌人计时／结束位、熄灭／离开气体／死亡的清理路径、移除与换槽待追 |
| 主机／客机 | 有本地处理／发给权威机路线 | 客机可见的 active 与归属是否同步、时序延迟、远端施加行为未实测 |

本项目缓存现在是 `known` 局部变量，不是其它模块能直接访问的公共接口；后续沿同一遍历传有限目标记录／复用原始块即可，不能声称目前已经可调用缓存 API。缓存 pointer 变化会丢弃旧条目；相同地址复用的情况仍需完整生命周期证据。原生 `goid` 也不能未经证据直接叫 generation。依据：[Runtime descriptor 与 health 方法](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/runtime/event_world.lua#L121)。

## 5. 成功次数的判定边界

只有证实目标是敌人、状态由本人施加、目标由非生效变为生效，才增加一次。一次范围攻击使8个敌人新进入燃烧，算8次；持续伤害与持续刷新不增加。`fire`／`burning_heavy` 的联合周期算一次；毒气四种状态的同次联合周期算一次，不能因混乱早一秒结束就新开中毒周期。

其它玩家首次施加、本人仅刷新时不追认本人成功；同一周期归属字段后来被改写也不能追加一次。没有证明完整归属时保持未验证，不补猜测归属。敌人消失、数据读取失败、未在轮转中检查、切换世界不等于状态已结束；状态结束与之后新的成功必须都有有效证据。第一次看到已经 active 的目标应建立基线，不能追补此前点燃。

若没有原生开始序号／可保留的变更记录，轮询只能提供“观察到的成功次数”；不能称全量精确统计。短周期在两次读取间开始并结束，或结束后又开始而两次都是 active，会漏记。这个漏记边界与 FPS 预算应同时列出。

## 6. 帧数约束与可验证性能方案

本轮没有游戏新增开销；没有 FPS 实测结论。`docs/kill-observer-performance.json` 现有数值来自 LuaJIT 与合成缓冲区的只读调用，排除了渲染、其它 MOD、真实网络及新实体突发，不能作为新增状态接口的帧数证明。

后续设计顺序：先证明字段，再确定读取窗口及上限；优先复用 `kill-observer` 每秒5次的 health 表／descriptor 身份缓存。读取状态仅使用已验证实例链，预分配 `native_view.slot()` 缓冲区；该模块支持 `read_into`，每个块上限1 MiB，不逐实体新建字符串和表。主机／玩家信息复用当前10 Hz观察。没有经过证明的短变更记录时，不启用全场逐帧扫描。

| 限制／指标 | 可落地验证 |
| --- | --- |
| 首次字段探针只观察4–8个已确认敌人 | 10 Hz、固定 buffer 和有界读取；字节／调用上限须按证明后的布局配置，先排除请求、tick 与刷新误计 |
| 后续复用已有发现遍历 | 每 poll 最多64个新 descriptor，沿用 current health 的4096 live／16384 hash槽硬上限，不额外重新查全部类型 |
| CPU与读取都要有硬上限 | 将状态遍历纳入同一2 ms检查预算；每64条检查并续游标，另设每 poll 的字节、调用、状态条目上限；预算是检查点而非绝对实时保证，单次读取耗时也要记录 |
| 不补读慢帧 | 频率门限到期只读一次，超时延后，不进行追赶循环；读取断档只标 incomplete，不制造 ended／新周期 |
| 覆盖与延迟一起报告 | 记录每目标实际重访间隔、active观察数、可证实周期数、漏掉／未验证与预算停顿；不能只报平均 CPU |

特别是不能把“64个新 descriptor”误解为“每次最多64个已知敌人的状态就足够”。若按64个目标轮询、5 Hz，4096个目标一次完整重访需要 `4096 / 64 / 5 = 12.8 s`，明显长于 `burning_heavy` 的1秒定义持续时间。后续必须根据已证明的紧凑 active 集合／变更序号选择批量读，或明确缩小为已覆盖目标的观察统计；不以静默漏计换帧数承诺。

离线基准用同一 LuaJIT、真实 `ReadProcessMemory` 自读合成缓冲区，与关闭状态观察的基线比较：0／8／128／1024／4096实体、没有状态／全active／新实体突发、刷新洪峰、槽位换位、失败读取及慢帧。输出新增 read calls／bytes、均值／p95／p99／最大轮询耗时、缓存容量、GC增长与incomplete；以断档不重复计数为必要条件。通过后再实机开／关做相同地图与战斗密度对照，沿用性能记录器比较帧时间p50／p95／p99和1%低帧，同时记录状态观察自身耗时。CPU读数小不能推出帧数“零影响”。

依据：[可复用有界 native_view](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/runtime/native_view.lua#L1)、[Runtime metrics](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/runtime/metrics.lua#L1)；本地 `src/kill-observer.lua:15–66`、`src/addon.lua:495–528`、`docs/kill-observer-performance.json`。

## 7. 唯一下一验证点

**取得一份匹配本 build 的任务内快照，先只重建 `0x69B1F0` 的 entity→active-state 读取链。** 完成标志是明确 map／容量／stride／active字段，并由创建、查询、删除三个方向的指令字节及至少一个真实实例互相核对；不要先接总计数。

现有官方 Armed Capture 已有本项目准备与安装记录，可复用现有 `tools/objective-capture.py`／`docs/objective-verification.md`。本轮没有启动采集。下一次用户正常进入任务、已有采集控制 heartbeat有效时，可从项目目录运行同一工具，标签用 `status-host-baseline`，无需新增安装或开自动采集。

完整 `.hd2snap` 要逐区间读取，常需1–4分钟，**不是瞬间抓取**。第一份的主要用途是得到运行后的解包代码和稳定实例链，不能要求3秒燃烧在整个采集过程不变，也不能把不同区间的状态／归属拼成一次成功。得到链之后，再制作仅4–8目标的连续只读探针，用正常武器施加作时间序列，依次验证首次生效→持续刷新→停止施加后有效结束→再施加；再加两个玩家竞争归属和主机／客机对照。

若 `0x69B1F0` 的 active 链得到证明，下一个代码范围才是 `0x699E40`：跟踪 instigator、跨阈值成功写入、timer刷新和结束写入；最后沿 `0x696820` 与 volume创建／消耗路线追毒气来源。所有步骤均只读，不调用 apply动作来生成测试状态。需要观察本人点燃／中毒时，由正常游戏攻击产生事件。

依据：[官方手动采集与非瞬间格式](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/docs/snapshots.md#L49)。

## 8. 本轮验证结果

- **已验证通过**：8份关键本地文件与上游固定提交逐字节一致；本机两份磁盘游戏文件哈希与 SDK profile一致；原生 fire／gas变体、查询／施加／持续区域路线及明确未知项有 primary出处。
- **未验证**：本项目读取敌人当前有效状态、状态实例施加者、实际周期开始／刷新／结束、多人同步、完整成功次数及真实 FPS。
- **当前缺少材料**：匹配 `.hd2snap` 中的已解包函数与真实状态实例。匹配磁盘 binary 已有，但不能替代运行后图像。

本地变更只含本文；没有新游戏读取或游戏状态变化。
