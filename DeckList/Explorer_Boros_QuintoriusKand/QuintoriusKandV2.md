# Quintorius Kand V2（火花替身倾探链 / Explorer / MTGA BO1）

基准日期：`2026-08-08`。模式 A 迭代：用户反馈 V1 完全丢掉了原定核心玩法——**复制品 + 昆托力康德：不断倾探（discover）拉出复制体，复制体变康德再倾探**。V2 以此为主轴重构；V1 的纯 value 轴降为备用方向。

一句话玩法：T5 康德落地 −3 倾探 4，翻中《火花替身》即从放逐区免费施放并复制康德（非传奇、5 忠诚）→ 替身康德立刻再 −3 倾探 4；圣阳造物监管人把每次倾探翻倍，多张康德在场时每张放逐区施放都各烧 2 回 2，链式反应一波带走。

## 连锁机制说明

- 康德进场 4 忠诚，−3 倾探 4（可用两次需 +1 一次，或配合链中替身）。
- **火花替身 {3}{U}**（WAR，法术力值 4，正好在倾探 4 射程内）：可复制**鹏洛客**，进场多 1 个忠诚指示物 → 替身康德 5 忠诚落地即可 −3 再倾探 4 → 继续翻替身继续链。Explorer 牌池中唯一能复制鹏洛客的牌（两种措辞检索均仅此 1 张命中）。
- 倾探施放的咒语来自放逐区 → 触发**所有**在场康德被动：n 张康德 = 每张放逐施放烧 2n 回 2n。
- **圣阳造物监管人 {3}{R} 3/3**：你每次倾探后再倾探一次（每回合一次）→ 每次 −3 实际翻两段。
- 多余的天然康德上手是废牌（传奇规则），故本体 3 张、替身 4 张；倾探翻出天然康德可拿回手牌等替身。

## MTGA 导入牌表

```text
2 Buried Treasure
1 Chimil, the Inner Sun
3 Clifftop Retreat
3 Curator of Sun's Creation
2 Demon Bolt
3 Etali's Favor
2 Glacial Fortress
2 Hallowed Fountain
1 Hidden Cataract
2 Hidden Courtyard
1 Hidden Volcano
4 Inspiring Vantage
3 Light Up the Stage
3 Lightning Strike
1 Mountain
2 Pia Nalaar, Consul of Revival
1 Plains
4 Portable Hole
3 Quintorius Kand
3 Raugrin Triome
4 Reckless Impulse
4 Sacred Foundry
4 Spark Double
2 Steam Vents
2 Trumpeting Carnosaur
```

机器目标：主牌 `60`、备牌 `0`（BO1）、组合技核心 `10`（康德 3 + 替身 4 + 监管人 3）、倾探密度 `13`（食肉龙 2 + 眷恩 3 + 珍宝 2 + 奇密理 1 + 洞穴地 4 + 康德自身）、真地 `24`、蓝源 `10`。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 3 | `{3}{R}{W}` | 昆托力康德 | Quintorius Kand | 核心引擎；−3 倾探 4 启动链；被动按在场数量乘算 |
| 4 | `{3}{U}` | 火花替身 | Spark Double | 复制康德变非传奇替身（5 忠诚）立刻再倾探；Explorer 唯一鹏洛客复制牌 |
| 3 | `{3}{R}` | 圣阳造物监管人 | Curator of Sun's Creation | 3/3；每回合把你的一次倾探翻倍 |
| 2 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 践踏终结；进场倾探 5；`{2}{R}` 弃掉当 3 点去除 |
| 3 | `{2}{R}` | 埃泰力眷恩 | Etali's Favor | 灵气进场倾探 3；+1/+1 践踏贴给 3/3 监管人交换占优 |
| 2 | `{2}` | 遭埋珍宝 | Buried Treasure | 两费加速珍宝；后期 `{5}` 坟场放逐倾探 5 |
| 1 | `{6}` | 内阳奇密理 | Chimil, the Inner Sun | 咒语不能被反击 + 每回合结束倾探 5；长盘独立引擎 |
| 2 | `{R}{W}` | 复兴执政琵雅纳拉 | Pia Nalaar, Consul of Revival | 放逐施放造 1/1 敏捷振翼机；链式回合群体膨胀 |
| 4 | `{1}{R}` | 鲁莽冲动 | Reckless Impulse | 放逐顶 2 找组合件；放逐施放触发康德/琵雅 |
| 3 | `{2}{R}`（spectacle `{R}`） | 照亮舞台 | Light Up the Stage | 同上；康德烧血后 spectacle 极易点亮 |
| 4 | `{W}` | 携带式次元洞 | Portable Hole | BO1 前期生存预算；放逐 2 费以下非地 |
| 3 | `{1}{R}` | 闪电炼击 | Lightning Strike | 点杀/直伤终结面；链式烧血后补刀 |
| 2 | `{2}{R}`（foretell `{R}`） | 恶魔电击 | Demon Bolt | 打生物/鹏洛客 4 点；延时后放逐区 1 费施放触发康德 |
| 4 | - | 圣洁锻炉 | Sacred Foundry | 红白电震地 |
| 2 | - | 崇圣喷泉 | Hallowed Fountain | 白蓝电震地（替身蓝源） |
| 2 | - | 蒸气喷发口 | Steam Vents | 红蓝电震地（替身蓝源） |
| 3 | - | 洛格凌群系 | Raugrin Triome | 三色群系地，横置进场；后期可循环 |
| 3 | - | 崖顶修行所 | Clifftop Retreat | 红白检查地 |
| 2 | - | 冰河要塞 | Glacial Fortress | 白蓝检查地 |
| 4→2 | - | 启迪胜地 | Inspiring Vantage | 红白快地，前期未横置 |
| 2 | - | 蔽匿庭院 | Hidden Courtyard | 白洞穴地；`{4}{W}` 牺牲倾探 4 |
| 1 | - | 蔽匿火山 | Hidden Volcano | 红洞穴地；`{4}{R}` 牺牲倾探 4 |
| 1 | - | 蔽匿巨瀑 | Hidden Cataract | 蓝洞穴地；`{4}{U}` 牺牲倾探 4，兼替身蓝源 |
| 1 | - | 平原 | Plains | 基础白源 |
| 1 | - | 山脉 | Mountain | 基础红源 |

## 概率校验（蒙特卡洛 20 万次，`research/mc_mana_v2.py`）

口径：纯颜色可达性，简单调度规则，未建模 BO1 手牌平滑与横置状态。

| 指标 | 概率 | 结论 |
|---|---:|---|
| T2 双色（琵雅 `{R}{W}`） | 96.3% | 三色化后仍在安全线 |
| T4 有蓝（准时火花替身） | 91.0% | 10 蓝源充足 |
| T5 满 5 地且双色（准时康德） | 61.8% | 与 V1 相同；珍宝加速 + 过牌补偿，实战 T5–T6 |
| T6 三色齐备 | 93.7% | 中盘组合技颜色无忧 |
| 简单规则调度率 | 15.6% | 正常 |

横置代价备注：群系×3 与洞穴地×4 恒横置，检查地×5 条件横置——起手评估时把这些当作慢一拍源；电震地×8 + 痛地式失血是色源方案的生命成本（预计每场 2–6 点，由康德被动回血覆盖）。

## 留牌指引

- 必留：含康德或替身 + 2 地以上双色的手；有遭埋珍宝的加速手优先。
- 组合技调度容忍度高：鲁莽冲动/照亮舞台本身就是找件引擎，缺件但有过牌的手可留。
- 调度：无组合件又无过牌的纯互动手、多横置地开局手。

## 打法要点与核心配合

- **链式启动**：康德 −3 优先于 +1——替身链的价值远高于 3/2 精怪；只有确定翻不出替身（墓地已有 3+ 替身）时才 +1 铺场。
- **监管人先于康德落地**：T4 监管人、T5 康德 −3 翻两段，替身命中率翻倍。
- **过牌留到链式回合**：鲁莽冲动/照亮舞台在康德在场时放，每张都是 2n 烧血。
- **奇密理落地后**：对手无法反击你的倾探翻出的咒语，控制对局直接通关。
- **两个独立赢点**：①替身链一波烧穿（每张放逐施放 2n 伤）；②食肉龙/监管人 beatdown + 直伤收尾。链被拆（康德被去除）时退化为普通红白中速仍有一战。

## 可调仓位

- `Doomskar`（末日劫难）：快攻环境换入（换 1 眷恩）。
- `Daring Discovery`（大胆发现）：5 费倾探 4 + 穿透，需要更多倾探密度时换入。
- `Saheeli, Sublime Artificer`：V1 的混血蓝铺场，链式版本卡位让给监管人；回归 value 轴时换回。
- 第二张云际/奇密理：控制环境加厚。
- 备牌化（若转 BO3）：坟场针对（替身链依赖坟场珍宝/坟场无怨言）、康针对。

## 落选候选与理由

- `Geological Appraiser`：3 费倾探 2 本是最强倾探引擎，**Explorer/Pioneer 禁牌**，硬性排除。
- `Hit the Mother Lode`：7 费倾探 10 太慢，链式不需要它收尾。
- `Hurl into History`：5 费反击+倾探 X，{U}{U} 双蓝与色源方案冲突（混血优先约束）。
- `Zoetic Glyph`：蓝色灵气贴神器变 5/4，配合珍宝有趣但与倾探链正交，卡位不足。
- `Slickshot Show-Off` / `Emberheart Challenger`（V1 主力）：链式版本前期不打beatdown，让位给组合件与互动。

## 验证记录

- 三重核对：新增 9 张（替身/监管人/珍宝/巨瀑/群系/喷泉/喷发口/冰河/眷恩）全部 Pioneer 合法 ✓ / Arena 可用 ✓ / mtgch 中文名 ✓；其余沿用 V1 核对结果。
- 机器门禁：`mtg_tool.py validate --format pioneer --platform arena --no-sideboard` → PASS 全过。
- Forge AI 模拟：vs SarkhansUnsealingV4 20 局 **3:17（胜率 15.0%）**，报告与原始日志存 `SimResult/20260808_174230_QuintoriusKandV2_vs_opp_SarkhansUnsealingV4.{md,log}`。日志核查结论：**机制全部实现**——替身复制鹏洛客的替代式效应正常触发（复制过监管人、琵雅、康德各若干次），倾探从放逐区免费施放替身并触发琵雅造振翼机的链条在日志中可见。但 **AI 操纵严重失真**：替身的复制目标多次选择琵雅纳拉而非康德（不启动倾探链），康德 −3 的使用时机也差，20 局日志中 discover 仅出现 5 次——等于组合技从未真正启动。结论：15% 不是该套牌的有效强度样本（符合工作流"Forge AI 组合技严重失真"口径），机制正确性才是本次模拟的有效产出。强度评估须改用 `forge_tool.py play` 人工试玩或 MTGA 真人对局。

## 运行清单

- 基准日期：2026-08-08；赛制 Explorer BO1；平台 MTGA。
- 新增检索（均含 `f:explorer game:arena date<=2026-08-08`，存 `research/`）：复制体 `o:"copy of a creature or planeswalker"`（1 张）/`o:"as a copy of a creature or planeswalker"`（1 张）/`o:"copy of target planeswalker" or o:"copy of any planeswalker"`（真实零结果）；蓝色倾探 `o:discover ci<=urw`（18 张，较 RW 新增巨瀑/冲入历史/动物雕纹 3 张）。
- 概率校验：`research/mc_mana_v2.py`（20 万次）。
- Forge 模拟对手：SarkhansUnsealingV4（同 V1 对照组）。
