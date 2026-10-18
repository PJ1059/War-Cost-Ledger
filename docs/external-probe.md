# 独立探针启动器 · 0.3.1

当前唯一目标：关闭 Codex 后，独立启动游戏、采集原生统计、引用现有性能日志。无需操作终端。桌面入口为“HD2 探针启动器”，项目入口为 `启动探针.cmd`。

## 使用

1. 游戏关闭时，关闭 Codex，再双击桌面“HD2 探针启动器”。
2. 点击“启动游戏并自动采集”，正常进入任务。自动每30秒一次，最多15分钟／31条请求。不会重叠采集；等待启动最长5分钟；首个结果最长等120秒，其后45秒。明确未就绪结果可低频重试，结构错误／无响应停止并显示原因。
3. 正常退出游戏，保持轻量探针窗口直到显示结束，再关窗口。会话索引及数据保留，回来后由Codex读文件；已有性能记录MOD同步自动运行。

如果只测一段短行为，可在窗口选标签，再点“采集一次”。按钮在上次请求待响应时不可重复触发。标签可输入中文自定义文字。右上角关闭会停止发送新命令并保持游戏运行；若窗口提前关闭，当前游戏仍缓存探针开关，自动停用需要窗口保持到游戏退出。

若启动失败，窗口会给出原因；基础错误日志为 `%LOCALAPPDATA%\HD2Runtime\mod_data\probe_launcher_error.log`。无需上传整个游戏目录或内存。

## 本轮收集内容

| 内容 | 怎么对照 | 用来证明什么 |
|---|---|---|
| 原生行进距离 | 站立基线 → 一段直线移动 → 移动后；采集保留角色位置；另保留飞船和进入任务的记录 | 距离key、整数或浮点槽、单位、任务清零／基线。不能用瞬移或死亡增援校准行走 |
| 辅助装弹 | 自行装弹、本人提供辅助、本人接受辅助前后；同一行为重复一次 | 可重复计数、计数加给提供者还是接受者。不能用一次性成就解锁位计每次装弹 |
| 火焰来源 | 火焰枪、飞鹰汽油弹、轨道汽油弹前后，使用可识别的标签 | 实际dealt_kills是否进入已证明的来源type；未知来源保留，不能用总击杀冒充指定来源 |
| 性能与加载 | 现有记录器日志与每份采集的UTC时间／PID、外部解码和JSON耗时 | 采集是否与Lua更新间隔／CPU尖峰重合、采样器自身开销；实际FPS仍需另看显示帧率 |

自动采集是定位线索；混合行为中同一字段发生变化不够证明因果。任务主支、爆头或敌种与致死武器的连接仍是之后的独立定位任务，这个启动器不做全场实体或全进程扫描。

## 数据与性能

默认请求 `format=binary`。游戏端只读已证明score映射，原始主表最多4096槽，来源固定64×16条，单次总输出上限1MiB。单次可选读取角色坐标及两个已知原生函数小代码区；不添加常態位置采样或新游戏hook。

二进制容器 `HD2STAT1`：28B头（8Bmagic、5个LEu32长度），依次为小metadata JSON、原始20B条目主表、64×328B来源表、两段可选代码。游戏线程不构造和编码整份条目JSON。`probe_decode.py`在外部验证精确长度、容量及玩家索引，保留独立i32/f32/bool、非有限float位、物理槽及重复来源块；完整JSON由外部生成，可继续用`tools/stat-probe.py diff`。原有手动JSON协议仍兼容。

采集目录为 `%LOCALAPPDATA%\HD2Runtime\mod_data\ledger_probe_<id>.bin/.json`；索引为其 `probe_sessions\<sessionid>.json`。索引包含标签、请求／完成时间、结果路径、错误、游戏PID和已有性能日志引用，完整JSON外部展开可大于1MiB，原始二进制上限不变。只删除本会话自己的待命令，不覆盖已有命令，不修改游戏运行中的账目设置；退出后读取最新账目，仅将`probe_enabled`设false。

已安装的 [性能记录器说明](../../performance-recorder/使用说明.txt) 规定：启动游戏即记录；日志在 `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Performance-*.log`，每秒CPU／内存，每5秒汇总，单文件4MiB。其更新间隔不是GPU显示帧时间或可靠FPS；脚本热点为统计采样，不能当逐MOD精确CPU归属。该启动器只引用对应日志路径，不改记录器代码或加载顺序。

`docs/probe-capture-performance.json` 保留原JSON整次采集测量及同次binary对照。真实游戏LuaDLL、真实ReadProcessMemory自进程合成表、真实文件写入／rename：正常64项主表＋满1024来源平均JSON8.29ms→binary0.434ms；4096槽满主表＋1024来源JSON33.32ms→binary0.469ms，binary P99 0.785／0.779ms。该测量未包括首次require、可选位置定位／代码区，不能作为实战FPS通过。Python外部满表解码约3.12ms、漂亮JSON生成27.41ms，已移出游戏更新线程。

独立窗口使用本机已有Python312/Tk，以低于正常的进程优先级运行，无网页服务器、常驻服务或开机自启项。进程检查每2秒通过只读Windows Toolhelp，不每秒创建tasklist子进程；同一用户会话仅允许一个启动器窗口。

## 开发验证

项目目录运行：

```powershell
& 'external/python.exe' -X utf8 -B tools/build.py
& 'external/python.exe' -X utf8 -B tools/test.py
& 'external/python.exe' -X utf8 -B tests/test_probe_session.py
& 'external/python.exe' -X utf8 -B tests/test_probe_decode.py
& 'external/python.exe' -X utf8 -B tools/probe-launcher.pyw --self-test
```

测试注入模拟进程、时钟和启动动作，仅写临时目录。实际Tk窗口构造和按钮回调经过验证；真实Steam启动、游戏采集、窗口实际画面和实战FPS待用户独立运行验证。[Steam启动协议依据](https://partner.steamgames.com/doc/api/ISteamApps#GetLaunchCommandLine)。

Uses code / research from HD2Runtime by SkyeShade: https://github.com/SkyeShade/HD2Runtime
