# 第五稿：9处修改，仅供审核

- 审核页：`docs/award-icons-review-0.4.57-v5.html`，默认只显示本轮9项。
- 5枚成就：参考旧“民主永不死、香喷喷”，改为平面米白/暗金图案。
- “等级不是问题”按用户最新的战争雷霆成就参考，改为大剪刀剪开厚钢板；前一版子弹穿板保留作历史，不再用于当前审核。
- 3枚敌人：证真者、御门者、肉瘤体，继续使用真实原图制作连续主体遮罩，不使用生成模型。
- 近战：保留用户认可的图2透视，增加肩甲、肘甲、护手，放在原横向绶带内。构图已认可，盔甲稿待审。

## PNG与制作记录

- 最终使用的平面位图：`compiled/`；三敌人位图：`enemies/`。
- 五枚成就由内置 `image_gen.imagegen` 生成；完整提示词、参考原图与生成结果：`medals/stars/prompts.json`、`medals/other/prompts.json`。
- 剪刀版的源图与完整编辑提示词：`medals/other/level-not-problem-scissors.png`、`medals/other/prompts-scissors.json`。
- 近战由内置 `image_gen.imagegen` 按参考图编辑；认可构图及加甲提示词：`melee/prompts.json`；源图保存在同目录。
- 三敌人的原图、裁切、确定性处理和SHA记录：`enemies/conversion-manifest.json`及该目录转换脚本。
- 完整输出路径与当前图案清单：`review-catalog.json`；编译源文件与SHA：`compilation-manifest.json`。
- 对照总图：`revised-nine-contact-sheet.png`。

编译仅将生成的平面源图转换为现有HUD的米白/暗金透明遮罩；原PNG保留。没有修改运行时、安装包、部署或存档。新图案尚未接入游戏。
