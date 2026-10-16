# 构筑与评测：第一批交付

日期：2026-10-16。用户明确排除Alchemy，当前优先强化构筑与评测。本批继续沿用现有工具链，没有安装新规则引擎，也没有启动MTGA或Forge对局。

后续进展见[第二批交付](ConstructedEvaluationBatch2_20261016.md)：固定主备牌约束、协同排序及网页评测已补充；本文保留第一批时点的模型与变更记录。

## 构筑修正

`constructed_strategy._land_entries`此前按每种咒语只统计一次有色符号，四张与一张同费咒语对法术力分配的影响相同。本批改为按实际数量加权，只取正面施放费用；已有非基本地的`produced_mana`进入来源统计，并排除可识别的限制/依赖来源。

补地时按已有色源后的需求重新分配剩余基础地，避免所有剩余槽位偏向按字母排序的第一种颜色。`mtg_tool search`规范化输出增加`produced_mana`，原有字段保留。

配额选牌理由改为由同一评分函数输出模块分、节奏分和总分；报告显示按张数加权的符号需求。这提供审阅依据，但配额/节奏仍是启发式，本批没有把它升级为协同搜索或胜率模型。

## 伦敦调度

新增纯函数`tools/opening_hand.py`，复用于8套现役金鱼与新评测入口。每次调度抓满起始手牌，选定后按非免费调度次数置底；底牌放入牌库底部，不会在下一次正常抓牌时立刻抓回。可配置免费调度和最大调度次数。

默认策略优先保留最多三张地，结合留牌地数范围和小手牌空间，随后优先置底高费咒语；这是公开的启发式选择，不声称最优留牌。保留`LONDON=False`旧兼容分支。

修正前直接重抓6/5张的实现不是完整伦敦调度。新模型标识`goldfish-london-bottom-v2`；重新记录了8套合成牌库（seed=20260924，N=8000）的回归基线。数值变化来自模型修正，不能解释成牌表本身变强。原有交付报告保留历史数字，`sim_*.py`兼容CLI仍沿用原打印格式；程序化`run`结果新增模型版本。

规则依据为此前查询并保存的官方CR 103.5，2026-09-25生效；本次共享函数另有手牌/牌库守恒、每次看满7张、底牌位置、免费调度和策略选择测试。

## 离线评测与版本对照

入口：[tools/deck_evaluate.py](../tools/deck_evaluate.py)。所需输入是既有牌表及完整的Scryfall/search JSON数组，非基本地和咒语必须能精确解析；基本地可自动补全。工具不联网。

```powershell
python tools/deck_evaluate.py evaluate deck.txt --cards cards.json --format pioneer --target "Beast Whisperer" --runs 10000 --out AuditReport/evaluation.json --report AuditReport/evaluation.md
python tools/deck_evaluate.py compare before.txt after.txt --cards cards.json --format standard --target "Lightning Strike" --out AuditReport/comparison.json --report AuditReport/comparison.md
```

`--target`是实际牌表条目的精确英文名称，可重复，最多12项；不指定时选择最多5种主牌咒语并另加主将。`--turns`最多12，默认5；`--runs`为1至50000，默认10000。参数写入结果，包括种子、先后手、留牌区间、最大/免费调度次数。CLI提供的format是场景标签与免费调度默认值，不进行合法性校验，Alchemy不在选项中。

报告输出牌库/土地/主将/备牌数量、费用曲线、角色计数、策略结束后的可留起手比例、手牌数和调度次数分布、逐回合可见土地数量潜力。每个关键咒语输出三种口径：

| 字段 | 母体 | 含义 |
|---|---|---|
| mana_potential | 全部抽样 | 忽略咒语是否抓到，已看到的支持土地能否支付该费用 |
| seen_and_mana | 全部抽样 | 既能访问目标牌，又有上述土地支付潜力 |
| mana_given_seen | 已能访问目标的抽样 | 在目标已可访问的条件下，具有土地支付潜力的比例 |

主将视为可访问，不进入洗牌牌库；备牌不混入抽牌母体。换备后需要另一份守恒牌表。结果同时给抽样数量与Wilson 95%区间；它只反映Monte Carlo抽样误差，不衡量模型与真实对局的误差。

每次返回规范化牌表哈希（包含分区）、输入快照哈希和模型标识`land-potential-london-v1`。compare要求相同模型、参数与快照，输出共有目标的描述性差值；不自动判断显著性或较强版本，同一种子在不同牌表上不等于严格配对实验。

## 当前模型边界

本批评估的是静态土地支付潜力，不是“第N回合实际必能施放”。每地只产一点，双色地不能同时付两种符号；支持通用、WUBRG、C、普通混血及单色混血的费用路线。

横置进场、下地顺序、生命支付、先前已施放咒语、非地加速、额外抓牌、替代费用、对手和战斗均不建模。MDFC选面、找地地、动态/限制色源及X/雪/非瑞费用按未覆盖报告。普通随机洗牌不复刻Arena BO1起手平滑。

`complete`仅表示选定模型输入没有额外未覆盖项，不能用来宣称完整规则执行或牌表合法。`partial`保留已知部分数据并列明来源/目标缺口，不填成成功；输入缺失或歧义为error。退出码为0/3/2。

## 实际验证

本批补充共享调度、支付匹配、牌库分区、输入证据、版本对比和构筑色源分配的行为测试。最终全量`python -X utf8 -m unittest discover -s tools -p "test_*.py"`共869项通过，零失败/错误/跳过。完整输出与JSON汇总在`AuditReport/ConstructedEvaluation_20261016/full_tests.log`及`full_tests.json`。首次运行的工作台本地HTTP连接中止未复现，单独21项与后续全量复测通过。

冒烟使用既有`CavalcadeHybridV3/V4`，只读本地Scryfall缓存，比较两张共同关键咒语，固定种子、各2000次抽样。命令已实际生成JSON与Markdown，没有改写历史牌表。结果在同目录`cavalcade_compare.json/.md`。它验证入口与证据流程，不是实战强度结论；小幅抽样差值不能自动支持换牌。

后续构筑评测的优先工作仍是更完整的土地时序/加速模型、候选与主题协同评估，以及输入哈希绑定的对手互动实验。真人日志的版本归因可以接续，但不阻塞本批离线工具。
