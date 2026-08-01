# LandPlant V4（先驱 / 纯绿种地 / MTGA）

模式 B 迭代，2026-08-01。相对 V3：移除"手牌下地"引擎（人工研判+引擎-资源匹配校验），低费位按逐面评估重排。主牌 60 / 备牌 15，全部通过三重核对：先驱合法 ✓ / MTGA 有售 ✓ / 中文名 ✓；费用字段以 API 实测为准。

## 玩法推断（沿用已确认结论）

- **主轴**：铺地（牌库找地进场）→ 地数量缩放生物身材 → beatdown；妮莎/盖伦碧堡放大；陨蹄斩杀
- **附带轴线**：地变生物（幼兽 earthbend、突发后果分形、多头蛇蜥巢穴、妮莎+1）；MDFC 地
- **资源流校验**：本套牌铺地全部来自**牌库**（突发后果/跺地兽/茁壮脚步/徒长副本），零抓牌——故只保留"牌库找地"类引擎，不用"手牌下地"类

## 导入格式（MTGA / MTGO 兼容）

```
4 Ashaya, Soul of the Wild
4 Badgermole Cub
3 Beanstalk Giant
2 Boseiju, Who Endures
2 Bushwhack
2 Castle Garenbrig
1 Craterhoof Behemoth
3 Cultivator Colossus
4 Emergent Sequence
17 Forest
3 Flourishing Bloom-Kin
2 Lair of the Hydra
2 Lumra, Bellow of the Woods
3 Nissa, Who Shakes the World
2 Studious First-Year
2 Tangled Florahedron
4 Topiary Stomper

Sideboard
1 Ancient Greenwarden
2 Carnage Tyrant
1 Heroic Intervention
1 Kazandu Mammoth
2 Ram Through
2 Scavenger Grounds
2 Shifting Ceratops
2 Snakeskin Veil
1 Summon: Titan
1 Tyrranax Rex
```

## 主牌对照表（按费用升序）

| 数量 | 费用 | 中文名 | English | 角色 |
|---|---|---|---|---|
| 2 | {G} | 野林开路 | Bushwhack | 互动：互斗/找地 |
| 2 | {G} | 好学新生 | Studious First-Year | 1费1/1站场；预备"徒长"({1}{G}找地)可留到后续任意回合施放 |
| 4 | {1}{G} | 獾地鼠幼兽 | Badgermole Cub | 引擎：earthbend 地变生物；生物产费+G |
| 4 | {1}{G} | 突发后果 | Emergent Sequence | 引擎：找地变分形，标记=当回合进场地数 |
| 3 | {1}{G} | 繁盛花亲 | Flourishing Bloom-Kin | 回报：身材=树林数；伪装{4}{G}翻面找2树林为可选铺地模式 |
| 2 | {1}{G} | 杂生花晶石 | Tangled Florahedron | MDFC：产费人/地 |
| 4 | {1}{G}{G} | 绿雕跺地兽 | Topiary Stomper | 引擎：找地；7地解锁 4/4 警戒 |
| 4 | {3}{G}{G} | 荒野之魂艾莎娅 | Ashaya, Soul of the Wild | 核心回报：身材=地数；生物变树林产费 |
| 3 | {3}{G}{G} | 撼世妮莎 | Nissa, Who Shakes the World | 放大器：树林产费翻倍；+1 地变 3/3 |
| 2 | {4}{G}{G} | 林间嚎吼卢玛拉 | Lumra, Bellow of the Woods | 回报：身材=地数，进场磨4回收全部坟场地 |
| 3 | {6}{G} | 豆茎巨人 | Beanstalk Giant | 回报：身材=地数；历险面 {2}{G} 找地进场 |
| 3 | {4}{G}{G}{G} | 培护巨像 | Cultivator Colossus | 终结：身材=地数带践踏，进场连放地+补牌 |
| 1 | {5}{G}{G}{G} | 陨蹄贝西摩斯 | Craterhoof Behemoth | 斩杀 |
| 17 | — | 树林 | Forest | |
| 2 | — | 历祚母圣树 | Boseiju, Who Endures | 通道地、解结界神器 |
| 2 | — | 盖伦碧堡 | Castle Garenbrig | 大法术力地 |
| 2 | — | 多头蛇蜥巢穴 | Lair of the Hydra | 生物地 |

地当量：真地 23 + MDFC×0.75 ≈ 24.5；牌库找地引擎 13 张（突发后果4/跺地兽4/茁壮脚步3/徒长副本2）。

## 备牌对照表（按费用升序）

| 数量 | 费用 | 中文名 | English | 对局 |
|---|---|---|---|---|
| 2 | {G} | 蛇皮帘幕 | Snakeskin Veil | 防点杀 |
| 2 | {1}{G} | 轰然撞倒 | Ram Through | 大身材互斗穿脸（契合主轴） |
| 1 | {1}{G} | 英勇干预 | Heroic Intervention | 防扫场 |
| 1 | {1}{G}{G} | 卡赞度长毛象 | Kazandu Mammoth | MDFC 地/打手，长盘补充地卡位 |
| 2 | {2}{G}{G} | 变幻犄角龙 | Shifting Ceratops | 对蓝色/多色 |
| 1 | {3}{G}{G} | 召唤：泰坦 | Summon: Titan | 长盘：回收坟场地、按地数膨大带践踏 |
| 1 | {4}{G}{G} | 远古育碧灵 | Ancient Greenwarden | 长盘：坟场地可直接下地 |
| 2 | {4}{G}{G} | 杀戮暴霸龙 | Carnage Tyrant | 对控制 |
| 1 | {4}{G}{G}{G} | 霸蛛暴龙 | Tyrranax Rex | 对控制/中速 |
| 2 | — | 荒骨咒土 | Scavenger Grounds | 坟场针对（地卡位免费） |

## 改动对照 diff（V3 → V4）

**砍出：**
- 云游者梓纱×3、依吕夏林地树灵×2："手牌下地"引擎，与套牌"牌库找地"资源流不匹配；套牌零抓牌导致异能空转，3费 1/2、2/3 身材对 beatdown 为负节奏（人工研判确认）

**加入：**
- 繁盛花亲×3：2费身材=树林数的主轴回报回归（V3 误判其伪装费用 {4}{G} 为全牌费用，已按砍牌门禁纠正）；伪装模式是可选的铺地引擎
- 好学新生×2：套牌唯一 1 费生物曲线；预备的"徒长"副本时间灵活，可 1 费先进场、3-5 费有空档时再铺地

**数量调整：** 无其他变动（备牌沿用 V3）。

**考虑过但排除：**
- 繁盛花亲第 4 张：2 费线已有幼兽/突发后果占满前期回合，花亲的最佳落地时点在中期，3 张足够，第 4 张列可调仓位
- 卡赞度长毛象进主：地当量已够，长盘对局再从备牌调入

## 打法要点（回合节奏已过费用校验）

- 1回合：下地空过 / 好学新生（唯一 1 费生物）
- 2回合：幼兽 / 突发后果 / 花晶石；繁盛花亲此时约 2/2~3/3，不急于下
- 3回合：跺地兽 / 豆茎历险面 / 好学新生的"徒长"副本
- 4回合：加速后出艾莎娅或妮莎（5费）；妮莎+1 地变 3/3 开始抢血
- 5-6回合：卢玛拉（6费）/ 培护巨像（7费）压场；此时繁盛花亲已是 2 费 6/6+，艾莎娅在场时进一步膨胀（所有生物都是树林）；陨蹄斩杀
- 艾莎娅在场时所有非衍生物是树林：点地产费（配合幼兽再+G），妮莎翻倍全场
- 弱点：地变生物吃扫场，对控制留英勇干预/蛇皮帘幕；坟场依赖局换入荒骨咒土

## 可调仓位

繁盛花亲第4张、好学新生第3张、野林开路×2、卢玛拉×2 ↔ Multani、Harmonious Grovestrider、银背长老、Spelunking、卡赞度长毛象
