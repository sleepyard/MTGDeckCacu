# Sarkhan's Unsealing V4（妖精操纵比赛 / Pioneer / MTGA BO3）

基准日期：`2026-08-06`。本次按模式 B 对 V3 做实测迭代。用户反馈 V3 的 4 张罗堰妖精显著改善展开，但移除《操纵比赛》后缺少超展开能力。V4 因此保留 V3 的全部法术力结构和解印触发生物，只把两个主牌互动位改回 `Fight Rigging`，恢复 Hideaway 免费施放与《萨坎解印》的连锁上限。

一句话玩法：T1 妖精建立四费时间优势，T2/T3 用《操纵比赛》埋下高价值牌，再以 6 力楚吉兽加指示物或 7+ 力终结者解锁免费施放，让解印触发、发现 5、Henge 抓牌在同一回合叠加。

## 优化结论

- `Llanowar Elves`×4、真地×24、潜在绿源×20全部保留。V3 已实测证明这一层负责顺滑度，不能为加入 Rigging 再砍地或妖精。
- `Fight Rigging`×2 回归，替换 `Hunter's Talent`×2。主牌 28 生物、24 张解印触发生物和 5 张 7+ 触发均不变，新增引擎不会稀释核心触发密度。
- `The Great Henge`×2 保留。Henge 既是独立长盘引擎，也是 Rigging 的高价值免费目标；如果为了 Rigging 砍掉 Henge，会恢复爆发入口却削弱爆发命中质量。
- 主牌首局即时互动从 Stomp×4 + Talent×2 收窄为 Stomp×4，主动轴更集中。BO3 中对快攻和坟场套把 Rigging 换成 Torch/Abrade/Baloth，对控制则换成 Intervention/Thrun。
- 不增加第三张 Rigging。两张起手出现率已为 `22.15%`，看到第十张约 `30.79%`；第三张会进一步增加无生物场面的引擎叠手，并与四张解印争夺非场面卡位。

## 改动对照 diff（V3 → V4）

| 改动 | 牌 | 理由 |
|---|---|---|
| 加 ×2 | 操纵比赛 / Fight Rigging | 恢复 Hideaway 5、每回合成长与免费施放；妖精允许最快 T2 落地，Trudge/Anzrag 最快 T3 解锁 |
| 砍 ×2 | 捕猎手才能 / Hunter's Talent | 一级互斗仍依赖己方高力量生物；为保留 24 地、28 生物、Henge 和完整终结密度，只能从可替换非核心咒语位释放卡槽 |
| 不变 | 罗堰妖精 / Llanowar Elves ×4 | 实测已确认顺滑度来源，不因恢复超展开而回退 |
| 不变 | 巨石圆阵 / The Great Henge ×2 | 既是独立续航，也是 Rigging 免费施放的优质命中 |

没有调整地牌、妖精、Trailblazer 或高费终结数量。V4 与 V3 的法术力概率、解印触发密度和 7+ 触发密度完全相同，变化仅在“互动下限”与“免费施放上限”之间。

## MTGA 导入牌表

```text
2 Anzrag, the Quake-Mole
4 Bonecrusher Giant
1 Boseiju, Who Endures
4 Bristlebane Battler
4 Copperline Gorge
2 Cragcrown Pathway
2 Fight Rigging
4 Forest
1 Ghalta, Primal Hunger
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

机器目标：主牌 `60`、备牌 `15`、生物 `28`、解印触发生物 `24`（4-6 力 `19`、7 力以上 `5`）、神器 `2`、结界 `6`、真地 `24`。妖精不触发解印；Rigging/Henge 也不能作为生物咒语触发。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 2 | `{2}{R}{G}` | 地动鼹鼠安札格 | Anzrag, the Quake-Mole | 8/4；解印第二段与 Rigging 立即解锁器；被阻挡时追加战斗阶段 |
| 4 | `{1}{R}` // `{2}{R}` | 碎骨巨人 // 一脚踩下 | Bonecrusher Giant // Stomp | 主牌唯一即时互动组；之后施放 4/3 生物面触发解印 |
| 1 | - | 历祚母圣树 | Boseiju, Who Endures | 绿源；通道处理神器、结界或非基本地 |
| 4 | `{1}{G}` | 驱鬃镇战员 | Bristlebane Battler | 堆叠上按 6 力触发；进场后为带 ward `{2}` 的 1/1，不是 Rigging 的快速解锁器 |
| 4 | - | 铜索峡谷 | Copperline Gorge | 前三块地内通常未横置的红绿源 |
| 2 | - | 岩冠通路 // 丛冠通路 | Cragcrown Pathway // Timbercrown Pathway | 未横置红/绿二选一；落地后颜色锁定 |
| 2 | `{2}{G}` | 操纵比赛 | Fight Rigging | Hideaway 5；己方战斗开始放一个 +1/+1 指示物，再检查是否有 7+ 力并免费施放所藏牌 |
| 4 | - | 树林 | Forest | 基础绿源；支持 T1 妖精与 Rootbound Crag |
| 1 | `{10}{G}{G}`，按总力量降费 | 始饥戈厄塔 | Ghalta, Primal Hunger | 12/12 践踏；Rigging 立即解锁、解印单向清场和免费施放终结 |
| 1 | - | 卡普路桑森林 | Karplusan Forest | 未横置红绿源；产有色时支付 1 点生命 |
| 4 | `{G}` | 罗堰妖精 | Llanowar Elves | T1 基础加速；允许 T2 Rigging 或三费生物、T3 解印/Anzrag |
| 4 | `{G}` // `{2}{G}` | 心之所爱 // 热恋野兽 | Heart's Desire // Lovestruck Beast | 一费造 1/1；三费施放 5/5 触发解印；单 Rigging 需两个战斗步骤才从 5 力升至 7 力 |
| 3 | - | 山脉 | Mountain | 基础红源；与双地合计保留 19 个潜在红源 |
| 3 | `{2}{G}`，预备 `{2}{G}` | 莽野帮开路人 | Outcaster Trailblazer | 4/2 触发、任意色补费与四力生物抓牌；Rigging 免费施放时仍会触发解印 |
| 1 | - | 落石山谷 | Rockfall Vale | 第三块地起稳定未横置的红绿源 |
| 3 | - | 盘根峭壁 | Rootbound Crag | 条件未横置红绿源；由 Forest/Mountain/Stomping Ground 支持 |
| 4 | `{3}{R}` | 萨坎解印 | Sarkhan's Unsealing | 核心；4-6 力打任意目标 4 点，7+ 力单向打全场 4 点 |
| 4 | `{X}{G}` | 沉眠楚吉兽 | Slumbering Trudge | 堆叠上固定 6/6；Rigging 放置一个指示物后成为 7 力，可在同一次触发结算中解锁 |
| 1 | - | 逆炉霜剑山 | Sokenzan, Crucible of Defiance | 红源；通道制造两个 1/1 |
| 4 | - | 晃动大地 | Stomping Ground | 红绿震地并带基本类别；需要节奏时支付 2 点生命未横置 |
| 2 | `{7}{G}{G}`，按最大力量降费 | 巨石圆阵 | The Great Henge | 独立续航；Rigging 免费命中时绕过费用，后续生物进场抓牌并成长 |
| 2 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 7/6 践踏；免费施放时触发解印第二段，结算后发现 5 继续连锁；亦可弃牌打 3 |

## 超展开规则与顺序

- `Fight Rigging` 的触发按牌面顺序结算：先给目标生物一个 +1/+1 指示物，再检查己方是否控制 7 力以上生物。因此 6/6 Trudge 会先变成 7/7，并在同一次触发中满足解锁条件。
- Battler 进场后实际为 1/1。Rigging 给它的 +1/+1 指示物会与一个 -1/-1 指示物相消，使其实际成长到 2/2；不能把它的牌面 6 力误当成场上 7 力解锁器。
- 单张 Rigging 给 5/5 Lovestruck Beast 第一次加指示物后只有 6 力，要到下一次己方战斗才达到 7。若同时有两张 Rigging，两次触发分别结算，第一张把它变成 6/6，第二张变成 7/7并可解锁第二张所藏的牌。
- Rigging 免费“施放”所藏的生物牌，不是直接放进战场。若解印已经在场，免费施放 4+ 力生物仍会正常触发；生物随后被反击也不会取消已经进堆叠的解印伤害。
- 免费施放 `Trumpeting Carnosaur` 的顺序是：先施放并触发解印第二段，Carnosaur 结算进场后再发现 5；发现并施放另一张 4+ 力生物会再次触发解印。
- 免费施放第二张解印或 Henge 不会追溯触发已经施放的解锁生物。它们的价值从后续咒语开始，因此若 Hideaway 同时看到终结生物和引擎，应按当前场面与手牌决定，而不是固定拿费用最高者。
- Rigging 每张只藏一张牌；藏牌被反击、无法合法施放或选择不施放后不会自动换一张。多张 Rigging 各自独立藏牌和触发，记录好对应关系。

## 经典回合线

- 最快 Rigging 线：T1 妖精；T2 两地加妖精施放 Rigging；T3 三地加妖精施放 `Trudge (X=3)` 或 Anzrag，进入战斗。Trudge 经 Rigging 指示物变 7/7，Anzrag 本身为 8/4，二者都能立即解锁 Hideaway。
- 解印优先线：T1 妖精；T2 Battler/Trudge；T3 三地加妖精施放解印；T4 施放 Anzrag，先触发单向 4 点清场。该线不依赖 Rigging，确保 V4 没抽到副引擎时仍按 V3 节奏运作。
- 双引擎线：先有 Rigging，Hideaway 藏 Carnosaur/Ghalta；解印落地后用 7 力生物解锁。解锁生物先触发一次，免费终结再触发一次；若是 Carnosaur，发现 5 可能继续产生第三次触发。
- Henge 线：Rigging 免费施放 Henge后，当回合若仍有法术力或 Trailblazer 进场补费，继续施放非衍生生物；Henge 抓牌与解印伤害分别入堆叠，不互相替代。

## 概率与结构变化（精确超几何，未计调度）

V4 与 V3 的 24 地、20 潜在绿源、19 潜在红源、4 妖精、24 张解印触发生物和 5 张 7+ 生物完全相同，因此 V3 的法术力与解印概率继续成立：七张至少两地 `85.73%`，七张至少一妖精 `39.95%`，先手第四回合具备解印施放路径约 `37.33%`。

- 两张 Rigging 在七张起手至少一张：`22.15%`；先手看到第十张时至少一张：`30.79%`。
- 立即/单次解锁器共 9 张：Trudge×4（由 6 力加到 7）与原生 7+ 生物×5。先手看到第十张时至少一张：`83.05%`。
- 先手第十张同时至少看到一张 Rigging 和一张上述解锁器：`24.74%`。这只表示组件同现，不代表已经按时支付或未被互动。
- 以完整 60 张为母体粗算，Hideaway 顶五至少出现一张“解印×4、Henge×2或原生 7+ 生物×5”的高价值牌：`65.09%`；若把所有 24 张解印触发生物也算作轴线命中，则顶五至少一张为 `97.39%`。实际藏牌时已抽取的手牌会改变条件概率。
- 忽略颜色顺序和对手去除，先手 T2 前满足“起手有妖精，前八张有两地和 Rigging”的牌序上限约 `7.51%`；进一步在 T3 前有第三地和 Trudge/Anzrag 的解锁组合约 `2.91%`。这是裸组合概率，不是超展开胜率。

## 生存、赢点与换备

- 首局互动下限是 Stomp×4，低于 V3 的六张。V4 主牌选择主动超展开，不声称快攻对局因此改善；后手面对快攻时，对一地妖精手要更严格，因为去除妖精会同时打断地数和引擎节奏。
- 赢点一：解印将 19 张 4-6 力生物转成定向 4 点。赢点二：5 张 7+ 生物单向清场后以践踏、额外战斗或发现连锁终结。赢点三：Rigging 免费施放与 Henge/Trailblazer 抓牌在没有解印时仍能形成独立资源优势。
- Izzet/红色快攻：换入 Torch×2、Abrade×2、Obstinate Baloth×2；换出 Rigging×2、Ghalta×1、Carnosaur×2、Henge×1。首局高上限在换备后转为低曲线生存。
- Badgermole/Company 生物中速：换入 Torch×2、Abrade×2；换出 Ghalta×1、Carnosaur×2、Henge×1。保留 Rigging，用 Trudge/Anzrag突破地面僵局。
- Greasefang/Cat-Oven：换入 Hearse×2、Abrade×2、Torch×2；换出 Rigging×2、Ghalta×1、Carnosaur×2、Henge×1。
- 蓝白/多色控制：换入 Heroic Intervention×2、Thrun×2；换出 Rigging×2、Henge×2。免费施放仍可被反击，换成确定保护和不可反击威胁。
- Lotus Field/单核心组合技：换入 The Stone Brain×2；换出 Stomp×2。此对局保留 Rigging的竞速上限。
- 单一神器、结界或飞行终结：换入 Pick Your Poison×1；换出 Ghalta×1。神器数量较多时再加入 Abrade×2并换出最慢的两张 Carnosaur。

## 可调仓位

- `Fight Rigging` 固定先测试 2 张，不立即升 3。下一轮至少记录：起手叠手率、T2 落地率、首次解锁回合、Hideaway 命中类型、藏牌是否被反击，以及它是否在无生物场面成为死牌。
- 若首局因缺互动明显恶化，优先把一张 Henge 改为 `Torch the Tower`，不要先砍妖精、地或 Rigging；这会把主动轴调整为 2 Rigging/1 Henge/1 Torch 的折中结构。
- 若 Rigging 经常命中低费 Battler/Elf而不是高价值牌，可将第三张 Carnosaur 加回，以第二张 Henge或第三张 Trailblazer为交换位；不要通过增加第 3 张 Rigging来修复命中质量。
- 若双 Rigging 经常叠手且首次解锁晚于第五回合，则说明问题是解锁器/对局环境而非抽不到引擎，应回到 V3 的互动结构而不是继续增加非场面结界。

## 验证与运行清单

- 运行基线沿用 V3：`2026-08-06`，Pioneer，MTGA，BO3，颜色 `ci<=rg`；本轮没有新增 oracle 牌名。
- `Fight Rigging` 已在 V2 按全部印刷核实：SNC 有 Arena 印刷、Pioneer legal；mtgch 中文名精确匹配为《操纵比赛》。其 Hideaway、战斗开始加指示物和 7 力检查均按牌面顺序复核。
- 主牌机器目标为 60，备牌 15，同名最多 4；主牌类型目标为生物 28、神器 2、结界 6、地 24。换备方案均一换一并保持 60 张。
- 本轮方案基于用户对 V3 的实际体验，但尚未获得具体对局日志。除“V3 展开更顺滑、缺少超展开”外，概率、强度与对局结论仍是结构分析，不是胜率数据。

数据源沿用 V3：[Scryfall Fight Rigging](https://api.scryfall.com/cards/named?exact=Fight%20Rigging)、[官方禁限牌列表](https://magic.wizards.com/en/banned-restricted-list)、[mtgch 中文牌名 API](https://mtgch.com/api/v1/card-names/)。
