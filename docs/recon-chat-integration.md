# 聊天侦察接入：2026-10-11 最小诊断切片

## 2026-10-16：0.4.51 特殊地点排除

用户实机反馈地图特殊地点被误计为侦察。原因已经闭合：0.4.49／0.4.50 只核对系统“发现”模板和本人 NAME，把 DISCOVERY 整段当去重指纹，没有识别发现对象名称，所以同一模板承载的特殊地点也会计入 R10。

本次仅对明确识别出的特殊地点排除，其他未知发现沿用原先允许的近似计数。游戏 15 种语言的静态本地化资源在三个相同 key（`01F261DE / D5BD7333 / DD55D46A`）提供主要／普通／次要特殊地点的 38 个不同名称。`native-recon-reader.lua` 直接精确匹配这三个 key，不依赖界面语言，也不对“特殊”“兴趣”“巢穴”等片段做宽泛关键词过滤。识别成功的行标记 `discovery_kind='point_of_interest'`，`recon-chat.lua` 保留其去重基线但不发 R10。真正目标、尚不认识的 key 继续计数；不回写、清除旧历史奖励。

真实样本 `dist/recon-target-live-20261016-v1/rows.json` 已纠正 type10 的解释：DISCOVERY 参数尾 `+16` 的低 32 位为 `0x1166A22E`，同构建中英文资源精确对应“轻型巢穴 / Light Nest”。2026-10-13 样本相同低 32 位，但高 32 位为 `0x10`，本轮则为 `0`；所以**不能把尾部 8 B 拼成字符串指针**。第一次候选读取因不可读而停止，否定了指针假设。正式 reader 只从已经读取并复核的 descriptor 取这一个 u32，不再解引用尾部，不增加读取地址、字节或次数；也不把本地化 key 当目标实例 ID。未知 key 仍沿用原规则计奖。此处有真实字段／静态本地化交叉依据，尚未声称取得 native formatter 的完整类型分派代码。

一次性诊断工具 `tools/recon-discovery-target-snapshot.py --pid <当前游戏 PID> --output <新的输出目录>` 复用原来已经验证的固定 64 行读取框架。修订 v2 只解析前 4 条发现的 NAME，从现成 descriptor 的 type10 尾低 32 位查本地中英文资源，完全不跟随 DISCOVERY 指针。完整最坏 63,282 B／239 次，保留 64 KiB／256 次／1.5 秒门，仍无写入／native 调用／递归遍历。v1 第一次候选采样的失败材料原样保留，不能再拿错误假设当当前实现。

源级回归：0.4.50 不可变 ZIP 的旧 counter 对“特殊地点不计奖”用例稳定失败；新 counter 8 项、真实 native 行布局的自有内存 fixture 16 项、诊断工具 6 项通过。覆盖三种地点 key、真实轻型巢穴 key、忽略高 32 位残值、未知 key 仍计、15 语言同 key 对齐、完整读取预算，以及既有本人归属／首轮基线／去重／新局边界。生产 native reader 保持原先 4 行全发现峰值 57 读／5,941 B。构建后 addon 联通与实际 POI 不发绶带仍由主任务继续确认。

## 2026-10-15：0.4.49 正式读取实现

本节取代下文旧研究记录中的“尚未接通／必须先取得绝对唯一事件号”等实施结论。用户已明确接受按本人的原生“已发现”通知合理推测侦察次数，不再要求证明目标实例或完全排除重复。现已完成正式只读 adapter `src/native-recon-reader.lua` 与纯计数模块 `src/recon-chat.lua`；由 addon 将增量接入既有 R10 侦察绶带。

采用真实采样已确认的聊天 HUD 系统文字槽，不读取普通玩家聊天正文，不根据“已发现”字样猜系统消息。读取入口为 `game.dll+0x346D538 → hud+0x14498 → chat+0x4390+i*0x3D8`，固定 64 行。行内 `+0x110` 的 kind8 子文字保留 native 本地化描述符。仅接受 `0x92871A58 / 0xCD539459` 发现模板、2／3 个参数、唯一 NAME=`341F7711` type1 和唯一 DISCOVERY=`38237B81` type10。NAME 的字符串最多读取 64 B，与当次四人 roster 的名称唯一匹配；peer 与原生 local peer 一致才算本人。队友、重名无法区分、未知名称均不计。可直接复用调用方已取得的完整当次 name／peer 玩家名单；缺名字时回退到固定原生四人 roster。**不解引用 type10**，不把其尾部原始字段宣称为目标实例 ID。

真实模板与布局依据仍为 2026-10-13 的发现样本（SHA `09b8e0008e67f3e5fecb2ef294d5f39bc52ea260ae25c4382a7fd7e2c6bab7ca`）和固定行 handler（SHA `ad82ac5125eac0b4d1acc2424abf91b7a7dfb901d4c67f114c830ce3b8ac17b2`）。Lua 回归直接采用真实描述符的 56 B 已声明模板／参数，只有 NAME 字符串存储使用自有测试数据。此处没有声称旧采样已得到真实本人归属；新实现通过相同原生 roster 接口在正式运行当时匹配。

接口与边界：

- `reader = native_recon_reader.new()`；`reader:step(world, players)` 每次最多处理 4 行，硬限 80 次读取／8 KiB、读操作之间有 2 ms 软时间门。无写入、native 调用或 UI 树遍历。16 步完成一轮，期间返回 `nil, 'RECON_SCANNING'`；完整返回 `{complete=true, identity, local_peer, rows}`。`players` 可省略。
- `counter = recon_chat.new()`；`counter:update(snapshot, {mission=true, sequence=...})` 返回新增本人通知数和诊断。每局第一次完整 sweep 只建立基线，不重放残留旧行。之后按原始 NAME 参数绑定与完整 DISCOVERY 参数指纹、该指纹出现次数的新增立即计数。两种颜色模板视为同类通知；相同原始描述符移槽、同一行重复轮询、旧行随后才解析出本人均不会重复。不同 DISCOVERY 原始字段可以区分同一人后续发现。
- 没有原生消息唯一事件号。指纹消失后重新出现按新通知推测；扫描期间行变化可能少量多发，完全相同通知未曾消失也可能漏计。这正是本轮接受的近似口径，未添加连续两轮确认等待。每次只保留当前最多 64 行指纹，不把通知无限累存在内存。
- 返舰／新局重置 reader 和 counter；counter 也会在 `mission~=true`／sequence 改变时自行重置。未完成一轮不更新计数基线；读取失败不返回伪造的空快照。

普通聊天 history 的 first／count=`+0x9590 / +0x9594` 属于普通网络正文 ring，**没有证明与系统发现通知共用序列，正式 reader 不使用它们**。BFV 1.7 已提取的两个 Lua 资源中也未找到发现通知／聊天侦察接口；搜索所得“侦察”仅为敌人名称。此功能沿用本项目自己的原生 UI 证据，不复制 BFV 逻辑。

源级验证：游戏 LuaJIT 中，纯计数 7 项、原生读取与联通 14 项通过，覆盖首轮旧行、两种模板、本人／队友／重名、普通聊天仿写、同人多个目标、移槽、重复轮询、NAME 后补解析、短读／参数变更／roster 变化拒绝、返舰、新局、时间门。4 行全部为发现通知时仍低于 80 reads／8 KiB。当前尚未进行 0.4.49 真实任务发现的实机确认；构建与 addon 接线由主任务统一完成。

## 2026-10-13 当前研究状态

**最新任务样本已命中真实发现模板。** `dist/recon-chat-row-child-descriptors-discovery-20261013-v2/rows.json`（SHA `09b8e0008e67f3e5fecb2ef294d5f39bc52ea260ae25c4382a7fd7e2c6bab7ca`）的 row 0 为 `0x92871A58`，其余 63 行无参加入模板；固定 61,918 B／209 次，515.976 ms。参数键已按 Stingray 高32位哈希核对：NAME=`341F7711`／type 1／字符串地址，DISCOVERY=`38237B81`／type 10／尚未解义。既有原生 setter 代码已证明 type 1 是字符串指针；BetterLobby 作者明确 kind 8 是 wrapped label，共用该 setter。

单独后续 NAME 短采样因任务已结束、控件描述符已变化而正确停止，**没有读取过期 NAME，也未取得真实玩家归属**。新工具 `tools/recon-discovery-row-source-snapshot.py` 将发现模板、当时 NAME 与当时四人 roster 合并为同一次固定64行快照。只解析最多 8 个有据 type1 名字，其他类型保持原始值；参数+count、NAME、父子/context、roster/localpeer、状态前后均复核。最坏 **64,214 B／255 次**，仍在原 64 KiB／256 次／1.5 秒门内；6 项新 fixture 与 5 项原复合行回归通过。未启动后台、未实采这个合并工具、未接正式绶带。下一次自然发现后由主任务执行一次即可，不要求重演上一条发现。

相同 descriptor 的重复轮询可以抑制重复；但行重用／同名新通知的 generation 尚未证明，不将 type10 尾槽或名字当目标唯一身份。正式计数仍缺 **本人归属的真实样本 + 可靠的新消息去重**。

侦察仍未接通。普通聊天的正文历史没有已证系统发现类型；`context+0x1F038` 的 64×0x20 会话 ring 目前只证实了加入／离开等会话通知，已停止扩展其调用索引。`185F8F0` 当前取得的 48 字节片段只证实布尔状态变化门，不能当作内容更新或发现生产者。

当前只验证一个新方向：聊天 HUD 的实际本地化文字控件是否仍保留系统消息的描述符。已采真实循环 `186042D..18604CE` 给出 `chat+0x4390+i*0x3D8`、共 64 个行控件。2026-10-13 的实际 Ship 快照确认这些行是 kind 1 容器，固定 child=`row+0x110`；后续同范围快照确认全部子节点为 **kind 8**，parent/context 一致，无更深子节点。当前生涯 reader 的 kind 7 门不适用于这里；原工具 `text_rows=0` 不能解释成无内容。

两份原始快照在 `dist/recon-chat-row-descriptors-ship-20261013-v2` 和 `dist/recon-chat-row-child-descriptors-ship-20261013-v1`，后者附离线 REPORT。64 个子节点 `+0x110` 都保留 `0x14DCC78A`，中文资源确认为“#NAME加入任务”，参数计数为 0；这只能说明当前预填形态，不是 64 次真实事件。两条发现模板仍为 `0x92871A58`／`0xCD539459`。

修订工具 `tools/recon-chat-row-child-descriptor-snapshot.py` 依据上述实采将 kind 门改为 8；读取范围不变，最坏 **61,918 B／209 次**，保留 64 KiB／256 次门限。PID 4268 的第一次任务样本在 0.5 秒墙钟门停止，未保存行数据；考虑 Ship 同计划已用 384 ms，仅将外部采集的墙钟门调为 **1.5 秒**，不扩字节、操作、行数或指针范围。五项复合行 fixtures 通过（含 1.0 秒延迟允许、达到 1.5 秒停止）。保存参数原始 type/value，**不跟随参数指针，不推测 NAME 是玩家 peer 或字符串，不计数**。本轮 Ship 读取已停止；唯一下一步是在一次自然发现通知仍显示时采同一范围，可与本人封虫洞测试合并。若仍只见预填模板则停止此控件源，不扩大子树或代码索引。只有真实模板、本人归属以及新通知去重依据闭合后，才创建正式侦察 reader；不接入 0.4.31。

当前已经能自动等待正常游戏启动、读取固定聊天历史消费者的有界代码范围并保存，成功或失败后都停止。**尚未取得历史行正文、系统消息类型、来源玩家；侦察绶带没有接通。** 本切片没有修改账单源码、构建、版本、安装或其他 MOD，也没有启动游戏／执行真实进程采集。

## 现有证据与唯一缺口

同构建 BetterLobbyManagement 的 `src/chat.lua:34–41` 指令 PIN：`game.dll +0x1097A7C`、`8B87949500008B8F90950000`，读取原生聊天历史 `first +0x9590 / count +0x9594`。其正式 reader 只读这两个整数，不读正文。游戏本地化另有 `2458327640 / 3444806745` 两个“#NAME 已发现 #DISCOVERY”模板；这证明游戏显示玩家归属，尚不是实时消息事件。

本切片只定位覆盖该 PIN 的 **非链式 RUNTIME_FUNCTION 范围**。RUNTIME_FUNCTION 是 Windows x64 程序记录的代码区间；即使没有 chaining，也不能证明所有被调用 helper／冷代码属于同一逻辑函数。二分只检查固定表中的搜索路径，不遍历全表验证全局排序。发现生产函数尚无已证 RVA／PIN，因此不读取 sender 或把它称为发现生产者。

## 自动等待工具

文件：[recon_chat_code_capture.py](tools/recon_chat_code_capture.py)。从项目目录执行：

```powershell
& 'external/python.exe' tools/recon_chat_code_capture.py
```

默认输出：[dist/recon-chat-code](dist/recon-chat-code)。`--check` 只核验磁盘 EXE/DLL SHA，完全不等游戏、不读进程。等待器每 2 秒查询进程列表，没有 120 秒超时；唯一游戏进程及 game.dll 加载后留 20 秒启动延迟，期间不读游戏字节。游戏在延迟期间关闭则继续等待下一次正常启动。

| 阶段 | 固定边界 |
|---|---|
| 构建校验 | Steam 25480438；复用 `fire_code_capture.py` 的精确 EXE／DLL SHA、路径和磁盘 stamp 校验。加载模块大小须 `0x4744000`。缓存复用前仍先核对当前磁盘构建。 |
| 函数边界 | PE exception directory 固定 `0x3FD340C / 0x1BF57C`；二分最多 24 条、每条 12 B，只找包含 `0x1097A7C` 的记录。 |
| 链式片段门 | 仅补读选中记录的 4 B unwind header；未知格式或 CHAININFO 直接停，不跟链、不扩大范围。 |
| 代码范围 | 记录长度最多 4,096 B。超限时只保存已查到的边界到失败状态，不采半函数。代码页须 committed / image / executable、无 guard。 |
| 总预算 | 所有 metadata 和 code 共用硬上限 8,192 B、32 次 RPM、32 次 query；当前计划最多 4,388 B、26 次 RPM。2 秒是 IO 间软门，不能打断一次阻塞的 Windows IO。 |

复用 `fire_code_windows.Process` 的 `OpenProcess(0x410)` 只读权限，以及隔离实例的 `fire_code_capture.capture` 原始字节／PIN 校验。PIN 从同一保存缓冲验证，无额外 PIN 读取。句柄退出关闭；没有 write、send、native call、保护更改、游戏启动或终止。实际读取开始后只有一次尝试；失败也不重试或追加窗口。

`status.json` 顺序是 `waiting_game → waiting_loaded_code → complete/failed`。成功写一个 BIN 和 JSON，含边界、二分所读 12 B 原文、unwind header、统一预算、build SHA、代码 SHA、PIN 结果。失败保留搜索记录与已知边界。成功缓存会重新检查搜索路径、边界、unwind 门、原始 PIN 和 SHA；有效缓存直接结束。输出明确 `chat_messages_read=0 / recon_events_emitted=0`，避免把诊断代码包误当聊天／侦察结果。

## 接入合同与下一步

本切片没有创建空壳 `native-recon-reader.lua`。真实正文接口闭合后，才可给 addon 一个低频、只在新消息时读新增条目的 reader：至少返回稳定消息序号／generation、真实系统发现模板或类型、游戏通知指定的玩家。按真实消息序号去重；来源唯一映射当局 roster 后计数。同名且无呼号区分时保留未知，不用颜色猜。普通用户聊天即使模仿发现文字也不能计入。

目标 instance 不是消息级侦察计数的先决条件；可以以后用 camp／objective identity 交叉确认。当前唯一下一步是分析正常启动后取得的代码包，确定历史行 stride／文本存储／系统类型与玩家字段，再实现有界 reader。若 PE 表或代码门失败，就根据实际失败边界调整诊断，而不伪造接通。

## 验证结果

- 新测试 `tests/test_recon_chat_code_capture.py`：14 项 owned fixtures，通过。覆盖非链式边界、超限不采片段、chain／未知 header 停止、PIN／短读、读写保护、统一字节／操作／时间门、缓存、等待超过 120 秒、一次失败退出。
- 复用的 `tests/test_fire_code_capture.py`：9 项回归，通过；未更改原 FIRE 全局配置。
- `--check` 当前磁盘同构建验证通过；Python 编译检查通过。

这些验证全部离线，没有读实际游戏进程。实际 code capture／聊天正文／侦察绶带／帧率尚未验证。
