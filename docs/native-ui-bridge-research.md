# 原生地图状态与任务列表定位：2026-10-11

## 已经接通的入口

`src/native-ui-bridge.lua` 直接读取游戏的地图状态。输入是 HD2Runtime
`runtime/event_world.lua:open()` 返回的 world；该入口先校验 EXE/DLL 文件指纹、映像大小和事件机器码。
bridge 另外核对 Runtime 的 `schemas/current.lua` 与这份布局证据对应同一构建。

| 字段 | 本构建地址 | 证据 |
| --- | --- | --- |
| HUD 管理器 | `[game.dll+0x346D538]` | HD2Runtime `research_teammate_hud.py`；当前安装的增援 HUD |
| mission HUD | `HUD+0x24E340` | HD2Runtime `research_stratagem_calldown.py` 的原生调度机器码 |
| mission 显示与就绪 | mission HUD `+0x58`、`+0x21F5B0` | 已安装 Enemy Reinforcement HUD 0.5.2 的 `ui_snapshot` |
| 地图打开 | `u8(HUD+0x3EF2FD)==1` | 同一 MOD 的 `ui_snapshot` 和 `fast_map` |

本机构建 Steam 25480438、EXE 1.8.46015.0，PIN：

```text
EXE F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06
DLL 2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E
```

实际来源是只读提取的
`dist/mod-research/reinforcement-hud/eee0d86609f31c53.lua:458`（PIN）、`:527`（状态）、`:648`（快速地图检查）。
2026-10-10 本机旧日志已有这条路线的真实运行记录：

- `%LOCALAPPDATA%/CowboyBingus/Helldivers2/Logs/EnemyReinforcementNativeProbe.log`：25 条 `map_open=true`、154 条 false，落地后有多次双向切换；SHA256 `615fdf4983419788d0a736029d93fe9121e6728db0867aa1b0d717fff2e4c527`。
- 同目录 `EnemyReinforcementHUD.log`：7 次 `draw_ok` 与 `hidden_map_closed` 交替，分辨率 2560×1440；SHA256 `32c9650e962c706fdd95e3a4cd5b8a73c3b9c0f19b7d3a740d5717cb40ee0480`。

每次 `bridge:poll(world)` 最多四次有界读取、11 字节，返回 `{mission,map_open,hud}`。
读失败或版本不符返回 `nil,reason` 并清掉旧状态。它不读取 TAB，也不根据地图按键切换猜测。
新模块在本轮未经过新的实机测试；已有实机证据属于上述安装 MOD 的相同状态入口。

## 完整任务父节点仍待证实

HD2 HUD+ 0.2.1 的实际打包代码，只公开了 self/squad/stratagem 的原生父级。
它的全部 sources 中没有目标任务列表或地图状态 source。
`widget_position_set` 是 `game+0x14476A0`，位置为 GUI element `+0x4` 的两项 float，
布局父链为 `+0xF0`；这些事实说明怎样移动**已知节点**，无法证明哪个节点包含所有任务。
Runtime `stratagem_hud.locate()` 只查战备列表，不能当作任务列表。

新的取证还检查了本机 2026-10-07 和 2026-10-10 的当前构建 crashdump。
二者 ModuleList 中的映像大小分别是 EXE 60,719,104、game.dll 74,727,424；
MemoryList 都没有 game.dll 或 HUD 区域，仅有 EXE `+0x626216` 的 256 字节。
当前 game.dll 的磁盘 PE 是压缩映像；相关 UI RVA 已超过其代码段 RawSize，
不能把磁盘填充或其它段的数据当作运行中 UI 机器码反汇编。
本机 HD2Runtime local_research 没有 `.hd2snap`，所以本轮没有足以确认任务完整父级的现有样本。

`bridge:reserve(...)` 明确返回 `TASK_CONTAINER_UNPROVEN`，没有写任务位置。
`restore()` 此修订不需要撤回任何修改。该状态应在设置菜单解释为“待原生任务容器定位”，
不显示成已完成让位。

### 后续离线研究：不再要求专项手动采集

本轮继续研究取得三个新参考包：OWHUD1.0.0提供实际原生控件树遍历、整组平移与恢复；
HUD+0.2.2新增全HUD根`manager+0x258`，可作只读定位起点；Objective Tracker0.5.4自绘自己的面板，
不提供完整原生任务父级。三个包均未执行或安装。

当前264个XAML和任务UI包已离线复核，未找到战斗任务列表的布局模板；结算页`ObjectiveList`不可代用。
下一步可以在正常进入任务后自动分批读取一次原生控件树，结合任务图标/文字身份验证具体容器，
不必把手动开图/关图采样作为唯一入口。此自动定位仍是未实现的研究方案，未确认任务身份前不改位置；
现有手动采集器保留为后备。详细证据见同目录`task-relocation-local-mod-research.md`、
`task-relocation-static-research.md`及`task-relocation-reference-research.md`。

## 现在可从游戏设置手动采集

`src/ui-layout-capture.lua` 已准备真实内存采集接口，默认关闭，只有用户手动触发才 start。
由 addon 在菜单关闭后调用；每 10Hz 最多调用一次 step。

```lua
local capture = UI_LAYOUT_CAPTURE.new({
    bridge = native_ui_bridge,
    log = function(message) mod:log(message) end,
})
capture:start(world, '任务列表定位')
capture:step(world)
-- 游戏 shutdown 或明确取消：
capture:cancel()
```

| 读取区域 | 长度 | 定位用途 |
| --- | --- | --- |
| HUD `[0,0x480000)` | 4,718,592 B（4.5MiB） | 已知 mission HUD 及末尾 `+0x46D8F0` 的就绪状态；离线重建各 GUI 节点父链 |
| game `[0x12E8000,0x12F8000)` | 65,536 B | 包含 mission HUD 构造 `0x12E96D0`、更新 `0x12EB670`、系统调度 `0x12F3C70` |
| game `[0x143A000,0x1452000)` | 98,304 B | 原生文字、位置、父子挂接与布局相关函数 |

这些代码窗口来自 Runtime research 脚本及官方 Mod Options Menu 当前构建机器码 PIN，
只读取，采集器不调用它们。
每份计划 binary 4,882,432 B（约4.66MiB），binary+JSON 上限 8MiB。
地图关闭/打开分别允许成功保存一份；二者文件总量约9.3MiB，8MiB是单份输出上限。
step 只读取一个最多65,280B的数据块；加上原生状态及结束首尾检查，总 native 读取仍≤65,536B。
不会在普通统计中触发，也不会完整 dump 进程或每帧扫描 HUD。

输出到：

```text
%LOCALAPPDATA%/HD2Runtime/mod_data/ledger_ui_<UTC>_map_open|map_closed_<序号>.bin
%LOCALAPPDATA%/HD2Runtime/mod_data/ledger_ui_<UTC>_map_open|map_closed_<序号>.json
```

JSON 记录 PIN、起止 mission/map/HUD、地址与长度、binary 偏移、分块成败、内存区域属性、
首尾16B是否一致，以及 `complete`。它是分时读取，`atomic=false`；首尾一致不能证明所有
动态字段在采集期间不变。身份或地图改变、读取失败、取消均保存 incomplete，不拿零字节
伪装成功。成功样本的解码和完整任务父级定位属于后续工作。

状态接口：`capture.status`（disabled/capturing/complete/incomplete），`capture.active`
存在时 `active.meta.bytes_written/bytes_planned` 是进度；结束后的 `capture.last` 是报告。
start 返回 meta 或 nil/reason；step 结束返回最终 meta 并清掉 active；无 active 的 step 无读取。

## 当前验证

使用游戏自带 `bin/lua51.dll` 运行：原生状态模块8项、采集模块8项测试全部通过。
状态测试覆盖读取预算、真实地址路由、地图切换、HUD换址、失读和构建不符。
采集测试覆盖默认关闭、64KiB每步限制、输出上限、两种地图样本、失败与取消的 incomplete
报告、对象边界变化、原生区域保护拒绝。测试没有给任务节点构造假的可写入口。

`tests/test_addon_options.lua` 另有10项真实构建入口集成测试：使用实际 `dist/addon.lua`、
当前 Runtime schema 与 JSON codec，只替换 Runtime/native/io 和公共菜单边界。覆盖菜单
注册及应用、F8同步、舰上8秒独立预览、不污染真实账单、数值 HUD 指针的地图切换、失读、
采集5秒延迟/取消/超时不复活/默认关闭、首份完成后再次预约的正确状态，以及完整菜单
请求到 binary+JSON 的成功链路。
成功链路逐帧将常规地图读取和采集读取合计，验证仍≤65,536B；测试产物全部在内存中，
不把离线模拟产物当作本机任务UI证据。

未验证：新代码在运行游戏中的实际输出、新设置菜单的本机画面、任务完整父级及让位。
用户本轮暂不便进入游戏，采集入口保留供之后手动使用。

## 设置菜单真实 API 复查

`dist/dependencies/Mod-Options-Menu-v1.2.zip` SHA256
`A977D84E7F8FDA62C587B5B5AF2012AAB3FA792E31945A9C8D5F458BFD453E13`。
其真实打包主 Lua（资源 FD50351F21814B0E）SHA256
`E03334C76D9B4B064378076A08D7E85E11E757BAFA9FC0380AFF5669FEE13C07`。
API 为 `api=1/version=3`，提供 `register_option/get/set/on_change/ready`，最多112分类、每分类32行。
`ready()` 以原生入口是否验证成功为准，注册成功本身不能证明菜单会显示。
选项回调在用户 Apply 后执行；代码 `set()` 不再回调，适合复位一次性采集/测试选择。
当前官方组件及这份实际包没有 `shared_API` 标识。

本机增援 HUD 0.5.2 的实际提取 Lua `dist/mod-research/reinforcement-hud/eee0d86609f31c53.lua`
1260—1306 已有此 API 的适配：`_G.ModOptionsMenu` 存在时恢复旧视图并注册
`local_reinforcement.hud.display_mode` 到自己的“拉烟计数器”分类，然后直接返回，
不再改写第四个菜单标签。无需修改此其他MOD来与战果设置共存。

来源路径：本地官方 VPM `components/ModOptionsMenu/src/api.lua`、`src/native.lua`、`src/view.lua`；
官方项目 [ModOptionsMenu](https://github.com/CowboyBingus/ModOptionsMenu)、
[HD2Runtime](https://github.com/SkyeShade/HD2Runtime)。
