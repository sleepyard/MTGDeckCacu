# MTGA 跨赛制开源项目调研与测试能力对照

日期：2026-10-16（Asia/Hong_Kong）。本报告是跨赛制调研入口，[此前报告](GitHubCommanderReferences_20261016.md)保留为Commander专题。范围包含Standard、Pioneer/Explorer、Historic、Timeless、Brawl家族及Draft/Sealed。用户已明确排除Alchemy，优先强化构筑和评测；各外部项目的赛制支持仍需分别核验。

第一批构筑/评测实现现已落地，见[能力说明与验证记录](ConstructedEvaluation_20261016.md)：修正伦敦调度、按张数加权色源分配，新增离线一致性评测与版本对照。下文记录调研时点的差距，已修复项目以该交付记录为准。

第二批已补固定主备牌约束、有依据的协同排序及网页评测/旧版比较，见[第二批交付](ConstructedEvaluationBatch2_20261016.md)。完整土地时序及对手互动实验仍未包含在本批。

本次新增9个仓库快照，连同前次8个候选共17个不同项目。新增仓库均读取README、许可证、默认分支HEAD和文件树，另取10份源码/配置样本（含Tapps旧预览脚本）。未安装第三方项目、构建新引擎或运行模拟。下文区分项目自述、源码观察和本地差距判断。

## mtg-skills 已有迁移

确实已完成数批适配，它是既有来源。迁移形态以适配为本项目标准库CLI、复用方法与协议为主，不是安装整个上游工具包。

| 上游方向 | 本地实现 | 当前状态与证据 |
|---|---|---|
| 规则事实查询 | [mtg_rules_tool.py](../tools/mtg_rules_tool.py)、[mtg-rules技能](../skills/mtg-rules/SKILL.md) | CR解析明确注明改编来源和固定提交；逐牌裁定、版本/新鲜度已接入 |
| Spellbook查询 | [mtg_combo_tool.py](../tools/mtg_combo_tool.py)、[mtg_card_facts.py](../tools/mtg_card_facts.py)、[mtg-combo技能](../skills/mtg-combo/SKILL.md) | 已有组件数量、区域、主将、主备和换备区分，不限定只查询EDH |
| 指南核验 | [mtg_guide_audit.py](../tools/mtg_guide_audit.py)、[mtg-guide-review技能](../skills/mtg-guide-review/SKILL.md) | 机器登记事实加全文语义审阅，已在布洛寇双版交付中使用 |
| deck-forge工作台模式 | [deck_workbench.py](../tools/deck_workbench.py)、[MtgWorkbenchPlan.md](../MtgWorkbenchPlan.md) | 快照、确定性内核、Agent桥协议已落地；计划§5记录Phase 0–3完成及后续接收端交付 |
| 其余上游能力 | Card IR、完整调优内核、phase-rs、MTGJSON全量数据、Cube等 | 不能由前四行推导已迁入，仍需分别评估 |

原始实用迁移记录为`AuditReport/MtgSkills_PracticalIntegration_20261011.md`。更早的`ExternalRef_MtgSkills_20261011.md`是迁移前评估，其中“尚未实施”不能描述当前状态；工作台也已在后续阶段交付。

## Tapps 的职责

Tapps读取真实Arena日志，存入SQLite，提供逐局时间线、起手/调度、单卡表现、牌表版本及队列统计。它增强实际打完后的分析和改牌反馈。依据：[固定版README](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/README.md)。

其`tests/deprecated/simulate_game.py`只是预览追踪器输出的旧脚本，顶部明确标记已废弃，不是规则引擎或AI对战后端。不能因为存在GameSimulator类便将整个项目归为自动对战模拟器。依据：[旧预览脚本](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/tests/deprecated/simulate_game.py)。

## 本项目现状与差距

以下基于当前源码阅读，不表示本次已重跑所有模拟或日志测试。

| 能力 | 已有基础 | 仍需补强 |
|---|---|---|
| 真人回收 | `mtga_log_tool.py`已有scan/report/decks/opponent/replay/risk/inventory；`mtga_auto_tool.py`有实时面板 | 基础match记录主要保存matchId、牌表名和event，report按牌表名聚合；需统一内容哈希、版本、队列、BO1/BO3、先后手、换备后实际牌表等归因 |
| 金鱼初筛 | `tools/newbie/goldfish/`已有8个牌组模块、种子、机制处理和测试 | 基类主要服务特定牌组/地哨兵模型；多色支付、动态法术力源、任意牌表覆盖与调度需要通用化 |
| AI对战 | `forge_tool.py sim/play/track`已接入Forge | 已可设种子、AI、局数并存日志；需统一座次配对、置信度、超时/失败样本、规则覆盖和版本实验回执 |
| 规则场景 | 官方CR/裁定查询、规则和指南登记核验 | 查规则、算资源并不执行完整局面；可补引擎中的预置场景与回归用例 |
| 限制赛 | draft cockpit已有17Lands、三路补充锚点、本地评级、brief/regress | 新收益在数据/样本分层、组包与选牌训练、最终套牌及成绩关联；避免重复相同评分界面 |
| Arena数字机制 | 客户端数据库、grpId补全、逐印刷与重平衡检查 | Seek/Conjure、永久性修改、A-版本的规则执行不能由纸质引擎导入成功推定 |

已确认一处模型差异：`goldfish/engine.py`的`GameBase.opening()`在`LONDON=True`时直接重抓较少张数，没有每次看满起始手牌再选择置底。现有测试检查7→6→5的终手牌数，未证明实现完整伦敦调度。按本次查得的官方CR 103.5（2026-09-25生效，fresh），应补齐此差异，不能把当前结果称作真实调度后的精确概率。证据在`AuditReport/GitHub_MTGA_20261016/mulligan_rules.json`。

`sim_dual.py`历史上有颜色和横置地逻辑，但已明确冻结/过时，不能据此称现役通用金鱼已覆盖多色。本次只登记观察，未改历史模拟和基准。

对“模拟测试是否短板”的判断是：**需要补强，但已有金鱼、Forge和真人日志基础。优先缺口是模型/赛制覆盖、可复现实验和版本对应的实战证据。**Tapps主要帮助最后一项；增加第二引擎也不能单独解决全部问题。

## 新增仓库与状态

日期为默认分支HEAD的committer日期（UTC），不是查询时间。完整SHA、许可证文件和原始来源留在研究目录。

| 项目 | 日期UTC / HEAD | 代码许可 | 定位与边界 |
|---|---|---|---|
| [ShawnMcCool/scry-2](https://github.com/ShawnMcCool/scry-2) | 2026-09-25 / `400b7ddf7ee0` | MIT | 构筑/限制赛日志、版本、先后手/局制统计；Windows实验性且不含完整收藏功能 |
| [Senryoku/Draftmancer](https://github.com/Senryoku/Draftmancer) | 2026-10-14 / `c757d1b73c37` | MIT | 多人轮抽、组包、机器人及Arena导出；不执行完整实战规则 |
| [rconroy293/mtga-log-client](https://github.com/rconroy293/mtga-log-client) | 2025-10-30 / `b87160b65cfe` | GPL-3.0 | 17Lands日志采集；适合事件协议对照，原程序可能上传数据，本次未运行 |
| [phase-rs/phase](https://github.com/phase-rs/phase) | 2026-10-16 / `b1be411564be` | MIT OR Apache-2.0 | Rust规则引擎、AI与可复现对战入口；README明确仍有大量牌未实现 |
| [Card-Forge/forge](https://github.com/Card-Forge/forge) | 2026-10-15 / `733a221e3561` | GPL-3.0 | 已接入的规则/AI后端；优先强化现有适配，不算新迁入 |
| [magefree/mage](https://github.com/magefree/mage) | 2026-10-15 / `cefedf905c4f` | MIT | XMage规则执行、AI及预置局面；未证明Arena全部数字机制兼容 |
| [lggarrison/landlord-ts](https://github.com/lggarrison/landlord-ts) | 2026-10-14 / `f929cd98c566` | MIT | 调度与有色费用可支付模拟；不是胜率模型，动态地/非地加速有限制 |
| [mtgoncurve/landlord](https://github.com/mtgoncurve/landlord) | 2025-04-06 / `18e995af042e` | MIT | 原始Rust按曲线施放模型；已归档，只作历史算法对照 |
| [bstaple1/MTGA_Draft_17Lands](https://github.com/bstaple1/MTGA_Draft_17Lands) | 2025-08-23 / `946993fd0a45` | MIT | 已归档，README称自2023年6月起不再维护/不可用，只作历史参考 |

phase的GitHub API只识别了Apache；额外读Cargo.toml与LICENSE-MIT确认双许可。其余许可均读取了独立文件。前次已有的Tapps、mtg-skills、MTGJSON SDK也纳入跨赛制候选，其能力不限Commander。

## 具体借鉴位置

### 真人对局分析：Tapps与Scry 2

Tapps的[队列归一化](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/src/mtga_tracker/format_normalizer.py)保留raw、family、best_of和Brawl标志，适合避免不同队列混算。它覆盖构筑与限制赛，代码许可为AGPL-3.0，本次做协议与设计对照。

Scry 2的[DeckVersion](https://github.com/ShawnMcCool/scry-2/blob/400b7ddf7ee087444000f3ba158b8da2c87412e0/lib/scry_2/decks/deck_version.ex)保存主备牌、增减、版本时点及先后手胜负；比赛按开始时点归到当时版本。可借鉴版本归因，但该规则也需处理日志缺失/离线改牌，不自动等于因果实验。

本地可扩展现有MatchRecord和分组报告，缺字段保留unknown；不另造并行日志系统，也不将某牌在胜局出现较多解释为换入它必然提升胜率。

### 法术力与调度：landlord-ts

源码：[london.ts](https://github.com/lggarrison/landlord-ts/blob/f929cd98c56682e82bf5f479b3e7548c8dd91ce1/src/mulligan/london.ts)。它保存每轮看起始手牌与置底过程，提供按曲线施放、缺地、颜色/时机失败等指标，适合作为本地模型和回归用例的参考。

但其[路线图](https://github.com/lggarrison/landlord-ts/blob/f929cd98c56682e82bf5f479b3e7548c8dd91ce1/wiki/concepts/mana-source-roadmap.md)明确：当前主要调度土地，未完整支持生物/神器加速；Cradle/Nykthos等动态地是近似，Lotus Field产三点同色的约束存在乐观建模。适合普通多色构筑的受控试点，不应直接裁决先驱莲花/献神构型。

普通随机洗牌或伦敦调度的数字也不能自动标成Arena BO1起手平滑后的准确概率；没有核实客户端算法时应说明模型边界。

### 自动对战与规则场景：Forge、phase、XMage

Forge已有本地seed、games/matches、AI、clock参数、加载失败提示及原始日志。下一步应统一牌表哈希、引擎/卡库版本、座次、失败/和局口径及对手样本。当前父进程调用使用`timeout=None`，仍需独立中止策略；不能把clock当作进程永不挂起的保证。

phase的[ai_duel.rs](https://github.com/phase-rs/phase/blob/b1be411564bec8c6072a395192945d4c4b9cf10d/crates/phase-ai/src/bin/ai_duel.rs)含种子、分组对战、JSON报告和逐局时间预算。当前上游与本地`Ref/mtg-skills/mtg-utils/src/mtg_utils/_phase.py`评估时的pin不同；后者曾需对任意牌表文件对战打适配补丁，不能假设升级后命令保持兼容。

XMage的[README](https://github.com/magefree/mage/blob/cefedf905c4f13a03b4977da5de5c4b851884a7e/README.md)说明支持本地服务器、AI和预设局面测试。可作关键规则的独立对照候选，但本次没有读完测试框架、建立适配或测量AI质量。

三个引擎都先验证目标牌表各牌和关键机制，再跑试点。成功加载不证明规则全部实现，Historic/Timeless中遇到的数字牌和重平衡仍不能从纸质Standard/Pioneer支持推定；Alchemy独立方向已排除。引擎结果描述所选AI/卡库/规则实现，不等于Arena真人胜率。

### 限制赛：Draftmancer和17Lands client

Draftmancer的[exportToMTGA.ts](https://github.com/Senryoku/Draftmancer/blob/c757d1b73c370f88135cb699091f58d8fc3a094b/client/src/exportToMTGA.ts)处理DOM/DAR、J21编号及双面/历险/分体名称；[Bot.ts](https://github.com/Senryoku/Draftmancer/blob/c757d1b73c370f88135cb699091f58d8fc3a094b/src/Bot.ts)提供抓牌机器人接口。可借鉴轮抽场景和导出fixture，不需将Node/Vue应用并入标准库核心。

17Lands client的[mtga_follower.py](https://github.com/rconroy293/mtga-log-client/blob/b87160b65cfe5be1ff9f526cecacf6405147b198/src/python/seventeenlands/mtga_follower.py)区分机器人/真人轮抽、牌包、提交牌表与开局消息，适合对照本地解析。原客户端含服务上传，本次只读源码。

本地已接17Lands直连/shiqidi兜底、补充评级、本地评分和回归。新收益在缺失事件、样本分层、选牌到最终套牌及成绩关联，重复一个GIHWR显示器的收益较小。保留本项目17地+24其他牌的通常起点及41/40张需解释的规约。

## 按MTGA赛制安排优先级

| 范围 | 首要问题 | 候选来源 | 验证边界 |
|---|---|---|---|
| Standard BO1 | 起手/颜色、卡地、先后手、版本表现 | landlord-ts、Tapps、Scry 2 | 起手平滑未知时不声称精确复刻 |
| Standard BO3、Pioneer/Explorer | 主备对照、换备后牌表、对局矩阵 | Forge、Tapps/Scry 2、mtg-skills | 队列与Arena印刷独立检查，非地加速/动态地另建模 |
| Historic、Timeless | 宽牌池、数字/重平衡、版本分组 | Tapps、卡牌事实快照、受控Forge/phase试点 | 只对已验证牌/机制报告结果 |
| Draft/Sealed（BO1/BO3） | 终态牌池、组包/选牌、评分覆盖、成绩 | Draftmancer、17Lands client、现有cockpit | 选牌模拟、组牌模型和实战胜率分别记录 |
| Brawl家族 | 主将/身份、免费调度、版本/对手主将 | mtg-skills、Tapps、独立赛制档案 | 不与四人EDH强度混算 |

建议先补通用法术力/真实调度、实验回执及版本归因，再评估第二引擎。用固定小牌表和可核对场景比较，不能只按README赛制列表或卡牌总数选型。这里提出研究与实施候选，没有自动启动迁移、安装、实战或模拟任务。

## 研究材料与范围

新增快照及两个只读脚本在`AuditReport/GitHub_MTGA_20261016/`，`sources.json`记录10份源码样本的完整SHA和URL。前次8个项目的证据复用`AuditReport/GitHub_EDH_20261016/`。所有研究输出保持gitignored。

归档状态、许可和源码缺口均针对记录版本。未复现性能、完整代码审计或第三方测试。后续实现应重新核对选定版本并补确定性测试。
