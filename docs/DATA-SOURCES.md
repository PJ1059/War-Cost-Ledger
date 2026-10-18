# 数据与图像来源 / Data and image sources

范围：0.4.65 公开源码与发行说明。记录实际使用的资料及来源边界；不把社区整理数据、游戏渲染图或其他 MOD 改编部分归为本项目独占原创。软件作者与依赖许可另见 [THIRD-PARTY](../THIRD-PARTY.md) 和 [NOTICE](../NOTICE)。

Scope: public source and release documentation for 0.4.65. This register distinguishes project work from community data, game renders and adapted material. Software credits and licensing are in [THIRD-PARTY](../THIRD-PARTY.md) and [NOTICE](../NOTICE).

## 费用 / Prices

直接计价来源是 [HD2-军需价格表-v0.2.xlsx](../pricing/HD2-军需价格表-v0.2.xlsx)。其“计费规则”“定价参数”说明：金额是本 MOD 的军需标准价，现实资料只作成本比例与技术类型的参考，**不是官方游戏价格，也不代表现实装备的实际报价**。采购、弹药、消耗和维护的取值及已确认修改保存在工作簿与对应计费文档。

The direct price source is the project's workbook. Its rules and parameter sheets define fictional requisition prices, informed by cost-scale and technology references. They are **not official game prices or real procurement quotations**. The workbook and billing notes preserve the applicable amounts and approved adjustments.

| 来源 / Source | 实际用途 / Use |
| --- | --- |
| [FY2026 Counter-ISIS Train and Equip Fund budget](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2026/FY2026_CTEF_J-Book.pdf#page=12) | 工作簿记录 PDF 第 12 页／印刷第 9 页的普通弹药单位成本作比例锚点；不把所有游戏装备等同现实武器。 / The workbook records ordinary-ammunition unit costs on PDF page 12 / printed page 9 as scale anchors, not a one-to-one pricing model for game weapons. |
| [UK Ministry of Defence: DragonFire](https://www.gov.uk/government/news/boost-for-armed-forces-as-new-laser-weapon-takes-down-high-speed-drones) | 激光技术与低单次发射成本的背景参考；MOD 激光维护折旧费由项目规则决定。 / Background on laser technology and low per-shot operating costs; the mod's maintenance charge is a project rule. |
| [Helldivers Wiki weapons](https://helldivers.wiki.gg/zh/wiki/%E6%AD%A6%E5%99%A8?variant=zh-sg), [stratagems](https://helldivers.wiki.gg/zh/wiki/%E6%88%98%E7%95%A5%E9%85%8D%E5%A4%87?variant=zh-hans), [Maintenance Report](https://helldivers.wiki.gg/zh/wiki/Maintenance_Report) | 名称、技术类别与背景；逐装备链接保留在工作簿 N 列，英文名在 P 列。 / Names, technology classes and background; per-item URLs are retained in workbook column N and English names in P. |
| [Ship Master voice lines](https://helldivers.wiki.gg/wiki/Ship_Master#Voice_Lines), [Liberty-Class Cruiser](https://helldivers.fandom.com/wiki/Liberty-Class_Cruiser) | 军需与舰船背景参考，来源保留在规则页。 / Requisition and ship-lore references retained on the rules sheet. |

`1 MC = 1 USD` 是本 MOD 的记账标尺，不是游戏货币的现实兑换承诺；不换算超级货币或申购点。汇率切换只影响显示，历史账目继续使用 MC。

`1 MC = 1 USD` is an accounting convention, not a real exchange offer for an in-game currency. Super Credits and Requisition Slips are not converted. Currency selection changes display; stored accounting remains in MC.

## 汇率 / Exchange rates

来源记录：[currency-rates-2026-10-11.json](currency-rates-2026-10-11.json)。使用 2026-10-09 的固定欧元参考汇率，2026-10-11 复核；以 EUR 报价换算为 USD/MC 基准。游戏运行时不查询网络，也不把该历史快照称为当前市场价格。

The [rate snapshot](currency-rates-2026-10-11.json) stores euro reference rates dated 2026-10-09, checked on 2026-10-11, converted to a USD/MC base. The mod makes no live exchange-rate requests; this historical snapshot is not advertised as current market pricing.

- [European Central Bank — euro foreign exchange reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.fr.html)
- [Bank of Lithuania — ECB daily reference rates](https://www.lb.lt/en/daily-euro-foreign-exchange-reference-rates-published-by-the-european-central-bank)
- [Banque de France — daily parities, 2026-10-09](https://www.banque-france.fr/en/statistics/rates-and-prices/exchange-rates-daily-parities-2026-10-09)

## 哈希、伤害与名称 / Hashes, damage and names

| 来源 / Source | 范围与对应记录 / Scope and records |
| --- | --- |
| [绝地潜兵2资源ID / resource-ID sheet](https://docs.qq.com/sheet/DQ3Rya0VudGd3WWtv?tab=000001) | 2026-10-15 读取，保留完整 64 位身份、原表坐标与中英文名称。表内署名记录为 SOPII-Jr、Darctor、S. 等维护者；本次公开页面无法重新读取，署名来自此前保留的来源记录。无歧义名称用于显示回退；名称冲突不自动选一个。 / Retrieved 2026-10-15; full 64-bit IDs, cell coordinates and bilingual labels retained. SOPII-Jr, Darctor, S. and contributors are credited in the retained source record; the live sheet was not readable during this audit. Only unambiguous labels are used. [resource-hash-aliases.json](resource-hash-aliases.json) |
| [伤害与常用 ID 表 / damage and common-ID sheet](https://docs.qq.com/sheet/DT0ttc2VhVkRDcWVS) | 交叉核对伤害共享关系与名称；2026-10-10 的“焚诀(常用id)”页还用于敌人完整哈希核对。未核实维护者名称，不作猜测。 / Cross-checks of names/shared damage; the recorded 2026-10-10 common-ID worksheet also supports full enemy-hash checks. Maintainer names have not been verified. [enemy-hash-evidence.json](enemy-hash-evidence.json), [damage-ID notes](damage-id-attribution-0.4.54.md) |
| [HD2Runtime SDK and research](https://github.com/SkyeShade/HD2Runtime/tree/dcd996daca2573443956c07252c55c2d86dd0320) — SkyeShade | 武器父来源、车辆挂载、原生射弹／爆炸／伤害／光束／电弧目录、状态效果、只读结构和事件字段。 / Parent weapons, vehicle mounts, typed projectile/explosion/damage/beam/arc catalogs, statuses and native fields. [integration catalog](integration-catalogs.json), [damage-source catalog](damage-source-catalog.json), [fire sources](fire-sources.json), [hellpod sources](hellpod-kill-sources.json) |
| [Filediver](https://github.com/xypwn/filediver) — xypwn and contributors | 原生类型名称与 datalibrary 枚举、离线游戏资源检查；完整程序不捆绑。 / Native type names, datalibrary enums and offline game-asset inspection; tool not bundled. |
| [Helldivers Wiki factions (EN)](https://helldivers.wiki.gg/wiki/Factions), [阵营 (ZH)](https://helldivers.wiki.gg/zh/wiki/%E9%98%B5%E8%90%A5) — wiki contributors | 敌人名册、中英文名称与类别参考；保留项目审核名称，不根据名称直接推断某次击杀的武器或归属。 / Roster, bilingual names and class references; a name alone does not establish an individual kill's source. [enemy catalog](enemy-catalog/units.json) |

资源哈希与射弹／爆炸／伤害类型编号是不同的身份空间，不能混用。静态目录能证明关联能力，不能证明某次击杀一定由该武器造成。共享破片、持续伤害和其他 MOD 改写仍需运行时上下文；没有证据时保留未知。英文展示目录复用上述已经核对的英文名称与项目原创界面翻译，不改玩家昵称、身份或历史原始记录。

Resource hashes and typed projectile/explosion/damage IDs are separate namespaces. Static relationships show capability, not ownership of an individual kill. Shared fragments, damage over time and overrides still require runtime context. English display reuses verified catalog names and project UI translations without changing player names, identities or historical records.

## 图像制作与权利 / Artwork production and rights

24 种敌人绶带从已有真实游戏渲染图制作：保留轮廓，裁切背景／多余主体，简化内部结构，再转米白单色并装入本项目绶带底框。没有用生成模型重新设计敌人。以下表格将来源网页和直接图像分别列出；不把图片托管方自动当作底层美术的权利人。

The 24 enemy ribbons use existing game renders: crop, remove irrelevant subjects, simplify interior detail, convert to ivory monochrome and compose with the project's ribbon frame. Enemy forms were not AI-generated. The table distinguishes hosting pages from direct files; a host is not necessarily the underlying art's owner.

[DiversHub 的页面署名](https://divershub.app/database/enemies/vox-engine)将游戏渲染图归于 Helldivers Wiki（wiki.gg / Fandom）贡献者，并列出 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 等条款。这不是逐图权利链的完整核验；现有清单对部分素材明确记录 `license_verified: false`。直接 wiki 图片与 Training Manual 的移动工厂图也未取得逐文件开放授权确认。**本项目 MIT 不覆盖这些图像或它们的衍生纹理，不能将其宣称为公有领域或允许无限制商业再分发。** 对适用 CC BY-NC-SA 的材料，需要保留来源、说明修改、遵守非商业和相同方式共享要求；底层游戏权利仍归相应权利人。

[DiversHub's attribution](https://divershub.app/database/enemies/vox-engine) credits Helldivers Wiki contributors and identifies [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) and related terms. That is not complete per-file rights verification. Some retained manifests explicitly say `license_verified: false`; individual permissions for direct wiki files and the Training Manual Factory Strider image remain unconfirmed. **The project's MIT license does not cover these images or derived textures.** Where CC BY-NC-SA applies, retain attribution, identify changes, and follow its noncommercial/share-alike conditions; underlying game rights remain with their owners.

### 敌人绶带逐图索引 / Individual enemy-ribbon sources

所有条目的处理均为上述裁切与单色化；证真者、御门者、肉瘤体进一步去除前景残骸／多余人物，增强小尺寸识别。 / All entries use the transformations above; Veracitor, Gatekeeper and Fleshmob additionally remove foreground wreckage/extra figures for small-size clarity.

| 输出图标 / Output icon | 单位 / Unit | 来源页面与原图 / Source |
| --- | --- | --- |
| `giant-dragonroach.png` | 蟑龙 / Dragonroach | [页面 / page](https://divershub.app/database/enemies/dragonroach) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1280px-Dragonroach_Enemy_Icon.png) |
| `giant-bile-titan.png` | 吐酸泰坦 / Bile Titan | [页面 / page](https://divershub.app/database/enemies/bile-titan) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/Bile_Titan_Enemy_Icon.webp) |
| `giant-spore-burst-bile-titan.png` | 孢裂吐酸泰坦 / Spore Burst Bile Titan | [页面 / page](https://divershub.app/database/enemies/spore-burst-bile-titan) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/Spore_Burst_Bile_Titan.webp) |
| `giant-vox-engine.png` | 噪轰引擎 / Vox Engine | [页面 / page](https://divershub.app/database/enemies/vox-engine) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/VoxEngine.webp) |
| `giant-factory-strider.png` | 移动工厂 / Factory Strider | [页面 / page](https://helldiverstrainingmanual.com/bestiary/automatons/factory-strider) · [原图 / image](https://helldiverstrainingmanual.com/images/bestiary/factory-strider.png) |
| `giant-leviathan.png` | 利维坦 / Leviathan | [页面 / page](https://divershub.app/database/enemies/leviathan) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/720px-Leviathan_Enemy_Icon.png) |
| `heavy-charger.png` | 强袭虫 / Charger | [页面 / page](https://divershub.app/database/enemies/charger) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/Charger.webp) |
| `heavy-charger-behemoth.png` | 巨兽级强袭虫 / Charger Behemoth | [页面 / page](https://divershub.app/database/enemies/charger-behemoth) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/960px-Charger_Behemoth_Enemy_Icon.png) |
| `heavy-spore-charger.png` | 孢子强袭虫 / Spore Charger | [页面 / page](https://divershub.app/database/enemies/spore-charger) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1043px-Spore_Charger_Enemy_Icon.png) |
| `heavy-rupture-charger.png` | 爆裂强袭虫 / Rupture Charger | [页面 / page](https://divershub.app/database/enemies/rupture-charger) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/Rupture_Charger_Enemy_Icon.webp) |
| `heavy-impaler.png` | 穿刺虫 / Impaler | [页面 / page](https://divershub.app/database/enemies/impaler) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/Impaler_Enemy_Icon.png) |
| `heavy-hulk-bruiser.png` | 巨型碾压者 / Hulk Bruiser | [页面 / page](https://divershub.app/database/enemies/hulk-bruiser) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1080px-Hulk_Bruiser_Enemy_Icon.webp) |
| `heavy-hulk-scorcher.png` | 巨型炙炎者 / Hulk Scorcher | [页面 / page](https://divershub.app/database/enemies/hulk-scorcher) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1080px-Hulk_Scorcher_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Hulk_Scorcher) |
| `heavy-hulk-obliterator.png` | 巨型抹煞者 / Hulk Obliterator | [页面 / page](https://divershub.app/database/enemies/hulk-obliterator) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1080px-Hulk_Obliterator_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Hulk_Obliterator) |
| `heavy-hulk-firebomber.png` | 巨型烈焰轰炸者 / Hulk Firebomber | [页面 / page](https://divershub.app/database/enemies/hulk-firebomber) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/773px-Hulk_Firebomber_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Hulk_Firebomber) |
| `heavy-annihilator-tank.png` | 湮灭坦克 / Annihilator Tank | [页面 / page](https://divershub.app/database/enemies/annihilator-tank) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1280px-Annihilator_Tank_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Annihilator_Tank) |
| `heavy-barrager-tank.png` | 铁幕坦克 / Barrager Tank | [页面 / page](https://divershub.app/database/enemies/barrager-tank) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/934px-Barrager_Tank_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Barrager_Tank) |
| `heavy-shredder-tank.png` | 碎裂坦克 / Shredder Tank | [页面 / page](https://divershub.app/database/enemies/shredder-tank) · [原图 / image](https://secejvpgd09sdpuq.public.blob.vercel-storage.com/1280px-Shredder_Tank_Enemy_Icon.webp) · [Wiki](https://helldivers.wiki.gg/wiki/Shredder_Tank) |
| `heavy-war-strider.png` | 战争纵步者 / War Strider | [原图 / image](https://helldivers.wiki.gg/images/War_Strider_Enemy_Icon.png?3f3211) |
| `heavy-veracitor.png` | 证真者 / Veracitor | [原图 / image](https://helldivers.wiki.gg/images/Veracitor_Enemy_Icon.png?456e79) |
| `heavy-gatekeeper.png` | 御门者 / Gatekeeper | [原图 / image](https://helldivers.wiki.gg/images/Gatekeeper_Enemy_Icon.png?ac7e7b) |
| `heavy-fleshmob.png` | 肉瘤体 / Fleshmob | [原图 / image](https://helldivers.wiki.gg/images/Fleshmob_Enemy_Icon.png?886d74) |
| `heavy-crusher.png` | 粉碎者 / Crusher | [原图 / image](https://helldivers.wiki.gg/images/Crusher_Enemy_Icon.png?5b5c38) |
| `heavy-harvester.png` | 猎杀器 / Harvester | [原图 / image](https://helldivers.wiki.gg/images/Harvester_Enemy_Icon.png?127c0a) |

来源哈希与制作记录 / Source hashes and processing records:

- [Source manifest](../artwork/review-0.4.57-source-v3/source-manifest-qq.json), [Titans](../artwork/review-0.4.57-source-v3/source-manifest-titans.json), [heavy bots](../artwork/review-0.4.57-source-v3/heavy-bots-sources.json), [other heavy units](../artwork/review-0.4.57-source-v3/heavy-source-manifest.json).
- [Monochrome conversion](../artwork/review-0.4.57-ribbons-v4/conversion-manifest.json), [three revised enemies](../artwork/review-0.4.57-ribbons-v5/enemies/conversion-manifest.json), [integrated artwork catalog](../artwork/integration-0.4.58/catalog.json).

这些清单的 `review_only` 或 `not_integrated` 是生成当时的历史状态；后来实际接入以 integration 清单与发行记录为准，不应据此认定最终素材没有分发。

`review_only` / `not_integrated` in early manifests describe their historical draft state. Later inclusion is established by the integration catalog and release notes; those old flags do not prove an asset is absent from the release.

### 成就、近战与原生符号 / Medals, melee and native symbols

- “民主之星”系列、“摧毁暴政减速带”、“等级不是问题”和加甲肘击等图案包含 OpenAI 图像生成结果、用户构图参考、人工审阅与后期处理。认可原图的导出没有再次生成，不意味着原始制作未使用生成工具。 / These medal and melee designs include OpenAI-generated images, user-supplied composition references, review and post-processing. Exporting an approved original without regeneration does not mean its initial production was non-generative.
- “等级不是问题”的剪刀剪钢板含义来自用户提供的 War Thunder 成就参考；横向绶带以 Battlefield 风格为构成参考；火焰成就部分参考 World of Warships 的 [Witherer](https://wiki.worldofwarships.com/Ship:Achievements)。引用概念与风格不构成对原游戏图标的重新授权。 / These games supplied concept/style references; their original icons are not relicensed by this project.
- 骷髅、雷达、KD 指示等部分符号或参考来自游戏原生 UI；原生轮廓、参考截图、下载图和其他游戏标志仍保留相应权利。截图／视频中的游戏画面归游戏权利人，项目作者提供的是拍摄与 MOD 展示。 / Some skull, radar and KD indicators or references originate in native UI. Native shapes, reference captures and marks retain their rights; recording a gameplay showcase does not confer ownership of the game's art.

制作索引 / Production records: [v5 artwork notes](../artwork/review-0.4.57-ribbons-v5/README.md), [approved exports](../artwork/approved-icons/0.4.58/catalog.json), [native KD geometry](../artwork/metric-icon-drafts/v1/native-kd-indicators/source.json).

## 尚未确认的来源信息 / Unresolved provenance

1. 24 种敌人图像的逐文件上传者与完整再分发授权尚未全部核实；Training Manual 的移动工厂图未标逐图许可。公开源码中的图像衍生部分不得被当作统一 MIT 资产。 / Individual uploaders and complete redistribution rights for the enemy images have not all been established, including the Training Manual Factory Strider image. Image-derived portions must not be presented as uniformly MIT-licensed.
2. 两份 QQ 资料没有在本轮重新取得可核实的完整再分发许可；保留表格链接和已有署名，项目不授予原表版权。 / Full redistribution terms for the two QQ sheets were not verified during this audit. Their links and recorded credits are retained; this project does not license the original sheets.
3. HD2 Enemy Reinforcement HUD 0.5.2 的作者和公开页面未从本地提供包确认。 / The supplied HD2 Enemy Reinforcement HUD 0.5.2 package did not establish an author or public source URL.

这里记录已知缺口，不宣称原作者已许可，也不以来源缺口替代对具体使用方式的判断。若来源作者提供补充署名或许可，应更新此索引。

These are specific gaps in the record, not claims of permission or blanket conclusions about every use. Update the register when source authors provide corrections or terms.
