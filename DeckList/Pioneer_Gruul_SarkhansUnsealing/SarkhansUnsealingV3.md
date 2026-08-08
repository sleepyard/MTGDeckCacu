# Sarkhan's Unsealing V3（四妖精坡道 / Pioneer / MTGA BO3）

基准日期：`2026-08-06`。本次是对 V2 的全局优化，用户实测确认萨坎解印需要固定投入 4 张罗堰妖精作为基础提速资源。主轴保持不变：低费高力量生物站场，提前落下《萨坎解印》，把后续生物咒语转成 4 点去除/直伤；`Anzrag`、`Trumpeting Carnosaur` 和 `Ghalta` 负责 7 力以上的单向清场与终结。

## 优化结论

- 4 张 `Llanowar Elves` 是强制基础包，不把它们算作解印触发生物；它们的价值是把四费解印和四费 Anzrag 各提前一个回合，并让 Plot/Trailblazer 线更容易连续展开。
- V2 的 `Fight Rigging`×2 与 `Ram Through`×2 一并移除。前者在快攻和控制对局都是慢一拍的非场面引擎，后者在没有己方生物时是死牌；妖精加入后，卡位应优先给确定的法术力和更早的高力量触发。
- `Outcaster Trailblazer` 从 2 张升至 3 张，作为四力触发、任意色补费和后续抓牌的中段枢纽；不升到 4 张，避免三费绿色咒语过密并与第三回合解印争用。
- `Anzrag` 回编 2 张、`Carnosaur` 收窄至 2 张、`Ghalta` 收窄至 1 张。这样仍有 5 张 7+ 触发，但其中 2 张是四费可达的 Anzrag；高费传奇冗余和空手卡手率下降。
- 地牌保持 24 张，不把妖精当作替代地。`Mountain`×4 → ×3，`Cragcrown Pathway`×1 → ×2，潜在绿源提高 19 → 20，保留 19 个潜在红源以支持 Carnosaur/解印。

## 改动对照 diff（V2 → V3）

| 改动 | 牌 | 理由 |
|---|---|---|
| 加 ×4 | 罗堰妖精 / Llanowar Elves | `{G}` 加 `{G}`；V3 的基础提速资源，T1 下、T2 进入两费高力量线，或 T3 支付解印 |
| 加 ×1 | 莽野帮开路人 / Outcaster Trailblazer | 四力触发、进场任意色法术力、后续四力生物抓牌；3 张足以提高出现率而不挤满三费段 |
| 加 ×2 | 地动鼹鼠安札格 / Anzrag, the Quake-Mole | `{2}{R}{G}` 的 8/4，第四回合可作为 7+ 触发，比 V2 的六费清场窗口提前 |
| 减 ×2 | 长吼食肉龙 / Trumpeting Carnosaur | 保留发现 5、践踏和弃牌 3 点的独立价值，但六费密度随妖精坡道收窄 |
| 减 ×1 | 始饥戈厄塔 / Ghalta, Primal Hunger | 传奇冗余和无场面时的高费卡手降低；保留 1 张作为独立 12/12 终结 |
| 砍 ×2 | 操纵比赛 / Fight Rigging | V2 首要观察位；Hideaway 在快攻无即时场面影响，控制对局又容易被反击 |
| 砍 ×2 | 轰然撞倒 / Ram Through | 依赖己方生物在场，妖精降低平均力量并增加被清场后的死牌率；主牌保留 Stomp/Talent 两类互动 |
| 调整 | 盘根峭壁方案中的 `Mountain`×4 + `Cragcrown`×1 → `Mountain`×3 + `Cragcrown`×2 | 保持 24 地和 19 潜在红源，增加 T1/T2 绿源，降低妖精与双绿牌的颜色失败 |

## MTGA 导入牌表

```text
2 Anzrag, the Quake-Mole
4 Bonecrusher Giant
1 Boseiju, Who Endures
4 Bristlebane Battler
4 Copperline Gorge
2 Cragcrown Pathway
4 Forest
1 Ghalta, Primal Hunger
2 Hunter's Talent
1 Karplusan Forest
4 Llanowar Elves
4 Lovestruck Beast
3 Mountain
3 Outcaster Trailblazer
1 Rockfall Vale
3 Rootbound Crag
4 Sarkhan's Unsealing
4 Slumbering Trudge
1 Sokenzan, Crucible of Defiance
4 Stomping Ground
2 The Great Henge
2 Trumpeting Carnosaur

Sideboard
2 Abrade
2 Heroic Intervention
2 Obstinate Baloth
1 Pick Your Poison
2 The Stone Brain
2 Thrun, Breaker of Silence
2 Torch the Tower
2 Unlicensed Hearse
```

机器目标：主牌 `60`、备牌 `15`、生物 `28`、解印触发生物 `24`、其中 4-6 力 `19`、7 力以上 `5`、真地 `24`。主牌不使用 MDFC；妖精是生物但不满足解印的 4 力门槛。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 2 | `{2}{R}{G}` | 地动鼹鼠安札格 | Anzrag, the Quake-Mole | 8/4；解印第二段单向清场；被阻挡时追加战斗阶段，第四回合可达 |
| 4 | `{1}{R}` // `{2}{R}` | 碎骨巨人 // 一脚踩下 | Bonecrusher Giant // Stomp | 早期两点互动；从放逐区施放 4/3，触发第一段解印 |
| 1 | - | 历祚母圣树 | Boseiju, Who Endures | 绿源；通道处理神器、结界或非基本地 |
| 4 | `{1}{G}` | 驱鬃镇战员 | Bristlebane Battler | 堆叠上按 6 力触发，进场后带 -1/-1 指示物并带 ward `{2}` |
| 4 | - | 铜索峡谷 | Copperline Gorge | 前三块地内通常未横置的红绿源 |
| 2 | - | 岩冠通路 // 丛冠通路 | Cragcrown Pathway // Timbercrown Pathway | 未横置红/绿二选一；落地时锁定颜色 |
| 4 | - | 树林 | Forest | 基础绿源；同时满足 Rootbound Crag 的类别条件 |
| 1 | `{10}{G}{G}`，按场上总力量降费 | 始饥戈厄塔 | Ghalta, Primal Hunger | 12/12 践踏；7+ 单向清场触发和独立终结，单张控制传奇冗余 |
| 2 | `{1}{G}`，升级 `{1}{G}` / `{3}{G}` | 捕猎手才能 | Hunter's Talent | 一级进场互斗，二级赋予践踏，三级为四力生物提供持续抓牌 |
| 1 | - | 卡普路桑森林 | Karplusan Forest | 未横置红绿源；产有色时支付 1 点生命 |
| 4 | `{G}` | 罗堰妖精 | Llanowar Elves | 基础加速；`{T}: Add {G}`，不触发解印，优先保护到第三回合 |
| 4 | `{G}` // `{2}{G}` | 心之所爱 // 热恋野兽 | Heart's Desire // Lovestruck Beast | 一费造 1/1；三费施放 5/5，触发第一段并提供独立站场 |
| 3 | - | 山脉 | Mountain | 基础红源；数量收窄后仍保留 19 个潜在红源 |
| 3 | `{2}{G}`，预备 `{2}{G}` | 莽野帮开路人 | Outcaster Trailblazer | 四力触发；进场加一点任意色，其他四力生物进场抓牌；Plot 可与解印排程 |
| 1 | - | 落石山谷 | Rockfall Vale | 第三块地起稳定未横置的红绿源 |
| 3 | - | 盘根峭壁 | Rootbound Crag | 控制山脉/树林时未横置；主牌 11 张无条件类别地支持条件 |
| 4 | `{3}{R}` | 萨坎解印 | Sarkhan's Unsealing | 核心引擎；4-6 力打任意目标 4 点，7+ 力单向打全场 4 点 |
| 4 | `{X}{G}` | 沉眠楚吉兽 | Slumbering Trudge | 堆叠上固定 6/6；`X=0` 是一费触发，`X=3` 是四费 6/6 |
| 1 | - | 逆炉霜剑山 | Sokenzan, Crucible of Defiance | 红源；通道制造两个 1/1 |
| 4 | - | 晃动大地 | Stomping Ground | 有基本类别的红绿震地；需要节奏时支付 2 点生命未横置 |
| 2 | `{7}{G}{G}`，按最大力量降费 | 巨石圆阵 | The Great Henge | 6 力生物在场时大幅降费；产双绿回血，非衍生物进场抓牌并加指示物 |
| 2 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 7/6 践踏与单向清场；发现 5 连锁，或弃牌造成 3 点 |

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局 |
|---:|---|---|---|---|
| 2 | `{1}{R}` | 风化侵蚀 | Abrade | 三点生物去除或摧毁神器 |
| 2 | `{1}{G}` | 英勇干预 | Heroic Intervention | 对扫场和控制保护解印与场面；不防放逐和反击 |
| 2 | `{2}{G}{G}` | 顽强巴洛西 | Obstinate Baloth | 4/4、进场回 4；对快攻和弃牌 |
| 1 | `{G}` | 挑选毒药 | Pick Your Poison | 处理单一神器、结界或飞行生物 |
| 2 | `{2}`，起动 `{2}` | 魔石大脑 | The Stone Brain | 针对 Lotus Field 和单核心组合技 |
| 2 | `{3}{G}{G}` | 破诫巨魔图伦 | Thrun, Breaker of Silence | 不可反击的 5/5 践踏；控制对策并触发解印 |
| 2 | `{R}` | 点燃塔楼 | Torch the Tower | 快攻低费放逐互动；祭炼后 3 点 |
| 2 | `{2}` | 无牌灵车 | Unlicensed Hearse | 坟场针对，后期可由大生物搭载成为威胁 |

备牌沿用 V2 的 15 张配置。妖精坡道在首局已经提供速度，备牌不再额外塞入高费牌；换备默认一换一并保持主牌 60 张。

## 核心规则与回合线

- 解印检查的是生物咒语在堆叠上的力量。`Llanowar Elves` 是 1/1，不触发任何一段；`Bristlebane Battler`、`Slumbering Trudge` 和 `Lovestruck Beast` 按咒语面 4-6 力触发，即使进场后力量下降也不改变已进入堆叠的触发。
- `Anzrag`、`Trumpeting Carnosaur`、`Ghalta` 按 7+ 力只触发第二段，对对手及其每个生物和鹏洛客各造成 4 点；不会同时触发第一段。
- 有妖精时的默认线是：T1 妖精；T2 用两点法术力施放 Battler 或 `Slumbering Trudge (X=1)`；T3 用三地加妖精施放四费解印。T4 若有 Anzrag，继续用三地加妖精施放 `{2}{R}{G}`，立即完成第二段清场。
- 没有解印但有 Trailblazer 时，T3 支付 `{2}{G}` 预备，T4 三地加妖精施放解印，再免费施放预备区的 Trailblazer；Trailblazer 进场产生一点任意色法术力，可继续施放 `Trudge (X=0)`，形成两个第一段触发。
- `Hunter's Talent` 一级互斗依赖己方生物在场。妖精只能提供 1 点力量，不能把它当作与大生物对撞的去除主体；优先让 Battler、Trudge、Lovestruck 或 Trailblazer承担互斗。
- `The Great Henge` 的降费看场上最大力量。`Trudge` 是 6 力时可显著降低其费用；不能把进场后为 1/1 的 Battler 按牌面 6 力用于降费。
- `Anzrag` 是传奇牌。两张同时在手不是自动非法，但应分开评估自然冗余；第一张的解印触发和场面压力通常已经足够，第二张可作为被弃牌/被反击后的重建资源。

## 曲线、生存与赢点

- 主牌生物 28 张：4 张一费妖精，8 张两费高力量生物（Battler/Trudge 的常规 X=1 线），7 张三费四力生物（Bonecrusher、Lovestruck、Trailblazer），5 张 7+ 终结，另有 4 张高力量四费解印触发位。24 张触发生物维持 V2 的密度，妖精只增加法术力，不稀释触发数量。
- 首局确定互动为 `Stomp`×4 与 `Hunter's Talent`×2；`Talent` 和战斗型互动都标记为“需己方生物在场”，不能替代无条件去除。Carnosaur 的弃牌异能提供中后期对生物/鹏洛客的 3 点补充。
- 赢点一：解印把 19 张 4-6 力生物转成 4 点定向伤害，先处理阻挡者再打脸。
- 赢点二：Anzrag/Carnosaur/Ghalta 共 5 张 7+ 生物完成单向清场，再用践踏、额外战斗或持续抓牌终结。
- 赢点三：没有解印时，Adventure 卡差、Trailblazer 抓牌、Henge 抓牌和大身材 beatdown 仍能独立获胜；妖精在中后期可由 Henge 放置指示物后转为可攻击的资源，但不把它当作主轴回报。

## 地源与概率（精确超几何，未计调度）

24 张真地，无 MDFC。按落地前可选择的潜在颜色计，绿源 `20`、红源 `19`；无条件基本类别地 `11`（Forest×4、Mountain×3、Stomping Ground×4），另有 Rootbound Crag×3 作为条件类别地。Rootbound Crag 的条件未横置不能从总色源直接推导。`Cragcrown Pathway` 每张落地后锁定一种颜色，不能在同一局同时重复计为红绿源。

- 七张起手至少一张妖精：`39.95%`；看到第九张时：`48.75%`。
- 七张起手至少两地：`85.73%`；先手到第四回合看十张至少四地：`63.18%`。妖精是额外法术力，不把它加进地牌卡位，也不把地数概率改写成“28 个 mana source”。
- 七张起手至少一个潜在绿源：`95.17%`；至少一个潜在红源：`94.18%`。绿源较 V2 的 `94.18%` 提高，红源保持 V2 水平；实际 T1 未横置颜色仍需按落地顺序判断。
- 先手第三回合（看九张）同时有妖精、三地和解印：`14.86%`；这是最早 T3 解印线，不把抽到妖精但没有三地的手算成成功。
- 先手第四回合（看十张）有解印且具备“妖精+三地”或“四地”任一路径：`37.33%`，V2 只有“解印+四地”的 `29.82%`。该提升是结构性速度提升，不是胜率。
- 先手第四回合同时具备解印、妖精、三地和 Anzrag：`4.94%`；它代表“已完成解印后下一回合立刻四费清场”的裸样本，不含调度、Trailblazer 预备或 Henge 降费。
- 先手第五回合仅以“妖精+五地+Carnosaur”达到六费的裸样本约 `8.99%`；Trailblazer 产费、Ghalta 降费和调度会改变实战表现，不能把该数字当作对局胜率。

## 留牌与换备

- 默认保留 2-4 地、T1/T2 有动作且有至少一张中段触发或解印的手。`Llanowar Elves + 两地 + 解印` 可留；若只有一地，即使有妖精也通常调度，因为妖精被去除后会失去第二块地。
- 先手 `妖精 + 三地 + 解印` 优先按 T1 妖精、T2 高力量两费生物、T3 解印规划；对快攻不要为了第三回合速度无条件支付 Stomping Ground 的 2 点生命。
- Izzet/红色快攻：换入 Torch×2、Abrade×2、Obstinate Baloth×2；换出 Ghalta×1、Carnosaur×2、The Great Henge×1、Hunter's Talent×2。保留妖精但不要把它当作阻挡者。
- 生物中速：换入 Torch×2、Abrade×2；换出 Ghalta×1、Carnosaur×2、The Great Henge×1。
- Greasefang/Cat-Oven：换入 Hearse×2、Abrade×2、Torch×2；换出 Ghalta×1、Carnosaur×2、The Great Henge×1、Hunter's Talent×2。
- 蓝白/多色控制：换入 Heroic Intervention×2、Thrun×2；换出 Hunter's Talent×2、The Great Henge×2。妖精应在能保护解印的窗口下，避免无收益地暴露。
- Lotus Field/单核心组合技：换入 The Stone Brain×2；换出 Hunter's Talent×2。若对手同时有大量小生物，保留一张 Talent，不要机械执行换备表。

## 可调仓位

- `Outcaster Trailblazer`×3 是第一观察位。若测试显示 Plot 经常无法在 T3 支付，可降回 2 张并把空出的卡位换为主牌 `Torch the Tower`×1。
- `Anzrag`×2 是第二观察位。若环境里大生物/非生物威胁更多，可改为第三张 `Trumpeting Carnosaur`；若小生物铺场明显，则升到 3 张并从 `Ghalta` 和 Henge 各减一张。
- 不建议再加入第 5-8 张一费妖精。八张会明显增加解印在场后的低力量抽牌，除非另建以大费法术或 Henge 为终点的独立坡道版本。
- 若红色来源连续导致 Carnosaur 卡手，优先把第二张 `Cragcrown Pathway` 改回 `Mountain`；若 T1 绿源失败更常见，则保留 V3 的绿源配置并减少一张高费终结。

## 验证与运行清单

- 运行基线：`2026-08-06`，Pioneer，MTGA，BO3，颜色 `ci<=rg`，截止日期 `2026-08-06`；官方 Pioneer 禁牌表复核通过，本表主备均未命中。
- 新增牌逐 oracle 核对：`Llanowar Elves`（FDN，Arena ID `93940`，Pioneer legal）、`Anzrag, the Quake-Mole`（MKM，Arena ID `89100`，Pioneer legal）；`Outcaster Trailblazer`（OTJ，Arena ID `90519`）重新确认。
- `The Great Henge` 的最新 Scryfall 印刷不一定带 Arena 标记，因此平台结论必须按 `unique:prints` 遍历其全部印刷；沿用 V2 已核实的 ELD Arena 印刷，不能只看最新 CMM 印刷。
- mtgch 中文名新增精确匹配：`Llanowar Elves` = `罗堰妖精`；其余牌名沿用 V2 已核实的 oracle 结果，并需在实际导入前再次按全量牌名集合跑一次。
- 主牌加总：`60`（生物 `28`、神器 `2`、结界 `6`、地 `24`）；备牌 `15`。同名上限、Pioneer 合法性、Arena 任一印刷和 `ci<=rg` 颜色身份均为机器门禁项。
- 本文概率均为静态超几何或组合计数，未计调度、对手互动、Trailblazer 产费、Henge 降费、牌库顶检索或 Arena 实际 BO3 日志；尚不能据此宣称胜率。下一次实测应至少记录妖精存活到 T3 的比例、T3 解印实际落地率、Anzrag/Carnosaur 卡手率和换备后首局互动命中率。

数据源：[Scryfall Llanowar Elves](https://api.scryfall.com/cards/named?exact=Llanowar%20Elves)、[Scryfall Anzrag](https://api.scryfall.com/cards/named?exact=Anzrag%2C%20the%20Quake-Mole)、[Scryfall Outcaster Trailblazer](https://api.scryfall.com/cards/named?exact=Outcaster%20Trailblazer)、[官方禁限牌列表](https://magic.wizards.com/en/banned-restricted-list)、[mtgch 中文牌名 API](https://mtgch.com/api/v1/card-names/)。
