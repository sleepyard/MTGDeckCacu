# Commander / Brawl 双版交付整理

日期：2026-10-16。案例为恒天霸犀布洛寇，目标是朋友中等休闲桌、零主宰牌，配套一份MTGA普通Brawl练习版。用户预算无上限，无需预算替换。

这是本次已完成工作的索引及可复用经验。通用流程已补入[组牌主流程](../MtgDeckCacuWorkFlow.md)及[Commander/Brawl技能分支](../skills/mtg-deckbuilding/references/commander-brawl.md)；专用代码和数据仍保留在gitignored案例目录，没有把它们宣传成通用EDH构筑引擎。

## 用到的流程与技能

| 材料 | 本次用途 | 本次变化 |
|---|---|---|
| [MtgDeckCacuWorkFlow.md](../MtgDeckCacuWorkFlow.md) | 主将身份、环境、候选、构筑、核验、版本交付 | 增加Commander/Brawl分支入口及当前工具限制提示 |
| [tools/README.md](../tools/README.md) | 查CLI参数、缓存、错误码、图像与版本工具 | 增加本次专项索引和边界说明 |
| [MtgDeckCostMetric.md](../MtgDeckCostMetric.md) | 沿用野卡签名、物质点与PP定义 | 未修改 |
| [mtg-deckbuilding](../skills/mtg-deckbuilding/SKILL.md) | 组牌总入口 | 补充Commander/Brawl引用；frontmatter整理为标准name/description |
| [mtg-rules](../skills/mtg-rules/SKILL.md) | 合变、主将税、合并永久物、主将伤害与帷幕 | 已使用，未修改 |
| [mtg-guide-review](../skills/mtg-guide-review/SKILL.md) | 独立审阅打法文字、数字和规则适用性 | 已使用，未修改 |

没有新增一个重叠的EDH技能；可复用细节放在现有技能的references，按需读取。`mtg-combo`及`forge_tool.py`没有在本次组牌任务中执行，不把它们列作已完成检查。牌表排除无限线路是构筑意图和语义审阅结论，不是Spellbook数据库的穷尽证明。

本次整理使用系统`skill-creator`指导技能组织，并执行其`quick_validate.py`。这是本次整理的辅助技能，区别于上次组牌已使用的三个仓库技能。

## 复用的现有脚本

| 脚本/模块 | 实际用途 | 不能由该结果推出的结论 |
|---|---|---|
| `tools/mtg_tool.py` | 查询主将、候选召回、逐牌合法性/平台/中文名、基线与一般validate | 一般validate未覆盖Commander精确总数、单卡与主将组合等完整档案；默认平台为Arena |
| `tools/deck_model.py` | 所有分区解析、牌数和版本差异的唯一牌表模型 | 不含卡牌规则或合法性引擎 |
| `tools/mtg_rules_tool.py` | 逐牌裁定、CR查询，留存版本/生效日/新鲜度 | 查到关键词不自动证明某条配合成立 |
| `tools/deck_version.py` | EDH与Arena目录各自生成V1 TXT/MD | 其基础门禁不是完整Commander验证 |
| `tools/deck_image.py` | 两份同名PNG；实际查看Arena图片 | 图片不是完整文本和规则核验的替代品 |
| `tools/newbie/deck_cost.py` | 两版执行sig；复用指标函数 | 仅统计main；主将需补计；实体版缺Arena牌时不能当完整造价 |
| `tools/mtg_guide_audit.py` | 每份指南登记5项计数 | pass仅覆盖登记项，不覆盖全文语义 |
| `tools/cn_audit.py` | 两份指南中的中文牌名反查 | 说明文字可能误识别；查询失败不能当成功 |

`deck_image.py`当前把顺序牌张打成视觉堆，每堆可以混合不同牌名；图片中“25堆”不是“只有25种牌”。这次没有修改图像程序。

## 编写的本地脚本与配置

实际为6个Python脚本和1份JSON配置，均在`AuditReport/Brokkos_20261016/`。它们是案例复现材料，没有新增到`tools/`的通用CLI。

| 文件 | 职责 | 主要输入/输出 |
|---|---|---|
| `research.py` | 分模块召回、补充精确查询、官方网页快照 | 写mutate/hosts/ramp/draw等JSON与官方HTML/TXT |
| `snapshot.py` | 从官方页面脚本数据提取主宰牌，对照Scryfall，输出赛制基线 | 写`game_changers_comparison.json`与两份baseline |
| `deck_plan.json` | 主将、角色分组、土地数量、候选与18项平台替换 | 唯一案例配置；不是可执行脚本 |
| `prepare.py` | 用配置生成两个种子TXT，以deck_model复算 | 写`paper_seed.txt`、`arena_seed.txt` |
| `verify.py` | 逐牌身份、合法性、全部印刷、中文印刷来源 | 写`checks/*.json`、`translations.json` |
| `deliver.py` | 两份专项结构审计、静态法术力、成本、指南与claims | 写同名`.audit/.mana/.cost/.claims.json`及MD |
| `review.py` | 现有CLI复核、计数、两版差异、TXT哈希与中文名日志 | 写`VerificationV1.json`及各核验日志 |

案例目录已有本次补写的README，记录执行依赖和重跑限制。研究目录、最终牌表和图片都按仓库约定保持gitignored；本索引和技能分支是可随Git保存的规范。

## 本次实际执行链

```text
主将英文身份与桌规
  -> research.py（候选和官方快照）
  -> snapshot.py（名单交叉核对及基线）
  -> deck_plan.json（人工构筑决策）
  -> prepare.py（两个种子）
  -> verify.py / verify.py translations（逐牌、印刷与译名）
  -> deck_version.py（EDH与Arena分别生成版本）
  -> mtg_rules_tool.py（关键规则证据）
  -> deliver.py（专项审计及指南）
  -> deck_image.py（两张图片）
  -> review.py + 全文语义审阅（最终回执）
```

实际查询与构筑中存在迭代；此处给出重现依赖，不把每次重试当成固定必需步骤。已有V1时不要重跑版本脚手架并指望覆盖；它会生成V2。也不要在改过牌表后只重写旧版指南来伪装同一版本。

## 已完成与尚未完成

最终本地案例入口为`DeckList/Commander_Sultai_Brokkos/README.md`；两份TXT各100张，结构为1主将、37地、62张其他牌。含主将各有17张合变牌，共享82张卡位，18项等量替换。数字仅描述本例，不是通用构筑配额。

已完成一般CLI核验、专项结构审计、逐牌赛制及已发行平台印刷、官方禁牌与主宰牌对照、每份5项指南计数、中文名反查和人工语义审阅。Arena成本补计主将后为4m36r25u21c；无个人库存扣减。

没有执行MTGA客户端导入、真人对局、Forge模拟或Spellbook全表扫描。Brawl可练操作和展开，但不提供四人桌强度、政治或多人收益的实测证据。

## 复用前需要解决的问题

| 观察 | 本次做法 | 后续建议 |
|---|---|---|
| 结构校验分散于一般CLI和案例脚本 | 对单一指定主将追加专项检查 | 先抽出统一赛制档案，支持合法多主将/牌面张数例外/行侣/所有面身份，再接现有CLI |
| 主将不在main成本内 | 按既有指标另补计 | 统一成本统计分区，并补主将/行侣范围测试 |
| case脚本固定路径、色组、37地/14基本地等数字 | 保留为案例 | 配置与确定性函数拆分后才提升到通用工具 |
| 缓存只看文件存在 | 使用独立日期目录 | 查询、名单、候选和输入哈希进入缓存键；明确fresh/stale |
| HTML解析依赖站点内嵌数据和固定45000字符窗口 | 官方与Scryfall逐名交叉核对 | 解析失败显式unknown，输出来源/内容哈希，不依赖窗口猜完整性 |
| `review.py`沿用此前audit，未对旧audit输入作强绑定 | 本次同一执行链复算TXT并留哈希 | 所有核验回执绑定TXT/配置/数据版本；改牌后旧回执自动过期 |
| 部分检查使用assert | 本例按普通Python执行 | 正式CLI使用显式错误状态，不能被`python -O`移除 |
| 简中反查误识别三处说明文字 | 改写噪声并重跑 | 未来使用结构化中英牌名配对；保留反查错误和限流状态 |

整理后只修改规范、技能及索引，没有在本次顺带实现上表的通用工具改造。GitHub借鉴调研见[外部项目报告](GitHubCommanderReferences_20261016.md)，其中给出对应源码位置与可实施的优先级。
