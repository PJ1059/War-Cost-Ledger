# 任务布局的定向代码读取 · 0.4.7

## 已确认

2026-10-11成功样本 `ledger_ui_20261011T022845Z_map_open_1` 的BIN为4,882,432B，SHA256 `ee338b1688205b060d545a99659a36005fb3c9d370f52314df3acef92eab9648`。77段连续覆盖，采集前后HUD身份、任务及地图状态一致；多帧采样非原子。

- HUD+29B180：2298节点，16个任务槽（stride F068），每槽8个子目标行。实际文本hash解为“启动燃料泵”，子目标为 `#OBJECTIVE_NAME / #TIME_REMAINING`。
- HUD+38CA10：65节点的焦点目标分支，含相同目标名称模板、目标主图与进度，不能忽略。
- 共同父HUD+2944A0还含资源与计时分支，不能仅根据外观称它为任务专用。此次仅首任务槽实填，其余为空；主／支线路由未实证。
- 垂直世界坐标为XZ平面的+9C，缩放为+8C，普通local位置仍+4/+8。不能照搬参考MOD的XY换算。
- 原生position_set 14476A0（Windows x64，两个float32打包uint64）会更新整组dirty和祖先布局。函数已经从实机保存代码验证，未调用。
- map_closed local_y=-10，map_open=-96。仍须核对每帧任务更新是否重设位置，避免10Hz调整出现闪动。

原始结构fixture：`tests/fixtures/task-ui-map-open-0.4.6.json`；分析报告：`dist/mod-research/task-layout/full-ui-20261011/REPORT.md` 和 `dist/task-module-position-offline-2026-10-11.md`。

## 本版唯一新增路径

event_world.open已证明当前EXE/DLL及原生接口；同一世界内验证实际外层update的两段caller指令，再只读：

| 范围 | 大小 | 用途 |
| --- | ---: | --- |
| game.dll+17CF800 | 2KiB | 覆盖布局辅助函数17CF8A0／17CFBB0 |
| game.dll+184B700 | 12KiB | 任务列表update正文 |

在舰上即可运行。共14KiB，10Hz分段，每步最多4096B原生代码读取；开始、PIN、payload、最终PIN复核分步处理。成功一次后持久停读，实际PIN／读／IO失败最多两次；设置关闭、手动采集优先和世界失效取消不消耗失败名额。仅读取代码，没有native调用、游戏写入、控件树扫描、新线程或新服务。

输出为 `%LOCALAPPDATA%/HD2Runtime/mod_data/ledger_task_layout_code_v1_*.json/.bin`，记录真实地址、每段偏移、完整状态、指纹及caller证据。旧 `ui_tree_probe_v1/v2/v3`、手动UI样本和账目不改写；新marker仅用 `task_layout_code_v1`。

## 操作和验收

安装0.4.7后，正常启动游戏，在舰上等待即可。若此前关了自动定位，需要在游戏菜单“自动补齐任务布局代码（测试）”开启并应用。正常默认开启不需菜单操作，也不需Codex运行。

离线验证覆盖真实caller回放、不同构建/PIN拒绝、每步预算、成功停读、失败上限、手动优先、舰上实际addon集成及旧记录保护。实际新采集、原生任务让位画面和FPS尚未验证。

现有性能证据：本局确有一次Ledger回调64.9ms，发生在有效手动采样约31秒前，不能归因此次完整采样。4KiB是读取量上限，不是单帧耗时或零FPS影响保证。
