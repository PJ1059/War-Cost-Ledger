# 原生任务列表布局：公开 MOD 参考调查

调查日期：2026-10-11。只读资料调查，未安装任何包、未启动游戏、未修改本项目源代码。

当前结论：没有找到能证明其移动了原生完整 Mission/Objectives 父列表的公开实现。最有价值的候选是 Objective Tracker，但作者说明它建立自己的目标面板，不能据此声称可以让原生列表自动让位。

## 三种实现方式须区分

1. **独立绘制**：读取游戏数据，另建自己的面板。可以自由定位/缩放该面板，但原生任务列表没有因此改变。Objective Tracker 的公开功能和本轮取得的源码均属于这条路线。
2. **纹理替换或 shader 隐藏**：改变已有图块，或阻止整组图形绘制。不能据此读取完整任务高度，也不能移动任务条目。Custom UI、Bit better UI、Clean HUD、FoosHUD 和 Toggle HUD 主要属于此类。
3. **原生控件移动**：定位实际承载全部任务行的容器，再使用游戏布局接口改变位置。必须证明找到的是完整列表父对象，而非单个任务、一个标题或自己创建的面板。这才满足本项目任务自动向下让位的要求；本轮未在候选中找到该证据。

## 优先候选

[Objective Tracker / plataodomo](https://www.nexusmods.com/helldivers2/mods/16913?tab=description)：最新 0.5.4，发布/更新日期 2026-10-10；Files 列表主包 351KB。

- 作者描述独立可定制目标 HUD，按距离排序，可在 ESC 中拖动和改变面板尺寸；可限制行数、自动适应内容、分页/分栏/堆叠、滚轮浏览。
- 0.4.9 起提供仅战术地图开启时显示。作者 posts 解释 ESC 显示属于面板布局编辑，独立于地图/舰上可见性设置。
- 主线仅覆盖列出的阶段；其他支持对象为支线、敌设施和部分携带物。作者明确说明覆盖有限，部分完成状态不可读。这与完整原生任务列表并不等价。
- [作者自己的说明](https://www.nexusmods.com/helldivers2/mods/16913?tab=posts)：包含未修改的官方 HD2Runtime；自定义任务完成检测代码属于 Tracker 自己。
- 同名 [GitHub 用户](https://github.com/plataodomo) 只有 2 个 Arma 项目，没有公开本 MOD 源码。该同名账号与 Nexus 作者的身份关联未额外证实。
- 普通 Files 页未提供可下载链接，需登录；Python 普通 HTTP 获取 Files 页返回 403。随后通过用户 Edge 正常下载 0.5.4 包，已取得作者随包源代码并完成下述只读核查。

有效用途：真实地图状态、可拖拽面板及目标完成读取已找到具体代码。不能把独立 Tracker 拖拽当作原生任务列表移动。

## Tracker 0.5.4 包内代码证据

源包：`external/Objective Tracker 16913 0.5.4 2026-10-10T11-19Z G8WAtVjnZ.zip`。

SHA256：`A4B3205547A181797418C0BAA5AF24F1B6B28F5BC226633003E6591E63243024`。

只读解包目录：`dist/mod-research/task-layout/objective-tracker`。没有执行包内 Lua，没有安装包，没有修改游戏。

关键源代码：[`source/objective_tracker.lua`](../dist/mod-research/task-layout/objective-tracker/source/objective_tracker.lua)，2972 行；SHA256：`039713426F45638D84513260CB5DD743712053891B749A5B3427B6BCBF7F956C`。`source/profile.json` SHA256：`ED37847A2EDF1D1E12180BF4C5A487C6135D93D67C245A0BED6D9D36243FE861`。

### 绘制与原生任务让位

- 650–654 行从 Stingray 取 `Application` / `World` / `Gui`；727 行 `World.create_screen_gui(world, 'scale', 1, 1)`，733–734 行 `Gui.rect` / `Gui.text`。它创建两层自己的 screen Gui，并按内容键重绘。
- 688–704 行 `H.hide()` 只销毁这两层自建 Gui。1189–1210 行完成筛选也只过滤它自己的 `targets` 数据；2060–2075 行 `c.hidden()` 控制自己的目标行是否返回。
- 整个随包 `source` 没有原生 `widget_parent`、Noesis、完整 Objectives 控件节点定位或布局写入口。包内内存适配器使用读取接口，没有 `WriteProcessMemory` / `VirtualProtect` 写入路线。
- 886 行之后的拖拽修改 `I.place`；HUD 的像素坐标由它自己的布局模型计算。不是移动原生任务条目。

因此本包不能直接解决任务自动让位。它能读取目标记录，但没有原生完整任务列表的父控件、可视高度、曲率/缩放后的边界或位置写接口。

### 真实地图状态

2363–2436 行 `MAP_VISIBILITY` 是独立原生读入口，不使用 TAB 按键猜测。

- 2436 行 profile：HUD 全局指针 `game.dll + 0x346D538`；初始化字节 `HUD + 0x24E334`；可用字节 `HUD + 0x46D8F0`；开启字节 `HUD + 0x46D8F2`。
- 2381–2400 行先验证 OpenMap / CloseMap 原生指令签名，再读取上述布尔状态并复查 root 和 flags；三个值均为 1 才认为地图已开启。
- 2406–2429 行按任务 epoch 重置，正常每 0.05 秒读取，失效后每 0.25 秒重试；区分 `known` 与 `open`。
- 2847–2848 行对象放在 `_G.PrivateObjectiveTrackerV1.map_visibility`，但 2914–2916 行只有本 MOD 启用 `map_only`、在任务且 ESC 未开时才 tick；其默认选项下不能把该对象当持续更新的通用地图服务。

这些地址是作者针对指定游戏构建提供的读取事实，仍须在本机实际游戏核对签名与开关变化，不能仅凭静态读源码称本项目已接通。

### 原生任务完成状态与公开事件

1764–1828 行 `OBJECTIVE_READER`：读取 `game.dll + 0x3326DA0` 的 objective manager，最多 256 个记录。manager `+0x24` 为 count；`+0x50/+0x60/+0x68` 为 descriptor、progress record、state 数组。记录步长分别为 8、`0x1078`、`0x64`；读取 descriptor / state / manager 后复核一致性。

1806–1810 行每条记录包括 `entity`、`unit`、`goid`、16 位十六进制 `type` 哈希、`owned`、`stage`、`state`、`stage_count`、`map_state`。这是原生任务记录列表；它并不提供原生 UI 行文本/父列表几何，也不等于显示了全部任务阶段。

1964–1975 行订阅 API，2852–2853 行公布为 `_G.ObjectiveTrackerEvents`：

```lua
local api = rawget(_G, 'ObjectiveTrackerEvents')
local unsubscribe = api.on('ObjectiveStateChanged', function(event)
    -- event.initial 为首次稳定观察；不应计作新完成。
    -- event.is_completed 是作者定义的原生完成判定。
end)
```

事件字段：原始记录字段，加 `event='ObjectiveStateChanged'`、`mission`、`sequence`、`initial`、`native_state`、`previous_native_state`、`previous_map_state`、`is_completed`。对外 `state` / `previous_state` 转为 `Completed` / `Incomplete`。`on()` 返回取消订阅函数。

- 1970 / 2004 行完成判定为原生 `state==2` **且** `map_state==2`。
- 2036–2054 行每 0.5 秒读取，并在前后确认任务上下文一致；失败后退到 2 秒重试。
- 1865–1900 行至少两次相同 state/map_state 才发事件，首次事件明确 `initial=true`；实体 identity 变化则重新建立观察。仅 stage 改变但 state/map_state 不变时不发事件。
- 2096 行有原生完成写 state=2 的指令签名，以及 game.dll SHA256 `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` 构建门槛；`reader/world.lua` 49–58 行验证实际载入模块对应文件哈希。
- `owned` 表示该 descriptor 的本地 authority 标志，**不是完成任务的玩家**。事件没有最后操作者、参与者，也没有直接主线/支线字段；需通过任务类型哈希及交互数据另行确认归属与分类。

已有 API 能作为“已确认某个目标状态完成”的研究入口；不能单凭它发玩家完成/协助绶带。结构死亡/消失 fallback（1234–1250 行）也与原生完成事件分开，日志明确提醒该 fallback 不是任务完成证明。

随包 `LICENSE.txt` 允许私人非商业使用及修改个人副本；本轮仅研究源代码/游戏读取事实，没有把作者源代码、图标或编译包复制进本项目发行内容。

## 排除或次要候选

| 作者原始来源 | 版本/更新时间 | 作者说明的实际方式 | 对任务让位的结论 |
|---|---|---|---|
| [Custom UI / KaruRega](https://www.nexusmods.com/helldivers2/mods/11273?tab=description) | 1.0 / 2026-02-22 | Crosshair、Hit Marker、Ping、NameTag、Mag、Backpack、Map Marker；列出 3 组 material / texture，编辑材质绑定的纹理 | 没有任务位置或父列表接口；不是通用布局编辑器 |
| [Bit better UI / SquidARMY7](https://www.nexusmods.com/helldivers2/mods/2749?tab=description) | 3.0 / 2026-08-16 | 武器/战备图标更新，需图标管理器；旧版日志指向 rank/FRV/exosuit spritesheet | 没有任务列表移动声明；本机九种 Eagle 图标 archive 已核查，每个仅 2 个 texture，无 Lua/XAML |
| [Monstertrucks Clean HUD](https://www.nexusmods.com/helldivers2/mods/13189) | 7.0 / 2026-08-13；日志写游戏 6.3.0 | 编辑少数 texture atlas，减少准星、互动、战备/队友背景图标 | 删除视觉图块，不提供原生任务列表移动 |
| [FoosHUD / 3FoosballTables](https://www.nexusmods.com/helldivers2/mods/1381?tab=description) | 1.1 / 2024-12-30 | 准星、命中标、跳弹标、ping spritesheet 视觉修改 | 没有任务父级路线；[作者2025-03说明](https://www.nexusmods.com/helldivers2/mods/1381?tab=posts)当时 MOD 损坏、待恢复，当前兼容未证明 |
| [Toggle HUD / Akelaphobia](https://www.nexusmods.com/helldivers2/mods/1?tab=description) | 1.87 / 2026-08-15 | ReShade ShaderToggler，一键隐藏整组 HUD shader；F4 Minimal-ish HUD | 可隐藏绘制，未给目标列表单独位置/高度/父对象；不是原生布局实现 |

[ShaderToggler 作者源码/说明](https://github.com/FransBouma/ShaderToggler/blob/main/README.md)确认其方式是按组启停游戏 shader；没有目标列表节点遍历或布局功能。上述 MOD 当前页面更新时间不等于已经在本机 25480438 Steam 构建上验证。

Bit better UI 本地核查来源：`external/BIT BETTER UI 2749 3.0 2026-08-16T15-26Z YUHF0QDSo_AR687998`。九种 Eagles 子目录的 `4c2203529ff1a9c4.patch_0` 均为 944 字节，header `file_count=2`，两项资源类型均为 `CD4238C6A0C69E32`（texture）。该证据只排除已检查的九个图标 archive，没有把未逐项检查的包中其他资源也断言为纹理。

## 下一条有价值的证据

Tracker 0.5.4 已排除“直接移动原生任务列表”的可能。下一条决定性证据是完整原生任务父控件的定位及布局写入口，须验证 HUD 缩放/曲率与多行任务增减；地图读入口与任务完成 API 可作为独立研究线索，不能代替父控件证据。
