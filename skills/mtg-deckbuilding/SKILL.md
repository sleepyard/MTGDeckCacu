---
name: mtg-deckbuilding
description: 在本仓库构筑、优化或补全万智牌套牌，包含环境调研、候选枚举、验证和版本化交付。用户要求 EDH/Commander、MTGA Brawl 配套牌表或套牌模拟时同样适用。
---

本仓库是 MTG 套牌构筑项目。开始任何套牌任务前，先读权威流程文档并严格遵守：

1. **主流程**：`MtgDeckCacuWorkFlow.md`（阶段 0 主题澄清 → 0b 体检 → 0c 识别核对清单 → 1 环境基线 → 2 候选枚举 → 3 构筑 → 4 验证/实测 → 5 交付）。新系列评测走 `MtgSetReviewWorkFlow.md`。
2. **工具用法**：`tools/README.md`（mtg_tool.py 环境基线/检索/三重核对/门禁，forge_tool.py 模拟，mtga_log_tool.py 真人战绩回收）。交付脚手架 `tools/deck_version.py`（版本化成对 .txt/.md、禁覆盖、基础门禁，中文参数走 `--config params.json`）；牌表图 `tools/deck_image.py`（同名 PNG 落入套牌目录，见下）；库存下界数据来源 `python tools/mtga_log_tool.py inventory`（StartHook 快照 → `MatchRecord/inventory.json`，含空结果保护；合成/开包/改牌后需重跑刷新）。
3. **EDH / Brawl 分支**：涉及桌规、主宰牌、Commander 构筑门禁，或同时交付线下与 Arena 牌表时，读取 [references/commander-brawl.md](references/commander-brawl.md)。它补充主流程，不把 Brawl 实战、零主宰牌或一般构筑的 `validate` 结果当作四人 EDH 强度证明。

历史任务沉淀的关键教训，优先于记忆执行：

- **当前范围与构筑评测**：Alchemy已明确排除。构筑/微调可用`tools/deck_evaluate.py`配合离线候选快照做起手、色源及版本对照，模型口径见`docs/ConstructedEvaluation_20261016.md`；网页后台评测、固定主备牌输入及有依据的协同排序见`docs/ConstructedEvaluationBatch2_20261016.md`。partial、stale、未覆盖来源与模型假设必须带入结论；协同分须核对具体配合，不把静态潜力、金鱼均杀或同种子差值当真人胜率。金鱼修正后模型为`goldfish-london-bottom-v2`，不能与修正前数字直接比较。
- **规则与配合核验**：涉及堆叠、时序、替代效应、层或关键词交互时，按 `skills/mtg-rules/SKILL.md` 查询 `tools/mtg_rules_tool.py` 的官方 CR 原文和逐牌 rulings，记录来源与规则生效日期；陈旧缓存须标注，不凭记忆填写规则编号。
- **组合技候选**：主题涉及组合技时，按 `skills/mtg-combo/SKILL.md` 查询 Spellbook；主牌已有、明确换备后可用、主备合计候选与缺组件分开报告，核对数量、前提和区域。命中仅作配合证据，不自动认可规则线路或替换牌表。
- **指南事实核验**：交付留牌/打法指南或修订配合说明前，按 `skills/mtg-guide-review/SKILL.md` 独立核对牌数、色源条件、循环费用/收益及各章节重复结论；可登记 claims 用 `tools/mtg_guide_audit.py` 复算，机器通过仅覆盖登记项，仍需逐项规则适用性审阅。
- **牌名锚点先行校验**：主题是具体牌名时（中英文皆可），先 mtgch 反查英文名 + `check` 核对赛制/平台，落到唯一卡牌再开工。"反人淤泥"= Slime Against Humanity 这类中文牌名容易被误读成主题描述。
- **Explorer 合法性推导**：Scryfall 无 explorer 字段；`--format explorer` 已由工具按先驱别名推导，但 BO1/队列特例禁牌（如 Tibalt's Trickery）仍需人工查官方公告。
- **"任意张数"牌**：Slime Against Humanity / Hare Apparent / Rat Colony 类牌面允许任意张数，`validate` 已支持自动豁免，不要误判违规。
- **Forge 实测口径**：**仅在用户明确要求时执行**（迭代收敛、达到可测试水平后再测，不要每版初稿自动测）；报告与日志用 `--outdir` 写入被测套牌自己的 DeckList 目录（如 `.../Golgari/sim/`），对手从 `DeckList/opponents/` 选。快攻/中速可信；坟场协同类与组合技套牌 AI 利用率低，胜率按保守下限解读。大环境套牌可同时用小环境对手做兼容测试（先驱/探索 ← 标准对手），作为强度下限参考。
- **并行枚举**：阶段 2 各模块可拆子代理并行检索，prompt 必须写清牌池过滤式（`f:{赛制} game:arena date<=...`）、颜色过滤、平台推导口径与已知坑位。
- **DeckList 组织**：自研套牌按主题一个文件夹、多方向用子文件夹；对手/meta 用例统一放 `DeckList/opponents/`，不与自研混放。
- **交付配套牌表图**：阶段 5 版本化交付（.txt/.md 落定、validate 通过）后，跑 `python tools/deck_image.py {Name}V{n}.txt --title "<标题>" --format <赛制>` 生成同名 `{Name}V{n}.png` 到同一目录；版本递增时重新生图（不覆盖旧版）。Pillow 未安装时 exit 3，先装 Pillow 再重跑。
- **造价/模拟默认交付项**：交付文档默认含造价块（`python tools/newbie/deck_cost.py sig <牌表>`：造价签名+物质点预算+PP；口径与 MRUC 视觉方案见 `MtgDeckCostMetric.md`；快照外牌走 Scryfall 回退补全，仅双重落空才标注「造价数据缺失」不得省略）；标准新手系列默认附对应 `sim_*.py` 金鱼均杀（公平/保守双口径），其他套牌模拟为可选项。
- **工具包使用顺序**：部族/主题工具包是人工筛选的可能相关牌集合，不是必选清单或最终候选池。每次系列、补充产品或牌面规则更新后，先更新工具包的牌名、合法性、平台印刷、角色标签和备注，再从中选取本次可能用上的牌作为种子或候选；未选牌只作备查，不自动进入最终牌表。
