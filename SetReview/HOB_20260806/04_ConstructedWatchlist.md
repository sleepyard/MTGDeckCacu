# HOB 构筑观察与测试队列

## 合法性口径

官方收集页声明 HOB 本身为全格式合法，HOC 是另一个只向 Commander、Legacy、Vintage 及已有合法版本开放的 Eternal-legal 产品。本文按 HOB 在 2026-08-14 生效、MTGA 在 2026-08-11 上线的假设筛选。8 月 6 日 Scryfall `legalities` 仍将 188 张新牌标成 `not_legal`，因此这不是当前可导入牌表。

目标赛制的最终合法性、禁牌和平台印刷必须在测试当天重读。HOB 的普通版本与数字重平衡版本不得混用。

## T0 / T1 候选

| 优先级 | 牌 | 赛制 / 外壳 | 用途 | 纸面理由 | 主要风险 |
|---|---|---|---|---|---|
| T0 | Bilbo's Gambit | Standard、Pioneer 控制 / Tempo | 现有补强 | `1W` 退回任意咒语；Gift 后当回合禁止继续施法，可把一次交换变成节奏锁 | Gift 给对手 Treasure；不能处理已落地永久物 |
| T0 | The Eagles Are Coming! | Standard、Pioneer Token / ETB | 新增冗余 | `2W` 保护自己的生物并在下一维护造 4/4 飞行；踢出可把 token 变成多个空军 | 目标必须是自己拥有的生物；扫场后回报延迟 |
| T0 | Bilbo, Thief in the Night | Standard、Pioneer 墓地法术 | 新轴核心 | `1U` 让非手牌施法减费，攻击时重复施放坟场的神器 / 瞬间 / 法术 | 2/2 无保护，攻击前需要活到回合 |
| T0 | Fateful Discovery | Standard、Pioneer Artifact / Treasure | 新轴核心 | 每个神器进场抓牌，可把 Treasure、Equipment、Boulder 变成持续引擎 | 五费无即时场面；需高神器密度 |
| T0 | Great Gilded Boat | Standard、Pioneer Vehicle / Recruit | 现有补强 | 三费 4/4、攻击即 Recruit，Crew 2 门槛低 | 依赖攻击窗口；Crew 与其他 tap 异能竞争 |
| T0 | Head of the Hunt | Standard、Pioneer 中速 / 坟场对策 | 现有补强 | 四费闪现 4/3，敌方生物死亡直接放逐并造 2/2 Wolf | 对手无生物死亡时只是普通威胁 |
| T0 | Gandalf, Goblins' Bane // Flameshape | Standard、Pioneer 法术 / Wizard | 新轴核心 | Adventure 先藏两张牌，主体每次非生物咒语同时成长并打脸 | 2/3 易被点杀；Adventure 需要 Wizard 才能使用牌 |
| T0 | Wood Elves | Standard、Pioneer、仓库 LandPlant | 现有补强 | 三费生物将 Forest 直接放进场，补 ramp、地数和 Ashaya 轴；比只把地找进手更有效 | 1/1 身材低；基础 Forest 目标会耗尽 |
| T0 | Mirkwood Pathmaker | Standard、Pioneer、仓库 LandPlant / Ramp | 新增冗余 | 三费力量防御等于地数，直接补齐“铺地 → 地数身材”主轴 | 前期地数不足时身材普通；遇到非地去除亏节奏 |
| T0 | Mirkwood Pathmaker | Pioneer Gruul Unsealing | 新增回报 | 四地时施放即达到力量 4 门槛，可触发以力量为条件的回报 | 需要同时拥有四地和回报牌 |
| T0 | Beorn's Hospitality | Standard、Pioneer Landfall / LandPlant 分支 | 新轴核心 | 两费持续 Landfall 指示物，后期七费变成地数身材 Bear | 前期不创造生物；严格地数主轴需接受 Landfall 语义扩展 |
| T0 | Radagast of Rhosgobel | Standard、Pioneer Creature Ramp | 新轴核心 | 四费 2/5，让每回合第一只生物减两费并可闪现，能连续制造法术力差 | 依赖生物密度；自身无立即卡差 |
| T0 | The Notary Hobbits | Standard、Pioneer Halfling / Token Ramp | 新轴核心 | 五费进场变成三个 1/1 Halfling，每个后续可按 Halfling 数量产无色费 | 需要下一回合存活或急速 / 重置；无色费不能支付有色符号 |
| T0 | Bard, King of Dale | Standard、Pioneer Token / Recruit | 新轴核心 | 非首张抽牌变两张、token 数量翻倍，直接放大 Recruit、Treasure 与 Soldier | 六费且三色；被立即去除时回报不足 |
| T0 | Thranduil, Sindarin Liege // Silvan Rally | Standard、Pioneer GU Elves | 新轴核心 | Adventure 填坟并找地，主体给 Elf +1/+1 且 Landfall 持续造 Elf | 四费双混色；Landfall 需要真实地源 |
| T0 | Thranduil, the Elvenking | Standard、Pioneer、Modern Elves | 新轴核心 | 从坟场获得所有 Elf 启动式异能，并为传奇 Elf 提供两张进一张出 | 三色五费；必须有足够 Elf 坟场和传奇 Elf 密度 |
| T0 | Glamdring, Foe-hammer // Gleam of Death | Pioneer、Modern Spells / Graveyard | 新轴核心 | 二费 Equipment 按装备生物力量减瞬间 / 法术，Adventure 一次填坟并回收六张中的法术 | 需要先有能存活的高力量生物；减费只减无色部分 |
| T0 | My Precious // Allure of Power | Standard、Pioneer、Brawl | 现有补强 / 新轴 | Adventure 是两费牺牲抽二；Equipment 三费提供辟邪与不可阻挡 | 装备支付生命和 Equip 费用，牺牲组件要有目标 |
| T0 | Orcrist, Goblin-cleaver | Standard、Pioneer Equipment / Token | 新轴核心 | 三费 Equipment 的战斗伤害按指定类别数量造 Treasure，能与 token 翻倍互相放大 | Equip 3；必须连接并打通战斗 |
| T1 | Settle the Wreckage | Standard、Pioneer 控制 / 备牌 | 现有补强 | HOB 重新带来四费瞬间扫场，对快攻和宽场提供明确答案 | 给对手基本地；需要对手攻击并承受留费压力 |
| T1 | An Unexpected Party // At the Door | Standard、Pioneer Dwarf / Token | 新轴核心 | Adventure 可按 X 造 Dwarf，主体给选定类别 +2/+2 | 五费先手慢；需要同类生物密度 |
| T1 | Kíli the Resourceful | Standard、Pioneer RW Dwarf / Equipment | 新轴引擎 | Storied 后首个 Equip 变成 0，另有每回合 Dwarf / Equipment 抽牌 | 两费 1/2，需有后续牌才能回本 |
| T1 | Fíli the Pathfinder | Standard、Pioneer Dwarf | 新轴回报 | Storied 后全队 +1/+1，Dwarf 进场继续造 2/2 | 四费且传奇；场面被扫后需要重建 |
| T1 | Dwalin, Weaponmaster | Standard、Pioneer Equipment | 新轴放大器 | 每次进场或攻击给所有 Equipment Hone counter，快速放大单个承载生物 | 2/1 先攻；Equipment 数量不足时上限低 |
| T1 | The Great Goblin | Standard、Pioneer BR Goblin / Amass | 新轴核心 | Goblin / Army counters 直接打脸，死亡后提供延迟牌差 | 需要稳定放 counters；三费身材普通 |
| T1 | Bothersome Noisemaker | Standard、Pioneer BR Spells | 新轴启用件 | 每个非生物咒语 Amass 1，能把法术动作变成场面 | 2/2 需要较多非生物咒语 |
| T1 | Smaug the Magnificent | Standard、Pioneer、Brawl Treasure | 新轴终结 | 四费 4/3 飞行急速，每次维护 Treasure，攻击按 Treasure 数量直伤 | 4/3 易被常见去除；需要 Treasure 先铺 |
| T1 | Desolation of Smaug | Standard、Pioneer Dragon | 新轴基建 | 四费对非 Dragon 造成 3 并提供四点仅限 Dragon 的法术力 | 对纯 Dragon 牌表自身收益低；四费清场对曲线要求高 |
| T1 | Last Light of Durin's Day | Standard、Pioneer Dragon Ramp | 新轴启用件 | 两费可 Mountaincycling，六次 Mountain 进场后从手 / 牌库直接进 Dragon | 需要六次 Landfall，单独抽到节奏慢 |
| T1 | Getaway Barrel | Pioneer、Modern Artifact Cheat | 新轴启用件 | 四费 Artifact 死亡后从顶十三张随机把生物放场，能把高费生物变成一次性 Polymorph | 随机、需要牺牲出口、对非生物组合牌无效 |
| T1 | The Master of Lake-town | Pioneer Peer / Devotion 分支 | 现有补强 / 备用赢点 | 玩家每失一血就磨同数量，三费双黑且死亡时按墓地阈值抽牌 | 需要大量生命损失或 Peer 轴；自身死触不能阻挡大场面 |
| T1 | Inside Information | Pioneer、Modern Life / Graveyard Combo | 新轴核心 | XBB 放逐对手顶 X 并本回合使用，改以生命支付费用 | 生命成本极高；目标牌库顶不稳定 |

## 仓库牌表补强

| 现有牌表 | 当前卡位 | HOB 候选 | 建议 | 改善 | 回退风险 |
|---|---|---|---|---|---|
| Pioneer MonoGreen LandPlant | 地数身材 / 三费动作 | Mirkwood Pathmaker | T0，先测 2–4 | 三费直接按地数给身材，严格命中主轴 | 前期低于四地时不如有 ETB 的铺地牌 |
| Pioneer MonoGreen LandPlant | 牌库铺地 | Wood Elves | T0，先测 2–4 | Forest 直接进场，是真正 ramp；可配 Ashaya | 1/1，需保留足够 Forest 目标 |
| Pioneer MonoGreen LandPlant | Landfall 分支 | Beorn's Hospitality | T0，独立分支 | 低费持续指示物，后期自身转地数 Bear | 会把主轴从地数量缩放拉向 Landfall，需用户确认主题边界 |
| Pioneer Gruul Sarkhan's Unsealing | 四力以上生物 | Large Bear、Mirkwood Pathmaker | T0，分别测 2–3 | 便宜四力门槛与急速践踏，能稳定触发 Unsealing | Large Bear 的混色要求，Pathmaker 依赖地数 |
| Pioneer MonoBlack Peer Into Abyss | 备用赢点 / 三费黑色永久物 | The Master of Lake-town | T1，测 1–2 | Peer 或 Underworld Dreams 造成的生命损失会转成额外磨牌 | 不是独立即时终结；可能只是重复已有 Dreams 作用 |
| Modern ColorLessBlue Lantern | Saga 可找一费神器 | Giant's Boulder | T2，规则验证后测 1 | 一费 Artifact、进场 Scry 2，Saga 可找；后期可滤色 / 拆永久物 | 产费需要先付一费，不能当作加速；七费拆牌过慢 |

## 暂不投入测试

普通牌中的高费纯身材、条件过窄的 Equipment、只在对手配合时有价值的 `Gleaming Splendor`，以及没有实际核心密度的三色传奇暂不建立完整牌表。它们保留在逐卡表的 `T2 / T3`，等环境或配套卡出现再复核。
