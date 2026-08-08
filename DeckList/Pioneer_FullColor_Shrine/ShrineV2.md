# Shrine V2（先驱 / 五色 Shrine / MTGA BO3）

本次把 `ShrineV1.md` 视为“主题种子牌池”，而不是一套待微调的完整牌表。V1 只有 17 张、没有地牌与备牌；V2 保留 V1 列出的全部 16 张 Pioneer Shrine，并围绕检索、结界降费、持续抓牌和五色法术力补成 60 主牌 / 15 备牌。基准日期为 `2026-08-01`，定位为主题保真优先、兼顾可对局性的 MTGA BO3 娱乐构筑。

## 运行基线

- 模式：C（主题种子补全）。V1 的 17 张牌均视为主题锚点；`Aang's Journey` 从 1 张提高到 3 张，其余 16 张 Shrine 各保留 1 张。
- 赛制 / 平台：Pioneer，MTGA 任一历史印刷可用，BO3，无预算上限。
- 主题边界：使用当前 Pioneer + Arena 牌池内全部 Shrine；不把套牌改造成 Enigmatic Incarnation、纯结界中速或普通五色好牌套牌。
- 强度定位：娱乐向可行构筑，不是已验证的环境主流套牌。威世智 `2026-06-29` 公告称 Pioneer 当前类型分布良好，Badgermole 中速/坡道为最常见策略，Greasefang 使用率下降，本表据此保留扫场、坟场和非生物咒语对策。
- 规则口径：Shrine 是结界类别，不是生物类别，不能为 `Secluded Courtyard`、`Unclaimed Territory` 等“选择一个生物类别”的牌选择 Shrine。

数据源：[Scryfall Pioneer + Arena 查询](https://scryfall.com/search?q=f%3Apioneer+game%3Aarena)、[官方 Pioneer 禁牌表](https://magic.wizards.com/en/banned-restricted-list)、[2026-06-29 禁限牌公告](https://magic.wizards.com/en/news/announcements/banned-and-restricted-june-29-2026)、[NEO 发行说明](https://magic.wizards.com/en/news/feature/kamigawa-neon-dynasty-release-notes-2022-02-09)、[mtgch 中文牌名 API](https://mtgch.com/api/v1/card-names/)。

## V1 体检

- V1 共 17 张、17 个唯一牌名，未设置 `Sideboard`，也没有任何地牌；它不是合法的构筑赛套牌，不能直接进入普通“砍入砍出”的优化流程。
- 其中 16 张为当前 Pioneer + Arena 可用的完整 Shrine 集合，V1 没漏掉该平台/赛制范围内的 Shrine。
- `Aang's Journey` 是 `{2}` 的 Lesson 法术；未增幅时找一张基本地，支付增幅 `{2}` 时改为找一张基本地和一张 Shrine，并获得 2 点生命。它是种子牌表里唯一的稳定 Shrine 检索。
- V1 已给出清晰身份，但缺少 43 张主牌卡位、全部地基、早期选牌、结界降费、持续卡差、主牌互动及完整备牌。
- 所有 Shrine 都是传奇永久物。各用一张可以避开重复抽到后受传奇规则约束的问题；`Aang's Journey` 与 `Sanctum of All` 负责提高单张 Shrine 的可达性。

## 候选检索摘要

候选以 `f:pioneer game:arena date<=2026-08-01` 为基础条件，并按 oracle 牌去重。宽查询只用于召回，随后再按主题、费用、牌型和自冲突过滤。

| 模块 | 原始命中 | 收敛结果 |
|---|---:|---|
| `t:shrine` | 16 | V1 已覆盖全部 16 张，全部保留 |
| oracle 文本包含 Shrine | 20 | 补充命中 Aang、Guru Pathik、Shrine Steward、White Lotus Hideout 等支援牌 |
| 结界抓牌 / 卡差 | 61 | 采用 Setessan Champion；Hallowed Haunting 放备牌 |
| 结界降费 | 6 | 采用 Jukai Naturalist；Inquisitive Glimmer 列可调仓位 |
| 结界 / Shrine 检索 | 8 | 采用 Aang's Journey 与 Commune with Spirits |
| 五色修色宽召回 | 282 | 采用 Mana Confluence、Thran Portal、Starting Town 及受限主题地 |
| 结界互动 | 95 | 采用 Leyline Binding 与 Tear Asunder |
| 结界保护 | 13 | 采用 Heroic Intervention；Destiny Spinner 处理反击 |

重点取舍：

- `Sythis, Harvest's Hand` 有 Arena 印刷，但当前不合法于 Pioneer，因赛制门禁硬排除；平台可用不能覆盖赛制不合法。
- `Guru Pathik` 四费且只看牌库顶五张，非结界；`Shrine Steward` 五费且只把牌加入手牌。两者都比当前低费选牌 / Aang 检索更慢，排除。
- `Inquisitive Glimmer` 也是两费结界降费生物，但蓝白费用不如绿白契合一回合 `Commune with Spirits`，且没有 Jukai 的系命，暂不进入主牌。
- `Hallowed Haunting` 需要双白且四费，主牌会进一步抬高曲线；保留 1 张在备牌，供慢速对局增加独立威胁。
- `Mana Confluence` 有 Pioneer 合法且 Arena 可用的历史印刷。采用 4 张，避免把所有修色压力交给仅前三回合未横置的 `Starting Town`。
- `Secluded Courtyard` / `Unclaimed Territory` 不能选择 Shrine，因为 Shrine 不是生物类别，硬排除。

## 最终导入牌表

```text
3 Aang's Journey
2 Botanical Sanctum
2 Brushland
4 Commune with Spirits
1 Crescent Island Temple
2 Forest
1 Go-Shintai of Ancient Wars
1 Go-Shintai of Boundless Vigor
1 Go-Shintai of Hidden Cruelty
1 Go-Shintai of Lost Wisdom
1 Go-Shintai of Shared Purpose
1 Indatha Triome
1 Island
4 Jukai Naturalist
1 Ketria Triome
1 Kyoshi Island Plaza
3 Leyline Binding
4 Mana Confluence
1 Mountain
1 Northern Air Temple
1 Plains
2 Plaza of Heroes
1 Sanctum of All
1 Sanctum of Calm Waters
1 Sanctum of Fruitful Harvest
1 Sanctum of Shattered Heights
1 Sanctum of Stone Fangs
1 Sanctum of Tranquil Light
4 Setessan Champion
1 Southern Air Temple
3 Starting Town
1 Swamp
1 The Spirit Oasis
2 Thran Portal
2 Weaver of Harmony
1 White Lotus Hideout

Sideboard
2 Deafening Silence
2 Depopulate
2 Destiny Spinner
2 Dovin's Veto
1 Hallowed Haunting
2 Heroic Intervention
2 Rest in Peace
2 Tear Asunder
```

机器计数：主牌 `60`，备牌 `15`；主备没有非基本地之外的同名牌超过 4 张；主牌 Shrine `16`，结界牌 `25`，地牌 `24`，基本地 `6`。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 4 | `{G}` | 野灵商谈 | Commune with Spirits | 看四找结界或地；本表主牌有 49 个理论命中 |
| 1 | `{B}` | 北气和寺 | Northern Air Temple | Shrine 进场吸血；后续 Shrine 进场继续吸 1 |
| 1 | `{W}` | 宁光圣殿 | Sanctum of Tranquil Light | 低费 Shrine；按 Shrine 数量降低横置生物异能费用 |
| 3 | `{2}`，增幅 `{2}` | 安昂的旅程 | Aang's Journey | 找基本地；四费模式同时找任意 Shrine，兼回 2 |
| 1 | `{1}{G}` | 蓬勃御神体 | Go-Shintai of Boundless Vigor | 回合末付 `{1}` 给 Shrine 放置 X 个指示物 |
| 1 | `{1}{U}` | 遗智御神体 | Go-Shintai of Lost Wisdom | 回合末付 `{1}` 磨 X，主要是主题组件与空中阻挡 |
| 1 | `{1}{B}` | 锐石圣殿 | Sanctum of Stone Fangs | 第一主阶段按 Shrine 数吸血，主终结之一 |
| 4 | `{G}{W}` | 树海归真师 | Jukai Naturalist | 系命站场；每个结界咒语少付 `{1}` 通用费用 |
| 2 | `{1}{G}` | 纺谐蛇人 | Weaver of Harmony | 强化结界生物；支付 `{G}` 横置复制结界来源的异能 |
| 1 | `{2}{R}` | 古战御神体 | Go-Shintai of Ancient Wars | 回合末付 `{1}` 对牌手 / 鹏洛客造成 X 点伤害 |
| 1 | `{2}{G}` | 丰收圣殿 | Sanctum of Fruitful Harvest | 第一主阶段产生 X 点同色法术力 |
| 1 | `{2}{R}` | 嶙峋圣殿 | Sanctum of Shattered Heights | 弃地或 Shrine，对生物 / 鹏洛客造成 X 点伤害 |
| 1 | `{2}{U}` | 神灵绿洲 | The Spirit Oasis | 进场按 Shrine 数抓牌，后续 Shrine 进场再抓 1 |
| 4 | `{2}{G}` | 瑟特萨斗士 | Setessan Champion | 每个己方结界进场时长大并抓一张；它本身不是结界 |
| 1 | `{3}{R}` | 新月岛烈火寺 | Crescent Island Temple | 进场按 Shrine 数造灵技 Monk，后续 Shrine 继续造 1 |
| 1 | `{3}{B}` | 掩暴御神体 | Go-Shintai of Hidden Cruelty | 回合末付 `{1}` 消灭防御力不高于 X 的生物 |
| 1 | `{3}{W}` | 共念御神体 | Go-Shintai of Shared Purpose | 回合末付 `{1}` 造 X 个 1/1 Spirit |
| 1 | `{3}{G}` | 虚子岛广场 | Kyoshi Island Plaza | 进场和后续 Shrine 进场时把基本地横置放进战场 |
| 1 | `{3}{U}` | 静水圣殿 | Sanctum of Calm Waters | 第一主阶段抓 X 再弃 1，持续卡差 |
| 1 | `{3}{W}` | 南气和寺 | Southern Air Temple | 进场大幅强化全军，后续 Shrine 给全军各放一个指示物 |
| 1 | `{W}{U}{B}{R}{G}` | 万物圣殿 | Sanctum of All | 维持阶段从牌库 / 坟场把 Shrine 直接放进战场；六座后倍增其他 Shrine 触发 |
| 3 | `{5}{W}` | 地脉束缚 | Leyline Binding | 闪现的 domain 放逐；五种基本地类别齐全时只需 `{W}` |

## 地牌与色源

| 数量 | 中文名 | English | 用途与限制 |
|---:|---|---|---|
| 4 | 魔力聚流 | Mana Confluence | 无条件五色，使用有 1 点生命成本 |
| 3 | 初始市镇 | Starting Town | 前三回合未横置；彩色法术力需支付 1 点生命 |
| 2 | 索蓝境界通道 | Thran Portal | 前期未横置并选择一种基本地类别；每次启用法术力异能多付 1 生命 |
| 2 | 植物圣所 | Botanical Sanctum | 前期未横置的绿 / 蓝源 |
| 2 | 矮丛林地 | Brushland | 绿 / 白痛地，兼产无色 |
| 2 | 群英广场 | Plaza of Heroes | 任意色只能施放传奇咒语，或按场上传奇永久物已有颜色产色；保护仅限传奇生物 |
| 1 | 白莲教匿所 | White Lotus Hideout | 任意色只能施放 Lesson / Shrine；`{1},{T}` 可低效地为普通咒语滤色 |
| 1 | 因达沙群系 | Indatha Triome | 横置白 / 黑 / 绿源，提供 Plains、Swamp、Forest 三种 domain 类别 |
| 1 | 克崔亚群系 | Ketria Triome | 横置绿 / 蓝 / 红源，提供 Forest、Island、Mountain 三种 domain 类别 |
| 2 | 树林 | Forest | 基本绿源与搜索目标 |
| 1 | 平原 | Plains | 基本白源与搜索目标 |
| 1 | 海岛 | Island | 基本蓝源与搜索目标 |
| 1 | 沼泽 | Swamp | 基本黑源与搜索目标 |
| 1 | 山脉 | Mountain | 基本红源与搜索目标 |

色源必须按“能施放哪张牌”计算，不能把 24 地直接当成 24 个五色源：

- 绿源共 17 个，其中 15 个在前三回合通常可未横置使用；这是 `Commune with Spirits`、Jukai、Setessan 和 Weaver 的基础。
- 无条件白源 13、蓝源 13、黑源 11、红源 11；这里把 Thran Portal 按手牌需要选择对应基本地类别，但同一张 Portal 不能同时算作多个实际颜色。
- 另有 2 张 Plaza 与 1 张 White Lotus 为 Shrine 提供条件五色；它们不能无条件施放 Setessan、Heroic Intervention 或 Dovin's Veto。
- 6 张基本地既供 Aang 搜索，也供 Kyoshi 连续拉地。Kyoshi 在中后期仍可能耗尽牌库基本地，触发结算时必须确认剩余目标。
- Indatha + Ketria 两张地即可覆盖五种基本地类别；Thran Portal 也会获得所选基本地类别，因此会真实影响 `Leyline Binding` 的 domain。

## 曲线与概率

按牌面法术力值统计主牌非地：

| 法术力值 | 张数 | 说明 |
|---:|---:|---|
| 1 | 6 | Commune 4、Northern 1、Tranquil 1 |
| 2 | 12 | Aang 3、Jukai 4、三个二费 Shrine、Weaver 2 |
| 3 | 8 | Setessan 4、三个三费 Shrine、Spirit Oasis 1 |
| 4 | 6 | 六个四费 Shrine |
| 5 | 1 | Sanctum of All |
| 6 | 3 | Leyline Binding；domain / Jukai 会降低实际支付 |

超几何结果采用 60 张主牌、随机抽取且未考虑调度、先后手和已知牌信息：

- 起手七张至少两地：`85.73%`。
- 起手七张至少一个前三回合未横置绿源：`88.25%`。
- 起手七张同时满足至少两地和至少一个未横置绿源：`80.68%`。
- 起手七张至少一张 Shrine：`90.08%`；看到九张牌时至少一张 Shrine：`95.20%`。
- 在只已知已经施放一张 Commune 的简化状态下，牌库余 59 张中有 49 个结界 / 地命中，顶四至少命中一张约 `99.954%`。它保证的是“类别命中”，不是一定找到当前最需要的颜色或互动。

## 核心规则与操作门槛

- `Jukai Naturalist` 只降低结界“咒语”的通用费用；不降低 Aang 及其增幅、不降低五色 Sanctum 的彩色符号，也不支付 Go-Shintai 回合末的 `{1}`。
- `Sanctum of Fruitful Harvest` 在第一主阶段产生法术力。未使用的法术力会在步骤 / 阶段结束时清空，不能留到结束步骤支付 Go-Shintai。
- Weaver 可复制自己控制的结界来源触发 / 起动异能，但不能复制法术力异能。复制带目标的 Go-Shintai 时，最好先支付 `{1}`，等“when you do”产生的第二个触发上堆叠，再支付 `{G}` 复制效果触发；`Go-Shintai of Shared Purpose` 使用的是 `If you do`，复制其整段回合末触发时仍需为副本另付 `{1}`。
- `Sanctum of All` 只额外触发“另一个 Shrine”的异能，不额外触发自身维持阶段检索。控制六座或更多 Shrine 后，新 Shrine 的进场触发和场上其他 Shrine 的“另一座进场”触发都会被放大；Weaver 还可以再复制其中一个非 mana 异能。
- Sanctum 从牌库 / 坟场直接把 Shrine 放进战场不是施放，Jukai 不降费，但会触发 Setessan、Shrine 进场异能和其他 Shrine 的联动。
- `Plaza of Heroes` 最后的保护能力只以传奇生物为目标：可以保护五张 Go-Shintai，不能保护非生物 Shrine、Jukai、Setessan 或 Weaver。
- Shrine 是结界类别而非生物类别。Go-Shintai 虽是结界生物，也没有名为 Shrine 的生物类别。
- 多数进场 Shrine 在自身异能结算时会把自己计入 X；若响应触发去除 Shrine，X 按异能结算时的实际数量计算。

## 留牌与回合节奏

- 默认保留 2–4 地、至少一个未横置绿源，并有 Commune、Jukai、Setessan 或一至两张低费 Shrine 的手牌。
- 只有 Plaza / White Lotus 而没有普通绿源的两地手，不能把条件色源当作能施放 Commune / Setessan 的绿源，通常应调度。
- 一回合优先 Commune 修正下一两回合，或先下 Northern / Tranquil 建立 Shrine 数；对未知对手通常 Commune 优先。
- 二回合优先 Jukai；若预计对手有立即去除且手中缺资源，可先 Weaver 或低费 Shrine，不必强行把降费生物暴露给去除。
- 三回合安全时先下 Setessan，再从下一张结界开始回本；需要立刻稳定手牌 / 地牌时则先铺 Shrine 或 Aang。
- 四回合的增幅 Aang 同时找基本地与关键 Shrine。缺颜色找对应基本地；已有颜色时通常找 `Sanctum of All`、`The Spirit Oasis` 或当前对局所需互动 Shrine。
- Go-Shintai 进入结束步骤前必须预留 `{1}`；不要把主阶段所有地都横置，尤其不要误以为 Fruitful Harvest 产生的 mana 能跨阶段保留。

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局定位 |
|---:|---|---|---|---|
| 2 | `{W}` | 震撼寂静 | Deafening Silence | 限制非生物多咒语组合技；也会限制己方非生物 Shrine，需主动规划 |
| 2 | `{1}{G}` | 编命师 | Destiny Spinner | 让己方生物与结界咒语不能被反击；对控制核心 |
| 2 | `{W}{U}` | 多温的否决 | Dovin's Veto | 不可被反击地处理非生物咒语、扫场和组合技关键牌 |
| 2 | `{1}{G}` | 英勇干预 | Heroic Intervention | 保护全体永久物免于消灭 / 伤害；不能阻止放逐、牺牲与减防御力 |
| 2 | `{1}{W}` | 得享安息 | Rest in Peace | Greasefang、复活和坟场资源；会关闭 Sanctum 从己方坟场找 Shrine 的一半能力 |
| 2 | `{1}{G}`，增幅 `{1}{B}` | 撕成碎片 | Tear Asunder | 基础模式放逐神器 / 结界；增幅后放逐任意非地永久物 |
| 2 | `{2}{W}{W}` | 扫除人口 | Depopulate | 对生物铺场与中速大生物扫场；会消灭己方 Go-Shintai 和支援生物 |
| 1 | `{2}{W}{W}` | 圣魂萦绕 | Hallowed Haunting | 慢速对局的独立结界回报和扫场后重建 |

## 换备简表

以下都是定性推演，未经过有样本量的实战验证；每组严格一换一。

| 对局 | 换入 | 换出 |
|---|---|---|
| 生物快攻 / Badgermole 中速 | Depopulate x2 | Go-Shintai of Lost Wisdom x1、Sanctum of Calm Waters x1 |
| Izzet / 蓝白控制 | Destiny Spinner x2、Dovin's Veto x2、Heroic Intervention x2、Hallowed Haunting x1 | Go-Shintai of Boundless Vigor x1、Go-Shintai of Hidden Cruelty x1、Go-Shintai of Shared Purpose x1、Sanctum of Tranquil Light x1、Southern Air Temple x1、Leyline Binding x2 |
| Greasefang / 坟场复活 | Rest in Peace x2、Tear Asunder x2、Dovin's Veto x2 | Go-Shintai of Boundless Vigor x1、Go-Shintai of Lost Wisdom x1、Go-Shintai of Shared Purpose x1、Sanctum of Tranquil Light x1、Southern Air Temple x1、Aang's Journey x1 |
| Lotus / 多咒语组合技 | Deafening Silence x2、Dovin's Veto x2 | Go-Shintai of Boundless Vigor x1、Go-Shintai of Hidden Cruelty x1、Southern Air Temple x1、Leyline Binding x1 |
| 神器 / 结界永久物轴 | Tear Asunder x2 | Go-Shintai of Lost Wisdom x1、Go-Shintai of Boundless Vigor x1 |

`Depopulate` 会清掉五张 Go-Shintai、Jukai、Setessan 和 Weaver，但不会清掉十一张非生物 Shrine。只有对方生物场面明显领先时才换入，不要把它当成无代价的单边扫场。

## V1 到 V2

- 原样保留：16 张不同的 Shrine，各 1 张。
- 数量增加：`Aang's Journey` 从 1 增至 3，提高四费精确找 Shrine 的密度。
- 新增引擎：Commune x4、Jukai x4、Setessan x4、Weaver x2。
- 新增主牌互动：Leyline Binding x3。
- 新增法术力基础：24 地，其中 6 张基本地、2 张带三种基本地类别的 triome、9 张无条件或早期通用五色 / 选色地、3 张 Shrine 条件色源。
- 新增完整 15 张备牌，覆盖生物场、控制 / 反击、坟场、组合技与神器 / 结界永久物。
- V1 没有可直接“砍掉”的完整构筑卡位；本轮实质是从 17 张种子补到完整套牌，而不是传统 60 张牌表的换入换出优化。

## 可调仓位

- 更重主题联动：`Weaver of Harmony` 第 3 张替换 1 张 Setessan；增加异能复制，降低稳定抓牌生物密度。
- 更低曲线：`Inquisitive Glimmer` x2 替换 2 张 Setessan；降低结界费用，但蓝白压力更高且失去持续抓牌。
- 更少痛地：`The World Tree` / `Fabled Passage` 替换 1–2 张 Mana Confluence；生命更安全，但前期速度和五色即时性下降。
- 更强主牌终结：把备牌 `Hallowed Haunting` 移入主牌替换 1 张 Setessan；四费与双白需求上升。
- 若实战频繁耗尽基本地：增加第 7 张基本地，优先砍 White Lotus Hideout；若普通法术反而频繁卡色，则反向砍 White Lotus，增加 Mana Confluence 类无条件色源。

## 验证清单

- 主牌 60 / 备牌 15：通过。
- 38 个非基本唯一牌名全量检查 Pioneer 合法与 Arena 历史印刷：通过；加入 Mana Confluence 后再次单卡核对：通过。
- 44 个含基本地的最终唯一牌名通过 mtgch `items[].translated_name` 精确中文名检查：通过。
- 当前 Pioneer 禁牌交叉检查：主备没有命中禁牌。
- 导入格式、主备分隔、同名牌数量上限：通过。
- 尚未完成：Arena 客户端实际导入、对局日志、胜率统计与按先后手拆分的实战样本。当前对局结论只能标记为“推演”。
