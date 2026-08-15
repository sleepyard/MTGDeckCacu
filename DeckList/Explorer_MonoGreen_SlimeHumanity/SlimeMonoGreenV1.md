# SlimeMonoGreenV1 — Explorer 纯绿反人淤泥（BO3 / MTGA）

> 模式 C 主题种子补全：种子锚点 = **反人淤泥 Slime Against Humanity**（MKM，{2}{G} 法术，造 0/0 流浆践踏 token 并放 X 个 +1/+1 指示物，X = 放逐区+你坟场中流浆或同名牌数 +2；牌面允许任意张数）。张数策略：中量 14 张（用户指定 12–16 档）。
> 主轴：**自磨把淤泥/流浆喂进坟场 → 3 费连拍大淤泥践踏 beatdown**。注意区分两类牌：自磨引擎服务的是"坟场同名计数"，不是地落。

## 牌表（MTGA 导入格式）

见同目录 `SlimeMonoGreenV1.txt`（主 60 + 备 15）。

## 分功能牌表（费用为 Scryfall API 实测，按法术力值升序，地最后）

| 数量 | 费用 | 中文名 | English | 定位 |
|---|---|---|---|---|
| 3 | {G} | 坚固鳞甲 | Hardened Scales | 放大：淤泥进场豆数 +1（每张鳞甲再 +1） |
| 4 | {1}{G} | 贪婪备储 | Cache Grab | 引擎：瞬发磨 4 捡永久物，节奏最好的自磨 |
| 4 | {1}{G} | 事后分析师 | Aftermath Analyst | 引擎/生物：ETB 磨 3，牺牲可回收全部地被 |
| 2 | {1}{G} | 引路羊蹄人 | Satyr Wayfinder | 引擎/生物：翻 4 拿地其余进坟，保地落 |
| 4 | {1}{G} | 腐食流浆 | Scavenging Ooze | 流浆/生存：本体计 X；把坟里淤泥放逐仍计 X；吃坟长豆回血 |
| 2 | {1}{G} | 轰然撞倒 | Ram Through | 互动：大淤泥践踏溢出变直伤穿脸 |
| 2 | {1}{G} | 纠结过往 | Grapple with the Past | 引擎：瞬发磨 3 兼回收生物/地 |
| 14 | {2}{G} | 反人淤泥 | Slime Against Humanity | **种子核心**：张数不限，践踏 token 终结 |
| 2 | {2}{G}{G} | 繁花龟 | Blossoming Tortoise | 引擎：进场/攻击各磨 3 并回收地，减费地异能 |
| 2 | 地 | 历祚母圣树 | Boseiju, Who Endures | 功能地：通道拆神器/结界（反坟场针对） |
| 2 | 地 | 圣府首都伊甸 | Eden, Seat of the Sanctum | 功能地：{5}{T} 磨 2，牺牲可回收永久物 |
| 1 | 地 | 多头蛇蜥巢穴 | Lair of the Hydra | 功能地：法术力水槽/备用打手 |
| 1 | 地/咒 | 巴勒格复苏 | Bala Ged Recovery | MDFC：回收坟中**任意牌**（含法术淤泥）回手再施放 |
| 17 | 地 | 树林 | Forest | 基本地 |

曲线：MV1×3 / MV2×18 / MV3×15(含 MDFC 正面) / MV4×2；地牌卡位 23（真地 22 + MDFC 1）。

## 核心配合

- **鳞甲放大**：Hardened Scales 在场，淤泥的 X 豆变 X+1（两张变 X+2）。T1 鳞甲 T3 淤泥是基础节奏。
- **放逐不掉 X**：X 同时计放逐区。Scavenging Ooze 吃掉自己坟里的淤泥/流浆、Eden 牺牲回收，都不减后续淤泥身材——放心用。
- **回收链**：Bala Ged Recovery / Grapple with the Past 把磨进坟的淤泥捞回手再拍一次，相当于"复制"一张同名进放逐/坟计数。
- **Ram Through 穿脸**：10/10 践踏淤泥 + Ram Through = 点杀对面生物同时溢出打脸，主牌仅有的"直伤"。

## 生存预算与留牌

- 生存件：Scooze×4（阻挡+回血）、Analyst×4（1/3 阻挡）、Ram Through×2、Wayfinder×2。前 3 回合可用阻挡/去除约 12 张，首局对快攻偏弱，靠 T3 起的大淤泥反超。
- 留牌阈值（超几何，60 张 23 地）：起手 ≥2 地 83.5%；T3 ≥3 地 75.5%；起手 ≥1 淤泥 86.1%。**留牌标准：2+ 地 + 至少 1 张引擎（Cache Grab/Analyst/Wayfinder）或淤泥；全引擎无淤泥可接（T3 前见淤泥 94.6%）；无 2 地调度。**

## 两个独立赢点

1. 反人淤泥连拍践踏 beatdown（主轴）。
2. 腐食流浆/繁花龟/多头蛇蜥巢穴的生物 beatdown（不依赖坟场，抗坟场针对时切换）。

## 换备简表

| 对手 | 换入 | 换出 |
|---|---|---|
| 快攻（红/白） | 3 Healer of the Glade、2 Obstinate Baloth、2 Tail Swipe | 3 Hardened Scales、2 Grapple、2 Cache Grab |
| 坟场针对（RIP/明灯/灵车） | 3 Haywire Mite、2 Natural State、1 Consuming Blob、2 Boseiju 已满则在主 | 2 Eden、2 Grapple、2 Cache Grab（降磨牌依赖） |
| 控制/扫场 | 2 Heroic Intervention、1 Consuming Blob、2 Tail Swipe | 3 Hardened Scales、2 Ram Through |
| Stone Brain 预期局 | 主牌分散投资，换入 2 Heroic Intervention + 1 Consuming Blob | 等量换出引擎 |

## 可调仓位

Satyr Wayfinder×2、Grapple with the Past×2、Lair of the Hydra×1、Ram Through×2、Hardened Scales 第 3 张。可换入候选：Seed of Hope（{G} 瞬发磨 2 回 2 血）、Commune with the Gods（翻 5 拿生物/结界）、Garruk's Uprising（全场践踏+抓牌）、Mossborn Hydra（独立赢点）、Innkeeper's Talent（豆翻倍）。

## 考虑过但排除

- 中量以上（20+）淤泥：用户指定 12–16 档。
- Insidious Roots（潜伏繁根）：需混黑且只吃生物牌进坟，与法术淤泥不联动，黑绿版再议。
- March of the World Ooze（{3}{G}{G}{G}）：6 费三色符号，娱乐有余稳定不足。
- Craterhoof/Overrun 类一票终结：淤泥 token 单体已够大，铺场数量少，Overrun 类收益低。
- Winding Way / Colossal Grave-Reaver：Explorer 不可用（前者先驱不合法，后者仅 Alchemy 数字牌）。

## 运行清单

- 基准日 2026-08-15；赛制 Explorer（以 `f:pioneer game:arena date<=2026-08-15` 为牌池代理，Explorer 禁牌 = 先驱禁牌表 + Tibalt's Trickery，官方页面已无独立 Explorer 区）；平台 MTGA；BO3；娱乐向但保证强度；无预算帽。
- 数据源：Scryfall（缓存 tools/cache/scryfall/）、mtgch.com 中文名、WotC 2026-08-10 禁牌公告（Explorer/Pioneer 无变动）。
- 枚举规模：三路检索 40+ 查询式（原始命中数见 tools/testdata/eng_*.json / pay_*.json / int_*.json），三重核对 224 张送检 219 通过。
- 门禁：`mtg_tool.py validate --format pioneer --bo3 --colors g` PASS（本次为 validate 新增"any number of cards named"牌面豁免，反人淤泥 14 张记为豁免非违规）。
- 实测：Forge AI 模拟结果见本文末"实测记录"节（样本来源：Forge AI，可信度低于真人对局）。

## 实测记录

Forge 2.0.13 AI vs AI，每组 20 局，共 13 组 260 局（样本来源：Forge AI 模拟，可信度低于真人对局；Forge AI 对坟场协同利用率偏低、操控控制套偏弱，胜率仅作定性参考）。报告均在 `SimResult/20260815_*`。

| 对手（环境/类型） | 胜-负 | 胜率 |
|---|---|---|
| SarkhansUnsealingV4（先驱中速） | 7-13 | 35% |
| SimicFlashV1（先驱节奏） | 8-12 | 40% |
| UWControlMeta（先驱控制） | 7-13 | 35% |
| DimirYorionMeta（先驱中速/控制，缺行侣资源） | 12-8 | 60% |
| URAggroMeta（先驱快攻） | 12-8 | 60% |
| GolgariAggroMeta（先驱快攻） | 13-7 | 65% ⚠2 局时钟判胜 |
| RDWMeta（先驱快攻） | 10-10 | 50% |
| TheRockMeta（先驱中速） | 2-18 | **10%** |
| IzzetProwessMeta（标准快攻） | 7-13 | 35% |
| IzzetSpellementalsMeta（标准法术） | 11-9 | 55% |
| MonoGreenLandfallMeta（标准地落） | 6-14 | 30% |
| OrzhovAggroMeta（标准快攻） | 4-16 | **20%** |
| FullColorControlMeta（标准控制） | 13-7 | 65% |

- 合计 97-163，约 37%（剔除时钟判胜与对手缺行侣水分后更低）。
- 无牌面未实现/加载失败；对局节奏正常，无死循环。
- 定性：**波动最大的一版**。对快攻看对手类型两极分化（对先驱 UR/黑绿快攻占优，对标准黑白快攻 20% 惨败——无去除挡不住铺场）；对五色/约力昂类慢控制占优（长局递归碾压）；对 TheRock 是黑洞对局（去除+坟场针对+优质生物三重压制）。
- 迭代方向：补主牌廉价去除/回血（Tail Swipe、Healer of the Glade 入主）；对 TheRock 类对局需备牌 Thoughtseize 维度（需混色）或接受为放弃对局。
