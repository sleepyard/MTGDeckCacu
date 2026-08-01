# LandPlant V3（先驱 / 纯绿种地 / MTGA）

按更新后工作流（模式 B）对 V1 重新优化，2026-08-01。主牌 60 / 备牌 15，全部通过三重核对：先驱合法 ✓ / MTGA 有售 ✓ / 中文名 ✓（双面/历险牌已读 `card_faces` 核实正背面；费用字段以 API 实测为准）。

## 阶段 0b 玩法推断（与用户确认）

- **核心思路**：铺地（额外下地、找地进场）→ 地数量缩放生物身材 → beatdown 取胜
- **主轴**：艾莎娅 / 豆茎巨人 / 培护巨像 / 卢玛拉（身材=地数量）；妮莎 / 盖伦碧堡（树林产费放大）；陨蹄斩杀
- **附带轴线**：地变生物（幼兽 earthbend、突发后果分形、多头蛇蜥巢穴、妮莎+1）；MDFC 地（花晶石）
- **明确不走**：landfall 触发流（眼镜蛇/比利/虫群为地落触发回报，与身材缩放是两类牌，本版不采用）

## 导入格式（MTGA / MTGO 兼容）

```
4 Ashaya, Soul of the Wild
3 Azusa, Lost but Seeking
4 Badgermole Cub
3 Beanstalk Giant
2 Boseiju, Who Endures
2 Bushwhack
2 Castle Garenbrig
1 Craterhoof Behemoth
3 Cultivator Colossus
2 Dryad of the Ilysian Grove
4 Emergent Sequence
17 Forest
2 Lair of the Hydra
2 Lumra, Bellow of the Woods
3 Nissa, Who Shakes the World
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
| 4 | {1}{G} | 獾地鼠幼兽 | Badgermole Cub | 引擎：earthbend 地变生物；生物产费+G |
| 4 | {1}{G} | 突发后果 | Emergent Sequence | 引擎：找地变分形，标记=当回合进场地数 |
| 2 | {1}{G} | 杂生花晶石 | Tangled Florahedron | MDFC：产费人/地 |
| 3 | {2}{G} | 云游者梓纱 | Azusa, Lost but Seeking | 引擎：每回合额外下地×2（待复核，见备注） |
| 2 | {2}{G} | 依吕夏林地树灵 | Dryad of the Ilysian Grove | 引擎：额外下地+调色（待复核，见备注） |
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

地当量：真地 23 + MDFC×0.75 ≈ 24.5；另有找地引擎 11 张（突发后果4/跺地兽4/豆茎历险3）与额外下地 5 张（梓纱3/树灵2）。

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

## 改动对照 diff（V1 → V3）

**砍出：**
- Studious First-Year×4：机制为 {G} 1/1 进场带"预备"，其 Rampant Growth 副本可在**之后任意回合**施放（如1费先进场站场、5费有空档时再铺地）——时间灵活性本身合格；但同为低费铺地，突发后果（白送分形身材）与花晶石（产费/地双功能）在本套牌优先级更高，移入可调仓位而非彻底否定
- Flourishing Bloom-Kin×3：正面 {1}{G} 2费可下、身材=树林数（契合主轴），伪装 {4}{G} 翻面找2树林是可选的铺地模式；2费线本轮竞争（幼兽/突发后果/花晶石）更契合铺地引擎定位，移入可调仓位待实测
- Fabled Passage×2：服务地落触发，主轴用不上
- 备牌 Khalni Ambush / Bala Ged Recovery / Naturalize：母圣树主牌已覆盖解场

**加入：**
- 云游者梓纱×3、依吕夏林地树灵×2："额外下地"引擎（梓纱经 PIO 核实先驱合法且 Arena 可用）。⚠️ 人工研判指出二者为"手牌下地"引擎，与本套牌"牌库找地"资源流不匹配且套牌零抓牌，提升有限——标记待复核，V4 拟移除
- 林间嚎吼卢玛拉×2：身材=地数+坟场地全回收，铺地轴的完美终结
- 远古育碧灵、卡赞度长毛象：坟场地/MDFC 地卡位
- 备牌：变幻犄角龙×2、英勇干预×1

**数量调整：**
- 艾莎娅 3→4（主轴核心拉满）、培护巨像 0→3、豆茎巨人 4→3（保留，已确认历险面 {2}{G} 找地进场的价值）、野林开路 3→2、树林 18→17、卢玛拉 0→2、多头蛇蜥巢穴 1→2

**考虑过但排除：**
- 莲花眼镜蛇/锐刺比利/硬盔虫聚群：地落触发回报，偏离主轴（V2 的跑偏点）
- Multani（+1/+1/地含坟场，践踏）：与培护巨像同费竞争落败，列可调仓位
- Harmonious Grovestrider（身材=地数，辟邪2）：5费线已拥挤，列可调仓位
- Tatyova（绿蓝）、Phylath（红绿）：违反纯绿颜色约束

## 打法要点（回合节奏已过费用校验）

- 1回合：下地空过（无1费生物曲线，野林开路留作互动）
- 2回合：幼兽 / 突发后果 / 花晶石（均为 {1}{G}）
- 3回合：跺地兽 / 梓纱·树灵（待复核）/ 豆茎历险面（3费）
- 4回合：加速后出艾莎娅或妮莎（5费）；妮莎+1 地变 3/3 即开始抢血
- 5-6回合：卢玛拉（6费）/ 培护巨像（7费，妮莎翻倍或盖伦碧堡后可达）压场，陨蹄斩杀
- 艾莎娅在场时所有非衍生物是树林：点地产费（配合幼兽再+G），妮莎翻倍全场
- 弱点：地变生物吃扫场，对控制留英勇干预/蛇皮帘幕；坟场依赖局换入荒骨咒土

## 可调仓位

Studious First-Year、Flourishing Bloom-Kin、野林开路×2、豆茎巨人×3、卢玛拉×2、树灵×2 ↔ Multani、Harmonious Grovestrider、银背长老、Spelunking、卡赞度长毛象
