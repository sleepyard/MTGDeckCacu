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
- **17Lands 数据口径**：公共 `card_ratings` 端点与 S3 桶已关闭（历史系列也全 0），17Lands 锚点直连优先、shiqidi 代理回退，仅在有缓存/镜像时可用；本地预生成评分表是当前唯一稳定锚点源。17Lands 不可用（无网/无缓存/无系列码）时锚点退回纯字母等级、signal 轴退回等级锚点，**只告警不阻断轮抓**。
- **pick 排名内核**：九轴 WASPAS（`tools/deck_core.py` 纯函数内核：曲线契合/主色契合/颜色开放度/信号/调色/去除/稀有度七条机器轴 + LLM 只出 RawPower/Synergy 两轴）；信号轴按真实 ALSA 判颜色开放，无 ALSA 降级为本包高等级牌计数快照；LLM 离线锚点 = 0.6 等级 + 0.4 GIH 归一化。设计先验见 `tools/draft_methodology.md`。
- **组牌策略**：`tools/limited_strategy.py` 先枚举 5 单色 + 10 双色方案，按颜色深度、splash 准入、曲线缺口、生物/去除配额选 23 张非地，再算动态地数、法术力配比和爆地/卡地检查。
- **LLM 建议**：`--llm` 需 `tools/llm_config.json`（OpenAI 兼容端点，api_key 可用 `DEEPSEEK_API_KEY` 覆盖，**不得提交**）；LLM 失败显式显示 offline 并保留机器排名，面板有"重试推荐"按钮。
- **失败语义**：评分表缺失、输入格式错误、卡牌查询失败均返回错误码，不静默产出；未评级牌显示 `?` 排最后，grpId 解析失败显示 `<grpId N>`，均不丢牌。
- **评级回归**：`python tools/mtga_draft_tool.py regress` 做评分表 vs 17Lands 回归；`brief` 生成赛前格式环境简报。

相关回归测试：`python tools/test_mtga_draft.py`、`python tools/test_draft_core.py`、`python tools/test_mtga_auto.py`（网络与 LLM 全 mock）。
