# SlimeGolgariV1 — Explorer 黑绿反人淤泥（BO3 / MTGA）

> 模式 C 主题种子补全：种子锚点 = **反人淤泥 Slime Against Humanity**（{2}{G}，放逐区+坟场中流浆/同名牌数 +2 个豆，张数不限），中量 14 张。
> 主轴：**黑色自磨效率（拼接师备尸/骇人回收）快速堆坟 → 大淤泥践踏 beatdown**，并用黑色互动补上纯绿版最缺的点杀与弃牌。

## 牌表（MTGA 导入格式）

见同目录 `SlimeGolgariV1.txt`（主 60 + 备 15）。

## 分功能牌表（费用为 Scryfall API 实测）

| 数量 | 费用 | 中文名 | English | 定位 |
|---|---|---|---|---|
| 4 | {B} | 拼接师备尸 | Stitcher's Supplier | 引擎：进场+死亡各磨 3，单卡磨 6 |
| 3 | {B} | 送终一击 | Fatal Push | 互动：1 费点杀，反抗扩到 MV4 |
| 4 | {1}{B} | 泥沼屈东 | Mire Triton | 引擎/生存：死触阻挡，ETB 磨 2 回 2 血 |
| 4 | {1}{G} | 腐食流浆 | Scavenging Ooze | 流浆/生存：本体计 X，吃坟长豆回血 |
| 4 | {B}{G} | 骇人回收 | Grisly Salvage | 引擎：瞬发翻 5 拿生物/地其余进坟 |
| 2 | {1}{G} | 纠结过往 | Grapple with the Past | 引擎：磨 3 兼回收生物/地 |
| 2 | {G} | 坚固鳞甲 | Hardened Scales | 放大：淤泥豆数 +1 |
| 1 | {B}{G} | 杀手留念 | Assassin's Trophy | 互动：万能去除，兼拆坟场针对 |
| 14 | {2}{G} | 反人淤泥 | Slime Against Humanity | **种子核心** |
| 4 | 地 | 蔓生墓园 | Overgrown Tomb | 双色地 |
| 4 | 地 | 花开沼地 | Blooming Marsh | 双色快地 |
| 3 | 地 | 罗堰荒野 | Llanowar Wastes | 双色痛地 |
| 2 | 地 | 黯隧通路 | Darkbore Pathway | MDFC 双色地 |
| 2 | 地 | 荒泽竹沼 | Takenuma, Abandoned Mire | 功能地：传讯磨 3+回收生物，弃牌出口 |
| 1 | 地 | 历祚母圣树 | Boseiju, Who Endures | 功能地：通道拆神器/结界 |
| 5 | 地 | 树林 | Forest | 基本地 |
| 2 | 地 | 沼泽 | Swamp | 基本地 |

曲线：MV1×7 / MV2×16 / MV3×14；地 23。色源：绿 19 / 黑 17（痛地 3 张，预计失血 1–3 点/局）。
法术力校验（超几何）：T1 有黑源 91.7%、有绿源 94.2%；T2 双色齐（骇人回收）92.1%，T3 双色齐 94.7%。

## 核心配合

- **备尸+骇人回收**一回合可把 6–11 张牌送进坟，T3 淤泥常见 X=5–7。
- **Takenuma 传讯**：不弃淤泥亏牌——弃多余淤泥进坟等于给后续所有淤泥 +1，还能顺带回收备尸再磨 6。
- **Scooze 吃自己坟里的淤泥/流浆**：挪到放逐区 X 照计，白赚豆与回血。

## 生存预算与留牌

- 生存件：Fatal Push×3、Mire Triton×3（死触）、Supplier×4（两个 1/1 挡拆）、Scooze×4、回血（Triton/Scooze）。对快攻显著优于纯绿版。
- 留牌：2+ 地且绿黑双全（起手双色齐约 86%）；优先留 Supplier/Triton/Scooze 的一二费曲线；淤泥 1 张即可（T3 前见淤泥 94.6%）。

## 两个独立赢点

1. 反人淤泥践踏 beatdown。
2. 备尸/泥沼屈东/腐食流浆的低费生物群 + 黑绿中速 value（不依赖大 token，抗 Stone Brain）。

## 换备简表

| 对手 | 换入 | 换出 |
|---|---|---|
| 快攻 | 2 Obstinate Baloth、1 The Meathook Massacre、2 Natural State | 2 Hardened Scales、2 Grapple、1 Trophy |
| 控制/组合技 | 3 Thoughtseize、2 Duress、2 Abrupt Decay | 3 Fatal Push、2 Scales、2 引擎 |
| 坟场针对 | 2 Haywire Mite、2 Natural State、2 Abrupt Decay | 2 Grapple、2 Supplier、2 Cache…（按对手针对件类型：RIP 用地脉类拆，灵车用 Natural State） |
| 镜像/坟场内战 | 2 Haywire Mite、1 Meathook | 2 Grapple、1 Trophy |

## 可调仓位

Grapple with the Past×2、Hardened Scales×2、Assassin's Trophy×1、Mire Triton 第 3 张。可换入候选：Undead Butler（磨 3+放逐回收）、Glowspore Shaman、Skull Prophet（产费+磨）、Go for the Throat / Heartless Act（更多点杀）、Crawling Infestation（持续磨+虫 token）。

## 考虑过但排除

- Old Stickfingers：只倒生物牌，法术淤泥不进坟，与主轴错位。
- Insidious Roots：放逐的是生物牌才产 plant，与法术淤泥联动弱，曲线拥挤。
- Bone Dragon / Polukranos escape 类：费用过高，escape 放逐收益不如直接拍淤泥。
- Umori（流浆行侣）：行侣条件要求全同色类别，淤泥是法术，直接冲突。

## 运行清单

- 基准日 2026-08-15；Explorer 代理口径、数据源、枚举规模同 MonoGreen V1（见该文档运行清单节）。
- 门禁：`validate --format pioneer --bo3 --colors bg` PASS（淤泥 14 张走牌面豁免）。
- 实测：Forge AI 模拟结果见文末（样本来源：Forge AI）。

## 实测记录

Forge 2.0.13 AI vs AI，每组 20 局，共 13 组 260 局（样本来源：Forge AI 模拟，可信度低于真人对局；Forge AI 对坟场协同利用率偏低、操控控制套偏弱，胜率仅作定性参考）。报告均在 `SimResult/20260815_*`。

| 对手（环境/类型） | 胜-负 | 胜率 |
|---|---|---|
| SarkhansUnsealingV4（先驱中速） | 6-14 | 30% |
| SimicFlashV1（先驱节奏） | 11-9 | 55% |
| UWControlMeta（先驱控制） | 4-16 | **20%** |
| DimirYorionMeta（先驱中速/控制，缺行侣资源） | 11-9 | 55% |
| URAggroMeta（先驱快攻） | 18-2 | **90%** |
| GolgariAggroMeta（先驱快攻） | 11-9 | 55% |
| RDWMeta（先驱快攻） | 9-11 | 45% |
| TheRockMeta（先驱中速） | 3-17 | **15%** |
| IzzetProwessMeta（标准快攻） | 7-13 | 35% |
| IzzetSpellementalsMeta（标准法术） | 8-12 | 40% |
| MonoGreenLandfallMeta（标准地落） | 9-11 | 45% ⚠1 局触钟判负 |
| OrzhovAggroMeta（标准快攻） | 8-12 | 40% |
| FullColorControlMeta（标准控制） | 10-10 | 50% |

- 合计 104-156，约 40%。
- 无牌面未实现/加载失败。
- 定性：**三版中最均衡、结构最优**。对快攻有统治力（UR 90%，靠 Supplier 快速填坟 + Fatal Push/Scooze 早期防御）；对节奏套 55% 为三版最佳；弱点集中在 UW 控制（扫场+反击）与 TheRock（去除+坟场针对）——两者都可用备牌 Thoughtseize/Duress/Meathook/Decay 部分修补。
- 迭代方向：对控制局可提速（加 Hardened Scales/早期威胁密度）；TheRock 对局考虑主牌或备牌加 Abrupt Decay 至 3–4 张。
