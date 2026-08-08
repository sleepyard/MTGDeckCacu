# SarkhansUnsealing V1（低费开印 / Pioneer / MTGA BO3）

基准日期：`2026-08-02`。本次按模式 A 从零构筑，采用仓库默认参数：娱乐向但保证可对局强度、MTGA、Pioneer BO3、无预算上限、禁用行侣。用户要求“直接构筑”，因此不等待中途方向确认，而是记录默认权重后自动选择方案。

一句话玩法：前期用带副作用的低费高力量生物站场，四费落下《萨坎解印》，随后把每张生物转成 4 点去除或直伤，并以 7 力以上生物先单向清场再进场终结。

## 运行基线

- 主题边界：主牌必须让《萨坎解印》成为真正引擎，而不是普通 Gruul 中速里的四张彩蛋；主牌高力量生物应兼顾“核心在场时的触发效率”和“没抽到核心时的独立战斗力”。
- 代表牌：《萨坎解印》为唯一强制锚点；自动候选以低费 4-6 力、7 力以上、卡差、互动和功能地五个模块展开。
- 优化权重：主题保真 `45%`、无核心时的可运作性 `35%`、当前环境生存与对策 `20%`。这是构筑偏好，不是实测胜率模型。
- 牌池：Pioneer、截至基准日已发行、存在任一 MTGA 印刷、红绿且允许无色（`ci<=rg`）。
- 系列基线：Scryfall `/sets` 显示最新已发行扩展为 `MSH`（Marvel Super Heroes，`2026-06-26`）；晚于基准日的系列不进入检索。
- 禁牌：Scryfall `banned:pioneer` 返回 31 张基础禁牌；官方列表另列仅 MTGA BO1 禁用的 `Tibalt's Trickery`。本表为 BO3，主备均未命中任何禁牌。
- 环境定位：官方 `2026-06-29` 公告称 Pioneer 宏观类型分布良好，Badgermole 中速/坡道与 Izzet 是主要参照。本表没有成熟赛事样本，定位为主题鲜明的娱乐向可行构筑，不宣称主流。

数据源：[Scryfall sets](https://api.scryfall.com/sets)、[Scryfall Pioneer + Arena](https://scryfall.com/search?q=f%3Apioneer+game%3Aarena+date%3C%3D2026-08-02)、[官方禁牌列表](https://magic.wizards.com/en/banned-restricted-list)、[2026-06-29 禁限牌公告](https://magic.wizards.com/en/news/announcements/banned-and-restricted-june-29-2026)、[mtgch 中文牌名 API](https://mtgch.com/api/v1/card-names/)。

## 候选检索

所有宽查询都使用 `f:pioneer game:arena date<=2026-08-02 ci<=rg`，按 oracle 牌去重；宽查询只负责召回，随后按费用、实际站场、副作用、卡差和主轴自冲突过滤。

| 模块 | 查询补充条件 | 命中数 |
|---|---|---:|
| 全部触发生物 | `t:creature pow>=4` | 805 |
| 三费及以下 4-6 力 | `t:creature pow>=4 pow<=6 mv<=3` | 102 |
| 7 力以上清场触发 | `t:creature pow>=7` | 110 |
| 六费及以下清场触发 | `t:creature pow>=7 mv<=6` | 47 |
| 大身材卡差 | `o:"power 4 or greater" o:draw` | 13 |
| 四力以上历险生物 | `t:creature pow>=4 is:adventure` | 12 |

### 重点候选

| 模块 | 候选 | Arena 系列 | 结论 |
|---|---|---|---|
| 核心 | 萨坎解印 / Sarkhan's Unsealing | JMP | 满编 4；所有生物位围绕其施放触发设计 |
| 低费触发 | 沉眠楚吉兽 / Slumbering Trudge | SOS | 满编 4；力量固定为 6，`X=0` 时只需 `{G}` 便可触发 4 点 |
| 低费触发 | 驱鬃镇战员 / Bristlebane Battler | ECL | 满编 4；堆叠上为 6/6，进场后才带五个 -1/-1 指示物 |
| 低费触发 | 穿山虎 / Tiger-Dillo | TLA | 采用 2；两费 4/3，但需要另一只四力生物才能攻防 |
| 双阶段牌 | 碎骨巨人 // 一脚踩下 | ELD | 满编 4；首局早期互动与三费触发生物共用卡位 |
| 双阶段牌 | 热恋野兽 // 心之所爱 | ELD | 满编 4；一费先造 1/1，三费 5/5 触发并独立站场 |
| 卡差/连锁 | 莽野帮开路人 / Outcaster Trailblazer | OTJ | 满编 4；自身四力、后续大生物抓牌，预备可制造四回合连锁 |
| 7+ 终结 | 地动鼹鼠安札格 / Anzrag, the Quake-Mole | MKM | 采用 3；四费 8/4，是最便宜且无需额外条件的单向清场触发 |
| 7+ 终结 | 长吼食肉龙 / Trumpeting Carnosaur | LCI | 采用 2；7 力清场，进场发现 5；卡手时可弃掉造成 3 点 |
| 7+ 终结 | 始饥戈厄塔 / Ghalta, Primal Hunger | J25 | 采用 1；12 力清场与践踏终结，可被场上总力量降费 |
| 选择 | 进军依夏兰 / Invasion of Ixalan | MOM | 采用 2；顶五找任意永久物；被击败后以背面施放 4/3，可额外触发解印 |
| 互动 | 点燃塔楼 / Torch the Tower | WOE | 主牌 2、备牌 2；补足一费放逐互动，总数不超过四张 |

### 考虑过但排除

- `Elvish Mystic` / `Llanowar Elves`：能把核心提前到第三回合，但八张一力生物会显著稀释核心落地后的触发密度。本版优先测试低费触发连锁。
- `Kiora, Behemoth Beckoner`：大身材进场抓牌很契合，但它本身不触发解印；`Outcaster Trailblazer` 同时提供四力触发、预备节奏、一次法术力和持续抓牌。
- `Garruk's Uprising`：能补牌与践踏，但与四张解印形成过多不影响场面的三至四费引擎，首局生存更差。
- `Migloz, Maze Crusher` / `Bloated Contaminator`：都是可靠三费四力，但每点法术力的触发效率低于两费候选，功能由主牌互动和备牌承担。
- `Hulking Raptor` / `Railway Brawler`：能提供资源或爆发，但四至五费非清场触发与解印争夺关键回合。
- `Etali, Primal Conqueror` / `Tyrranax Rex` / `Titan of Industry`：7 力以上质量高，但七费密度会令没抽到解印的对局过于笨重。
- `Casey Jones, Vigilante`：三费四力兼抓三很强，但下个维持随机弃三会破坏为解印连锁保留的手牌。

## 构筑方向

| 方向 | 做法 | 优点 | 代价 |
|---|---|---|---|
| A 低费开印连锁（采用） | Trudge、Battler、Tiger-Dillo 与 Trailblazer 压低每次触发成本 | 核心在场时爆发最高，28 张触发生物；仍有历险和大生物独立作战 | 部分低费生物带明显攻防副作用 |
| B 妖精坡道 | 八张一费妖精加速三回合解印，顶端增加 Etali/Tyrranax | 核心更早登场，高费单卡质量高 | 一力妖精不触发，后期连续开印能力低，怕去除加速源 |
| C 七力清场坡道 | 增加 Hulking Raptor、Carnosaur 与七费终结 | 更频繁触发第二段单向扫场 | 解印和高费牌同时在手时容易被快攻惩罚 |

## MTGA 导入牌表

```text
3 Anzrag, the Quake-Mole
4 Bonecrusher Giant
1 Boseiju, Who Endures
4 Bristlebane Battler
2 Copperline Gorge
4 Cragcrown Pathway
2 Forest
1 Ghalta, Primal Hunger
2 Invasion of Ixalan
4 Karplusan Forest
4 Lovestruck Beast
4 Outcaster Trailblazer
2 Restless Ridgeline
4 Rockfall Vale
4 Sarkhan's Unsealing
4 Slumbering Trudge
1 Sokenzan, Crucible of Defiance
4 Stomping Ground
2 Tiger-Dillo
2 Torch the Tower
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

机器目标：主牌 `60`、备牌 `15`、主牌生物 `28`、解印触发生物 `28`、4-6 力触发 `22`、7 力以上触发 `6`、真地 `24`。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 2 | `{R}` | 点燃塔楼 | Torch the Tower | 一费造成 2；若祭炼则为 3，目标本回合将死时改为放逐 |
| 4 | `{X}{G}` | 沉眠楚吉兽 | Slumbering Trudge | 堆叠上固定 6/6；`X=0` 是一费触发，`X=3` 是无晕眩指示物的四费 6/6 |
| 4 | `{1}{G}` | 驱鬃镇战员 | Bristlebane Battler | 堆叠上 6/6；进场成为带 ward `{2}` 的 1/1，后续每只生物为其移除一个 -1/-1 指示物 |
| 2 | `{1}{R}` | 穿山虎 | Tiger-Dillo | 两费四力触发；场上另有四力生物时才可攻击或阻挡 |
| 2 | `{1}{G}` // 背面 | 进军依夏兰 // 好斗帝王龙 | Invasion of Ixalan // Belligerent Regisaur | 顶五找永久物；被击败后放逐并以背面施放 4/3 践踏，因此会触发解印 |
| 4 | `{1}{R}` // `{2}{R}` | 一脚踩下 // 碎骨巨人 | Stomp // Bonecrusher Giant | 两费造成 2；之后从放逐区施放 4/3，触发 4 点 |
| 4 | `{G}` // `{2}{G}` | 心之所爱 // 热恋野兽 | Heart's Desire // Lovestruck Beast | 一费造 1/1；之后施放 5/5，触发 4 点且可由衍生物解锁攻击 |
| 4 | `{2}{G}`，预备 `{2}{G}` | 莽野帮开路人 | Outcaster Trailblazer | 4/2 触发；进场加一点任意色，其他四力生物进场时抓牌 |
| 4 | `{3}{R}` | 萨坎解印 | Sarkhan's Unsealing | 核心；施放 4-6 力生物打任意目标 4 点，施放 7+ 力生物单向打全场 4 点 |
| 3 | `{2}{R}{G}` | 地动鼹鼠安札格 | Anzrag, the Quake-Mole | 四费 8/4；触发单向清场，战斗中被阻挡可追加战斗阶段 |
| 2 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 7/6 践踏与单向清场；进场发现 5，或 `{2}{R}` 弃掉对生物/鹏洛客造成 3 点 |
| 1 | `{10}{G}{G}`，按场上总力量降费 | 始饥戈厄塔 | Ghalta, Primal Hunger | 12/12 践踏；清场触发与独立战斗终结，仅一张降低传奇和卡手风险 |
| 1 | - | 历祚母圣树 | Boseiju, Who Endures | 绿源；通道处理神器、结界或非基本地 |
| 2 | - | 铜索峡谷 | Copperline Gorge | 前三块地内通常未横置的红绿源；作为第四块地会横置 |
| 4 | - | 岩冠通路 // 丛冠通路 | Cragcrown Pathway // Timbercrown Pathway | 未横置红/绿二选一，落地后颜色锁定 |
| 2 | - | 树林 | Forest | 基础绿源 |
| 4 | - | 卡普路桑森林 | Karplusan Forest | 未横置红绿源；产有色时失去 1 点生命 |
| 2 | - | 不息山脊 | Restless Ridgeline | 横置红绿源；长盘变 4/4，提供不占咒语位的攻击轴 |
| 4 | - | 落石山谷 | Rockfall Vale | 第一或第二块地时通常横置，第三块地起稳定未横置 |
| 1 | - | 逆炉霜剑山 | Sokenzan, Crucible of Defiance | 红源；通道制造两个 1/1 灵俑 |
| 4 | - | 晃动大地 | Stomping Ground | 有基本类别的红绿震地；需要节奏时支付 2 点生命未横置进场 |

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局 |
|---:|---|---|---|---|
| 1 | `{G}` | 挑选毒药 | Pick Your Poison | 让对手牺牲神器、结界或飞行生物之一；针对单一高价值永久物 |
| 2 | `{R}` | 点燃塔楼 | Torch the Tower | 对快攻把主牌一费互动补到四张，并处理死亡触发/坟场价值生物 |
| 2 | `{1}{R}` | 风化侵蚀 | Abrade | 三点生物去除或直接摧毁神器 |
| 2 | `{1}{G}` | 英勇干预 | Heroic Intervention | 全体永久物获得辟邪与不灭，保护解印和生物；不防放逐或反击 |
| 2 | `{2}` | 无牌灵车 | Unlicensed Hearse | 可响应地放逐坟场牌，后期由大生物搭载成为威胁 |
| 2 | `{2}`，起动 `{2}` | 魔石大脑 | The Stone Brain | 定点移除非基本地同名牌，针对 Lotus Field 与单核心组合技 |
| 2 | `{2}{G}{G}` | 顽强巴洛西 | Obstinate Baloth | 4/4 触发生物，进场回 4；对弃牌还可免费进场，但免费进场不会触发解印 |
| 2 | `{3}{G}{G}` | 破诫巨魔图伦 | Thrun, Breaker of Silence | 不可反击的 5/5 践踏控制对策，同时仍触发解印 |

## 核心规则与配合

- 解印检查的是生物咒语在堆叠上的力量；即将进场的指示物和进场后的力量变化不计。`Bristlebane Battler` 因而按 6 力触发，随后才以五个 -1/-1 指示物进场成为 1/1。
- `Slumbering Trudge` 的力量固定为 6；X 只决定费用、晕眩指示物与是否横置。解印在支付完成后看到的仍是 6 力，所以 `X=0`、总费用 `{G}` 时也会造成 4 点。
- 解印触发先于生物咒语结算；即使生物被反击，伤害触发仍会结算。对手必须反击/移除解印或另行处理触发，单纯反击生物不能阻止伤害。
- 7 力以上只触发第二段：对对手、对方每个生物及鹏洛客各造成 4 点，不会再额外触发第一段。`Anzrag`、`Carnosaur` 和 `Ghalta` 共提供六张这种触发。
- `Carnosaur` 的 7 力触发先清场，随后它进场并发现 5；若发现并施放另一张四力以上生物，解印会再次触发。发现到第二张解印则将其放进场，但不会追溯触发已经施放的 Carnosaur。
- `Invasion of Ixalan` 被击败时不是直接在战场上转化：它先被放逐，再以 `Belligerent Regisaur` 一面施放。该背面是 4 力生物咒语，解印会正常触发；若被反击，4 点触发仍已进入堆叠。
- 三回合预备 `Outcaster Trailblazer`，四回合先施放解印，再免费施放预备区的 Trailblazer：先造成 4 点，Trailblazer 进场再加一点法术力；该点绿色可施放 `X=0` 的 Trudge，再造成 4 点。这是本表最干净的四回合 8 点连锁。
- 解印在场后，五点法术力可依次施放 `Trudge(X=0)`、Battler、Tiger-Dillo，共造成 12 点；先让 Trudge 进场，便能满足 Tiger-Dillo 后续攻防所需的另一只四力生物。
- 两张解印会分别触发。重复核心不是完全死牌，但在没有生物手牌时仍会亏节奏，因此只用 Invasion 做软检索，不再加入更多纯引擎。

## 曲线、生存与赢点

- 主牌有 28 张触发生物。按牌面费用计：Trudge×4 为可变一费，常规两费生物 6 张，三费生物 12 张，四费 Anzrag 3 张，六费 Carnosaur 2 张，条件降费 Ghalta 1 张。
- 第一回合可用 Heart's Desire 建立 1/1 阻挡者，或保留 Torch；低 X 的 Trudge 横置进场且带晕眩，不能虚报为即时阻挡。
- 第二回合共有四张 Stomp 与两张 Torch 作为首局互动；Battler 有 ward `{2}` 但初始仅 1/1，Tiger-Dillo 在没有另一只四力生物时也不能阻挡。
- 第三回合的 Bonecrusher、Lovestruck Beast 与 Trailblazer 共 12 张正常四力以上站场，负责在解印落地前阻挡；主牌没有回血，红色快攻对局依靠换入 Baloth。
- 赢点一：解印把 22 张 4-6 力生物变成可指向牌手的 4 点伤害，不依赖攻击穿过阻挡。
- 赢点二：六张 7+ 力生物先清掉对方四防以下场面，再以 Anzrag 追加战斗、Carnosaur 连锁或 Ghalta 践踏结束对局。
- 赢点三：没抽到解印时，Adventure 卡差、Trailblazer 抓牌、大身材 beatdown 与 Restless Ridgeline 生物地仍能正常获胜；这条轴线不依赖四费结界存活。

## 地源与概率

主牌为 24 张真地，无 MDFC 地。红源 21、绿源 23；只有 Sokenzan 不产绿，只有 Forest×2 与 Boseiju 不产红。Cragcrown Pathway 必须在落地时选择颜色，不能把同一张已落地通路同时算作红绿源。

- 七张起手至少两地：`85.73%`；起手 2-5 地：`84.39%`。
- 七张起手至少一个绿源：`97.33%`。
- 先手到第四回合共看 10 张时，至少四地：`63.18%`。该裸算未计 Invasion 顶五找地与调度，因此四费达成率应结合实际留牌改善，但不能把 Invasion 当作地牌卡位。
- 四张解印在七张起手至少一张：`39.95%`；先手到第四回合看 10 张：`52.77%`；后手看 11 张：`56.55%`。
- 若前八张没有解印、手中已有 Invasion 并在第二回合结算，假设四张解印都仍在剩余 52 张牌库中，顶五找到至少一张的条件概率为 `34.12%`。
- 直接生命成本来自 Karplusan Forest×4 与 Stomping Ground×4。面对快攻时不要为无关紧要的双拼主动支付生命；Restless Ridgeline 总是横置，Copperline Gorge 作为第四块地也会横置，安排四回合解印前必须检查落地顺序。

## 留牌与回合节奏

- 默认保留 2-5 地且能在前三回合使用手牌的起手。两地 + Invasion/Adventure + 三费生物通常可留；只有高费终结和解印、没有早期动作时调度。
- 一地手即使有 Heart's Desire 或低 X Trudge 也应调度；这些牌不把地放进手牌，不能解决第二块地缺失。
- 有 `Trailblazer + Unsealing + 四地路径` 时，优先第三回合预备 Trailblazer，不要急着让 4/2 进场换短期节奏。
- 没有解印时，Trudge 通常用 `X=3` 作为四费未横置 6/6；不要无理由以低 X 施放，让它带多个晕眩指示物长期离线。
- 有解印时，优先按“先处理阻挡者，再把后续触发打脸”分配伤害；不要把第一发直伤浪费在即将被 7+ 触发扫掉的四防生物上。
- Ghalta 的降费只看场上己方生物总力量；Battler 进场后的实际力量通常是 1 而不是牌面 6，计算费用时必须使用当前力量。

## 换备简表

| 对局 | 换入 | 换出 |
|---|---|---|
| Izzet / 红色快攻 | Torch×2、Abrade×2、Obstinate Baloth×2 | Ghalta×1、Carnosaur×2、Invasion×2、Battler×1 |
| Badgermole / Company 生物中速 | Torch×2、Abrade×2 | Ghalta×1、Carnosaur×2、Invasion×1 |
| Greasefang / Cat-Oven | Hearse×2、Abrade×2、Torch×2 | Ghalta×1、Carnosaur×2、Invasion×2、Battler×1 |
| 蓝白 / 多色控制 | Heroic Intervention×2、Thrun×2 | Torch×2、Tiger-Dillo×2 |
| Lotus Field / 单核心组合技 | The Stone Brain×2 | Torch×2 |
| 单一神器、结界或飞行终结 | Pick Your Poison×1；神器较多时再加 Abrade×2 | 先换 Ghalta×1；再按速度换最慢的两张 Carnosaur |

以上方案均一换一并保持主牌 60 张。具体环境版本可能改变 Stone Brain 的命名优先级；没有对手牌表或对局日志时，不把静态命名建议伪装成确定答案。

## 可调仓位

- 更稳首局：Tiger-Dillo×2 或 Battler×1-2 可换成额外互动、`Migloz, Maze Crusher` 或 `Bloated Contaminator`。
- 更快核心：另建八妖精版本，而不是在本版零散加入两三张一费产费生物；该方向必须重新计算触发密度和地数。
- 更强长盘：`Kiora, Behemoth Beckoner`、`Garruk's Uprising`、第二张 Ghalta 或第三张 Carnosaur；相应代价是非场面引擎或高费密度上升。
- 更偏清场：`Hulking Raptor` 接 `Tyrranax Rex` / `Etali, Primal Conqueror`，但应作为独立坡道版本测试。

## 验证与运行清单

- 抓取时间：`2026-08-02 00:46 +08:00`；格式 `Pioneer`，平台 `MTGA`，队列 `BO3`，颜色 `ci<=rg`，截止日期 `2026-08-02`。
- 最终主备共 28 个唯一牌名。逐 oracle 遍历截至基准日的全部 Arena 印刷后，28/28 为 Pioneer legal 且至少存在一个 Arena 印刷；Adventure 与 Pathway 按正面导入名、全 oracle 印刷聚合核对。
- 28/28 个唯一牌名均在 mtgch `items[]` 中获得英文名精确匹配的中文名；另行核对 Stomp、Heart's Desire、Belligerent Regisaur 与 Timbercrown Pathway 背面名称。
- Scryfall 核心规则释义确认：解印触发先于生物咒语结算；生物被反击不取消触发；即将进场的指示物不参与力量检查。
- 查询执行中，首个 Scryfall 精确请求因缺少 `Accept` 头返回一次 HTTP 400，修正为 `User-Agent + Accept: application/json` 后全部完成；未出现 429、分页缺失或最终零结果。mtgch 首轮输出命令误用 PowerShell 保留变量，修正后全量精确匹配通过，未将本地脚本错误解释为牌名缺失。
- 尚未完成 Arena 客户端实际导入与 BO3 对局测试。所有对局、换备和强度判断均为规则与结构推演，不是胜率数据。
