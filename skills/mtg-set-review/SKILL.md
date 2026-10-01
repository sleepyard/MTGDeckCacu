---
name: mtg-set-review
description: 本仓库的 MTG 新系列评测工作流入口：售前预览追踪、全卡逐张评分、限制赛环境合成、构筑补强挖掘与系列评测报告
type: prompt
whenToUse: 用户要求做新系列评测、售前单卡评分、预览追踪或轮替审查时
---

本仓库的新系列评测有权威流程文档，开始任何系列评测任务前先读并严格遵守：

1. **权威流程**：`MtgSetReviewWorkFlow.md`——模式 P（预览追踪）/ F（全卡表初评）/ E（上线后校准）/ R（定期复盘），阶段 0 建档 → 1 数据完整性 → 2 系列骨架 → 3 全卡逐张初评 → 4 限制赛环境合成 → 5 构筑可用性挖掘 → 6 实测校准 → 7 交付复盘，含 G1-G4 门禁。构筑候选进入完整牌表后转交 `MtgDeckCacuWorkFlow.md` 模式 B/C。
2. **产出模板**：`MtgSetReviewTemplate.md`（运行清单、结论摘要、机制表、原型矩阵、全卡评价表、补强表、变更日志等完整骨架）。每个系列独立目录 `SetReview/{SET}_{YYYYMMDD}/`，原始数据放同目录 `data/`。

配套工具（用法详见 `tools/README.md`）：

- `tools/set_preview_tool.py`：预览期增量批次——`init` 建档、`fetch` 抓取并 diff、`rate` 增量评分、`status`/`report` 汇总、`watch` 持续监控。工具只负责数据获取与骨架，评级结论仍按流程复核。
- `tools/rot_audit.py`：标准轮替存活审计（`deck`/`card` 子命令）。
- `tools/cn_audit.py`：中文牌名门禁——`check <交付md>` 抓「英文名正确、中文名手写编造」的牌；`zh`/`en`/`set` 批量查官方中文名。交付文档过 `check` 是默认门禁。
- `tools/mtg_tool.py`：环境基线（`baseline`）、候选检索（`search`）、逐牌核对（`check`）。

关键口径（从工作流文档提炼，执行时不得违反）：

- **未发售系列合法性**：Scryfall 对未发售系列所有牌统一标 `not_legal`，legalities 不能作为"发售是否入赛制"的依据；`set_type=expansion` 且非 digital 的系列发售即入先驱/摩登等对应赛制，可提前纳入候选。
- **轮替判据**：不用 `f:standard`（促销印会显示 legal 但救不了牌），按 `set_type ∈ {core, expansion}` 且非 digital 且 `released_at` ≥ 轮替后最旧系列。
- **置信度分级**：C0（牌面不完整）→ C1（纸面推演）→ C2（有口径数据）→ C3（多窗口复核）；置信度不是强度，预览期结论只给临时评级，不宣称"全系列最佳"或实战胜率。
- **双坐标评价**：限制赛用锚定 A-F 等级（Draft / Sealed 分开给），构筑用「用途 + 测试优先级 T0-T3」两字段；两者绝不混成一个总分。强协同牌写「基础等级 → 指定原型等级」。
- **范围分离**：主系列 / bonus sheet / 特殊来宾 / 仅数字版分别开关，限制赛可开出范围与构筑合法范围分开；合法性逐牌读取，不能从系列名称推断。
- **中文牌名**：英文名作为稳定键；中文名只来自 mtgch 等明确数据源，暂无官方中文名保留英文并标记待补，不得手写编造（`cn_audit.py check` 会拦）。
- **变更纪律**：每次校准保留「原评级 → 新评级、证据、样本口径」，禁止静默改分；个人小样本战绩只能支持"本次样本观察"，Draft 数据不能直接校准 Sealed，BO1 不能校准 BO3。
