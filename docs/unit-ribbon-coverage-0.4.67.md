# 0.4.67 穿刺虫绶带与重型／巨型目录检查

穿刺虫图案本身没有缺失。既有 T05 `heavy_impaler` 已有经审阅的真实原图单色绶带、边框与生涯接线，但只覆盖 `AE57FCDB49F74E98`（云表标作 Impaler MK2），遗漏当前完整穿刺虫本体 `DCF8E74212FBEE3B`。

## 原因与证据

- HD2Runtime 0.30.3 的 `domains/event_entities.lua` 将 `DCF8E74212FBEE3B` 标为 `Impaler`、`enemy/v1/terminids/impaler`、`kill=false`。上游 `scripts/generate_event_entities.py:117` 的 `kill` 来自健康模板的 `kill_score > 0`，不是完整敌人／部件的通用分类；本项目原生成器将所有 `kill=false` 敌人直接排除。
- 同一版本 SDK `sdk/EnemyAuthoringCapabilities.json` 的 `Impaler` 项通过资源路径哈希识别完整本体 `content/fac_bugs/cha_impaler/cha_impaler`，含 4000 主体生命、23 个身体分区及致命头部。独立触手是不同资源 `672F7DA17F3BA34A`、`content/fac_bugs/cha_impaler/cha_impaler_tentacle`，不会因此获得绶带资格。
- 补丁只为该精确本体资源建立本地例外，保存 `runtime_kill_flag=false` 与原始路径作为差异说明，并在重建时校验 SDK 路径、生命、分区和头部。其他 `kill=false` 敌人、部件、构筑不自动提升。

## 修复范围

`docs/integration-catalogs.json` 从 134 增至 135 个目标资源，仍为 76 个名册种类。原 134 条记录、1185 个来源、94 个战备价格和 81 个弹药价格不变。T05 同时绑定旧 MK2 与完整本体，复用已批准的 `artwork/review-0.4.57-ribbons-v4/heavy-impaler.png`，不更换任何图像。

检查完整原生资源目录及 76 个已命名名册：24 种重型／巨型单位（6 种巨型、18 种重型）都有对应图案、稳定键与运行时接线，修复后覆盖 29 个精确资源别名。重型／巨型中只有完整穿刺虫本体遭到上述 `kill=false` 过滤；其他已命名完整本体没有同类漏配。未知体型与 BOSS 不擅自转成重型或巨型；触手、炮塔部件不算第二个敌人。

新本体仍沿用原有归属门槛：已验证的本地最终击杀者可以计入；他人归属不能计入；缺少最终击杀者时必须由现有短窗口内原生本地击杀增量支持。不会回填旧历史，也不会把触手或不明尸体改造成穿刺虫。

## 验证

- 新回归在旧 0.4.66 实际构建产物上复现 `T05 alias did not earn its own variant`，日志位于 `dist/career-combat-0.4.67/ribbon-built-before.log`。
- 目录完整性、原图与运行时名称一致、例外 SDK 身份变化会停止重建、来源边界与计价重建测试通过；SDK 图案编译检查另见同目录 `ribbon-game-icons-after.log`。
- 最新 0.4.67 实际构建回放通过，覆盖全部 24 种单位／29 个资源别名、首次提示及图案、单场／生涯／时段／保存重读，以及本体／触手／他人归属／无本地计杀额度的区别，日志位于 `dist/career-combat-0.4.67/ribbon-built-after.log`。本文件不将离线结果等同于实战验证。
