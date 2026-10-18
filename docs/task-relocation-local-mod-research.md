# 任务列表让位：本机 MOD 源码核对

核对日期：2026-10-11。结论：OWHUD 1.0.0 提供了**原生控件树遍历和整组移动**的真实源码范例；它的聊天上移使用另一套**聊天专用原始位置字段**。本轮仍未取得 Objectives 完整列表的专用根节点，不能将聊天或整个 Mission HUD 的偏移当作任务容器偏移。

本轮只读取 ZIP、资源表和源码。没有执行第三方 Lua/Python、安装 MOD、启动游戏或修改 Arsenal 配置。经授权，仅把 OWHUD 文本研究材料解出到 `dist/mod-research/task-layout/overwatch-hud/`、把 HUD+ 0.2.2 原样 Lua 正文解出供静态复核，并编写本文。图片及 Addon 主 archive 未解出。OWHUD 完整文本文件的 SHA256 在该目录 `extraction-manifest.json`。

## OWHUD 来源与实际装载内容

来源 ZIP：`external/OWHUD V1.0.0 17122 1.0.0 2026-10-09T09-26Z Zdo1YygCp.zip`。

| 对象 | SHA256 |
| --- | --- |
| ZIP | `8dd9ceeb4064434d17f875566795dced448eed4b349486003695deb9c1d40c31` |
| `Addon/9ba626afa44a3aa3.patch_0` | `b8013feffd2c1755bf5349950d58ed7eae32f8d5914f9acc3f3914f59450b3bc` |
| `Source/embedded.lua` / 实际 Addon Lua 正文 | `4282be39438768f2b5e2d75977b1acfb2b52227bca282ed561c05506fb42a7a6` |
| `Source/native_features.lua` | `0ffe3a56b81e462ec34db2f76a00b3a5918b33843bb88dc065e8b1a806a0d1f2` |
| `Source/native_weapon.lua` | `18193f0a9fedad3fe00e68c78334eca0efa8de01f18954aec3b45b43d9d02c19` |
| `Source/hud_bridge.lua` | `4f582edfbaf3920e86cb65aa2a13c4d0ef3dc4cee4276fdc248073f04afe3601` |
| `Source/inventory-profile.json` | `5cb83ad5735a204e673db686f577f200d91408695f98db2c7d8042837a28cd67` |
| `Source/app.lua` | `94b9c481dd7de6494e7e90671c3496e877d24d7949720b651689a4d12eb54664` |

Manifest 名称 `OWHUD 1.0.0`，GUID `7d16d51f-f6fa-497f-bd38-8b1796f67587`。README 第 13–14 行说明此发行名保留了此前 0.3.15 功能和设置。作者要求 Loader v19 推荐、Runtime 0.28.1 或 API 1 兼容新版、MOM v1.2 或 API 1 兼容新版；这是包内兼容性声明，本轮没有实机确认。

主 archive 仅一个 Lua 资源：`93C207034DFA98A0` / 类型 `A14E8DFA2CD117E2`。去掉 8 字节 Lua 资源头后的 24,290,433 字节与 `Source/embedded.lua` **逐字节相同**。`native_features.lua`、`native_weapon.lua`、`hud_bridge.lua` 和 `app.lua` 的完整文本均包含在该 embedded 正文中。因此下列函数属于实际 Addon 内容，不仅是遗留研究文件。

## 聊天上移：对象明确，但字段不通用

`Source/native_features.lua:123` 的 `M.chat_new`，对应 embedded 第 1919 行。`Source/inventory-profile.json:408` 给出对象和指令核对值：

| 字段 | 数值 | 含义与证据 |
| --- | --- | --- |
| `hud` | `game + 0x346D538` | 读取 HUD manager 指针 |
| `widget` | manager `+0x14498` | 聊天控件起点；chat 捕获函数第 128 行 |
| `position` | chat `+0x139A0` | 原始位置，两项 float32；**不是通用 widget local position +4** |
| `transition` | chat `+0x139BD` | 捕获前检查两个字节均为零 |
| `docked` | chat `+0x139BE` | profile 中存在；与上述两字节检查重叠 |
| `setter` | `game + 0x1860930` | 特定聊天 setter；profile 中机器码 `48 89 91 A0 39 01 00 C3`，即将 8 字节写到 `[RCX+0x139A0]` 后返回 |

profile 第 415–435 行还固定核对五段相关机器码。这里是**固定 RVA 上比较精确指令字节**，不是自动搜索新版本地址。

捕获过程第 125–141 行：读取 chat `0x100` 字节、原始位置和转换状态；从 `+0xF0` 得父级、`+0xF8` 得 GUI context；检查控件种类、父级 context、正比例和有限坐标。第 145–158 行调用前重新捕获身份，并在调用后回读原始位置。

第 170–193 行按 `原始 Y + 屏幕偏移 / 父级 Y 比例` 计算目标，不反复累加。位置已经达到目标时直接返回，不重复调用 setter。第 160–168 行仅恢复身份相同且仍保持本 MOD 最后写入值的对象；第 175–178 行遇到其他 MOD 修改原始位置时让步。

`Source/app.lua:966` 表明调用位于 10Hz 状态轮询，偏移按 `chat_offset * height / 1080` 换算，保留游戏自行计算的地图偏移。`Source/hud_bridge.lua:740` 在 proof 不通过时停用聊天移动。

`Source/features_035_tests.lua:89` 开始的测试采用模拟内存与注入 setter，覆盖固定偏移、父级比例、240 次稳定轮询不重复 setter、地图变化、恢复和其他 MOD 修改。**本轮没有执行这些测试；它们也不构成实机移动任务列表的证据。**

## 通用原生控件树与整组移动

`Source/native_weapon.lua:24` 的 `tree()`（embedded 第 721 行）是本轮新增的关键证据：

| 原生 widget 字段 | 相对偏移 |
| --- | --- |
| 第一个子控件 | `+0xE0` |
| 下一个同级控件 | `+0xE8` |
| 父控件 | `+0xF0` |
| GUI context | `+0xF8` |
| 本地 X/Y | `+4 / +8` |
| 本地 X/Y 比例 | `+0x14 / +0x18` |
| 变换矩阵 | `+0x64`，16 项 float32 |
| dirty 标记 | `+0xB8` |

`tree()` 从已知根开始，读取每个节点 `0x100` 字节，沿 child/sibling 遍历后再沿 parent 收集祖先。默认最多 64 个子孙，深度及祖先最多 24；检查循环、子控件回指父级、非零 flags、共同 GUI context。它不是依靠文字关键词寻找 Objectives 的函数。

`Source/inventory-profile.json:60` 的 `widget_update` 给出与 child/parent/dirty/refresh 相关的三段指令字节核对值，字段 `child=224`、`sibling=232`、`parent=240`、`dirty=184`。`Source/hud_bridge.lua:21` 也有 opacity 子孙和祖先遍历，保持 dirty/ancestor 更新语义。

`Source/native_weapon.lua:97` 的 `M.plan()`（embedded 第 794 行）验证树、动画/dirty 状态、父子矩阵，计算位置与比例。第 121–134 行的 `translation=true` 支持没有自身宽高的 layout container：保持比例，从现有矩阵和父级比例解出本地平移，而不借用子控件尺寸。

`Source/native_weapon.lua:53` 的 `checked_write()`（embedded 第 750 行）在写入前回读整棵树和祖先身份、验证可写区域，保存回滚 journal；更新根位置/比例后传播子孙 dirty 和 refresh flags，再更新祖先 flags。没有重新挂接或替换子控件。

`Source/hud_bridge.lua:705` 起验证武器与弹药两个原生组的具体父级和子链接，第 733 行明确调用整组移动。`Source/native_weapon.lua:167` 的 `content_target()` 对已知子内容求布局，第 207 行起的 `restore()` 按身份和最后拥有值恢复。这些函数提供“找到任务列表独立父容器以后，移动完整列表”的实现参考。

**尚缺的一步：确定任务列表自身的独立父容器，以及游戏是否每次刷新任务/开地图时重设其源位置。** OWHUD 的生产源码没有 Objectives 专用偏移；`hud_bridge.lua:758` 唯一普通 objectives 文字只是“携带任务物品”的注释，不能用于任务 HUD 定位。

## 上轮本机包检查补录

当前 Arsenal default 58 个条目、library 55 个。安装目录按 manifest 和文件名筛选，再针对候选读取主 archive 资源表/Lua。未扫描图片像素、GPU 或游戏全数据内容。

### HD2 HUD+ 0.2.1

路径：`external/9ba626afa44a3aa3.patch_0`。

主 archive SHA256 `72775038fb6397e39d45e05259becc501ccca11b0ef64fa67fbcada836018626`；Lua 资源 `56E46A6DC1DF0A13` 正文 SHA256 `1242c75a8665a1e4153e1372623e6b90688dcc0239bae80cbb6ba611de4b3ab9`。

包内 Lua 第 265 行 `GameBaked`：HUD manager 根 RVA `0x346D538`；Mission HUD 内嵌 `+0x24E340`；其下自身面板 `+0x60`、队友面板 `+0x1F8C8`、战备面板 `+0x146DC0`。因此 **Mission HUD 根不是仅任务列表**。

第 4537 行 `set_pair`、4562 行 `edit`，第 4584 行 `append` 验证父级，第 5622 行 `mount` 验证父级/context 后 detach/attach。widget parent `+0xF0`；position setter `game+0x14476A0`，refresh `+0x144BD60`，attach `+0x144C5C0`，shown setter `+0x14508E0`。这些是包内研究地址与签名，本轮未实机复核；该包未给任务专用根。

### DeathSourceNotice 0.3.44

ZIP：`external/DeathSourceNotice_0.3.44_Helldivers2.zip`，SHA256 `a91fd07df4dd6349ab68cdfeab9cb2ac6515897e426fb35330c824d365d16310`。

主 archive SHA256 `58194b2754919727da1903e2da6460f0117c66d86f4c2be17c80c5efa4eec965`；Lua `93C9A8B3ABBE9EC1` 正文 SHA256 `129718e2cb883d6220cf86fdcc4176b89536b733c8246f32a17e9a2a6f493bfe`。第 3873 行自建 screen GUI。第 6130 行 `escape_menu()` 沿原生 ESC 菜单/UI stack 定位；后续 widget 为嵌入 MOM 的选项控件。没有任务列表父级遍历。该 ESC screen 链不能当成 Objectives 定位链。

### Battlefield5 Kill Feedback

ZIP：`external/Battlefield5 Kill Feedback 16832 3 2026-10-09T14-19Z sZaXo0k70.zip`，SHA256 `2afd3061d199dec7082c526fa6968b88bd66fd854bc7d77278b052a91f2faaed`；manifest 实际版本是 `BF5_kill_feedback 0.1.13`。

主 archive SHA256 `72f75a92cb902b4111448663010b966f47a6ae9d8e3d2e6d088ebe0c5c7658c2`；Lua `D6943546EB766CAC` 正文 SHA256 `6a416ecfd44cca04ef16f0b5e06d20c45c85868141208b4217e8b86a9685313a`。第 2911 行 `ensure_gui()`、2918 行自建 screen GUI、第 3506 行绘制命中和击杀卡片，没有任务父级或原生 widget child traversal。

### BIT BETTER UI 3.0

目录：`external/BIT BETTER UI 2749 3.0 2026-08-16T15-26Z YUHF0QDSo_AR687998`。Manifest 描述明确是战备图标。`Eagles/*/4c2203529ff1a9c4.patch_0` 九份主 archive 均为 944 字节、两项 texture（类型 `CD4238C6A0C69E32`），没有 Lua/XAML；主 archive 均有 SHA256 `d6071944a7eca201fb4b1def8b892c06e6af9f66b8a261e538875cd6282ec260`。GPU 文件没有读取。

最初的文件名检查只发现已安装 HUD+ 0.2.1；后续下载 0.2.2 的对照结果见下一节，两份版本未安装混用。

## 后续补充：HUD+ 0.2.2 与 0.2.1 的静态来源对照

根代理随后正常下载 `external/HD2 HUD Plus 0.2.2 15298 0.2.2 2026-10-07T01-06Z DBAEbGm95.zip`。新版已取得，但没有安装。

| 对象 | SHA256 |
| --- | --- |
| 0.2.2 ZIP | `2a8b640cf23a2a1d0420afb36d653012a6700309c829ef2ddc1dcc6f788389d4` |
| 主 archive `9ba626afa44a3aa3.patch_0` | `5da7897d174f5b39337df3195fe3a70d8c48d42f47903fbb83c8ec2560bf2b99` |
| Lua `56E46A6DC1DF0A13` 正文 | `4be0d359d3338b4e5eb580bf7ce3406869294dcf22165bd674936445c68f507c` |

主 archive 721,977 字节；实际 Lua 正文 674,274 字节，供复核的原样正文保存为 `dist/mod-research/task-layout/hud-plus-0.2.2/56E46A6DC1DF0A13.lua`。`GameBaked` 从 0.2.1 第 265 行变为 0.2.2 第 266 行。本轮以字符串和括号范围解析静态字面量，**没有执行 Lua 或新版 Addon**。

`GameBaked.sources` 来源条目 656→699，新增 51、移除 8；新增项集中在持枪面板唤醒、终端交互、投掷/C4、战备原生列表与 HUD 显示状态。没有新增 `objective`、`task`、`goal` 专用来源，也没有新增可定位任务列表的 child/sibling 来源。

其中与下一步有界控件树定位有关的新来源：

| 来源名 | 0.2.2 静态定义 |
| --- | --- |
| `hud.root` | `hud.manager + hud_root_widget`，`form="address"`；`hud_root_widget=600 (0x258)` |
| `hud.root_shown` | `hud.root` flags 的 `widget_shown_bit=4` |
| `hud.root_opacity` | `hud.root + widget_local_opacity=68 (0x44)`，float32 |
| `hud.root_lit` | 上述 opacity 为正 |
| `hud.map_open` | `hud.manager + hud_map_open_at=4125437 (0x3EF2FD)`，bool；还要求显示就绪且未展示战备 |
| `hud.clock` | `hud.mission + hud_clock=2225576 (0x21F5A8)`，float32 |

原 HUD manager RVA `0x346D538`、Mission HUD `+0x24E340`、widget parent `+0xF0` 未改变。`hud.root` 是整个原生 HUD 的控件根，可作为只读遍历的**定位起点**；它不是任务列表专用父级，不能把整个根整体向下移动。此新版没有消除“定位 Objectives 独立容器”的缺口。

新版 `GameBaked.patterns.hud_root_widget_site` 有明确指令搜索模板：`410fb6d7488d8f........e8........4c8b1d........`；`take={hud_root_widget={7,4,"u"}}`，`a={0,7}`。HUD manager 模板 `roots_hud_manager_rva_site` 为 `c780........01000000488b0d........4885c9`，提取 `{13,4,"rip"}`。这是包内静态定位规则，不是本机已成功匹配的证据。

## 公开源码补查

GitHub 仓库检索与已读取的作者源码未找到可直接使用的 Objectives 完整列表移动入口。可以确认的相邻项目：

- [Treasure Map 固定源码](https://github.com/Th3chef/Treasure-Map/blob/77b11252fdfb7405cc1d6e34ad4b4a37bcd7bc5a/src/lua/body.lua#L317)：读取战术地图和拾取物位置，以 `gui_for()` 自建 screen GUI；不移动任务容器。
- [DRIVER HUD 固定源码](https://github.com/FireScallion/DRIVER-HUD---HD2-Vehicle-HUD/blob/1737f689aedce44ae8eaf6081a821a1f02752e9b/src/frv_ui.lua)：绘制车辆状态；没有任务列表定位。

此结果只说明本轮候选和已检查来源未提供入口，不能证明其他未检查项目不存在该功能。下一步应复用 OWHUD 已证实的树字段和 HUD+ 的原生结构证据，定位任务列表独立父容器，再验证多任务与开/关地图刷新后的整体布局。
