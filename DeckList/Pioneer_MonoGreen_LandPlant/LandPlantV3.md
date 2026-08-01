# LandPlant V3（先驱 / 纯绿种地 / MTGA）

按更新后工作流（模式 B）对 V1 重新优化，2026-08-01。主牌 60 / 备牌 15，全部通过三重核对：先驱合法 ✓ / MTGA 有售 ✓ / 中文名 ✓（双面/历险牌已读 `card_faces` 核实正背面）。

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

## 主牌对照表（分功能）

| 数量 | 中文名 | English | 角色 |
|---|---|---|---|
| 4 | 荒野之魂艾莎娅 | Ashaya, Soul of the Wild | 核心回报：身材=地数；生物变树林产费 |
| 3 | 豆茎巨人 | Beanstalk Giant | 回报：身材=地数；历险面=3费找地进场 |
| 3 | 培护巨像 | Cultivator Colossus | 终结：身材=地数带践踏，进场连放地+补牌 |
| 2 | 林间嚎吼卢玛拉 | Lumra, Bellow of the Woods | 回报：身材=地数，进场磨4回收全部坟场地 |
| 1 | 陨蹄贝西摩斯 | Craterhoof Behemoth | 斩杀 |
| 4 | 獾地鼠幼兽 | Badgermole Cub | 引擎：earthbend 地变生物；生物产费+G |
| 4 | 突发后果 | Emergent Sequence | 引擎：找地变分形，标记=当回合进场地数 |
| 4 | 绿雕跺地兽 | Topiary Stomper | 引擎：找地；7地解锁 4/4 警戒 |
| 3 | 云游者梓纱 | Azusa, Lost but Seeking | 引擎：每回合额外下地×2 |
| 2 | 依吕夏林地树灵 | Dryad of the Ilysian Grove | 引擎：额外下地+调色 |
| 3 | 撼世妮莎 | Nissa, Who Shakes the World | 放大器：树林产费翻倍；+1 地变 3/3 |
| 2 | 野林开路 | Bushwhack | 互动：1费互斗/找地 |
| 2 | 杂生花晶石 | Tangled Florahedron | MDFC：1费产费人/地 |
| 17 | 树林 | Forest | |
| 2 | 历祚母圣树 | Boseiju, Who Endures | 通道地、解结界神器 |
| 2 | 盖伦碧堡 | Castle Garenbrig | 大法术力地 |
| 2 | 多头蛇蜥巢穴 | Lair of the Hydra | 生物地 |

地当量：真地 23 + MDFC×0.75 ≈ 24.5；另有找地引擎 11 张（突发后果4/跺地兽4/豆茎历险3）与额外下地 5 张（梓纱3/树灵2）。

## 备牌对照表

| 数量 | 中文名 | English | 对局 |
|---|---|---|---|
| 2 | 荒骨咒土 | Scavenger Grounds | 坟场针对（地卡位免费） |
| 2 | 杀戮暴霸龙 | Carnage Tyrant | 对控制 |
| 2 | 变幻犄角龙 | Shifting Ceratops | 对蓝色/多色 |
| 1 | 英勇干预 | Heroic Intervention | 防扫场 |
| 2 | 蛇皮帘幕 | Snakeskin Veil | 防点杀 |
| 2 | 轰然撞倒 | Ram Through | 大身材互斗穿脸（契合主轴） |
| 1 | 霸蛛暴龙 | Tyrranax Rex | 对控制/中速 |
| 1 | 召唤：泰坦 | Summon: Titan | 长盘：回收坟场地、按地数膨大带践踏 |
| 1 | 远古育碧灵 | Ancient Greenwarden | 长盘：坟场地可直接下地 |
| 1 | 卡赞度长毛象 | Kazandu Mammoth | MDFC 地/打手，长盘补充地卡位 |

## 改动对照 diff（V1 → V3）

**砍出：**
- Studious First-Year×4：正面仅 1/1，对 beatdown 无压力；加速位已被更优牌占满（已读 card_faces 确认其背面为 Rampant Growth）
- Flourishing Bloom-Kin×3：5费伪装节奏太慢，回报被卢玛拉/培护巨像上位替代
- Fabled Passage×2：服务地落触发，主轴用不上
- 备牌 Khalni Ambush / Bala Ged Recovery / Naturalize / Summon: Titan×1→保留1：母圣树主牌已覆盖解场

**加入：**
- 云游者梓纱×3、依吕夏林地树灵×2：主轴最缺的"额外下地"引擎（梓纱经 PIO 核实先驱合法且 Arena 可用）
- 林间嚎吼卢玛拉×2：身材=地数+坟场地全回收，铺地轴的完美终结
- 依吕夏林地树灵、远古育碧灵、卡赞度长毛象：坟场地/MDFC 地卡位
- 备牌：变幻犄角龙×2、英勇干预×1

**数量调整：**
- 艾莎娅 3→4（主轴核心拉满）、培护巨像 0→3、豆茎巨人 4→3（保留，已确认历险面价值）、野林开路 3→2、树林 18→17、卢玛拉 0→2、多头蛇蜥巢穴 1→2

**考虑过但排除：**
- 莲花眼镜蛇/锐刺比利/硬盔虫聚群：地落触发回报，偏离主轴（V2 的跑偏点）
- Multani（+1/+1/地含坟场，践踏）：与培护巨像同费竞争落败，列可调仓位
- Harmonious Grovestrider（身材=地数，辟邪2）：5费线已拥挤，列可调仓位
- Tatyova（绿蓝）、Phylath（红绿）：违反纯绿颜色约束

## 打法要点（回合节奏已过费用校验）

- 1回合：下地空过，或杂生花晶石（唯一1费动作）
- 2回合：幼兽 / 突发后果（{1}{G}）
- 3回合：跺地兽 / 梓纱 / 树灵 / 豆茎历险面（3费）
- 4回合：加速后出艾莎娅或妮莎（5费）；妮莎+1 地变 3/3 即开始抢血
- 5-6回合：卢玛拉（6费）/ 培护巨像（7费，妮莎翻倍或盖伦碧堡后可达）压场，陨蹄斩杀
- 艾莎娅在场时所有非衍生物是树林：点地产费（配合幼兽再+G），妮莎翻倍全场
- 弱点：地变生物吃扫场，对控制留英勇干预/蛇皮帘幕；坟场依赖局换入荒骨咒土

## 可调仓位

Bushwhack×2、豆茎巨人×3、卢玛拉×2、树灵×2 ↔ Multani、Harmonious Grovestrider、银背长老、Spelunking、卡赞度长毛象
