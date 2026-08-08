# Lantern V2（Modern / UB Lantern Control / 实体与 MTGO BO3）

本次按模式 B 对 `LanternV1.md` 执行工作流回归，基准日期为 `2026-08-01`。平台按实体牌/MTGO 处理，不追加 `game:arena`；优化优先级为“保留 Lantern 控顶锁身份 > 提高锁件自然可达率 > 抵抗当前环境的神器针对 > 控制改动量”。

## 运行基线

- 核心主轴：`Lantern of Insight` 公开牌库顶，以 `Codex Shredder`、`Ghoulcaller's Bell`、`Pyxis of Pandemonium` 删除对手有效牌顶，最终磨空牌库
- 防守轴：`Ensnaring Bridge` 配合低曲线和 `The Underworld Cookbook` 压低手牌；弃牌与反击保护锁件
- 工具箱：`Urza's Saga` 搜索费用正好为 `{0}` 或 `{1}` 的神器，`Whir of Invention` 把更高费用银弹直接放进战场
- 赛制/平台：Modern、实体牌或 MTGO、UB 且允许无色、BO3、无预算上限
- 合法性：V1 的 32 个唯一牌名均为当前 Modern 合法；`Mox Opal` 当前不在 Modern 禁牌表中
- 环境：2026-07-16 职业赛环境以 Boros Energy、Izzet Affinity、Broodscale、Eldrazi Tron、Esper Goryo's 为主要组成，Lantern 未形成可统计主流；神器套牌占比高也会提高 `Meltdown`、`Wrath of the Skies`、`Force of Vigor` 等针对牌的密度

数据源：[官方 Modern 禁牌表](https://magic.wizards.com/en/banned-restricted-list)、[2026-06-29 禁限牌公告](https://magic.wizards.com/en/news/announcements/banned-and-restricted-june-29-2026)、[2026-07-16 Modern 环境分布](https://www.magic.gg/news/pro-tour-marvel-super-heroes-modern-metagame-breakdown)、[2026-07-23 Modern 胜率复盘](https://www.magic.gg/news/metagame-mentor-modern-win-rates-and-lessons-from-pro-tour-marvel-super-heroes)。

## V1 体检

- 主牌 60、备牌 15、主备合计 32 个唯一牌名；牌数、同名上限和当前 Modern 合法性通过。
- V1 只有 `Codex Shredder×4 + Pyxis×2` 六个可重复处理牌库顶的永久物。忽略调度与导师，到第三回合共看九张时自然同时看到 Lantern 与至少一个控顶件的概率约为 29.73%。
- `Narset×3` 不能单独推进 Lantern 锁；牌表又没有 `Geier Reach Sanitarium`，因此没有形成 Narset 锁，只留下三费、非神器和 `{U}{U}` 的结构成本。
- V1 有 25 个神器，却只有 `Mox Opal` 自身是零费神器；由于传奇规则，重复 Mox 不能在首回合共同维持 metalcraft，首回合启用 Mox 实际不可达。
- `Whir×4` 需要三个真实蓝色法术力，improvise 只能支付 `{X}`。V1 的 20 地中有 5 个纯无色地，不能把“神器很多”直接当作 `{U}{U}{U}` 已满足。
- `River of Tears` 有时点语义：本回合己方地进场后产黑，否则产蓝。它适合在对手回合施放 Whir，但己方回合必须根据下地顺序安排蓝黑费用。
- 主牌四张 Bridge 可以提高自然抽到率，但 Whir 已提供额外虚拟数量；重复 Bridge 会积压手牌，反过来削弱自己的 Bridge。
- 备牌 `Vexing Bauble` 会反制正常零费施放的己方 Mox、Bauble 与 Welding Jar；`Void Mirror` 会反制未花有色法术力施放的己方 Mox，并让 Saga 无色费施放神器变得危险。两者不是无成本银弹。
- `Harbinger of the Seas` 会把己方非基本地变成海岛，使 Saga 失去能力并送墓，也会关闭 Academy Ruins 的回收能力；必须等 Saga 榨取价值后再使用。
- V1 没有主牌 Welding Jar 或通用反击。在神器清场密度较高的环境中，只靠弃牌无法保护已落地的锁。

## 候选检索覆盖

所有搜索使用 `f:modern date<=2026-08-01 ci<=ub`，按 oracle 牌去重；宽查询只作召回，再按费用、神器类型、Saga/Whir 可检索性与自冲突筛选。

| 模块 | 精确模板 | 命中 |
|---|---|---:|
| 牌库顶信息 | 公开牌顶 / 查看目标牌手牌顶 | 9 |
| 可重复牌顶否决 | 神器或地；单磨 / 双方磨 / 双方放逐牌顶 | 8 |
| 一费神器循环 | 神器、MV≤1、抓牌或查看牌顶 | 44 |
| 神器导师 | 搜索神器 / 按神器法术力值搜索 | 21 |
| 便宜神器保护 | 神器、MV≤2、重生 / 改目标 / 辟邪 / 不灭 | 32 |
| 便宜反击 | UB 身份、MV≤3、反击咒语 | 146 |
| 坟场神器 | 放逐单卡或整个坟场 | 19 |
| 锁件神器 | 禁止启动 / 进场触发 / 施放 | 17 |

反击模块的 146 个命中说明 Modern 牌池不能直接人工逐张浏览；本轮用当前主要对局、费用一至三、能否保护神器清场和能否利用 improvise 继续缩小。

### 重点候选

| 候选 | 结论 |
|---|---|
| Mishra's Bauble | 零费建立 metalcraft，Lantern 未出现时临时查看牌顶，并延迟补牌；加入 4 |
| Ghoulcaller's Bell | 一费可重复控顶件，将该类永久物从 6 增至 8；加入 2 |
| Welding Jar | 零费、Saga 可找，保护单个神器免受大多数 destroy；加入 1 |
| Spell Pierce | 一费保护 Bridge/Lantern，能覆盖有色神器清场；加入 2 |
| Polluted Delta / Otawara / Spire of Industry | 规范 UB 地基，保留 15 个名义蓝源并增加功能；加入 3/1/1 |
| Consign to Memory | 针对 Eldrazi、Kozilek's Command、Saga 章节等无色咒语或触发；备牌加入 3 |
| Metallic Rebuke | 利用神器 improvise 的通用反击，后期比 Pierce 可靠；备牌加入 2 |
| Padeem, Consul of Innovation | 保护神器免受 Boseiju、Haywire Mite、Force of Vigor 等指向性处理；备牌加入 1 |
| Surgical Extraction | 弃牌或磨掉关键件后直接清除整套，兼顾坟场组合与 Lantern 的信息优势；备牌加入 2 |
| Tezzeret, Agent of Bolas | 对控制换下 Bridge 后提供卡差和不依赖战斗的终结；备牌加入 1 |

## 最终导入牌表

```text
1 Academy Ruins
4 Codex Shredder
4 Darkslick Shores
1 Disruptor Flute
3 Ensnaring Bridge
2 Ghoulcaller's Bell
1 Grafdigger's Cage
2 Inquisition of Kozilek
2 Island
4 Lantern of Insight
4 Mishra's Bauble
4 Mox Opal
1 Otawara, Soaring City
1 Pithing Needle
3 Polluted Delta
2 Pyxis of Pandemonium
3 River of Tears
2 Spell Pierce
1 Spire of Industry
1 The Underworld Cookbook
4 Thoughtseize
1 Torpor Orb
4 Urza's Saga
1 Watery Grave
1 Welding Jar
3 Whir of Invention

Sideboard
3 Consign to Memory
1 Cursed Totem
1 Damping Sphere
1 Dismember
1 Engineered Explosives
1 Harbinger of the Seas
1 Hurkyl's Recall
2 Metallic Rebuke
1 Padeem, Consul of Innovation
2 Surgical Extraction
1 Tezzeret, Agent of Bolas
```

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 4 | {0} | 米斯拉的饰品 | Mishra's Bauble | 零费 metalcraft 与牌顶侦察；延迟抓牌需服从 Bridge 时点 |
| 4 | {0} | 蛋白玛珂 | Mox Opal | metalcraft 彩色加速；传奇，重复牌不能共同留场 |
| 1 | {0} | 焊熔坛 | Welding Jar | Saga 可找的单神器重生保护 |
| 4 | {1} | 纸本搅碎器 | Codex Shredder | 定向磨掉已知牌顶；五费牺牲可回收任意牌 |
| 2 | {1} | 尸鬼牧者响铃 | Ghoulcaller's Bell | 双方各磨一，补足可重复控顶密度 |
| 1 | {1} | 挖坟人囚笼 | Grafdigger's Cage | 阻止坟场/牌库生物进场及从坟场/牌库施放 |
| 2 | {B} | 寇基雷的审讯 | Inquisition of Kozilek | 无失血拆除三费内互动或组合件 |
| 4 | {1} | 洞察明灯 | Lantern of Insight | 公开双方牌顶；牺牲可迫使目标牌手洗牌 |
| 1 | {1} | 穿髓金针 | Pithing Needle | Saga 可找的指定名称启动异能锁 |
| 2 | {1} | 魔异盒 | Pyxis of Pandemonium | 放逐牌顶而不填坟；通常不启动七费翻面能力 |
| 2 | {U} | 点破咒语 | Spell Pierce | 保护锁件，优先覆盖清场、鹏洛客和组合咒语 |
| 1 | {1} | 地底世界食谱 | The Underworld Cookbook | 丢弃冗余传奇/锁件以压低手牌，Food 缓冲快攻 |
| 4 | {B} | 攫取思绪 | Thoughtseize | 全范围手牌信息与组合保护，注意失血成本 |
| 1 | {2} | 纷扰笛 | Disruptor Flute | 瞬间指定名称，提高咒语费用并限制非法术力启动异能 |
| 1 | {2} | 迟钝法球 | Torpor Orb | 阻断生物进场引起的触发，对 Energy、Goryo's、Blink 有效 |
| 3 | {3} | 陷阱桥 | Ensnaring Bridge | 手牌越少可攻击的生物力量上限越低，主要防守锁 |
| 3 | {X}{U}{U}{U} | 创发隆响 | Whir of Invention | 瞬间神器导师；improvise 只能支付 X，不能支付三个蓝符号 |
| 1 | - | 大学院废墟 | Academy Ruins | 回收被处理或主动牺牲的神器到牌库顶 |
| 4 | - | 暗光海滨 | Darkslick Shores | 前期无痛 UB 源 |
| 2 | - | 海岛 | Island | 基本蓝源，抵抗非基本地针对 |
| 1 | - | 霄城大田原 | Otawara, Soaring City | 蓝源；通道作为难被反击的临时解答 |
| 3 | - | 聚污三角洲 | Polluted Delta | 获取 Island 或 Watery Grave，按生命压力决定目标 |
| 3 | - | 泪河 | River of Tears | 本回合地进场后产黑，否则产蓝；适合对手回合 Whir |
| 1 | - | 工业尖塔 | Spire of Industry | 有神器时用 1 点生命换任意颜色，补足 UB 弹性 |
| 4 | - | 克撒传 | Urza's Saga | 产费、构装体和 `{0}`/`{1}` 精确费用神器导师 |
| 1 | - | 积水墓地 | Watery Grave | 可检索 UB 地，必要时横置进场保留生命 |

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 3 | {U} | 托诸记忆 | Consign to Memory | 可复制地反击无色咒语或触发异能 |
| 2 | {B/P} | 手术摘除 | Surgical Extraction | 免费坟场点名与整套清除，配合弃牌/磨牌 |
| 1 | {X} | 密设爆裂物 | Engineered Explosives | 清理 token 或低费永久物；会波及己方同费用锁件 |
| 1 | {1}{B/P}{B/P} | 肢解 | Dismember | 处理 Collector Ouphe、Haywire Mite 等必须立即解的生物 |
| 1 | {2} | 诅咒图腾像 | Cursed Totem | 关闭生物启动异能，包括 Broodscale 产生物的法术力异能 |
| 1 | {2} | 滞阻法球 | Damping Sphere | 针对多产费地与连锁施法，也会提高己方同回合后续咒语费用 |
| 1 | {1}{U} | 河鼓的召还 | Hurkyl's Recall | 将目标牌手全部神器回手，主要针对 Affinity |
| 2 | {2}{U} | 聚金拒斥 | Metallic Rebuke | improvise 通用反击，保护已建立的锁 |
| 1 | {1}{U}{U} | 海疆先兆师 | Harbinger of the Seas | 非基本地锁；使用前先完成己方 Saga 章节 |
| 1 | {3}{U} | 求新执政珀蒂 | Padeem, Consul of Innovation | 给予己方神器辟邪；不能阻止不取目标的全场清理 |
| 1 | {2}{U}{B} | 波拉斯特务泰兹瑞 | Tezzeret, Agent of Bolas | 控制对局卡差与直接失血终结，不依赖越过 Bridge 攻击 |

## 数字校验

- 主牌 60、备牌 15、主备合计 37 个唯一牌名；非基本牌均未超过四张。
- 主牌 20 地、29 神器、11 张非神器咒语；曲线为 MV0 9、MV1 23、MV2 2、MV3 6、地 20。
- V2 有 8 个可重复控顶件。忽略导师和调度，到第三回合看九张时自然同时见到 Lantern 与控顶件约 35.21%，V1 为 29.73%。
- V2 有 Mox×4、Bauble×4、Jar×1。起手七张同时有 Mox 和至少两个其他零费神器、从而首回合直接启用 metalcraft 的概率约 3.17%；V1 为 0%。
- 20 地中有 15 个名义蓝源；忽略 Mox，到第三回合九张内至少看到三个名义蓝源约 39.90%。这不是 Whir 可施放率，因为仍需足够总法术力、Spire 条件和 River 时点。
- 11 个无条件首回合黑源的起手七张至少见一张约 77.76%；Spire 与已落地零费神器会提供额外条件黑源。

## 改动对照

### 主牌新增

| 改动 | 理由 |
|---|---|
| +4 Mishra's Bauble | 零费 metalcraft、临时牌顶信息与低成本循环 |
| +2 Ghoulcaller's Bell | 将可重复控顶件由 6 提升至 8 |
| +2 Spell Pierce | 防止有色清场和组合咒语穿过弃牌窗口 |
| +1 Welding Jar | Saga 可找的单件保护 |
| +3 Polluted Delta、+1 Otawara、+1 Spire | 替换分散 fetch 和一个 Island/River，保持蓝源同时增加 UB 弹性与功能 |

### 主牌移除或降量

| 改动 | 理由 |
|---|---|
| -3 Narset, Parter of Veils | 没有 Geier Reach 时不是完整锁，三费非神器拖慢手牌排空 |
| Inquisition 4→2 | 保留早期信息，但降低后期死牌密度 |
| Bridge 4→3 | Whir 提供虚拟副本，减少重复 Bridge 卡手 |
| Pithing Needle 2→1 | Saga/Whir 可找，第二张移为按环境调仓位 |
| Whir 4→3 | 降低多个 UUU 咒语积压，同时保持工具箱可达性 |
| 主牌 Cursed Totem→备牌 | 当前并非所有对局有效，避免首局抽到空白锁件 |
| 三种单张 fetch→Polluted Delta×3 | 规范化可检索地；不再需要为 Needle 人为拆分 fetch 名称 |

### 备牌重构

- 保留：Cursed Totem×1、Damping Sphere×1、Harbinger×1。
- 移除：Amulet、Ashiok×3、Emrakul、Soulless Jailer×3、额外 Torpor Orb、Vexing Bauble、Void Mirror。
- 新增：Consign×3、Metallic Rebuke×2、Surgical×2、Dismember、Engineered Explosives、Hurkyl's Recall、Padeem、Tezzeret。

## 核心操作与规则门槛

- Lantern 公开危险牌顶后，优先用 Shredder 定向磨掉；Bell 会同时填自己的坟场，也可能帮助对手坟场策略；Pyxis 不填坟，但牌被面朝下放逐后通常不应启动七费能力。
- 没有 Lantern 时可用 Bauble 看目标牌手牌顶，再决定是否启动 Shredder/Pyxis。Bridge 已建立时不要在自己的回合随意牺牲 Bauble：它会在对手的下个维持抓牌，可能在对手战斗前提高己方手牌数。安全窗口通常是对手战斗后。
- Saga 第三章检查的是神器的印刷费用正好为 `{0}` 或 `{1}`，不是“牌库中的法术力值不大于 1”；它不能寻找费用为 `{X}` 的 Engineered Explosives。Whir 可用 X=0 找到牌库中的 Explosives，但其进场没有充电指示物。
- Whir 的 improvise 只支付 `{X}`。三蓝必须由地或已启用的 Mox 实付；默认在对手结束步骤施放，让 River 产蓝并减少暴露窗口。
- 重复 Mox 会因传奇规则不能共同留场；多余副本优先交给 Cookbook。不要把“场上短暂有两张 Mox”计入 metalcraft。
- Bridge 同样限制己方 Saga 构装体。需要改用构装体获胜时，必须主动提高己方手牌、移除 Bridge，或改走 Tezzeret 直接失血。
- Welding Jar 只覆盖 destroy；不能阻止放逐、回手、牺牲和不以摧毁描述的处理。Padeem 只覆盖取目标处理；不阻止 Meltdown/Wrath 一类不取目标清场。

## 留牌与节奏

- 默认保留两地、至少一个可用彩源、Lantern/牌顶侦察件、一个重复控顶件，以及弃牌或保护中的至少一种。
- 只有 Saga/Academy 的手牌不能施放 Thoughtseize、Pierce 或 Whir，不能按“两地手”无条件保留。
- 一回合优先根据对局选择弃牌或铺 Lantern/零费神器；已知对方能首回合组合时先弃牌。
- 二回合争取达到 metalcraft，并保留 Pierce；若已看到危险牌顶，至少保留一个未横置控顶件。
- 三回合按压力选择 Bridge、Whir 工具箱或继续控制牌顶。Whir 找三费 Bridge 通常还需要三个蓝源与足够可横置神器。
- Saga 的构装体主要用于阻挡和迫使对手交处理；第三章优先找缺失的 Lantern/控顶件，其次才是 Needle、Cookbook 或 Jar。

## 换备简表

| 对局 | 换入 | 换出 |
|---|---|---|
| Boros Energy | Dismember×1、Explosives×1、Rebuke×2、Padeem×1 | Cage×1、Bell×1、Pyxis×1、Bauble×1、Whir×1 |
| Izzet Affinity | Consign×3、Cursed Totem×1、Hurkyl's Recall×1、Rebuke×2、Padeem×1 | Cage×1、Torpor Orb×1、Bell×2、Pyxis×2、Bauble×1、Whir×1 |
| Broodscale / Eldrazi | Consign×3、Cursed Totem×1、Damping Sphere×1、Dismember×1、Harbinger×1 | Cage×1、Torpor Orb×1、Cookbook×1、Bauble×2、Bell×1、Pyxis×1 |
| Esper Goryo's / Reanimator | Surgical×2、Rebuke×2 | Bell×2、Bauble×2 |
| Ruby Storm | Damping Sphere×1、Rebuke×2、Surgical×2 | Bridge×3、Torpor Orb×1、Pithing Needle×1 |
| 控制 / 大量神器处理 | Rebuke×2、Padeem×1、Surgical×2、Tezzeret×1 | Bridge×3、Torpor Orb×1、Cage×1、Pyxis×1 |

以上方案均保持主牌 60。对手实际展示的卡优先于 archetype 标签；例如 Affinity 未出现 Emry 时，不换入 Cursed Totem，保留一张 Bauble。

## 考虑过但排除

- `Narset + Geier Reach Sanitarium`：能形成额外抓牌锁，但需要增加无色地并恢复三费非神器密度，列为独立分支而非本次微调。
- `Vexing Bauble`：会反制己方正常零费施放的 Mox/Bauble/Jar；除非换出零费包，否则排除。
- `Void Mirror`：己方用 Saga 无色费施放神器会被反制，零费 Mox 无法主动花有色费规避；排除。
- `Emry, Lurker of the Loch`：回收能力强，但与 Cursed Totem 冲突、主动磨自己且重新打开对方生物去除；列 grind 分支。
- `Tezzeret, Cruel Captain`：三费能找一费神器，但只加入手牌，终极把神器变生物又与 Bridge 冲突；采用 Agent of Bolas 的直接失血终结。
- `Krang & Shredder`、`Mystic Forge`：费用过高或只处理己方牌库顶，不能提高早期 Lantern 锁稳定性。
- `Ashiok, Dream Render×3`：功能有效但三张非神器三费牌过重；当前用主牌 Cage、备牌 Surgical 和针对性反击覆盖。
- `Soulless Jailer×3`：与 Cage/手术摘除重叠，且神器生物会重新启用对方生物处理；不保留三张密度。

## 运行清单

- 基准日期：`2026-08-01`
- 查询格式：`f:modern date<=2026-08-01 ci<=ub`；未使用 `game:arena`
- Scryfall：10 组宽召回、8 组精确模块查询、V1 与重点候选 collection 批查；最终 37 个唯一牌名全部通过 `Modern + MTGO + date<=2026-08-01` 联合门禁
- mtgch：最终主备 37 个唯一牌名逐张精确匹配，中文名全部命中
- 官方环境：2026-06-29 Modern 无进一步禁限调整；2026-07-16 与 07-23 职业赛数据用于备牌权重
- 机器校验目标：60/15、主备合计同名上限、字母排序、Modern 合法、发布日期不晚于基准日、换备数量一致
- 本次没有 MTGO/Arena 实战日志；概率仅为忽略调度、导师与实际施放条件的超几何基线，对局结论均为定性推演
