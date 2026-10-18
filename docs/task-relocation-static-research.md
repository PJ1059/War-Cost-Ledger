# 战斗任务列表让位：离线资源复查

日期：2026-10-11。范围：读取本机当前游戏资源、HUD Plus 0.2.1、OWHUD 1.0.0 附带源码及 HD2Runtime 0.30.3 的研究代码；补入另一代理已完成的 HUD Plus 0.2.2 静态来源对照。没有启动游戏、安装补丁、执行下载的 MOD，也没有修改游戏资源或项目运行源码。

## 结论

**游戏资源能够离线解包，但本次解出的资源没有提供可直接修改的战斗任务列表模板。** 当前资源中的 `OverlayHud` 是空页；名为 `ObjectiveList` 的真实资源是任务结算页，并非战斗右上角列表。不能据此修改 `Margin` 或 `Canvas.Top`，然后声称已让完整任务列表让位。

**不需要把“玩家专门手动采集开图/关图样本”作为唯一下一步。** OWHUD 的源码证明可以从已知原生控件沿父子链进行有界读取，并且已有正确的整体平移、刷新和还原方法。下一次正常游玩可自动读取有限 UI 树，先确定任务容器身份；当前尚不能只凭右上角几何位置对未知节点写入。

## 本机资源版本与读取方法

游戏目录：`G:/SteamLibrary/steamapps/common/Helldivers 2`。

当前资源的 `ah_bin` 构建信息实际解包结果：

```json
{
  "version": "release/01.007.101",
  "commit": "f8c9037f96047f7a86c66",
  "build_id": 19155,
  "combined": "19155 f8c9037f96047f7a86c66 [release/01.007.101] 2026-09-23 07:25:16"
}
```

读取工具：

- CLI：`external/filediver.exe`。
- CLI SHA-256：`7cd8172dfc0b84f383bd9ec53244dc729b38cb467a42474fd5357f41e09cb473`。
- 本地 filediver 源码提交：`e5c4b91fcc02c04aed05dfac3136d7de23004526`。原仓库：[xypwn/filediver](https://github.com/xypwn/filediver)。
- `stingray/slim_edition.go:51` 定义 DSAR 头，`:87` 实际处理无压缩/LZ4 数据，`:316` 读取 Slim 资源目录及 DSAA 索引。当前基础游戏资源是 DSAR，不能用仅接受普通 `F0000011` 头的 SDK 读取失败来证明“游戏不存在布局资源”。
- `stingray/xaml/xaml.go:12` 定义 16 字节头；`:163` 从资源读取文本；`extractor/xaml/extractor.go:25` 输出原 XAML 文本。

所有派生读取结果位于：
`external/hd2-task-asset-research-20261011`。

复现命令（输出目录必须另选不存在的新目录，以保留已有研究结果）：

```powershell
& 'external/filediver.exe' `
  -g 'G:/SteamLibrary/steamapps/common/Helldivers 2' -l -i '*' -P

& 'external/filediver.exe' `
  -g 'G:/SteamLibrary/steamapps/common/Helldivers 2' -i '*' -T xaml `
  --xaml-format xaml -o '<新的临时输出目录>' -P
```

当前 CLI 的 `-T 'xaml,gui,config'` 实测输出零项，`-T xaml` 则正确输出 264 项。因此本轮按单个类型读取，没有将多类型过滤失败当成不存在的证据。

## 实际资源证据

完整索引共 107,628 项；包含 264 个 XAML、3 个 config、10 个 Lua、1 个 geleta、5 个 hash_lookup。没有 `gui`、`ui_settings` 或 `ui_config` 类型。264 个 XAML 全部成功输出文本，其中 58 个路径尚未知，保留其哈希名并一并搜索。

| 已解资源 | 实际内容 | 对让位的意义 |
| --- | --- | --- |
| `content/ui/shared/xaml/overlay_hud.xaml`，名称哈希 `1b82bcb2c79c750d` | 第 9 行 `x:Class="ui.OverlayHud"`，第 10 行仅 `<Grid/>` | 没有战斗任务子节点或位置模板 |
| `content/ui/shared/xaml/root.xaml`，名称哈希 `3b0826c67e56230c` | 第 8—12 行为 HudContainer、MenuContainer、PopupContainer、OverlayHudContainer | 只有页面层容器，未绑定任务列表；改动全页层不能证明只移动任务 |
| `0x050c579d97022c58.xaml` | 第 9 行 `ui.MenuMissionEnd`；第 42 行 ObjectiveList；含 MAIN OBJECTIVES、Optional objectives、MISSION COMPLETED | 明确属于任务结算页；排除同名假线索 |
| `packages/content/ui_mission.package`，名称哈希 `07f10cad298067ec` | 340 项依赖：335 material、5 texture | 任务 HUD 美术资源已找到，但没有布局或任务父节点配置 |
| `packages/content/atlas_mission.package` | 7 项依赖：6 texture、1 texture_atlas | 图集资源不能直接给控件屏幕位置 |
| `content/input.config` | 输入绑定和地图灵敏度 | 没有任务布局定义 |
| 两个 `performance_hud.config` | 引擎性能调试 HUD 配置 | 与战斗任务列表无关 |
| `0x8105986402e7f076.geleta.main` | 18,285,360 字节二进制；没有可直接辨认的 objective/hud/gui/layout 文本 | 未取得结构解析证据；不能声称它已被排除为布局配置，也不能按猜测改字段 |
| 10 个 Lua | boot、debug、引擎动画、Wwise、向量场、反射探针 | 未发现战斗任务 UI 的 Lua 构建脚本 |

整个 XAML 集合中，HUD/Mission 类名只有 `ui.HudShip`、`ui.MenuLoadingIntoMission`、`ui.MenuMissionEnd`、`ui.OverlayHud`。`MajorOrder.Objective` 绑定属于战略指令页面，不是战斗任务。

filediver 的历史哈希字典中虽有 `content/ui/basic_mobile_hud`、`content/ui/resourcedictionary0`，本机当前完整索引均未包含它们。旧字典的字符串不等于当前游戏资源存在证明。

可用于后续身份识别的真实任务图标资产：

```text
content/ui/mission/hud/misc/objective_primary.material
name = 230be372b3e9baac
type = eac0b497876adedf
archive = 07f10cad298067ec

content/ui/mission/hud/misc/objective_primary.texture
name = 230be372b3e9baac
type = cd4238c6a0c69e32
archive = 033fd51c0660afa2
```

它可以成为任务图标识别依据，但本轮没有得到“原生 widget 的 material 指针 → 此名称哈希”的已验证映射。

## 现成 MOD 与原生树的证据

HUD Plus 0.2.1：
`external/hudplus-0.2.1-main.lua`。

- 第 265 行的 GameBaked 实际包含 HUD、自己/队友面板、战备等 source；其中没有 objective/task 定义，不能把已知战备面板后面的内存当任务面板。
- 第 4537—4546 行 `set_pair` 使用已经声明的 widget 本地 position/size；第 4562—4573 行 `Instance:edit` 调用此入口。
- 第 4762—4784 行 `reset_layout` 提供已知对象的布局复位。
- GameBaked 的 `widget_material_get` 是 `uintptr_t (*)(uintptr_t)`、RVA `0x144F6E0`。返回 native material 指针；它不是资源名称哈希，不能直接拿返回值比对 `230be372b3e9baac`。

OWHUD 1.0.0 解包目录：
`dist/mod-research/task-layout/overwatch-hud`。

- `Source/native_weapon.lua:24—51`：以每节点 `0x100` 字节读取树，子/兄弟/父/上下文分别 `+0xE0/+0xE8/+0xF0/+0xF8`；上限 64 节点、24 层；验证 parent/context 一致。
- `Source/native_weapon.lua:97—134`：整体 translation 模式允许零固有尺寸的布局容器；用现有父/自身矩阵求平移，而非猜测子元素位置。
- `Source/native_weapon.lua:53—94`：读取全部节点身份，传播 dirty/ancestor refresh，保存 journal；失败或关闭时可还原自己实际持有的值。
- `Source/inventory-profile.json` 保存 widget update 的机器码 pins，确认子/父链及刷新字段；不是只有模拟测试里的随意数字。
- `Source/map_profile.py:10—21` 与 `Source/derive_inventory_profile.py:8—19` 原本从 `live-code-research/report.json` 和 `code-00001000.bin` 取证。**当前下载包未带这些机器码文件**。包中仅留下局部派生 pins；没有完整 `0x12E96D0` 任务 HUD 构造、`0x12EB670` 更新函数窗口可重新解码。不要把脚本文件的存在等同于机器码仍可用。

HD2Runtime 本地 `scripts/research_stratagem_calldown.py:94—165` 已证实 HUD global `0x346D538`、mission `+0x24E340` 以及自己面板等原生路径。它同时记录进入 mission 时运行原生 HUD 构造，支持沿原生控件路线继续研究；当前没有完整任务容器声明。

### HUD Plus 0.2.2 的新增只读根

本轮由同组代理正常下载后仅静态解析的新包：
`external/HD2 HUD Plus 0.2.2 15298 0.2.2 2026-10-07T01-06Z DBAEbGm95.zip`。
ZIP SHA-256：`2a8b640cf23a2a1d0420afb36d653012a6700309c829ef2ddc1dcc6f788389d4`。
主 Lua `56E46A6DC1DF0A13` 正文 SHA-256：`4be0d359d3338b4e5eb580bf7ce3406869294dcf22165bd674936445c68f507c`。
正文保存于 `dist/mod-research/task-layout/hud-plus-0.2.2/56E46A6DC1DF0A13.lua`；本代理再次只读核对了正文哈希与第 266 行。

新版 GameBaked 第 266 行新增 `hud.root`：`hud.manager + hud_root_widget`，其中 `hud_root_widget=600 (0x258)`。同组新增 `hud.root_shown`、`hud.root_opacity`（`+0x44`）、`hud.map_open`（manager `+0x3EF2FD`）；没有 objective/task/goal 来源。完整字面量对照见 [task-relocation-local-mod-research.md](task-relocation-local-mod-research.md) 的“HUD+ 0.2.2 与 0.2.1”节。

`hud.root` 可以作为下一轮只读树定位的首选起点，减少绕自己面板回溯的读取；**这是作者新版 source 的静态证据，本项目尚未实机验证该起点**。它是整 HUD 根，不能直接向下平移这个根来充当任务列表让位。

新版还给出 `hud_root_widget_site` 的取证模式：

```lua
{
  b="410fb6d7488d8f........e8........4c8b1d........",
  take={hud_root_widget={7,4,"u"}},
  a={0,7}
}
```

这说明新增字段有作者的原生指令来源模式，仍不等于本项目已匹配到当前运行指令地址，更不证明任务子节点身份。

## 无需专项人工采集的下一条路线

可以在下一次正常游戏进入 mission 后自动执行一次**只读 UI 树定位**；不需要玩家先/后各按一次采集：

先等待现有真实 mission HUD 的显示和 ready 状态成立，再开始一次定位。不能从启动游戏开始固定 120 秒倒计时，以免玩家尚未进入战斗就结束。玩家正常打开/关闭地图时可顺带记录原生状态和布局；身份切换、时间不足或未读完整时应明确标记 `incomplete`，不能补造完整样本。

1. 首选新版 source 给出的 `HUD + 0x258`，先验证 flags、context、父子链等结构。将已有代码 pins 证明的自己面板 `HUD + 0x24E340 + 0x60` 沿 `+0xF0` 回溯，作为根/context 的交叉核查；不能仅因为 source 中有数字就跳过起点验证。
2. 按已知 `+0xE0/+0xE8` 在 10 Hz 步骤中分批遍历，每步骤**所有读取合计不超过 16 KiB**，祖先、状态、回读校验都计入总量，因此实际节点数少于 64。总上限 1024 个节点、24 层；每次任务只尝试有限一次定位，不在每帧重复扫描。FPS 影响尚未实测，这只是明确读取预算。
3. 记录 identity、父子关系、屏幕矩阵/尺寸、已知 widget kind。右上角几何仅作为候选筛选；再通过代码构造路径、任务图标资源身份或已验证文本参数证实语义。地图开关可直接使用已验证 native flag，在玩家正常开关时自动更新观测。
4. 取得任务专属公共父节点证据后，再复用已有 translation + identity + restore 方案整体下移。若候选不唯一或身份尚不明，仅保存候选诊断，不写未知对象。

这条路线减少玩家操作，但需要正常进入一次战斗才能取得当前活体 UI 树。**离线部分已证明可用的树结构和移动算法，尚未证明具体任务 root；本报告不把方案当作已接通。**

## 可复核文件摘要

| 派生证据 | SHA-256 |
| --- | --- |
| asset-index.txt | `5c385fe89e70d39dee3bfefc196e08d692a937b4489ad3b7b36efaf6248fea36` |
| ah_bin/0xe8e80a83f3fa774d.ah.json | `4fad6d3954b6b8775d048b4d95c17c4a8ea5fd90699f1ec3500f3eb17639b940` |
| xaml/content/ui/shared/xaml/root.xaml | `8fa8f6d52a3aab06046ebb280b01925f683b23abea42588783161f2f74906b21` |
| xaml/content/ui/shared/xaml/overlay_hud.xaml | `969481df3114f1a6138dc66194e79bd1b7f10f1041b2018c9bd8c7e180f485f3` |
| xaml/0x050c579d97022c58.xaml | `a0dcf1c2f40532d6470d336b54f0ea77a348d639809a13318921ee34727343cb` |
| package/packages/content/ui_mission.package.json | `fab11ec5a196caa17d46c06a40518698c45a6fbb33298fe4093b39e3d1857b47` |
| package/packages/content/atlas_mission.package.json | `14ce56b3b391c2c191657846eadcd183a514acd2aa80759f0b82950e05c73fa7` |
