# 来源、依赖与致谢 / Sources, dependencies and credits

本项目是非官方的 HELLDIVERS 2 MOD。下列作品分别提供运行接口、部分代码或研究、数据与图像。署名不代表原作者认可本项目，也不把第三方内容重新授权为 MIT。

This is an unofficial HELLDIVERS 2 mod. The projects below supply runtime interfaces, code or research, data, and artwork. Credit does not imply endorsement or relicense third-party material under MIT.

Uses code / research from HD2Runtime by SkyeShade  
https://github.com/SkyeShade/HD2Runtime

许可范围见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)；费用、汇率、名称、哈希和逐图来源见 [DATA-SOURCES](docs/DATA-SOURCES.md)。

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for licensing boundaries, and [DATA-SOURCES](docs/DATA-SOURCES.md) for prices, exchange rates, names, hashes and individual image sources.

## 运行依赖 / Runtime dependencies

这些依赖由玩家单独安装；本 MOD 不捆绑它们的完整发行包。版本为本项目使用或研究的版本，不表示上游最新版本。

Install these dependencies separately. Their complete releases are not bundled. Versions below identify those used or studied by this project, not the latest upstream release.

| 项目 / Project | 作者 / Credit | 用途 / Use | 许可 / Terms |
| --- | --- | --- | --- |
| [HD2Runtime](https://github.com/SkyeShade/HD2Runtime), 0.30.3 | SkyeShade | 事件、保存、原生结构、SDK、HUD 与只读采集 / Events, persistence, native structures, SDK, HUD and read-only collection | [HD2Runtime License, pinned source](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/LICENSE) |
| [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader), v19 | CowboyBingus | 加载器；归档打包算法有小范围改编 / Loader; limited adaptation of archive-building algorithms | [Zero-Clause BSD](https://github.com/CowboyBingus/BingusSharedLoader/blob/68b9d05fd8e49ba3fb07e7e669ea46d350e9df8f/LICENSE) |
| [Mod Options Menu](https://github.com/CowboyBingus/ModOptionsMenu), v1.2 API | CowboyBingus | 设置菜单、语言接口 / Settings and language API | [Zero-Clause BSD](https://github.com/CowboyBingus/ModOptionsMenu/blob/main/LICENSE) |
| [HD2 HUD+](https://www.nexusmods.com/helldivers2/mods/15298), 0.2.1 / 0.2.4 host; 0.2.2 research | DDRK1ing; Nexus uploader: DDRK1NG | 原生控件宿主与公开扩展接口 / Native widget host and extension API | 上游页面条款；不捆绑 / Upstream terms; not bundled |

## 改编代码与研究 / Adapted code and research

**HD2Runtime.** 主研究版本固定在 `dcd996daca2573443956c07252c55c2d86dd0320`。`src/native-stats.lua`、`src/demolition-world.lua` 和相关只读适配采用其事件结构、描述符及统计研究；虫洞补充参考固定提交 `75988a992141023e50fc0193f4b1de017d9e4b57` 的 `runtime/event_sources.lua`、`runtime/event_world.lua` 和 `domains/event_natives.lua`。车辆、武器、射弹、爆炸、伤害、光束、电弧和状态效果目录也使用其 SDK 与研究。须保留上方可见署名，相关部分继续遵守上游自定义许可。

**HD2Runtime.** The principal pinned source is `dcd996daca2573443956c07252c55c2d86dd0320`. Statistics, world descriptors and related adapters use its code/research; bughole support also references `75988a992141023e50fc0193f4b1de017d9e4b57`. SDK-derived catalogs retain upstream terms. Keep the visible attribution above.

**Bingus Shared Loader.** `tools/build.py` 的归档格式与 seed-zero MurmurHash64A 算法改编自固定提交 `68b9d05fd8e49ba3fb07e7e669ea46d350e9df8f` 的 `scripts/archive.py` / `scripts/build_addon.py`。完整 0BSD 声明保留在 [NOTICE](NOTICE)。

**Bingus Shared Loader.** Archive formatting and seed-zero MurmurHash64A in `tools/build.py` adapt the pinned `scripts/archive.py` / `scripts/build_addon.py`. The 0BSD notice is retained in [NOTICE](NOTICE).

**[Filediver](https://github.com/xypwn/filediver)** — xypwn and Filediver contributors. 离线资源检查、数据类型名称与 datalibrary 枚举研究工具；研究记录固定提交为 `e5c4b91fcc02c04aed05dfac3136d7de23004526`。不捆绑完整程序。其 BSD-3-Clause 声明保留在 [NOTICE](NOTICE)。

**Filediver** provided offline asset inspection, type names and datalibrary enum references. The recorded research revision is `e5c4b91fcc02c04aed05dfac3136d7de23004526`. The executable is not bundled; its BSD-3-Clause notice is retained.

## 提供技术参考的 MOD / Mods consulted as technical references

以下 MOD 不属于运行前置。本项目没有再分发它们的完整代码、音频或图案；按本项目记录，对应逻辑由独立适配和测试实现。上游页面可能限制转载或改编，列为参考不构成再使用许可。

These are research references, not runtime requirements. Their complete code, sounds and graphics are not redistributed. Project records describe independent adapters and tests. Upstream redistribution/modification restrictions remain applicable; this credit is not a license to reuse those files.

| 参考 / Reference | 作者 / Credit | 本项目参考内容 / Contribution |
| --- | --- | --- |
| [Battlefield 5 Hit and Kill Feedback](https://www.nexusmods.com/helldivers2/mods/16927), 1.6.1 / 1.7 | DrOrangi; 页面另致谢原版作者 jadeeeeeeeeee / page also credits the original by jadeeeeeeeeee | 分离死亡与来源事件、即时队列配对、拆除反馈行为 / Separate death/source streams, immediate queue pairing and demolition feedback behavior |
| [DeathSourceNotice](https://www.nexusmods.com/helldivers2/mods/17151), 0.3.71 / 0.3.74 | AxoloFox | 死因展示与来源覆盖研究 / Death-cause presentation and source coverage |
| [OVERWATCH HUD CN EN / OWHUD](https://www.nexusmods.com/helldivers2/mods/17122), 1.0.0 | JoeJackman（页面 Created by 字段）；SmashClaws（上传者及正文署名），正文亦署名 ChatGPT / page creator field: JoeJackman; uploader and description credit: SmashClaws; description also credits ChatGPT | `native_weapon.lua` 控件树，以及 `weapon_heat.lua` / `backpack_ammo.lua` 热量、散热片与背包读数研究 / Widget trees, heat, heat sinks and backpack readings |
| [HD2 HUD+](https://www.nexusmods.com/helldivers2/mods/15298), 0.2.2 research | DDRK1ing / DDRK1NG | 根控件、初始化 ABI、存活检查与挂接布局 / Root widgets, initialization ABI, liveness and attachment layout |
| HD2 Enemy Reinforcement HUD, 0.5.2 | 本地提供包未标可核实作者或公开页面 / Author and public page not established from the supplied package | `ui_snapshot` / `fast_map` 原生地图与 HUD 状态研究 / Native map and HUD state research |
| [Objective Tracker](https://www.nexusmods.com/helldivers2/mods/16913), 0.5.4 | plataodomo | 任务与虫洞研究参考；未复制或分发该 MOD / Objective and bughole research; no redistribution of that mod |

研究记录 / Research records: [kill source notices](docs/kill-source-notice-research.md), [BFV attribution](docs/bfv-kill-attribution-research.md), [local HUD references](docs/task-relocation-local-mod-research.md), [heat sinks](docs/heatsink-reader-evidence.json), [backpack fuel](docs/backpack-fuel-billing-evidence.json), [death causes](docs/death-causes-0.4.61.md).

## 数据与图案 / Data and artwork

- **价格与汇率 / Prices and FX:** 本项目军需标准价工作簿，参考官方预算比例、英国国防部技术说明及 Helldivers Wiki；显示汇率使用欧洲央行及成员央行发布的固定快照。价格不是官方游戏价格。 / Project-defined requisition prices use budget-scale and game-description references. Display conversion uses a fixed ECB/central-bank snapshot, not live rates.
- **哈希与伤害表 / Hash and damage sheets:** 感谢《绝地潜兵2资源ID》表所列 SOPII-Jr、Darctor、S. 等维护者，以及用户提供的伤害表维护者。作者名称来自项目保留的表格署名；未确认的作者不补写。 / Thanks to the resource-ID sheet's recorded maintainers SOPII-Jr, Darctor, S., and contributors to the supplied damage sheet. Unverified names are not invented.
- **敌人名称与渲染图 / Enemy names and renders:** 感谢 Helldivers Wiki（wiki.gg / Fandom）贡献者、[DiversHub](https://divershub.app/database/enemies)（Wild Pluto）和 [Helldivers Training Manual](https://helldiverstrainingmanual.com/bestiary/automatons/factory-strider)。24 种单位绶带使用真实游戏渲染图转单色，未生成新的敌人形象。 / The 24 unit ribbons convert existing game renders to monochrome; enemy anatomy was not AI-generated.
- **成就与其他图案 / Achievements and other graphics:** 本项目设计、用户提供构图与审阅、OpenAI 图像生成及后期处理共同完成部分成就和近战图案；保留的原生游戏符号和参考图另有权利归属。 / Some medal and melee artwork was developed using project direction, user review, OpenAI image generation and editing; retained native game symbols and reference images remain third-party material.
- **视觉参考 / Visual references:** Battlefield 风格的横向绶带；War Thunder“剪刀剪钢板”的成就表达；World of Warships 的 [Witherer 成就概念](https://wiki.worldofwarships.com/Ship:Achievements)。这些是构成或含义参考，不表示获得其游戏素材的开放许可。 / Ribbon composition and achievement concepts reference these games; such inspiration does not grant an open license to their assets.

逐图网址、处理方式、许可尚未确认的部分，以及本项目可授予的范围详见 [DATA-SOURCES](docs/DATA-SOURCES.md)。

Individual image URLs, transformations, unresolved permissions and the limits of this project's grant are recorded in [DATA-SOURCES](docs/DATA-SOURCES.md).
