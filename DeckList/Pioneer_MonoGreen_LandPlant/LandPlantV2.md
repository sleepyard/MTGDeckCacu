# LandPlant V2（先驱 / 纯绿种地 / MTGA）

基于 V1 按工作流优化（2026-08-01，最新系列 MSH；禁牌表核对 31 张，主题相关：Field of the Dead、Leyline of Abundance、Once Upon a Time、Veil of Summer 均不可用）。
主牌 60 / 备牌 15，全部通过三重核对：先驱合法 ✓ / MTGA 有售 ✓ / 中文名 ✓。

## 导入格式（MTGA / MTGO 兼容）

```
3 Ashaya, Soul of the Wild
3 Azusa, Lost but Seeking
4 Badgermole Cub
2 Boseiju, Who Endures
3 Bristly Bill, Spine Sower
2 Bushwhack
2 Castle Garenbrig
2 Cavalier of Thorns
1 Craterhoof Behemoth
2 Cultivator Colossus
4 Emergent Sequence
1 Fabled Passage
17 Forest
2 Lair of the Hydra
4 Lotus Cobra
3 Nissa, Who Shakes the World
2 Tangled Florahedron
3 Topiary Stomper

Sideboard
1 Ancient Greenwarden
2 Carnage Tyrant
1 Heroic Intervention
2 Ram Through
2 Scavenger Grounds
2 Scute Swarm
2 Shifting Ceratops
2 Snakeskin Veil
1 Tyrranax Rex
```

## 主牌对照表（分功能）

| 数量 | 中文名 | English | 定位 |
|---|---|---|---|
| 4 | 莲花眼镜蛇 | Lotus Cobra | 地落产费引擎（新） |
| 4 | 獾地鼠幼兽 | Badgermole Cub | 地变生物+产费放大（保留） |
| 3 | 锐刺播种师尖棘比利 | Bristly Bill, Spine Sower | 地落+1/+1、翻倍终结（新） |
| 3 | 云游者梓纱 | Azusa, Lost but Seeking | 额外下地×2，PIO 已上 Arena（新） |
| 3 | 绿雕跺地兽 | Topiary Stomper | 找地+4/4（4→3） |
| 3 | 荒野之魂艾莎娅 | Ashaya, Soul of the Wild | 核心回报，生物变树林产费 |
| 3 | 撼世妮莎 | Nissa, Who Shakes the World | 树林产费翻倍（保留） |
| 2 | 荆棘骁骑 | Cavalier of Thorns | 5费延展+放地+回收（新） |
| 2 | 培护巨像 | Cultivator Colossus | 倾泻手牌地、补牌的终结（新） |
| 1 | 陨蹄贝西摩斯 | Craterhoof Behemoth | 斩杀（保留） |
| 4 | 突发后果 | Emergent Sequence | 找地变分形生物（保留） |
| 2 | 野林开路 | Bushwhack | 互斗（3→2） |
| 2 | 杂生花晶石 | Tangled Florahedron | MDFC 地/加速（保留） |
| 17 | 树林 | Forest | |
| 2 | 历祚母圣树 | Boseiju, Who Endures | 通道地、解结界神器 |
| 2 | 盖伦碧堡 | Castle Garenbrig | 大法术力地 |
| 2 | 多头蛇蜥巢穴 | Lair of the Hydra | 生物地（1→2） |
| 1 | 神奇小径 | Fabled Passage | 触发生地落（2→1） |

地当量：24 真地 + 2 MDFC×0.75 ≈ 25.5，另有突发后果×4 / 跺地兽×3 / 梓纱引擎。

## 备牌对照表

| 数量 | 中文名 | English | 对局 |
|---|---|---|---|
| 2 | 荒骨咒土 | Scavenger Grounds | 坟场针对（保留） |
| 2 | 杀戮暴霸龙 | Carnage Tyrant | 对控制（保留） |
| 2 | 变幻犄角龙 | Shifting Ceratops | 对蓝色/多色套牌（新） |
| 1 | 英勇干预 | Heroic Intervention | 防扫场（新） |
| 2 | 硬盔虫聚群 | Scute Swarm | 长盘备选调（新） |
| 1 | 远古育碧灵 | Ancient Greenwarden | 长盘/坟场地回收（新） |
| 2 | 轰然撞倒 | Ram Through | 额外互斗（3→2） |
| 2 | 蛇皮帘幕 | Snakeskin Veil | 保护（保留） |
| 1 | 霸蛛暴龙 | Tyrranax Rex | 对控制/中速（保留） |

## 相对 V1 的主要改动与理由

- 砍：Beanstalk Giant×4（7费太笨重，被培护巨像/荆棘骁骑上位替代）、Flourishing Bloom-Kin×3、Studious First-Year×4（2费 1/1 太弱，加速位被眼镜蛇/梓纱占据）、Summon: Titan、Khalni Ambush、Bala Ged Recovery、Naturalize（母圣树主牌已覆盖）。
- 加：莲花眼镜蛇、梓纱、比利三张引擎/回报是 V1 最大的强度缺口；荆棘骁骑补卡差与延展；培护巨像给"手里一把地"一个出口。
- 注意：Tatyova（绿蓝）、Phylath（红绿）符合主题但违反纯绿约束，列为排除项。

## 打法要点

- 主轴（校正后）：铺地 → 地数量缩放生物身材（艾莎娅/培护巨像）→ beatdown 取胜；地落牌（眼镜蛇/比利/虫群）是加速与放大手段，不是主轴本身。若要更纯粹回归主轴，可把比利/虫群换成身材缩放类牌（如 Lumra、豆茎巨人）。
- 经典节奏（费用校验后）：1回合下地空过（本套牌无1费曲线，眼镜蛇/幼兽均为2费）→ 2回合眼镜蛇/幼兽/突发后果 → 3回合梓纱连下地或妮莎 → 4回合起艾莎娅/荆棘骁骑落地，树林产费翻倍爆发。
- 艾莎娅进场后所有非衍生物都是树林：点地即产费（配合幼兽再+1G），妮莎翻倍全场；生物铺开后陨蹄贝西摩斯是天然斩杀。
- 母圣树的通道、城堡的启动费都算"生物"线索下的收益点；注意地变生物吃扫场，对控制留英勇干预/帘幕。
