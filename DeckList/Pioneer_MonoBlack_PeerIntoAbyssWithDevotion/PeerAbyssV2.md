# PeerAbyss V2（先驱 / 纯黑献力组合 / MTGA BO3）

本次为对 V1 的独立工作流回归测试，基准日期 `2026-08-01`。优化目标按“保留 Peer into the Abyss 主轴 > 提高组合抗干扰与可达性 > 保留黑献力备用计划”排序；主牌 60 / 备牌 15。

## 运行基线

- 模式：B（既有牌表优化）
- 核心玩法：黑色永久物累积献力，Nykthos 提供斩杀法术力；Peer into the Abyss 配合 Underworld Dreams / Sheoldred / Bloodletter 使对手大量抓牌或失去双倍半血而致死
- 备用计划：Gray Merchant 献力吸血；Sheoldred、Bloodletter、Phyrexian Obliterator 空中/地面施压；Scheming Silvertongue 提供可重复的 Sign in Blood
- 牌池：先驱、MTGA 任一印刷可用、纯黑且允许无色（`ci<=b`）、BO3、无预算上限
- 系列：最新已发售扩展为 `MSH`（2026-06-26）；`HOB`、`FRA`、`TRK` 尚未发售并排除
- 禁牌：Scryfall 返回 31 张先驱基础禁牌；官方列表另有仅 MTGA BO1 禁用的 Tibalt's Trickery。本牌表未使用禁牌
- 环境：威世智 2026-06-29 公告将当前先驱描述为类型分布良好，Badgermole Cub 中速/ramp 与 Izzet 仍是主要力量；Peer 黑献力组合没有被列为主流，定位为娱乐向可行构筑

数据源：[Scryfall sets](https://api.scryfall.com/sets)、[Scryfall Pioneer bans](https://api.scryfall.com/cards/search?q=banned%3Apioneer)、[官方禁牌列表](https://magic.wizards.com/en/banned-restricted-list)、[2026-06-29 禁限牌公告](https://magic.wizards.com/en/news/announcements/banned-and-restricted-june-29-2026)。

## V1 体检

- 主牌 60、备牌 5、17 个唯一牌名。构筑赛备牌允许 0-15 张，因此 V1 合法，但空置了 10 个高价值卡位。
- 17 个唯一牌名全部先驱合法并存在 Arena 印刷。Fatal Push、Gray Merchant、Nykthos、The Meathook Massacre 的最新印刷不一定在 Arena，但旧印刷可用。
- 主轴推断成立：Underworld Dreams / Sheoldred 是抓牌惩罚，Peer 是大规模抓牌终结；Nykthos、四黑献力的 Obliterator 和 Gray Merchant 构成献力备用轴。
- Scheming Silvertongue 的正面是 `{1}{B}` 1/3 飞行系命；当回合获得至少 2 点生命后，在第二行动阶段开始时准备 `{B}{B}` 的 Sign in Blood 副本。Sheoldred 在己方正常抓牌时获得 2 点生命，能稳定满足准备条件。
- V1 没有 Thoughtseize/Duress 一类手牌干扰，七费组合容易被反击、弃牌或瞬间去除打断。
- Wishclaw Talisman 是分段支付的高效导师，但若在不能当回合获胜时启动，会把完整导师交给对手；V1 没有说明这一关键使用门槛。
- Phyrexian Arena×4 与四费威胁形成慢速资源堆叠，且不能直接加强组合；备牌只有五张，无法覆盖快攻、坟场、控制与组合技。
- V1 的 20 Swamp + 4 Nykthos 虽然都是地，但 Nykthos 前期通常只能产无色。忽略献力启动的简化计算中，到第三回合看九张牌满足自然 `{B}{B}{B}` 约 63.78%，到第四回合看十张满足自然 `{B}{B}{B}{B}` 约 44.05%。

## 候选检索覆盖

检索统一使用 `f:pioneer game:arena date<=2026-08-01 ci<=b`；以下为 oracle 级去重命中，同一卡可跨模块重复：

| 模块 | 查询 | 命中 |
|---|---|---:|
| M1 抓牌惩罚 | `whenever an opponent draws a card` | 4 |
| M1 生命损失翻倍 | `opponent would lose life` + `twice` | 1 |
| M1 半血效果 | `half their life` | 8 |
| M2 黑献力回报 | `devotion to black` | 8 |
| M2 三个以上黑色符号 | `mana:{B}{B}{B}` | 32 |
| M3 任意牌导师到手 | `search your library for a card` + `into your hand` | 22 |
| M3 任意牌导师置顶 | `search your library for a card` + `on top` | 2 |
| M4 一次抓多牌 | `draw two cards` / `draw three cards` | 50 |
| M5 非地手牌干扰 | `reveals their hand` + `nonland` | 35 |
| M5 弃牌 | `target opponent discards` | 27 |
| M5 生物/结界去除 | `destroy target creature or enchantment` | 5 |
| M6 单卡坟场放逐 | `exile target card from a graveyard` | 17 |

第一版抓牌惩罚查询使用了 `loses`，漏掉文字为 `they lose` 的 Sheoldred；补充完整短语查询后命中。这再次证明关键词检索必须覆盖词形和完整模板，不能以单条查询为全集。

### 重点候选

| 候选 | 系列 | 结论 |
|---|---|---|
| Bloodletter of Aclazotz | LCI | Peer 的半血损失在己方回合翻倍即致死；同时强化灰商、Sign、Annex，加入 3 |
| Rush of Dread | OTJ | `{3}{B}{B}` 选择半血模式，配合 Bloodletter 直接致死；作为副轴导师目标加入 1 |
| Beseech the Mirror | WOE | 可牺牲 Blade/Wishclaw/重复结界；找四费内启动件可免费施放，找 Peer 则安全入手，加入 1 |
| Thoughtseize | THS/旧 Arena 印刷 | 一费保护组合并打断对方曲线，加入 4 |
| Unholy Annex // Ritual Chamber | DSK | 当回合末抓牌；Bloodletter 是 Demon，会让 Annex 吸血且将对手失血翻倍，加入 3 |
| Urborg, Tomb of Yawgmoth | M15/PIO Arena 印刷 | 令 Nykthos 也能直接产黑，改善三黑/四黑需求，加入 2 |
| Scrawling Crawler | FDN | 能惩罚并增加抓牌，但零黑献力且对称给牌可能让对手先找到干扰，排除 |
| Grim Tutor | M21 | 安全三费导师，但失去 3 点生命且不能像 Beseech 免费施放启动件，列可调仓位 |
| Insatiable Avarice | OTJ | 置顶与抓三可组合，但完整模式五费且不建立献力场面，排除 |
| Damping Sphere | DOM Arena 印刷 | 能针对 Lotus/连锁施法，但会直接关闭己方 Nykthos 多产费，硬性排除 |
| Unstoppable Slasher | DSK | 与 Bloodletter 形成战斗伤害半血斩杀，但依赖穿过阻挡，列激进分支 |
| Archenemy's Charm | EOE | 三黑瞬间放逐与回收都很强，但不解决组合可达性，列互动分支 |

## 构筑方向

| 方向 | 做法 | 优点 | 代价 |
|---|---|---|---|
| A Peer 献力补强（采用） | 保留 Peer/Dreams/Sheoldred，加入 Bloodletter、Thoughtseize、Annex 和少量安全导师 | 保持 V1 身份，同时补强抗干扰、卡差与备用斩杀 | 仍依赖高黑色需求与复杂排序 |
| B Bloodletter 半血组合 | 增加 Rush/Unstoppable Slasher，减少 Peer 和 Dreams | 五费即可形成部分斩杀，速度更快 | 主轴变成 Bloodletter，偏离牌表名称与原始主题 |
| C 纯黑献力中速 | 移除多数七费组合件，增加 Annex、Preacher、Archfiend 与互动 | 单卡质量和对快攻能力更稳定 | Peer 退化为彩蛋，不再测试原工作流目标 |

## 最终导入牌表

```text
1 Beseech the Mirror
3 Bloodletter of Aclazotz
4 Fatal Push
2 Gray Merchant of Asphodel
4 Nykthos, Shrine to Nyx
1 Peer into the Abyss
2 Phyrexian Obliterator
1 Rush of Dread
4 Scheming Silvertongue
3 Sheoldred, the Apocalypse
17 Swamp
1 Takenuma, Abandoned Mire
4 Thoughtseize
3 Tithing Blade
3 Underworld Dreams
3 Unholy Annex
2 Urborg, Tomb of Yawgmoth
2 Wishclaw Talisman

Sideboard
2 Cling to Dust
2 Duress
2 Leyline of the Void
2 Path of Peril
1 The Meathook Massacre
2 The Stone Brain
2 Thought Distortion
2 Withering Torment
```

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 4 | {B} | 送终一击 | Fatal Push | 一费生物去除；Blade/craft/bargain 可开启 revolt |
| 4 | {B} | 攫取思绪 | Thoughtseize | 组合保护、拆解对方关键牌 |
| 4 | {1}{B} // {B}{B} | 策谋雄辩师 // 以血立契 | Scheming Silvertongue // Sign in Blood | 一献力站场；回血后准备双抓/失血副本 |
| 3 | {1}{B} // craft {4}{B} | 奉献祭刃 // 噬人坟墓 | Tithing Blade // Consuming Sepulcher | 一献力 edict；后期 craft 为持续吸血，变换后不再提供黑色符号 |
| 2 | {1}{B}（启动 {1}） | 愿爪饰符 | Wishclaw Talisman | 一献力分段导师；只在可当回合斩杀时启动 |
| 3 | {B}{B}{B} | 地底幻梦 | Underworld Dreams | 三献力；对手每次抓牌受 1 点伤害 |
| 3 | {2}{B} // {3}{B}{B} | 不洁别馆 // 仪式会厅 | Unholy Annex // Ritual Chamber | 回合末抓牌；Demon 在场时吸血，后期解锁 6/6 飞行 Demon |
| 1 | {1}{B}{B} + spree | 惧尸猛冲 | Rush of Dread | Bloodletter 副斩杀；半血模式总费用 `{3}{B}{B}` |
| 1 | {1}{B}{B}{B} | 恳求魔镜 | Beseech the Mirror | 模态导师；bargain 后免费施放法术力值 4 以下的牌 |
| 3 | {1}{B}{B}{B} | 阿洛佐兹放血魔 | Bloodletter of Aclazotz | 三献力 Demon；己方回合将对手生命损失翻倍 |
| 2 | {B}{B}{B}{B} | 非瑞克西亚抹煞兽 | Phyrexian Obliterator | 四献力备用威胁，惩罚伤害型去除和阻挡 |
| 3 | {2}{B}{B} | 启示天灾希欧蕊 | Sheoldred, the Apocalypse | 两献力抓牌惩罚；己方抓牌回血并开启雄辩师 |
| 2 | {3}{B}{B} | 安福陵的暗贾 | Gray Merchant of Asphodel | 献力备用斩杀与回血；Bloodletter 在己方回合翻倍失血 |
| 1 | {4}{B}{B}{B} | 窥探深渊 | Peer into the Abyss | 主终结；与三类启动件组成斩杀 |
| 17 | - | 沼泽 | Swamp | 基础黑源 |
| 1 | - | 荒泽竹沼 | Takenuma, Abandoned Mire | 黑源；通道回收生物/鹏洛客 |
| 2 | - | 约格莫夫之墓乌尔博格 | Urborg, Tomb of Yawgmoth | 让 Nykthos 与其他地同时成为沼泽 |
| 4 | - | 夜天神殿尼索斯 | Nykthos, Shrine to Nyx | 献力爆发法术力；传奇且无 Urborg 时前期只产无色 |

地牌共 24。按 17 Swamp + Takenuma + 2 Urborg + 4 Nykthos 的简化模型，到第三回合满足自然 `{B}{B}{B}` 约 66.54%，第四回合满足自然 `{B}{B}{B}{B}` 约 49.15%；比 V1 有改善，但仍要求起手认真检查黑源。计算未把已有献力激活 Nykthos 的复杂路线计入。

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局 |
|---:|---|---|---|---|
| 2 | {B} | 执持化尘 | Cling to Dust | 响应式坟场放逐，兼回血/抓牌与 escape |
| 2 | {B} | 逼从 | Duress | 对控制与组合技增加一费干扰 |
| 2 | {1}{B}{B} | 险峻路途 | Path of Peril | 清理法术力值 2 以下的快攻铺场 |
| 2 | {2}{B} | 凋萎折磨 | Withering Torment | 瞬间处理生物或结界，固定失去 2 点生命 |
| 2 | {2}（启动 {2}） | 魔石大脑 | The Stone Brain | 可命名非基本地的组合技定点拆解 |
| 2 | {2}{B}{B} | 虚空地脉 | Leyline of the Void | 起手免费坟场封锁；硬施放时提供两点黑献力 |
| 1 | {X}{B}{B} | 肉钩大屠杀 | The Meathook Massacre | 可调幅度扫场与回血 |
| 2 | {4}{B}{B} | 思想扭曲 | Thought Distortion | 不可反击地放逐控制/组合技的手牌与坟场非生物牌 |

## V1 → V2 改动

### 主牌砍出/减量

- Phyrexian Arena×4 → 0：改用能立即在回合末抓牌、与 Demon/Bloodletter 联动并有后期 6/6 模式的 Unholy Annex。
- Gray Merchant×4 → 2：保留献力备用斩杀，降低五费卡手与不建立后续资源的问题。
- Phyrexian Obliterator×4 → 2：保留四献力威胁，但避免四费位完全被不推进组合的牌占满。
- Sheoldred×4 → 3：传奇牌减一，仍维持核心启动件密度。
- Tithing Blade×4 → 3、Underworld Dreams×4 → 3：给手牌干扰和新启动件腾位；三张仍可由导师查找。
- Wishclaw Talisman×3 → 2：降低提前启动后把导师交给对手的风险，以一张 Beseech 补充安全查找。
- Swamp×20 → 17：加入 Takenuma×1 和 Urborg×2；Nykthos 保持 4 以保留献力爆发身份。

### 主牌加入

- Thoughtseize×4：补上 V1 完全缺失的组合保护和一费主动干扰。
- Bloodletter of Aclazotz×3：Peer/Rush 半血翻倍致死，也是三献力、飞行 Demon 和其他失血效果的放大器。
- Unholy Annex×3：补牌；Bloodletter 在场时每个己方结束步骤让对手实际失去 4、己方获得 2。
- Rush of Dread×1：Bloodletter 的五费备用斩杀，保持为单张导师目标而非改成 Rush 主轴。
- Beseech the Mirror×1：安全导师；可 bargain 冗余 Blade/Wish/结界并免费施放四费以内启动件。
- Takenuma×1、Urborg×2：功能地与黑源修正。

### 备牌补全

- 保留 The Meathook Massacre×1。
- 移除 Feed the Swarm、Invoke Despair、Sheoldred's Edict、Vein Ripper：这些牌各自合法，但原五张备牌没有形成完整对局计划。
- 加入 Cling/Leyline 对坟场，Duress/Thought Distortion 对控制，Stone Brain 对单核心组合技，Path/Meathook 对快攻，Withering Torment 对生物与结界。

## 核心配合与规则门禁

- Peer + Underworld Dreams：Peer 先让对手抓牌并失去半血，每次抓牌再触发 Dreams；通常远超剩余生命，但实际伤害取决于对手牌库张数。
- Peer + Sheoldred：对手每抓一张失去 2 点生命。
- Peer + Bloodletter：Peer 的半血生命损失发生在己方回合，被翻倍后必定不少于对手当前生命，直接致死。
- Bloodletter + Rush of Dread：Rush 选择 `{2}` 半血模式，总费用 `{3}{B}{B}`；半血损失被翻倍，直接致死。
- Bloodletter 只在你的回合生效；不会放大对手正常抓牌步骤中 Dreams/Sheoldred 造成的生命损失。
- Bloodletter + Gray Merchant / Sign in Blood / Unholy Annex：这些效果在己方回合让对手失去生命，均被翻倍。Dreams 造成的是伤害，伤害导致的生命损失同样会被翻倍。
- Beseech bargain 后，Rush 的法术力值为 3，可免费施放但仍需支付 spree 的 `{2}`；Peer 法术力值为 7，只会进入手牌。
- Wishclaw 只有在同一回合能完成斩杀或已能处理其控制权转移时才启动；“先找牌、下回合再杀”会允许对手使用它。

## 留牌与回合节奏

- 默认保留 2-5 地且至少两个直接黑源；含 Nykthos 但没有 Urborg 的手牌必须按其前期产无色评估。
- 两地 + Thoughtseize/Fatal Push + 二费永久物可留；只有 Nykthos 的一地手必须调度。
- 1 回合：Thoughtseize 拆解反击/去除/更快组合；没有目标时留 Fatal Push。
- 2 回合：Scheming Silvertongue、Tithing Blade 或 Wishclaw；Wishclaw 只部署，不提前启动。
- 3 回合：Underworld Dreams 或 Unholy Annex；有 Sheoldred 计划时优先保留雄辩师的准备条件。
- 4 回合：Bloodletter、Sheoldred、Obliterator，或按手牌用 Beseech 补齐缺件。
- 5 回合：Bloodletter + Rush 可用五地直接斩杀；Peer 路线通常需要 Nykthos 与已建立的献力，不能把五地自动当成七费。
- 组合未齐时以 Sheoldred/Obliterator/Annex 转中速，Gray Merchant 回血并压低斩杀阈值。

## 换备简表

| 对局 | 换入 | 换出 |
|---|---|---|
| Izzet/红色快攻 | Path of Peril×2、Meathook×1、Withering Torment×2 | Peer×1、Beseech×1、Wishclaw×1、Underworld Dreams×2 |
| Greasefang / Cat-Oven | Cling to Dust×2、Leyline of the Void×2 | Obliterator×2、Underworld Dreams×1、Unholy Annex×1 |
| 蓝白/多色控制 | Duress×2、Stone Brain×2、Thought Distortion×2 | Fatal Push×4、Tithing Blade×2 |
| Lotus Field / 单核心组合技 | Duress×2、Stone Brain×2、Thought Distortion×2 | Fatal Push×4、Tithing Blade×2 |
| Badgermole 生物中速 | Path of Peril×2、Meathook×1、Withering Torment×2 | Peer×1、Beseech×1、Wishclaw×1、Underworld Dreams×2 |

以上均保持一换一和主牌 60 张；规则允许不等量换备，但本版本没有理由主动增加主牌张数。

## 可调仓位

- 更快半血分支：Rush of Dread 第 2 张、Unstoppable Slasher×2-3；相应减少 Peer/Dreams。
- 更稳导师分支：Grim Tutor、Beseech 第 2 张、Insatiable Avarice；相应减少 Wishclaw。
- 更偏献力中速：Archenemy's Charm、Preacher of the Schism、Archfiend of the Dross、Erebos, Bleak-Hearted。
- 可调对：Obliterator×1-2、Gray Merchant×1-2、Unholy Annex×2-3、Wishclaw×1-2、Urborg 第 2 张。

本次只完成牌表、API、概率和规则文本推演，尚未导入 Arena 进行真实对局；所有对局结论均为定性假设，不是胜率数据。
