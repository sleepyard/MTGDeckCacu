---
name: mtg-limited-draft
description: 本仓库的 MTG 限制赛工作流入口：牌池组牌（limited）、轮抓座舱（draft --watch）、17Lands 锚点评分与 LLM 抓牌建议
type: prompt
whenToUse: 用户要求限制赛组牌（Sealed/Draft 牌池）、轮抓实时建议、评分表生成或限制赛数据分析时
---

本仓库的限制赛工具链围绕两个入口展开（用法详见 `tools/README.md`）：

1. **轮抓驾驶舱**：`python tools/deck_pooper.py draft --watch --set <SET> [--llm] [--port 8643]`——实时 pick 排名面板，复用 mtga_auto_tool 的日志管线；启动时自动打印赛前环境简报（`mtga_draft_tool.py brief` 同口径）。
2. **牌池组牌**：`python tools/deck_pooper.py limited --pool pool.txt --set <SET> --strategy mid --out deck.txt --report report.md [--explain]`——只接受终态牌池文本或含 `DraftStatus=Complete/Completed` 的轮抓录样 JSONL，不用中间态数据。

关键口径与前置要求：

- **评分表预生成（硬前置）**：`deck_pooper.py limited`/`draft` 都要求本地预生成评分表，缺失即报错不产出伪造结果。生成：`python tools/mtga_draft_tool.py build-ratings --set <SET> --context SetReview/<SET>_*/02_LimitedEnvironment.md`（分批调 LLM，逐批落盘 `tools/cache/draft_ratings/<SET>.json`，中断重跑自动续评，幂等）。
- **17Lands 数据口径**：直连优先、shiqidi 同源代理兜底（2026-08 直连一度失效、由代理维持，2026-10 复查直连已恢复），磁盘缓存 3 天；本地预生成评分表是喂给 LLM 的事实锚点。两端均不可用（无网/无缓存/无系列码）时锚点退回纯字母等级、signal 轴退回等级锚点，**只告警不阻断轮抓**。
- **外部锚点（17Lands 之外三路，`load_external_anchors` 聚合）**：新系列上线初期 17Lands（尤其 QuickDraft）样本不足、GIH 大面积置空时补充——MTGA Assistant（AI 用户数据 + Pro 人工双 0-5 评分，无反爬，缓存 1 天）、draftsim pick order（售前专家评分，JS bundle 内嵌 TSV，缓存 3 天）、17Lands public dataset（逐 pick 行级数据自算 ATA/ASA，缓存 7 天，仅已放出的赛制可用）。归一化为 assistant_norm/draftsim_norm/ata_norm，GIH 缺失时在 `power_anchor` 按 0.6 等级 + 0.4 外部均值混合；单源失败只告警不阻断。调研记录：`AuditReport/ExternalRef_DraftDataSources_20261009.md`。
- **pick 排名内核**：九轴 WASPAS（`tools/deck_core.py` 纯函数内核：曲线契合/主色契合/颜色开放度/信号/调色/去除/稀有度七条机器轴 + LLM 只出 RawPower/Synergy 两轴）；信号轴按真实 ALSA 判颜色开放，无 ALSA 降级为本包高等级牌计数快照；LLM 离线锚点 = 0.6 等级 + 0.4 GIH 归一化（GIH 缺失退回外部锚点均值）；基本地不参与推荐（不进 prompt、综合分置空沉底）。设计先验见 `tools/draft_methodology.md`。
- **组牌纪律**：通常按 **17 地 + 24 张其他牌 = 41 张**组牌，最终交付可为 **41/40 张**，必须注明实际组成和最后一张的保留/裁剪理由；40 张通常为 17 地 + 23 张其他牌。调整地数须说明依据，不能仅因 41 张就判错或机械砍牌。详见 `tools/draft_methodology.md` §4。
- **组牌策略**：`tools/limited_strategy.py` 先枚举 5 单色 + 10 双色方案，按颜色深度、splash 准入、曲线缺口、生物/去除配额从 23 张非地起选，再按动态地数调整非地目标、计算法术力配比和爆地/卡地检查。CLI 当前默认总张数 40，41 张候选需指定 `--deck-size 41`；最终按上述组牌纪律复核。
- **LLM 建议**：`--llm` 需 `tools/llm_config.json`（OpenAI 兼容端点，api_key 可用 `DEEPSEEK_API_KEY` 覆盖，**不得提交**）；LLM 失败显式显示 offline 并保留机器排名，面板有"重试推荐"按钮。
- **失败语义**：评分表缺失、输入格式错误、卡牌查询失败均返回错误码，不静默产出；未评级牌显示 `?` 排最后，grpId 解析失败显示 `<grpId N>`，均不丢牌。
- **评级回归**：`python tools/mtga_draft_tool.py regress` 做评分表 vs 17Lands 回归；`brief` 生成赛前格式环境简报。

相关回归测试：`python tools/test_mtga_draft.py`、`python tools/test_draft_core.py`、`python tools/test_mtga_auto.py`（网络与 LLM 全 mock）。
