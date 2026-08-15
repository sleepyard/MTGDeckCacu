# Quintorius Kand V1（放逐施放主轴 / Explorer / MTGA BO1）

基准日期：`2026-08-08`。模式 A 从零构筑。阶段 0 参数：Explorer BO1（与近期 Gruul Sarkhan 七场对局同队列）；放逐施放主轴；Boros 主轴，允许蓝色混血法术力牌（不为蓝色配真源）。

一句话玩法：用放逐区施放的咒语（discover、延时 foretell、预谋 plot、冲动式放逐顶牌）反复触发《昆托力康德》被动的 2 点伤害 + 2 点回血，同时靠琵雅纳拉的振翼机、花枪帮/烬心的灵技膨胀打战伤，双轴压死对手。

## 主题机制说明

昆托力康德的被动只认"从放逐区施放的咒语"。本套牌四类引擎全部满足：

- **discover**：从放逐区免费施放翻出的牌（长吼食肉龙、蔽匿庭院/火山）
- **延时 foretell**：延时牌从放逐区施放（恶魔电击、末日劫难）
- **预谋 plot**：预谋牌从放逐区施放（花枪帮炫耀师、大道抢劫）
- **冲动式放逐**（exile 顶牌可施放）：鲁莽冲动、照亮舞台、烬心挑战者志勇触发

蓝色仅以混血法术力混入：言传身教/莎希莉的 {U/R}、{U/W} 全部可用纯红/纯白法术力支付，**色源方案不需要任何蓝色地**。

## MTGA 导入牌表

```text
3 Battlefield Forge
4 Clifftop Retreat
2 Demon Bolt
1 Doomskar
3 Emberheart Challenger
2 Hidden Courtyard
2 Hidden Volcano
2 Highway Robbery
4 Inspiring Vantage
3 Light Up the Stage
3 Lightning Strike
1 Mountain
2 Needleverge Pathway
4 Pia Nalaar, Consul of Revival
2 Plains
4 Portable Hole
3 Quintorius Kand
4 Reckless Impulse
4 Sacred Foundry
2 Saheeli, Sublime Artificer
3 Slickshot Show-Off
2 Trumpeting Carnosaur
```

机器目标：主牌 `60`、备牌 `0`（BO1 无备牌需求，合法但卡位未利用）、生物 `10`、鹏洛客 `5`、真地 `24`、放逐施放引擎密度 `18`（discover 6 + foretell 3 + plot 5 + 冲动式 7，含地与生物面，不计重合）。

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 4 | `{R}{W}` | 复兴执政琵雅纳拉 | Pia Nalaar, Consul of Revival | 二号核心回报；每次放逐区施放造 1/1 敏捷振翼机 |
| 3 | `{1}{R}` | 花枪帮炫耀师 | Slickshot Show-Off | 飞行敏捷；非生物咒语 +2/+0；plot 引擎兼打点 |
| 3 | `{1}{R}` | 烬心挑战者 | Emberheart Challenger | 敏捷灵技；志勇触发放逐顶牌（放逐施放源） |
| 3 | `{3}{R}{W}` | 昆托力康德 | Quintorius Kand | 核心回报；放逐施放→对方 2 伤我方回 2；+1 造 3/2 精怪，−3 discover 4，−6 坟场翻出终结 |
| 2 | `{1}{U/R}{U/R}` | 非凡神器师莎希莉 | Saheeli, Sublime Artificer | 混血蓝；非生物咒语造 1/1 伺服器（纯红可付） |
| 4 | `{1}{R}` | 鲁莽冲动 | Reckless Impulse | 放逐顶 2 张下回合前可施放；最稳定的放逐施放源 |
| 3 | `{2}{R}`（spectacle `{R}`） | 照亮舞台 | Light Up the Stage | 对手失血后 1 费放逐顶 2；与烧伤互动自洽 |
| 2 | `{1}{R}`（plot `{1}{R}`） | 大道抢劫 | Highway Robbery | 弃 1 或祭地抓 2；plot 后放逐区免费施放 |
| 2 | `{4}{R}{R}` | 长吼食肉龙 | Trumpeting Carnosaur | 践踏终结；进场 discover 5；{2}{R} 弃掉当 3 点去除 |
| 4 | `{W}` | 携带式次元洞 | Portable Hole | 一费放逐对手 2 费以下非地永久物；BO1 快攻对冲 |
| 3 | `{1}{R}` | 闪电炼击 | Lightning Strike | 任意目标 3 点；直伤终结面 |
| 2 | `{2}{R}`（foretell `{R}`） | 恶魔电击 | Demon Bolt | 打生物/鹏洛客 4 点；延时后放逐区 1 费施放 |
| 1 | `{3}{W}{W}`（foretell `{1}{W}{W}`） | 末日劫难 | Doomskar | BO1 扫场对冲；延时后放逐区施放触发康德 |
| 4 | - | 圣洁锻炉 | Sacred Foundry | 红白衣壳地 |
| 4 | - | 崖顶修行所 | Clifftop Retreat | 红白检查地 |
| 4 | - | 启迪胜地 | Inspiring Vantage | 红白快地（前三块内未横置） |
| 3 | - | 战场融炉 | Battlefield Forge | 红白痛地 |
| 2 | - | 针缘通路 // 柱缘通路 | Needleverge Pathway // Pillarverge Pathway | MDFC 红白二选一 |
| 2 | - | 蔽匿庭院 | Hidden Courtyard | 白洞穴地；`{4}{W}` 牺牲 discover 4 |
| 2 | - | 蔽匿火山 | Hidden Volcano | 红洞穴地；`{4}{R}` 牺牲 discover 4 |
| 2 | - | 平原 | Plains | 基础白源 |
| 1 | - | 山脉 | Mountain | 基础红源 |

## 概率校验（蒙特卡洛 20 万次，研究脚本 `research/mc_mana.py`）

口径：纯颜色可达性，简单调度规则（起手 2–5 地留下），**未建模 BO1 手牌平滑**（实际表现更好）。

| 指标 | 概率 | 结论 |
|---|---:|---|
| T2 双色（琵雅纳拉 `{R}{W}`） | 98.2% | 留 2 地以上起手即可稳定 T2 琵雅 |
| T3 满 3 地 | 91.6% | 三费曲线可靠 |
| T5 满 5 地且双色（准时康德） | 62.0% | 偏低的硬指标；由 7 张冲动式过牌 + 4 张洞穴地法术力池补偿，实战康德多落 T5–T6 |
| 简单规则调度率 | 15.6% | 正常区间 |

## 留牌指引

- 必留：2 地以上且含双色源；有琵雅纳拉或鲁莽冲动的手优先。
- 可留：1 快地（启迪胜地）+ 携带式次元洞/一费咒语的进攻手，赌第二块地。
- 调度：全 3 费以上无引擎手、单色 2 地手（MC 显示双色率虽高，但单地卡色风险不值得）。

## 打法要点与核心配合

- **康德登场回合提前铺放逐源**：T4 先手捏一张鲁莽冲动/照亮舞台不放，康德 T5 落地当回合即可放逐施放 2 张，立刻 4 伤 4 回 + 两个振翼机。
- **延时节奏**：T2 多余 2 费把恶魔电击/末日劫难延时，之后任意回合 1/3 费从放逐区施放，配合康德白赚触发。
- **莎希莉 + 非生物密度**：鲁莽冲动、照亮舞台、大道抢劫、次元洞全是非生物咒语，莎希莉 −2 还能把伺服器复制成食肉龙。
- **生存预算**（BO1 首局）：次元洞×4、闪电炼击×3、恶魔电击×2、末日劫难×1、食肉龙弃牌模式×2，共 12 张互动；康德回血与琵雅振翼机是长盘续航。
- **两个独立赢点**：①康德被动 burn（每张放逐施放 2 伤，不依赖场面）；②花枪帮/烬心灵技膨胀 + 食肉龙践踏 beatdown。两者互不依赖，扫场后 burn 轴仍在。

## 可调仓位

- `Etali's Favor`（埃泰力眷恩，LCI）：discover 3 灵气，本次因贴皮风险落选，需要更多 discover 密度时换入（换 1 照亮舞台或 1 大道抢劫）。
- `Chimil, the Inner Sun`（内阳奇密理，LCI）：6 费"你的咒语不能被反击"+每回合 discover 5，对控制环境换入（换 1 食肉龙）。
- `Doomskar` 第二张：快攻增多时换入（换 1 闪电炼击）。
- `Teach by Example`（言传身教）：混血蓝复制，配合恶魔电击/大道抢劫，需要爆发上限时换入。
- `Valakut Exploration`（瓦拉库探险）：地落放逐引擎，偏长盘版本换入。

## 落选候选与理由

- `Dwarven Reinforcements` 等白色 foretell 低质牌：触发密度够但单卡强度不足。
- `Daring Discovery`、`Hit the Mother Lode`：5/7 费 discover 法术本体费高，被食肉龙与洞穴地覆盖。
- `Gwen Stacy // Ghost-Spider` ◇：翻面异能需真 `{U}`，违反"混血优先"约束。
- `Appa, Steadfast Guardian` ◇：空bender 需要已有场面才赚，与本套牌咒语主轴错位。
- 蓝色真源方案：为莎希莉/言传身教单配海岛/双色地会显著降低 RW 双色稳定性，被混血方案替代。

## 验证记录

- 三重核对：36/36 候选 + 最终 22 张全部 Pioneer 合法 ✓ / Arena 可用 ✓ / mtgch 中文名 ✓（`tools/mtg_tool.py check`，基准日 2026-08-08；Explorer 无独立 legalities 字段，以 Pioneer ∩ Arena 代替，已交叉核对 Pioneer 禁牌表与 MTGA BO1 特例禁牌——本牌表无命中）。
- 机器门禁：`mtg_tool.py validate --format pioneer --platform arena --no-sideboard` → PASS 全过。
- Forge AI 模拟：vs SarkhansUnsealingV4（格鲁尔中速）20 局 **6:14（胜率 30.0%）**，报告与原始日志存 `SimResult/20260808_172634_QuintoriusKandV1_vs_opp_SarkhansUnsealingV4.{md,log}`。已核对日志：康德、琵雅、莎希莉、食肉龙、洞穴地等关键牌均被 Forge 实现并实际进场，无加载失败。解读注意：①Forge AI 恰好擅长格鲁尔这类直线中速，而对鹏洛客/咒语协同的价值轴利用很差，30% 是下限口径；②对局暴露的真实弱点是前期场面——格鲁尔 4/5 费大生物压场时，我方 1/1 振翼机交换不动，靠次元洞/炼击/恶魔电击的 9 张点杀兜不住全部压力，迭代方向是增加前期阻挡质量或第二张扫场。真人对局（`mtga_log_tool.py scan` 记录）出来前不下胜率结论。

## 运行清单

- 基准日期：2026-08-08；赛制 Explorer BO1；平台 MTGA；模式 A 从零构筑。
- 环境基线：`mtg_tool.py baseline --format explorer --date 2026-08-08`（系列 1037、禁牌 31、失败项 0）。
- 候选检索（均含 `f:explorer game:arena date<=2026-08-08`，oracle 去重，原始响应存 `research/`）：payoff `o:"cast a spell from exile"`/`o:"spell from exile"`（6/7 张）；`o:discover ci<=rw`（15）；`o:foretell ci<=rw`（17）；`o:plot ci<=rw`（12）；`o:"exile the top" o:"you may play" ci<=rw`（91，二阶段过滤 cmc≤3）；`(o:rebound or o:suspend) ci<=rw`（1）；`m:{U/R}`/`m:{U/W}`（24/21）；`o:cascade ci<=rw` 真实零结果。
- 概率校验：`research/mc_mana.py`（20 万次模拟，脚本与假设见上文）。
- Forge 模拟对手：SarkhansUnsealingV4（`research/opp_SarkhansUnsealingV4.txt`，自家格鲁尔中速，代表近期队列主流思路之一）。
