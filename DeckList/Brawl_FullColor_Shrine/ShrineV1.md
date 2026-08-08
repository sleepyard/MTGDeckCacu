# Shrine V1（Go-Shintai 五色 Shrine / MTGA Brawl）

基准日期：`2026-08-01`  
输入种子：`DeckList/Pioneer_FullColor_Shrine/ShrineV1.md`  
定位：普通 Brawl、BO1、娱乐向但保持强度、无预算上限

这里的“MTGA 环境 EDH”按 Arena 的普通 Brawl 落地：一名指挥官加 99 张牌、除基本地外单卡、25 点起始生命、无备牌。普通 Brawl 比 Competitive Brawl 更接近本次主题构筑目标；两者不能共用禁牌结论。

V1 的 17 张主题种子全部保留。`Go-Shintai of Life's Origin` 担任指挥官，并补齐 Arena 上五张 Honden，使套牌拥有当前 Arena 的完整 22 张 Shrine（含指挥官）。

## MTGA 导入牌表

```text
Commander
1 Go-Shintai of Life's Origin

Deck
1 Aang's Journey
1 Anguished Unmaking
1 Arcane Signet
1 Assassin's Trophy
1 Binding the Old Gods
1 Blood Crypt
1 Bloodstained Mire
1 Breeding Pool
1 Brilliant Restoration
1 Calix, Guided by Fate
1 Captain Sisay
1 Chromatic Lantern
1 Chronicler of Worship
1 Command Tower
1 Crescent Island Temple
1 Cultivate
1 Dance of the Manse
1 Depopulate
1 Dryad of the Ilysian Grove
1 Enchantress's Presence
1 Fabled Passage
1 Flooded Strand
4 Forest
1 Get Lost
1 Go-Shintai of Ancient Wars
1 Go-Shintai of Boundless Vigor
1 Go-Shintai of Hidden Cruelty
1 Go-Shintai of Lost Wisdom
1 Go-Shintai of Shared Purpose
1 Greater Auramancy
1 Guru Pathik
1 Hallowed Fountain
1 Hallowed Haunting
1 Harrow
1 Hei Bai, Forest Guardian
1 Heroic Intervention
1 Honden of Cleansing Fire
1 Honden of Infinite Rage
1 Honden of Life's Web
1 Honden of Night's Reach
1 Honden of Seeing Winds
1 Idyllic Tutor
1 Indatha Triome
2 Island
1 Jukai Naturalist
1 Ketria Triome
1 Kyoshi Island Plaza
1 Leyline Binding
1 Mana Confluence
1 Marsh Flats
1 Mirari's Wake
1 Misty Rainforest
1 Mountain
1 Northern Air Temple
1 Overgrown Tomb
2 Plains
1 Plaza of Heroes
1 Polluted Delta
1 Prismatic Vista
1 Raugrin Triome
1 Relic of Legends
1 Sanctum of All
1 Sanctum of Calm Waters
1 Sanctum of Fruitful Harvest
1 Sanctum of Shattered Heights
1 Sanctum of Stone Fangs
1 Sanctum of Tranquil Light
1 Sanctum Weaver
1 Savai Triome
1 Setessan Champion
1 Shigeki, Jukai Visionary
1 Shrine Steward
1 Soul-Guide Lantern
1 Southern Air Temple
1 Starfield of Nyx
1 Starting Town
1 Sterling Grove
1 Stomping Ground
1 Swamp
1 Swords to Plowshares
1 Sythis, Harvest's Hand
1 Temple Garden
1 The Spirit Oasis
1 The World Tree
1 Trial of Ambition
1 Urza's Ruinous Blast
1 Verdant Catacombs
1 Watery Grave
1 Weaver of Harmony
1 White Lotus Hideout
1 Windswept Heath
1 Wooded Foothills
1 Zagoth Triome
1 Zur, Eternal Schemer
```

机器目标：`1` 名指挥官、牌库 `99`、总计 `100`、地 `38`、非地 `61`；除基本地外无重名。牌库中有 `21` 张 Shrine，连同指挥官共 `22` 张。

## 构筑主轴

| 模块 | 关键牌 | 作用 |
|---|---|---|
| Shrine 核心 | 全部 21 张牌库 Shrine | 保持主题完整；低费 Shrine 先建立计数，高费 Honden 和 `Sanctum of All` 将计数转成持续优势 |
| 指挥官 | Go-Shintai of Life's Origin | 每张非衍生物 Shrine 进场再造一个 Shrine 衍生物；五色横置异能回收结界 |
| 找牌 | Aang's Journey、Idyllic Tutor、Sterling Grove、Captain Sisay、Shrine Steward | 优先找到 `Sanctum of All`、缺失颜色的 Shrine、保护或控制结界 |
| 抓牌 | The Spirit Oasis、Sanctum of Calm Waters、Honden of Seeing Winds、Sythis、Enchantress's Presence、Setessan Champion | 同时覆盖“施放结界”和“结界进场”两类触发，避免作弊进场时抓牌组件空转 |
| 重建 | Dance of the Manse、Brilliant Restoration、Starfield of Nyx、Shigeki | 对手拆场后从坟场恢复；`Soul-Guide Lantern` 只清对手坟场，不关闭己方回收 |
| 互动 | Swords、Get Lost、Trophy、Anguished、Trial、Binding、Leyline Binding | 从一费到四费处理生物及非地永久物；多张互动本身也是结界或永久物 |

## 生存预算

- 一至二回合：`Swords to Plowshares`、`Get Lost`、`Assassin's Trophy`、`Trial of Ambition` 提供四张直接互动；`Northern Air Temple` 与 `Sanctum of Stone Fangs` 开始回补生命，`Go-Shintai of Lost Wisdom` 可作 0/4 飞行阻挡。
- 三至四回合：`Anguished Unmaking`、`Binding the Old Gods`、`Leyline Binding` 扩大回答范围；`Go-Shintai of Hidden Cruelty` 和 `Sanctum of Shattered Heights` 提供可重复去除。
- 扫场：`Depopulate` 是四费紧急重置；`Urza's Ruinous Blast` 保留所有传奇非地 Shrine 和多数主题组件，只清除非传奇永久物。它不能处理对方指挥官，因此两张扫场承担不同任务。
- 保护：`Sterling Grove` 与 `Greater Auramancy` 保护其他结界，`Heroic Intervention` 应对扫场。若 `Starfield of Nyx` 已把非灵气结界变成生物，使用 `Depopulate` 前必须重新评估己方损失。

## 独立赢点

1. `Northern Air Temple`、`Sanctum of Stone Fangs`、`Go-Shintai of Ancient Wars` 与 `Honden of Infinite Rage` 形成不依赖战斗的吸血和直伤轴。
2. 指挥官 Shrine 衍生物、`Crescent Island Temple`、`Go-Shintai of Shared Purpose`、`Honden of Life's Web` 与 `Hallowed Haunting` 形成铺场轴；`Southern Air Temple` 将横向场面转成致命攻击。
3. `Honden of Night's Reach` 消耗手牌，`Go-Shintai of Hidden Cruelty` 控制生物，`Sanctum of All` 每回合直接部署最合适的 Shrine，形成资源压制轴。

扫场会清除部分 Shrine 生物和衍生物，但不会同时关闭直伤轴和非生物 Shrine。`Brilliant Restoration`、`Dance of the Manse` 与指挥官回收提供重建，不把单一永久物当成唯一胜利条件。

## 五色地基

| 类别 | 数量 | 说明 |
|---|---:|---|
| 基本地 | 10 | Forest x4、Plains x2、Island x2、Swamp x1、Mountain x1；为 `Aang's Journey`、`Cultivate`、`Harrow`、`Kyoshi Island Plaza` 保留足够目标 |
| 搜索地 | 10 | 八张传统 fetch、`Fabled Passage`、`Prismatic Vista`；八张传统 fetch 均可借带基本地类别的双地或 triome 找到绿色 |
| Triome | 5 | Indatha、Ketria、Raugrin、Savai、Zagoth；横置换取三色与可搜索类别 |
| Shock land | 7 | 以四张含绿 shock land 为核心，补充白蓝、蓝黑、黑红；需要时支付生命换节奏 |
| 特殊调色 | 6 | Command Tower、Mana Confluence、Starting Town、The World Tree、Plaza of Heroes、White Lotus Hideout |

`Plaza of Heroes` 的彩色模式主要服务传奇咒语，`White Lotus Hideout` 的免费五色模式只服务 Lesson / Shrine；Hideout 的 `{1}, {T}` 模式是付费滤色，不是净加速，二者都不计作普通无条件五色源。`The World Tree` 要在六个地后才把全部地转为五色源。`Mana Confluence`、`Starting Town`、九张需要支付生命的 fetch / Vista 和 shock land 必须按对局节奏控制生命成本。

## 触发费用

- 五张 NEO Go-Shintai 的结束步骤能力各自需要 `{1}`，不是自动结算。多张同时触发时，先保留最需要的去除、造衍生物或直伤费用。
- `Sanctum of Fruitful Harvest` 在第一主阶段产生的 mana 不能保留到结束步骤，不能用它支付 Go-Shintai 触发。
- `Weaver of Harmony` 复制结界来源的触发或起动式异能还需要 `{G}` 并横置；它与结束步骤 `{1}` 必须共同进入当回合预算。
- `Go-Shintai of Life's Origin` 的回收需要完整 `{W}{U}{B}{R}{G}`，优先在 `Chromatic Lantern`、`Dryad of the Ilysian Grove` 或六地后的 `The World Tree` 支持下启用。

## 起手与检索顺序

- 保留两至三地且能在前三回合产生绿色的起手；只有受限五色地而没有普通绿源的手牌不算合格。
- 二费优先加速或抓牌引擎，四费再下指挥官。对快攻则先用低费互动和 Shrine 阻挡，避免为了曲线裸出指挥官。
- `Captain Sisay` / `Sanctum of All` 默认先找 `The Spirit Oasis` 或 `Sanctum of Calm Waters` 补牌；缺防守时找 `Northern`、`Stone Fangs`、`Hidden Cruelty`；准备结束时找 `Southern`、`Ancient Wars` 或 `Infinite Rage`。
- `Kyoshi Island Plaza` 的连续触发会消耗基本地。十张基本地同时服务四张找地咒语和 Kyoshi，后盘应检查牌库剩余目标，不能把空触发当加速。

## 种子保留与取舍

- V1 的 17 张牌全部保留，没有把种子表伪装成损坏的 60 张牌表后逐张砍牌。
- 新增五张 Honden，补齐 Arena 现有 Shrine；新增指挥官和 `Chronicler of Worship`、`Guru Pathik`、`Hei Bai`、`Shrine Steward`、`White Lotus Hideout` 等直接主题支援。
- `Sisay, Weatherlight Captain` 没有通过当前 Arena 历史印刷门禁，改用新进入 Arena 且 Brawl 合法的 `Captain Sisay`。
- 未采用 `United Battlefront`：100 张单卡制下，三费以下非生物永久物密度不足以稳定双命中。
- 未采用 `Farewell`：它会放逐 Shrine 生物、指挥官衍生物与坟场，和本表的回收主轴冲突。`Urza's Ruinous Blast` 更符合传奇 Shrine 的不对称控制计划。

## 验证边界

- 已完成：100 张计数、单卡规则、五色身份、普通 Brawl 禁牌、`date<=2026-08-01`、Scryfall 任一 Arena 历史印刷门禁。
- 已完成：最终 95 个唯一牌名全部通过 mtgch `items[].translated_name` 精确命中。
- 未完成：Arena 客户端实际导入、指挥官 UI 识别和真实 BO1 对局；本文不报告胜率。

规则来源：[Wizards Brawl format](https://magic.wizards.com/en/formats/brawl)、[Wizards banned and restricted list](https://magic.wizards.com/en/banned-restricted-list)。卡牌与平台数据来源：Scryfall API、[mtgch API](https://mtgch.com/api/v1/docs)。
