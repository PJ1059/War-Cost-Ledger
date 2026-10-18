# 原生点燃／中毒读取：本轮新增证据与材料接口

日期：2026-10-11。统计仍采用用户已确认的规则：本人使敌人首次进入相应有效状态才计一次；刷新不加次数；同族变体合并；有效结束后重新施加才另计。本文不修改规则。

## 本轮更新：自动一次代码材料采集已准备

新增 `tools/status-code-capture.py`，独立于安装的 MOD 和原 Lua 手动材料入口。它自动等待下一次正常启动，不启动／关闭游戏；只等待 `game.dll` 加载后延迟20秒，不声称验证了上舰状态。无需玩家在点火、挂毒或停止攻击前后手动取样。

范围严格沿下文六个原候选窗口，共 **10,288B、7次正文读取**，最大单次4096B；每次正文之间间隔0.1秒。只读 committed executable image，并使用同一句柄；没有管理器头、敌人、状态队列或目标数据读取。读取后在已经捕获的字节中核对 Runtime `event_natives.status.prologue` 的41B真实PIN；其它窗口没有上游独立字节PIN，仍明确属于候选范围。磁盘EXE/DLL SHA、实际模块路径／大小／base与前后模块身份分别核对，不将候选窗口描述为已证明的函数边界。

等待正常启动没有120秒截止；最多两次失败的采集尝试。每次最多10,288B，失败总尝试上限20,576B。成功保存一个合并BIN和JSON（每窗offset、每段长度／耗时、PIN、SHA、构建身份），并停止；后续运行先验证成功缓存，直接返回，不重读游戏。默认输出 `dist/status-code-capture/`，与 FIRE、资产代码材料隔离。

`--check` 仅验证磁盘构建并输出范围，不导入进程适配器、不读取游戏；任何“local_build_matches”都不代表状态接口已接通。采集材料同样保持 `layout_ready=false`、`success_count_available=false`、`atomic=false`，不包含任何 `effective` 或 `ended` 事件。当前没有游戏进程，尚未实际启动该等待器或取得六窗材料；只完成隔离测试与磁盘校验。

```powershell
Set-Location -LiteralPath '.'
& 'external/python.exe' -B 'tools/status-code-capture.py' --check
```

父任务统一安排等待器与命中材料采集的启动顺序，避免两个探针同时读取。将来正常启动时，后台启动使用 `Start-Process -WindowStyle Hidden`；本模块不创建新的常驻服务，不修改已安装 MOD。

自动材料入口仅替代取得代码的步骤。真正挂火／挂毒事件仍需原指令闭合 entity→状态实例、active/type、首次归属、刷新与有效结束。原 `status-feedback.lua` 的18项纯合成检查已验证首挂计数、同族去重、刷新不增、结束后重挂、身份代次和2秒收纳；不能用这些合成检查替代原生字段证据。本轮没有把申请、伤害tick、火焰武器击杀或不明读取转换为成功状态计数。

新增 `tests/test_status_code_capture.py` 的10项隔离检查通过，包括六窗与本地reader一致、PIN与真实Runtime一致、7次精确读取、长度／PIN拒绝、模块／保护页拒绝、>120秒等待、最多两次失败、成功缓存停读及`--check`不读进程。

**当前结论：敌方身份中的 generation 已找到现成原生证据；成功施加的 active、首次施加者与结束字段尚未证明。新增的 `src/native-status-reader.lua` 只捕获进一步反汇编所需的原始材料，不是已接通的状态计数器。它未嵌入 addon、未安装或运行采集。**

## 1. 这次补到的事实

### 实体代次已有准确读取链

旧研究文档把 generation 列为尚无原生字段证明，这一点应更正。固定提交 `dcd996daca2573443956c07252c55c2d86dd0320` 的 `runtime/event_world.lua:253–266` 已提供 `entity_exists(world, id)`：

1. `index = id % 4194304`，`generation = floor(id / 4194304) % 256`。
2. 引擎实体管理器为 `[exe + 0x1B135B8]`；generation 数组长度位于管理器 `+0x80`，字节数组指针位于 `+0x88`。
3. 仅当该 index 的当前 generation 字节与请求 ID 相符，实体句柄才仍有效。读取失败返回未知，而不是死亡。

创建指令 `0x604160/0x604163` 将 generation 左移22位加入 ID；销毁 `0x6047A2/0x6047A5/0x6047CF` 比较并增加8位 generation。它是引擎实体代次，**不是 descriptor 的 goid**。8位会环回，不能把它说成永不复用的无限生命周期号；跨任务还应保留现有任务 sequence。此链可以防止普通槽位复用让旧敌人的状态继续落到新敌人身上，但不能提供状态周期号。

来源：[原生实体身份研究与指令](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_state.py#L294)、[实际只读 `entity_exists`](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/runtime/event_world.lua#L253)。

### 缺少研究 JSON 的原因已确定

HD2Runtime 的 `research` 是 Git 子模块，`.gitmodules` 指向 `https://github.com/SkyeShade/HD2Runtime-Research.git`，不是下载源码 ZIP 内的普通文件夹。本机目录为空。2026-10-11 查询研究库的 GitHub API、tree 与固定提交 raw JSON 均得到404；只能确认当前访问不到，不能判断它已删除还是私有，更不能宣称已读到研究 JSON。

当前上游主分支 SHA 为 `bf86adf79c5a58438fea0ba6933c63995fb30931`，提交时间 `2026-10-10T23:54:31Z`，VERSION 为0.31.0；research 子模块指向 `eef456fedf135ab8f3b67209e6cd2aafb88f5ccd`。已逐字节比对六份关键文件：

| 文件 | 与本机0.30.3固定源码比较 |
| --- | --- |
| `scripts/research_avatar_fields.py` | 完全相同；SHA256 `65acdd959e5165be95635433b744e9ace5c7d21c80914fb85f2b94de59531cc1` |
| `scripts/research_event_actions.py` | 完全相同；SHA256 `27b7be069e94165b11e555ee16e7228c344651d876a4d6c5460d9123e9f07bbe` |
| `runtime/event_world.lua` | 完全相同；SHA256 `407980b97198dff9b7ea7e0bdf3c1c9bfe85171eb278207a1e08ba042707dea2` |
| `domains/event_natives.lua` | 完全相同；SHA256 `2774766b8eca615530f7b926a3b6568104c4d7bc043c88bef106dd6be13d6233` |
| `schemas/build_profile.json` | 完全相同；SHA256 `25205addef75e5813f90ec5a925ad8cf7cd97da946fc8ef1724fa33392b098e3` |
| `VERSION` | 已变为0.31.0 |

新版公开的状态读取相关源码没有补齐 active、instigator 或状态容器布局，升级版本本身不能解决缺口。未更换已安装 Runtime。

来源：[上游固定新提交](https://github.com/SkyeShade/HD2Runtime/tree/bf86adf79c5a58438fea0ba6933c63995fb30931)、[研究子模块声明](https://github.com/SkyeShade/HD2Runtime/blob/bf86adf79c5a58438fea0ba6933c63995fb30931/.gitmodules)。

### 磁盘函数字节仍不能替代运行图像

本轮直接解析本机 `data/game/game.dll` 的 PE 节表，并对五个候选 RVA 映射磁盘位置：

| RVA | 磁盘情况 |
| --- | --- |
| `0x69B1F0` 查询 | 64字节有对应正文，但位于加壳区；开头为 `fe f8 f6 fe 87 9d 9c 34`，不是已证明的查询指令 |
| `0x699E40` 实际施加 | 64字节有对应正文，加壳区开头 `73 67 19 aa 2f 8c 91 c5` |
| `0x6994F0` 接收条件 | 64字节有对应正文，加壳区开头 `86 0c 8c 1c 29 fb a7 fc` |
| `0x69AEC0` 未知callee | 64字节有对应正文，加壳区开头 `dd 31 03 cb bf 39 24 62` |
| `0x129F170` 状态申请 | RVA超过该节8,718,336字节磁盘正文范围，没有对应函数正文 |

不能对这些随机磁盘字节做线性反汇编后赋予状态字段含义。该节虚拟正文大小34,667,155字节，与磁盘长度明显不同。已对 Documents、Downloads、LocalTemp 和本项目相关 LocalHD2Runtime 目录搜索 `.hd2snap`、游戏module dump，没有找到可用的HD2运行图像；其它游戏的崩溃文件不属于本项目材料。

## 2. 新接口现在实际能做什么

`src/native-status-reader.lua` 是手动、只读、固定范围的**研究材料接口**。构造时不读游戏，不设置定时器，不注册帧回调。调用者必须传入现有 Runtime `event_world.open()` 已验证的 world，并显式请求 `{manual=true}`。它持续声明 `layout_ready=false`、`success_count_available=false`，不返回 `events`、`statuses` 或累计计数。

读取前核对固定 build profile、状态申请的完整原生 prologue 与状态管理器指针。捕获六个固定代码窗口：

| 材料标签 | 起始RVA | 长度 | 用途 |
| --- | --- | --- | --- |
| receive_condition_candidate | `0x6994F0` | `0x950` | 找状态容器索引、接收条件，不能直接叫免疫判断 |
| apply_buildup_and_refresh_candidate | `0x699E40` | `0x1080` | 找阈值成功分支、首次 active、timer与instigator写入 |
| unknown_status_callee | `0x69AEC0` | `0x330` | 追调用者及读写；尚不命名为移除函数 |
| has_status_query_candidate | `0x69B1F0` | `0x700` | 优先还原 entity→状态实例→有效状态判定 |
| queue_request_and_target_lookup | `0x129F170` | `0x130` | 补齐申请函数中实例映射与第5参数的保存链 |
| request_router_and_instigator_arguments | `0x129F2A0` | `0x300` | 查实际施加调用时 instigator 参数来源 |

代码共10,288字节。这是有界研究窗口，**不保证正好等于函数起止范围**；若分支落到窗口外，之后按真实指令补指定目标块。管理器仅捕获512字节原始头，不解释任何未知偏移。可以附带最多8个已知敌人 descriptor，前后使用 SDK 原生 generation 链确认实体仍有效，再保留24字节 descriptor 与准确 ID/index/generation/type/unit/goid。它不从玩家手持武器、敌人的伤害来源或请求成功推断施加归属。

所有材料标明 `atomic=false`：多个顺序读取不构成同一瞬间状态快照。读取失败、descriptor改变或generation不符时拒绝本次材料，不输出“状态结束”。该接口没有接入生产帧循环；本轮没有状态扫描或由此新增的游戏开销。手动捕获的实际耗时与FPS影响尚未测试。

代码入口示意，仅供未来的手动采集接线：

```lua
local reader = create_native_status_reader(world_api, natives)
local world = world_api.open()
local materials, reason = reader:capture(world, {
    manual = true,
    targets = known_descriptors, -- 最多8条，沿用现有敌人发现结果
})
```

这段示意没有安装，也没有运行；不应将此接口连接绶带的成功累加入口。

## 3. 合成验证与真实接通的区别

`tests/test_native_status_reader.lua` 使用游戏 LuaJIT 和固定 Runtime native定义，但内存内容由测试构造。已验证：默认零读取、手动开关、8目标上限、固定代码总字节、prologue不符拒绝、descriptor身份改变拒绝、generation与goid区分、8位环回以及不调用native／不写游戏／不输出状态次数。

执行命令：

```powershell
Set-Location -LiteralPath '.'
@'
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path('tools').resolve()))
from test import run_lua
run_lua(Path('tests/test_native_status_reader.lua'), Path('src/native-status-reader.lua'), Path(r'external/HD2Runtime'))
'@ | & 'external/python.exe' -
```

预期输出以 `PASS: synthetic manual-only status research capture` 开始，并明确说明真实 active／instigator 未验证。

**未验证**：这些窗口的本机运行后代码内容、敌方状态容器的布局、active判定位、首次施加者、刷新时归属是否改写、有效结束、多人同步与FPS。合成测试通过不能称状态已经接通。

## 4. 仍需的一份运行材料与完成标志

先取得匹配当前 build 的任务内解包代码，不要求在整个完整快照的1–4分钟内保持同一团火：代码材料稳定即可。已有官方 Armed Capture 可以提供 `.hd2snap`，或后续将本接口连接既有手动研究采集入口以获取上述约11KB材料；本轮未接该入口、未自动启动。

拿到代码后的先后顺序是：查询函数证明容器布局与active判定 → 施加函数证明首次成功与instigator保存 → 更新／清理函数证明结束和刷新 → 仅4–8个目标的短连续实际观察。需要实际时序：未生效、本人首次成功、持续刷新、全部同族效果确实结束、再次成功；另加两玩家相继施加和主机／客机。代码定义中的3秒或1秒不代替实际结束证据。

完成标志是**创建、查询、结束三个方向的原生指令与真实目标记录一致，并能明确区分首次成功、刷新和其它玩家施加**。在那之前，绶带的点燃／中毒成功数量保持未接入。
