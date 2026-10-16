# GitHub 指挥官构筑项目调研

本文保留为Commander专题。跨赛制总览、mtg-skills已迁移状态、Tapps职责及本地测试差距，见[MTGA跨赛制调研](GitHubMtgaReferences_20261016.md)。后续搜集覆盖构筑与限制赛，不限定指挥官。

核查日：2026-10-16（Asia/Hong_Kong）。目标是改善本项目EDH/Brawl双版交付、赛制校验、数据证据与后续实战反馈。结论依据GitHub仓库元数据、固定提交的README/许可证及14份源码/协议文档抽样；未安装或运行这些项目，没有把README宣传当性能测量。

建议优先参考`mtg-skills`的赛制档案、Commander Spellbook的数据契约、Commander Builder的实验记录。MTG Analyzer适合作为校验缺口与统计输出的对照，但其部分检查策略不能直接采用。

本次8个候选中，6个找到明确代码许可证；另外2个仅能确认是公开源码，未找到明确源码许可证，不将它们列作已确认可复制代码的开源依赖。所有仓库在本次API快照均为`archived=false`，不据此推断维护承诺。

## 候选与版本

以下“提交日期”为默认分支HEAD的committer日期（UTC），不是网页抓取时间；具体版本均已保存。许可证以独立LICENSE实际内容为准，仓库API识别只作辅助。

| 项目 | 提交日期UTC / 短SHA | 已核实代码许可 | 与本项目关系 |
|---|---|---|---|
| [dan-blanchard/mtg-skills](https://github.com/dan-blanchard/mtg-skills) | 2026-10-14 / `4bcd621cc2f1` | [0BSD](https://github.com/dan-blanchard/mtg-skills/blob/4bcd621cc2f193606c3b7515457163c3cbe98f44/LICENSE) | 已适配规则、组合检索、指南核验和工作台协议；继续研究赛制抽象 |
| [QuackQuackLabs/MTG-Analyzer](https://github.com/QuackQuackLabs/MTG-Analyzer) | 2026-10-06 / `8cd121332d3a` | [MIT，代码范围](https://github.com/QuackQuackLabs/MTG-Analyzer/blob/8cd121332d3aa0b9c021bd5e1d0ef2eb4e479630/LICENSE)；API标NOASSERTION | 本次新查，主要对照Commander报告与起手模拟 |
| [SpaceCowMedia/commander-spellbook-backend](https://github.com/SpaceCowMedia/commander-spellbook-backend) | 2026-10-14 / `9141cc904e7e` | [MIT](https://github.com/SpaceCowMedia/commander-spellbook-backend/blob/9141cc904e7e4595518a46d7db43c7b1a68cf92e/LICENSE) | 本项目已有Spellbook CLI；本次核对上游组件和命中桶语义 |
| [LlamaAdam/commander-builder](https://github.com/LlamaAdam/commander-builder) | 2026-08-27 / `0b944ef1e6f7` | [MIT](https://github.com/LlamaAdam/commander-builder/blob/0b944ef1e6f7dfdd925b30a4de200c3c444845d9/LICENSE) | 本次新查，适合借鉴版本比较与实验回执 |
| [mtgjson/mtgjson-sdk-python](https://github.com/mtgjson/mtgjson-sdk-python) | 2026-03-29 / `c75898f6eb3e` | [MIT](https://github.com/mtgjson/mtgjson-sdk-python/blob/c75898f6eb3eec6bf68bed9c3af7f1205a888dad/LICENSE) | 可选离线数据源，不建议直接替换标准库工具链 |
| [pattont/MTGA-Tapps](https://github.com/pattont/MTGA-Tapps) | 2026-10-11 / `7071c7409c9c` | [AGPL-3.0](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/LICENSE) | 本次新查，适合协议和队列归一化研究；许可不同于本项目MIT |
| [LeekTM/commander-deck-pool](https://github.com/LeekTM/commander-deck-pool) | 2026-10-12 / `4f004697e3e4` | 未找到明确源码许可证 | 公开实现参考：TXT为源、批量查询、PR检查 |
| [DeckerDesign/mtg-commander-builder](https://github.com/DeckerDesign/mtg-commander-builder) | 2026-10-05 / `92fcc5b5b000` | 未找到明确源码许可证 | 公开设计参考：确定性引擎与个人构筑配置分开 |

MIT/0BSD等代码许可不覆盖第三方卡图、Oracle或服务数据。上述记录不替代各来源的数据条款；本次仅下载少量公开源码到gitignored研究目录，没有复制进正式实现。

## 值得吸收的具体实现

### 1. mtg-skills：统一赛制档案，减少CLI各处推导

源码：[formats.py](https://github.com/dan-blanchard/mtg-skills/blob/4bcd621cc2f193606c3b7515457163c3cbe98f44/mtg-utils/src/mtg_utils/formats.py)、[legality_audit.py](https://github.com/dan-blanchard/mtg-skills/blob/4bcd621cc2f193606c3b7515457163c3cbe98f44/mtg-utils/src/mtg_utils/legality_audit.py)。

其`Format`把是否有主将、精确/最小牌数、同名上限、主将伤害、平台与队列合法性放在同一对象；校验层再按该档案检查分区、身份、牌面张数例外和行侣。它显式检查主将未指定或不能解析，不让空色组悄悄绕过身份检查。

适合吸收的是这一职责划分：本项目仍由`deck_model`负责解析，新建纯赛制配置层供`mtg_tool`、构筑器、workbench和成本模块共同读取。不能为了接入另建牌表解析器，也不把对方Brawl/Historic Brawl命名和默认牌数原样套进本项目的当前队列。

本项目已在`tools/README.md`注明规则查询参考该项目的较早提交，本次属于继续借鉴，不重复声称首次引入。对方技能包含多代理讨论和逐步批准；那是其工作方式，不是本次授权，也不会被复制成每次交付强制停顿。

### 2. MTG Analyzer：拆分校验结果、分类统计与模拟假设

源码：[analysis/report.py](https://github.com/QuackQuackLabs/MTG-Analyzer/blob/8cd121332d3aa0b9c021bd5e1d0ef2eb4e479630/backend/mtg_analyzer/analysis/report.py)、[simulation/goldfish.py](https://github.com/QuackQuackLabs/MTG-Analyzer/blob/8cd121332d3aa0b9c021bd5e1d0ef2eb4e479630/backend/mtg_analyzer/simulation/goldfish.py)。

报告对象分别保存数量/身份问题、功能分布、曲线、主宰牌与分档理由；模拟把牌库轮转和留牌策略分开，输出保留率、卡地/泛滥和主将施放时点。可以借鉴分层报告与种子化统计接口，并将主将作为牌库外的可访问资源。

这份源码也提供明确反例：`_validate`把缺主将、未解析牌放进warnings，最终`legal`主要由issues决定；`_singleton_exempt`把“up to N”整类豁免，未在该处分辨真实上限。单卡资格还依赖传奇生物/允许当主将文字的简化判断。正式本地校验应把这些未完成项显示为unknown或明确失败，按牌面例外精确核验，不直接照抄。

`goldfish.py`仅用统一法术力池，未建颜色需求，且用简化加速和留牌策略；因此它的“主将落地回合”不能直接替代本例双绿合变和三色原费的模型。其四人胜率功能是启发式，不是完整规则引擎，本次没有复现实验来验证排名准确度。

### 3. Commander Spellbook：数量、区域和主将条件必须保留

源码：[models/ingredient.py](https://github.com/SpaceCowMedia/commander-spellbook-backend/blob/9141cc904e7e4595518a46d7db43c7b1a68cf92e/backend/spellbook/models/ingredient.py)、[views/find_my_combos.py](https://github.com/SpaceCowMedia/commander-spellbook-backend/blob/9141cc904e7e4595518a46d7db43c7b1a68cf92e/backend/spellbook/views/find_my_combos.py)。

组件模型保留quantity、起始区域、各区卡牌状态、must_be_commander；查牌表时使用多重集合比较，分别输出已含、缺组件、需改主将、需增颜色等结果。分页也有明确边界，不能把第一页当全库。

本地`mtg_combo_tool.py`已保留数量、前提、区域及换备可用性等关键语义。本次应继续用上游契约补fixture，而不是引入其PostgreSQL/Django整套后端。特别是“无命中”只说明查询覆盖内没找到，不能据此证明整副牌不存在无限。

### 4. Commander Builder：版本实验应带来源、样本口径和失败状态

源码：[compare_versions.py](https://github.com/LlamaAdam/commander-builder/blob/0b944ef1e6f7dfdd925b30a4de200c3c444845d9/src/commander_builder/compare_versions.py)、[knowledge_log.py](https://github.com/LlamaAdam/commander-builder/blob/0b944ef1e6f7dfdd925b30a4de200c3c444845d9/src/commander_builder/knowledge_log.py)。

版本比较交替座次，区分旧/新版本胜利、其他玩家获胜、和局及失败pod；达到回合上限的局不会自动判给某一方。记录层保留牌表快照、比较结果、判定参数、内容哈希和测量版本，避免不同口径的历史结果被混合计算。

最适合迁移的是小型实验回执：输入牌表哈希、规则/名单版本、对手与座次、种子、实际完成/失败/和局数量、模型版本和结论依据。当前`runlog`是运行自证，`VerificationV1.json`是案例汇总，两者都还不是完整实验历史。

其[README](https://github.com/LlamaAdam/commander-builder/blob/0b944ef1e6f7dfdd925b30a4de200c3c444845d9/README.md)明确把Forge结果限定为对AI的表现，不能代表真人桌政治。保留本仓库仅在用户明确要求时运行Forge的约定；本次只研究代码，不启动循环实验。

### 5. MTGJSON Python SDK：批量数据与版本化缓存可选接入

源码：[cache.py](https://github.com/mtgjson/mtgjson-sdk-python/blob/c75898f6eb3eec6bf68bed9c3af7f1205a888dad/mtgjson_sdk/cache.py)，架构见[README](https://github.com/mtgjson/mtgjson-sdk-python/blob/c75898f6eb3eec6bf68bed9c3af7f1205a888dad/README.md)。

它按需下载Parquet/JSON，在DuckDB中查询，提供模型化返回值；缓存含远端版本比对、临时文件下载后替换和同一文件下载的并发去重。可借鉴版本标识、原子落盘和批量查询，减少本次全牌池/逐张请求的成本。

不建议马上引入DuckDB/Pydantic/httpx替换标准库工具；先量化本地缓存体积、重复查询和离线需求。其`is_stale()`在无法取得远端版本时返回False，注释也说明按fresh处理；本项目应继续区分fresh、stale与无法核验，不复制该状态语义。

### 6. MTGA-Tapps：按真实队列归一化实战反馈

Tapps覆盖Arena构筑与限制赛的真实日志追踪/分析，本段仅讨论Brawl应用。它不承担自动规则对战模拟；废弃simulate_game脚本只用于输出预览，详见跨赛制报告。

材料：[MTGA_LOG_FORMAT.md](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/docs/MTGA_LOG_FORMAT.md)、[format_normalizer.py](https://github.com/pattont/MTGA-Tapps/blob/7071c7409c9c8e3207573bd59fc7cf96d61aece9/src/mtga_tracker/format_normalizer.py)。

归一化对象保留raw队列、展示名、family、best_of和Brawl标记；协议文档记录Player.log事件。结合其README中的主将维度和牌表版本统计，可以规划Brawl实测回收：己方/对方主将、队列、先后手、调度、牌表哈希和对局结果。

本项目已有`mtga_log_tool.py`和`mtga_auto_tool.py`，应补自己的协议fixture与字段，不另造一个并行追踪器。该项目代码为AGPL-3.0，不能作为MIT片段直接搬入；本次仅做协议与设计对照。

### 7. Commander Deck Pool：借鉴源文件与CI组织，不搬宽松门禁

源码：[scripts/scryfall.py](https://github.com/LeekTM/commander-deck-pool/blob/4f004697e3e470afc7148b9b81367552960620ed/scripts/scryfall.py)、[scripts/validate_deck.py](https://github.com/LeekTM/commander-deck-pool/blob/4f004697e3e470afc7148b9b81367552960620ed/scripts/validate_deck.py)。

它以TXT为源，JSON数据库及TTS文件由脚本生成；Scryfall访问集中在一个模块，批量collection查询保留不认识的牌名，CI检查与展示生成解耦。值得借鉴的是“输入为源，审计与展示都关联同一输入”的产物链。

但当前验证将总数不为100、禁牌放进warnings，`ok`只看errors；README也明确这是其群组试牌政策。`compute_bracket`按主宰牌0/1–3/4+映射2/3/4，仅作排序，不能作为本项目的官方分档判定。本项目的正式交付继续使用硬数量/合法性门禁。源码许可未明确，本次不复制代码。

### 8. DeckerDesign：将个人偏好、牌包和构筑引擎分开

设计文档：[ADR 0002](https://github.com/DeckerDesign/mtg-commander-builder/blob/92fcc5b5b0002c4c98dfe843efb2b8e2a49b4290/docs/adr/0002-engine-profile-split.md)，工作流见[README](https://github.com/DeckerDesign/mtg-commander-builder/blob/92fcc5b5b0002c4c98dfe843efb2b8e2a49b4290/README.md)。

它把主将、个人牌池、预算、功能包与桌规放入Profile，Engine只读取配置；为本次`deliver.py`仍嵌入布洛寇名称、37地与18替换等固定内容提供了直接的拆分参照。可以用本项目现有JSON实现相同职责，无需为此新增YAML依赖。

其逐项确认流程不适合原样移植；本项目继续沿用用户已给的预算、主将与授权。README中的少量模拟游戏不应被当作高置信度四人强度测量。未找到明确源码许可证，本次只记录设计思路。

## 建议实施顺序

这是基于本次代码检查作出的工程判断，尚未实施下表功能。

| 优先级 | 本项目改动候选 | 借鉴来源 | 可验证的完成条件 |
|---|---|---|---|
| P0 | 统一Commander/Brawl/普通构筑档案，接入validate与workbench | mtg-skills | 99/100/101张、合法多主将、无法解析主将、颜色例外、限定张数、行侣、平台与队列差异有确定性fixture |
| P0 | 成本分区统一，含主将；实体未知成本不输出伪完整签名 | 本次案例＋mtg-skills价格入口思路 | 现有main统计兼容；主将成本、多主将、缺平台印刷与基本地均有覆盖 |
| P0 | 审计回执绑定TXT/配置/规则/名单内容哈希；缺证据为unknown | Commander Builder＋现有card_facts | 改一张牌或名单后旧审计自动过期；未知来源不能变pass |
| P1 | 通用批量事实快照，按查询与输入哈希缓存 | MTGJSON SDK＋Commander Deck Pool | 修改候选/日期不复用错误批次；网络失败显式保留stale/unknown |
| P1 | Brawl对局回收绑定队列、主将与牌表版本 | MTGA-Tapps | 日志fixture区分普通/Standard/Competitive Brawl；不将双人胜率标成四人强度 |
| P2 | 可选种子化展开分析和版本A/B实验 | MTG Analyzer＋Commander Builder | 颜色/横置/先后手假设明确，和局/失败数量不混入胜率分母，Forge仍显式触发 |

不建议优先做自动“强度评分”、完整Django组合库、本地全量DuckDB或自动LLM换牌循环。先补可验证的赛制和证据缺口，可以直接减少下一次Commander交付的临时脚本。

## 可复现材料与限制

研究材料在`AuditReport/GitHub_EDH_20261016/`：`research_github.py`获取8个仓库的metadata、默认分支HEAD、树、README和LICENSE；`read_sources.py`按固定SHA保存上述14份样本；`sources.json`记录文件来源。外部内容未当作技能执行，也未安装任何依赖。

Python直连GitHub曾发生连接重置，改为限时`curl.exe`读取GitHub API及base64内容响应；元数据已成功核验并保存。GitHub未登录API有配额，脚本应按快照复用，不应高频重跑。同一任务中停止了已被替代的旧重试进程。

本次只做定点源码阅读，不声称审计整个仓库、完整验证所有规则或复现作者的性能数字。两项未找到许可证的公开项目与有明确许可的六项分开列出；许可证、HEAD和活跃状态以后可能变化，后续迁移时重新检查。
