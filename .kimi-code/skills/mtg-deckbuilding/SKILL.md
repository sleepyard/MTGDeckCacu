---
name: mtg-deckbuilding
description: 本仓库的万智牌套牌构筑/优化/补全工作流入口：环境调研、候选枚举、构筑、验证、Forge/MTGA 实测与交付
type: prompt
whenToUse: 用户要求构筑新套牌、优化既有牌表、按主题种子补全、或跑套牌模拟测试时
---

本仓库是 MTG 套牌构筑项目。开始任何套牌任务前，先读权威流程文档并严格遵守：

1. **主流程**：`MtgDeckCacuWorkFlow.md`（阶段 0 主题澄清 → 0b 体检 → 1 环境基线 → 2 候选枚举 → 3 构筑 → 4 验证/实测 → 5 交付）。新系列评测走 `MtgSetReviewWorkFlow.md`。
2. **工具用法**：`tools/README.md`（mtg_tool.py 环境基线/检索/三重核对/门禁，forge_tool.py 模拟，mtga_log_tool.py 真人战绩回收）。

本轮（2026-08-15 反人淤泥任务）沉淀的关键教训，优先于记忆执行：

- **牌名锚点先行校验**：主题是具体牌名时（中英文皆可），先 mtgch 反查英文名 + `check` 核对赛制/平台，落到唯一卡牌再开工。"反人淤泥"= Slime Against Humanity 这类中文牌名容易被误读成主题描述。
- **Explorer 合法性推导**：Scryfall 无 explorer 字段；`--format explorer` 已由工具按先驱别名推导，但 BO1/队列特例禁牌（如 Tibalt's Trickery）仍需人工查官方公告。
- **"任意张数"牌**：Slime Against Humanity / Hare Apparent / Rat Colony 类牌面允许任意张数，`validate` 已支持自动豁免，不要误判违规。
- **Forge 实测口径**：**仅在用户明确要求时执行**（迭代收敛、达到可测试水平后再测，不要每版初稿自动测）；报告与日志用 `--outdir` 写入被测套牌自己的 DeckList 目录（如 `.../Golgari/sim/`），对手从 `DeckList/opponents/` 选。快攻/中速可信；坟场协同类与组合技套牌 AI 利用率低，胜率按保守下限解读。大环境套牌可同时用小环境对手做兼容测试（先驱/探索 ← 标准对手），作为强度下限参考。
- **并行枚举**：阶段 2 各模块可拆子代理并行检索，prompt 必须写清牌池过滤式（`f:{赛制} game:arena date<=...`）、颜色过滤、平台推导口径与已知坑位。
- **DeckList 组织**：自研套牌按主题一个文件夹、多方向用子文件夹；对手/meta 用例统一放 `DeckList/opponents/`，不与自研混放。
- **工具包使用顺序**：部族/主题工具包是人工筛选的可能相关牌集合，不是必选清单或最终候选池。每次系列、补充产品或牌面规则更新后，先更新工具包的牌名、合法性、平台印刷、角色标签和备注，再从中选取本次可能用上的牌作为种子或候选；未选牌只作备查，不自动进入最终牌表。
