# SlimeSimicV1 — Explorer 蓝绿反人淤泥（BO3 / MTGA）

> 模式 C 主题种子补全：种子锚点 = **反人淤泥 Slime Against Humanity**（{2}{G}，张数不限），中量 14 张。
> 主轴：绿色自磨 + **蓝色的廉价堆坟与反击保护**。流浆王斯罗咕是传奇流浆（计 X），地牌进坟给它加豆，与自磨轴同向；备牌反击咒针对控制与大法术。

## 牌表（MTGA 导入格式）

见同目录 `SlimeSimicV1.txt`（主 60 + 备 15）。

## 分功能牌表（费用为 Scryfall API 实测）

| 数量 | 费用 | 中文名 | English | 定位 |
|---|---|---|---|---|
| 4 | {U} | 异界凝视 | Otherworldly Gaze | 引擎：1 费瞬发占卜 3 任意入坟，精堆 |
| 2 | {G} | 坚固鳞甲 | Hardened Scales | 放大：淤泥豆数 +1 |
| 4 | {1}{G} | 贪婪备储 | Cache Grab | 引擎：瞬发磨 4 捡永久物 |
| 3 | {1}{G} | 事后分析师 | Aftermath Analyst | 引擎/生物：ETB 磨 3，牺牲回收地 |
| 4 | {1}{G} | 腐食流浆 | Scavenging Ooze | 流浆/生存 |
| 2 | {1}{G} | 轰然撞倒 | Ram Through | 互动：践踏溢出穿脸 |
| 14 | {2}{G} | 反人淤泥 | Slime Against Humanity | **种子核心** |
| 3 | {1}{G}{U} | 流浆王斯罗咕 | Slogurk, the Overslime | 传奇流浆：计 X；地进坟加豆；死亡回收地 |
| 1 | {2}{G} | 贾路的反抗 | Garruk's Uprising | 放大：全场践踏+大兽进场抓牌 |
| 4 | 地 | 滋生之池 | Breeding Pool | 双色地 |
| 4 | 地 | 内陆港湾 | Hinterland Harbor | 双色地 |
| 3 | 地 | 植物圣所 | Botanical Sanctum | 双色快地 |
| 2 | 地 | 树渠通路 | Barkchannel Pathway | MDFC 双色地 |
| 2 | 地 | 幻根瀑布 | Dreamroot Cascade | 双色慢地 |
| 2 | 地 | 圣府首都伊甸 | Eden, Seat of the Sanctum | 功能地：磨 2/牺牲回收 |
| 1 | 地 | 历祚母圣树 | Boseiju, Who Endures | 功能地：通道拆神器/结界 |
| 5 | 地 | 树林 | Forest | 基本地 |

曲线：MV1×6 / MV2×13 / MV3×18；地 23。色源：绿 23 / 蓝 15。
法术力校验（超几何）：T1 有蓝源 88.2%（Gaze 非必须 T1）；T3 蓝绿齐（斯罗咕）94.0%。

## 核心配合

- **斯罗咕 + 自磨**：磨牌把地送进坟 → 斯罗咕加豆；它本身计 X，死亡还回收被磨的地——磨得越多越大。
- **异界凝视精堆**：1 费瞬发看 3 任意入坟，主动把淤泥/流浆放进坟，而不是赌随机磨。
- **贾路的反抗**：4 攻斯罗咕或 5/5 淤泥进场抓牌，全场践踏让所有生物变穿透。

## 生存预算与留牌

- 生存件：Scooze×4、Analyst×3、Ram Through×2；无黑色点杀，前 3 回合防御弱于黑绿版，靠备牌反击与疗疾灵补。
- 留牌：2+ 地含 1 绿即可（全地皆产绿）；有 Gaze/Cache Grab + 任意生物 = 标准起手；留 1 蓝源再留斯罗咕。

## 两个独立赢点

1. 反人淤泥践踏 beatdown。
2. 斯罗咕（吃地进坟滚雪球）+ 腐食流浆生物 beatdown。

## 换备简表

| 对手 | 换入 | 换出 |
|---|---|---|
| 控制/大法术 | 3 Negate、2 Disdainful Stroke、2 Mystical Dispute | 2 Ram Through、2 Scales、2 Cache Grab、1 Uprising |
| 快攻 | 2 Healer of the Glade、2 Heroic Intervention | 3 Negate 位未入主时换 2 Gaze、2 Scales |
| 坟场针对 | 2 Haywire Mite、2 Natural State、2 Heroic Intervention | 2 Eden、2 Gaze、2 Cache Grab |

## 可调仓位

Garruk's Uprising×1、Hardened Scales×2、Ram Through×2、Slogurk 第 3 张。可换入候选：Grapple with the Past、Satyr Wayfinder、Bala Ged Recovery（回收淤泥）、Toski（不灭抓牌）、Blossoming Tortoise（若加绿源密度）。

## 考虑过但排除

- Sludge Monster（泥泞怪物）：牌面是 Horror **不是流浆**，不喂 X，剔除（易误判点）。
- 纯蓝磨牌（如 Thought Scour 类不在牌池）：Explorer 蓝绿自磨以 Gaze 为最优。
- Uro：先驱禁牌。

## 运行清单

- 基准日 2026-08-15；Explorer 代理口径、数据源、枚举规模同 MonoGreen V1。
- 门禁：`validate --format pioneer --bo3 --colors gu` PASS（淤泥 14 张走牌面豁免）。
- 实测：Forge AI 模拟结果见文末（样本来源：Forge AI）。

## 实测记录

Forge 2.0.13 AI vs AI，每组 20 局，共 13 组 260 局（样本来源：Forge AI 模拟，可信度低于真人对局；Forge AI 对坟场协同利用率偏低、操控控制套偏弱，胜率仅作定性参考）。报告均在 `SimResult/20260815_*`。

| 对手（环境/类型） | 胜-负 | 胜率 |
|---|---|---|
| SarkhansUnsealingV4（先驱中速） | 9-11 | 45% |
| SimicFlashV1（先驱节奏） | 7-13 | 35% |
| UWControlMeta（先驱控制） | 6-14 | 30% |
| DimirYorionMeta（先驱中速/控制，缺行侣资源） | 8-12 | 40% |
| URAggroMeta（先驱快攻） | 12-8 | 60% |
| GolgariAggroMeta（先驱快攻） | 9-11 | 45% ⚠2 局时钟判胜 |
| RDWMeta（先驱快攻） | 9-11 | 45% |
| TheRockMeta（先驱中速） | 5-15 | 25% |
| IzzetProwessMeta（标准快攻） | 8-12 | 40% |
| IzzetSpellementalsMeta（标准法术） | 6-14 | 30% |
| MonoGreenLandfallMeta（标准地落） | 5-15 | 25% |
| OrzhovAggroMeta（标准快攻） | 8-12 | 40% |
| FullColorControlMeta（标准控制） | 9-11 | 45% |

- 合计 91-169，约 35%（三版最低）。
- 无牌面未实现/加载失败。
- 定性：**Slogurk 轴未见收益，全面偏差**。没有对局显著优于另外两版，对节奏/地落等速度型对手跟不上，斯罗咕 3 费出场在快环境拖速。蓝色的备牌反击维度未能在主牌局中体现价值。
- 迭代方向：若保留蓝绿轴，需减斯罗咕加低费互动（或改 Gaze 为更多 Cache Grab/一费防御）；否则建议以 Golgari 版为主力、本版降级为备选。
