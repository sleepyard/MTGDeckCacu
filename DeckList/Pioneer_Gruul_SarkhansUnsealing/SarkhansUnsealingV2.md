# SarkhansUnsealing V2（混合优化 / Pioneer / MTGA BO3）

基准日期：`2026-08-06`。本次按模式 B 牌表优化，输入为用户实测后的 V1 衍生牌表（下称"实测版"，60/12）。用户反馈实测运转良好，选择"混合优化"幅度：引擎区取舍 + 补首局互动 + 备牌补满 15。主轴不变：低费高力量生物站场，四费《萨坎解印》落地后把生物咒语转成 4 点去除/直伤，7 力以上生物单向清场终结。

## 改动对照 diff（实测版 → V2）

| 改动 | 牌 | 理由 |
|---|---|---|
| 砍 ×2 | 贾路的反抗 / Garruk's Uprising | 用户选定。四张引擎中它与解印同为"不直接影响场面的三费结界"，本版由 Talent 一级互斗与 Henge 承担其价值轴；释放 2 个主牌卡位给首局互动 |
| 加 ×2 | 轰然撞倒 / Ram Through | 用户选定。`{1}{G}` 力量结算伤害，配合本套 4-7 力生物等于两费解任意大生物；己方生物有践踏（Carnosaur/Ghalta/开印后的大生物）时溢出伤害打脸，与主题同向 |
| 备 +2 | 英勇干预 / Heroic Intervention | 补满备牌；对控制/扫场的核心对策，V1 备牌原有、实测版被砍 |
| 备 +1 | 无牌灵车 / Unlicensed Hearse | 补满备牌；坟场针对从 2 张回到 3 张，提高对 Greasefang/Cat-Oven 的上手率 |

### 考虑过但排除

- `Strangle` {R}：无条件 1 费 3 点，稳定性优于 Ram Through，但不随生物力量缩放、与主轴零配合；作为 Rigging 后续砍位的备选保留。
- `Torch the Tower` 回主牌：1 费 2 点+祭炼放逐很稳，但用户选择主题契合的 Ram Through；备牌仍留 2 张，对快攻换入后总数 4 张一费互动。
- 砍 `Fight Rigging`×2：四引擎中即时场面影响最弱，但 Hideaway 埋大生物可免费施放并再次触发解印，用户选择保留；列为下一轮首要观察位。
- `Hard-Hitting Question` / `Bushwhack` {G}：同为一费互斗类，Ram Through 的践踏溢出条款在本套上限更高；Bushwhack 的找地模式是条件地源，本套不缺血源。
- `Anzrag, the Quake-Mole` 回编：四费 8/4 能把单向清场从 6 费提前到 4 费，但本次用户未选激进换血；列入可调仓位。

## MTGA 导入牌表

```text
4 Bonecrusher Giant
1 Boseiju, Who Endures
4 Bristlebane Battler
4 Copperline Gorge
1 Cragcrown Pathway
2 Fight Rigging
4 Forest
2 Ghalta, Primal Hunger
2 Hunter's Talent
1 Karplusan Forest
4 Lovestruck Beast
4 Mountain
2 Outcaster Trailblazer
2 Ram Through
1 Rockfall Vale
3 Rootbound Crag
4 Sarkhan's Unsealing
4 Slumbering Trudge
1 Sokenzan, Crucible of Defiance
4 Stomping Ground
2 The Great Henge
4 Trumpeting Carnosaur

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

机器目标：主牌 `60`、备牌 `15`、生物 `24`、解印触发生物 `24`（4-6 力触发 `18`、7 力以上触发 `6`）、真地 `24`。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 2 | `{1}{G}` | 轰然撞倒 | Ram Through | 力量结算去除；己方生物践踏时溢出伤害打脸（新增） |
| 2 | `{1}{G}`，升级 `{1}{G}` / `{3}{G}` | 捕猎手才能 | Hunter's Talent | 进场互斗=一费点杀；二级攻击者 +1/+0 践踏；三级四力生物站场每回合抓一 |
| 4 | `{X}{G}` | 沉眠楚吉兽 | Slumbering Trudge | 堆叠上固定 6/6；`X=0` 一费触发解印，`X=3` 四费无晕眩 6/6 |
| 4 | `{1}{G}` | 驱鬃镇战员 | Bristlebane Battler | 堆叠上 6/6 触发解印；进场带五个 -1/-1 指示物变 1/1，ward `{2}` |
| 4 | `{1}{R}` // `{2}{R}` | 一脚踩下 // 碎骨巨人 | Stomp // Bonecrusher Giant | 两费 2 点不可防止；之后放逐区施放 4/3 触发解印 |
| 4 | `{G}` // `{2}{G}` | 心之所爱 // 热恋野兽 | Heart's Desire // Lovestruck Beast | 一费造 1/1；之后施放 5/5 触发解印并解锁攻击 |
| 2 | `{2}{G}`，预备 `{2}{G}` | 莽野帮开路人 | Outcaster Trailblazer | 4/2 触发；进场加一点任意色，其他四力生物进场抓牌；预备可制造四回合连锁 |
| 2 | `{2}{G}` | 操纵比赛 | Fight Rigging | Hideaway 5 埋牌；战斗开始放 +1/+1 指示物，场上有 7 力生物时免费施放埋藏牌（埋生物则再触发解印） |
| 4 | `{3}{R}` | 萨坎解印 | Sarkhan's Unsealing | 核心；施放 4-6 力生物打任意目标 4 点，施放 7+ 力生物单向打全场 4 点 |
| 4 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 7/6 践踏与单向清场；进场发现 5 可连锁解印触发；`{2}{R}` 弃掉对生物/鹏洛客造成 3 点 |
| 2 | `{7}{G}{G}`，按己方最大力量降费 | 巨石圆阵 | The Great Henge | 场上有 6 力 Trudge 时只需 `{1}{G}{G}`；产 `{G}{G}` 回 2 血，非衍生物进场放指示物并抓一 |
| 2 | `{10}{G}{G}`，按场上总力量降费 | 始饥戈厄塔 | Ghalta, Primal Hunger | 12/12 践踏；单向清场触发与独立终结；两张提高上手但可接受传奇冗余 |
| 1 | - | 历祚母圣树 | Boseiju, Who Endures | 绿源；通道处理神器、结界或非基本地 |
| 4 | - | 树林 | Forest | 基础绿源；Rootbound Crag 未横置条件 |
| 4 | - | 山脉 | Mountain | 基础红源；Rootbound Crag 未横置条件 |
| 4 | - | 铜索峡谷 | Copperline Gorge | 前三块地内通常未横置的红绿源 |
| 3 | - | 盘根峭壁 | Rootbound Crag | 控制山脉/树林时未横置的红绿源；套牌 12 张基本类别地支持 |
| 1 | - | 卡普路桑森林 | Karplusan Forest | 未横置红绿源；产有色失去 1 点生命 |
| 1 | - | 岩冠通路 // 丛冠通路 | Cragcrown Pathway // Timbercrown Pathway | 未横置红/绿二选一，落地锁定 |
| 1 | - | 落石山谷 | Rockfall Vale | 第三块地起稳定未横置的红绿源 |
| 1 | - | 逆炉霜剑山 | Sokenzan, Crucible of Defiance | 红源；通道造两个 1/1 |
| 4 | - | 晃动大地 | Stomping Ground | 有基本类别的红绿震地；付 2 血未横置，同时是 Rootbound Crag 的未横置条件 |

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局 |
|---:|---|---|---|---|
| 2 | `{1}{R}` | 风化侵蚀 | Abrade | 三点生物去除或摧毁神器 |
| 2 | `{1}{G}` | 英勇干预 | Heroic Intervention | 全体永久物辟邪+不灭；对控制/扫场保护解印与生物，不防放逐和反击 |
| 2 | `{2}{G}{G}` | 顽强巴洛西 | Obstinate Baloth | 4/4 触发生物进场回 4；对快攻与弃牌套 |
| 1 | `{G}` | 挑选毒药 | Pick Your Poison | 让对手牺牲神器、结界或飞行生物之一 |
| 2 | `{2}`，起动 `{2}` | 魔石大脑 | The Stone Brain | 定点移除非基本地同名牌，针对 Lotus Field 与单核心组合技 |
| 2 | `{3}{G}{G}` | 破诫巨魔图伦 | Thrun, Breaker of Silence | 不可反击 5/5 践踏，仍触发解印；控制对策 |
| 2 | `{R}` | 点燃塔楼 | Torch the Tower | 对快攻把一费互动补到 4 张；祭炼放逐处理死亡触发/坟场价值生物 |
| 2 | `{2}` | 无牌灵车 | Unlicensed Hearse | 响应放逐坟场牌，后期由大生物搭载成威胁；3 张提高对坟场套上手率 |

## 核心规则与配合（沿用 V1，新增项标注）

- 解印检查生物咒语在堆叠上的力量；Battler 按 6 力触发后才以 1/1 进场，Trudge 力量固定为 6 与 X 无关；触发先于生物结算，反击生物不能阻止伤害；7 力以上只触发第二段单向清场。
- 【新】`Ram Through` 是非生物咒语，不触发解印；它的价值在解印之外：场上有 Carnosaur/Ghalta（践踏）时，对阻挡者造成的溢出伤害改由该生物操控者承受，等于去除+直伤一体。它是法术且需要己方生物在场，空场时是死牌——留牌阶段要把它算作"有生物后的互动"而非无条件去除。
- 【新】`The Great Henge` 降费看场上己方生物的当前最大力量：Trudge 在场 6 力→`{1}{G}{G}`；Bonecrusher 4 力→`{3}{G}{G}`；注意 Battler 进场后是 1 力，不能按牌面 6 力算。Henge 的进场抓牌触发与解印互不冲突，同一波铺场双引擎同时结算。
- 【新】`Fight Rigging` 的 Hideaway 免费施放若施放 4 力以上生物咒语，解印正常触发；7 力条件看战斗开始时场上生物当前力量（含 Henge/Rigging 指示物加成后的数值）。
- 【新】`Hunter's Talent` 一级进场互斗由己方生物按力量造成伤害——用 Battler 触发时按当前 1 力结算，务必选 Trudge/Carnosaur 等高力量生物为目标。
- 三回合预备 Trailblazer、四回合解印+免费 Trailblazer 的 8 点连锁仍然成立；Henge 落地后同类连锁每波铺场都附赠抓牌与 +1/+1。

## 曲线、生存与赢点

- 首局互动 8 张：Stomp×4（两费）、Talent×2（一费互斗，需目标己方高力生物）、Ram Through×2（两费力量结算，需站场）。其中 6 张依赖己方生物在场，真正的无条件去除只有 Stomp×4——对红色快攻第一局仍是弱势对局，依赖换备。
- 引擎 8 张：解印×4、Rigging×2、Henge×2；Talent 同时算引擎与互动。引擎密度从实测版 12 张降到 8-10 张，卡手率下降。
- 7+ 清场触发 6 张（Carnosaur×4、Ghalta×2），最早第六回合；没有 4 费 Anzrag 后，前五回合清场只能靠解印第一段的 4 点点杀。
- 赢点一：解印把 18 张 4-6 力生物变成可指向 4 点。赢点二：6 张 7+ 生物单向清场后 Carnosaur 连锁/Ghalta 践踏终结。赢点三：无解印时 Adventure 卡差、Henge 抓牌、Trailblazer 抓牌与大身材 beatdown 独立获胜。
- 践踏来源：Carnosaur、Ghalta 天然践踏；Talent 二级攻击时赋予；这保证 Ram Through 的溢出条款和解印直伤之外的伤害穿透。

## 地源与概率（2026-08-06 复算）

24 真地，无 MDFC。红源 19、绿源 19（4 山脉与 Sokenzan 不产绿，4 树林与 Boseiju 不产红）。基本类别地 12 张（树林 4、山脉 4、晃动大地 4）支撑 Rootbound Crag 未横置。

- 七张起手至少两地：`85.73%`；2-5 地：`84.39%`（与 V1 相同）。
- 七张起手至少一个绿源：`94.18%`——较 V1（23 绿源，`97.33%`）下降 3.15 个百分点。这是 4 山脉方案的直接代价：一费绿牌（Heart's Desire、Trudge X=0）与双绿咒语（Henge、备牌 Baloth/Thrun）的稳定性都受影响，列为重点观察项。
- 起手至少一张基本类别地（Rootbound Crag 未横置条件）：`80.94%`。
- 先手第四回合（看 10 张）至少四地：`63.18%`；未计调度与 Trailblazer 产费。
- Carnosaur `{4}{R}{R}` 达成：先手第六回合（看 12 张）≥6 地且 ≥2 红源 `88.73%`；后手（13 张）`93.62%`。
- 四张解印：起手至少一张 `39.95%`；先手第四回合 `52.77%`；本版已无 Invasion 软检索，解印可得性完全靠自然抽取与 Henge/Talent 三级抓牌。
- 先手第十张前至少抓到一张生物：`99.66%`，Henge 降费与 Ram Through/Talent 需要站场的条件在对局早中期基本总能满足。

## 留牌与回合节奏

- 默认保留 2-5 地且前三回合有动作的起手；只有一地的手即使有 Heart's Desire/Trudge 也应调度。
- 全红地+多张一费绿牌的起手要调度：绿源起手率已从 97% 降到 94%，三色源拼接手（如 Cragcrown+山脉）优先保绿。
- 留牌评估时把 Ram Through、Talent 记为"有生物后互动"：起手只有互动没有生物的手牌，前两回合是空转的。
- 有解印时伤害分配原则不变：先清阻挡者再打脸；Ram Through 优先指给践踏生物吃溢出伤害。
- Henge 落地时机：场上有 6 力生物时第三至四回合即可 `{1}{G}{G}` 施放，不必等七费；但它与解印争夺三/四费回合，先下解印仍是默认序。

## 换备简表（V2 更新，均保持主牌 60）

| 对局 | 换入 | 换出 |
|---|---|---|
| Izzet / 红色快攻 | Torch×2、Abrade×2、Obstinate Baloth×2 | Ghalta×2、Carnosaur×2、Fight Rigging×2 |
| Badgermole / Company 生物中速 | Torch×2、Abrade×2 | Ghalta×2、Carnosaur×2 |
| Greasefang / Cat-Oven | Hearse×2、Abrade×2、Torch×2 | Ghalta×2、Carnosaur×2、Fight Rigging×2 |
| 蓝白 / 多色控制 | Heroic Intervention×2、Thrun×2 | Ram Through×2、Fight Rigging×2 |
| Lotus Field / 单核心组合技 | The Stone Brain×2 | Ram Through×2 |
| 单一神器、结界或飞行终结 | Pick Your Poison×1；神器较多再加 Abrade×2 | Ghalta×1；再按速度换 Carnosaur×2 |

对控制换出 Rigging 的理由：Hideaway 免费施放会被反击且节奏慢，控制对局中它的收益低于 Intervention/Thrun 的确定性与不可反击。对快攻换出 Rigging 的理由：它是主牌唯二"进场零场面影响"的牌之一（另一是解印本身），恰恰在最快节奏的对局里最拖节奏。

## 可调仓位（下一轮观察池）

- `Fight Rigging`×2：首要观察位。若实测继续偏弱，优先换 `Torch the Tower`×2（稳定互动）或 `Strangle`×2（1 费 3 点）。
- 地牌绿源：若一费绿牌卡手感明显，把 2 张山脉换回 `Karplusan Forest` 与第二张 `Cragcrown Pathway`（绿源回到 21，起手 ≥1 绿约 96.5%）；代价是 Carnosaur 双红概率略降。
- `Outcaster Trailblazer` 第 3-4 张：实测版砍到 2 张后抓牌连锁变弱；若长盘资源不足可回升。
- `Anzrag, the Quake-Mole` 回编 1-2：把单向清场从六费提前到四费，适合环境中小生物铺场增多时。
- `Ghalta` 第 2 张：若卡手率高或传奇冗余明显，可回到 1 张换第三张 `The Great Henge` 或其他终结。

## 验证与运行清单

- 抓取时间：`2026-08-06`；格式 `Pioneer`，平台 `MTGA`，队列 `BO3`，颜色 `ci<=rg`，截止日期 `2026-08-06`。
- 系列基线：最新已发行扩展仍为 `MSH`（2026-06-26），与 V1 基线一致；`banned:pioneer` 31 张，主备无命中。
- 本次新增/复核牌的逐 oracle 全印刷遍历：`Ram Through`（IKO 有 Arena 印刷）、`Rootbound Crag`（XLN/YEOE）、`Hunter's Talent`（BLB）、`Fight Rigging`（SNC）、`The Great Henge`（ELD）、`Heroic Intervention`（KLR 等 8 个 Arena 印刷）、`Unlicensed Hearse`（SNC/OTP）、`Trumpeting Carnosaur`（LCI）、`Ghalta, Primal Hunger`（J25 等 5 个）、`Mountain`——全部 Pioneer legal 且至少一个 Arena 印刷。曾先用默认搜索只回最新印刷、误判 `Ram Through`/`Rootbound Crag` 无 Arena 版本，已按坑位清单改用 `unique:prints` 全印刷遍历纠正。
- mtgch 中文名：`Ram Through`=轰然撞倒、`Rootbound Crag`=盘根峭壁、`Hunter's Talent`=捕猎手才能、`Fight Rigging`=操纵比赛、`The Great Henge`=巨石圆阵，均精确匹配；其余沿用 V1 核对结果（基线内无新牌/新禁牌，不重复抓取）。
- 互动候选枚举：互斗类 `mv<=2 o:fight` 命中 23 张、点杀类命中 116 张、力量结算类命中 37 张；宽查询仅召回，已按费用/条件/主题自冲突过滤。
- 主备牌数机器加总：主牌 60（生物 24 / 神器 2 / 结界 8 / 瞬间 2 / 地 24）、备牌 15，同名上限与赛制档案校验通过。
- 所有强度与对局判断仍为规则与结构推演；本轮改动尚未经 Arena 实导入与 BO3 对局验证。
