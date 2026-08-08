# LandPlant V5（先驱 / 纯绿种地 / MTGA BO3）

本次为对 V1 的独立工作流回归测试，基准日期 `2026-08-01`。默认目标为“主题保真优先，在不改成相邻主流套牌的前提下补强结构”；主牌 60 / 备牌 15。

## 运行基线

- 模式：B（既有牌表优化）
- 玩法推断：牌库铺地/地变生物 → 按地或树林数量放大身材 → beatdown；妮莎、盖伦碧堡和獾地鼠幼兽放大法术力，陨蹄终结
- 明确排除：以地落触发为主要回报的 Lotus Cobra / Bristly Bill 路线；允许一张牌兼有地落文字，但不能让构筑主轴漂移
- 牌池：先驱、MTGA 任一印刷可用、纯绿且允许无色（`ci<=g`）、BO3、无预算上限
- 系列：Scryfall `/sets` 显示最新已发售扩展为 `MSH`（2026-06-26）；`HOB`（2026-08-14）、`FRA`、`TRK` 尚未发售并排除
- 禁牌：Scryfall 返回 31 张先驱基础禁牌；官方列表另有仅 MTGA BO1 禁用的 Tibalt's Trickery。主题相关的 Field of the Dead、Leyline of Abundance、Once Upon a Time、Veil of Summer 均不可用
- 环境：威世智 2026-06-29 公告称先驱环境宏观类型分布良好，Badgermole Cub 中速和 ramp 正在上升；本牌表使用其中组件，但“地数身材”版本仍定位为娱乐向可行构筑，不宣称主流

数据源：[Scryfall sets](https://api.scryfall.com/sets)、[Scryfall Pioneer bans](https://api.scryfall.com/cards/search?q=banned%3Apioneer)、[官方禁牌列表](https://magic.wizards.com/en/banned-restricted-list)、[2026-06-29 禁限牌公告](https://magic.wizards.com/en/news/announcements/banned-and-restricted-june-29-2026)。

## V1 体检

- 数量正确：主牌 60 / 备牌 15。
- 25 个唯一牌名全部先驱合法并存在 Arena 印刷。Ram Through、Scavenger Grounds、Topiary Stomper 的最新印刷不在 Arena，但旧印刷在；只读 `/cards/named` 最新印刷会误判。
- V1 有 25 张真地和 2 张 Tangled Florahedron MDFC，共 27 张起手可当地使用的牌；启发式加权地当量为 `25 + 2×0.75 = 26.5`。
- V1 有大量铺地：Emergent Sequence×4、Topiary Stomper×4、Beanstalk Giant 历险面×4、Studious First-Year 预备副本×4；Bushwhack 只把地放进手牌，不是加速。
- 主牌没有即时卡差引擎，只有 Bushwhack×3 可作生物互动；大量找地后容易进入“有很多法术力、没有有效牌”的状态。
- Ram Through 的穿透伤害依赖己方生物有践踏，而 V1 主牌通常只有陨蹄回合满足；Naturalize 过窄；备牌堆叠了过多六至七费控制威胁，却缺少对快攻、坟场和组合技的低费方案。
- Fabled Passage 并非纯粹跑题：牺牲再找地可提高 Emergent Sequence 当回合的指示物数，且能被 Lumra 回收，因此保留 1 张而非全部移除。

### 检索覆盖

以下为 `f:pioneer game:arena date<=2026-08-01 ci<=g` 下的 oracle 级去重命中数；同一卡可跨模块重复：

| 模块 | 查询变体 | 命中 |
|---|---|---:|
| M1 地数/树林数回报 | `lands you control` / `Forests you control` | 60 |
| M1 地数力量回报 | `for each land` / `number of lands` | 29 |
| M2 牌库铺地 | `search your library` + `land card` + `battlefield` | 78 |
| M2 基础地铺地 | `basic land card` + `battlefield` | 69 |
| M2 额外下地 | `additional land` | 13 |
| M3 大身材卡差 | `power 4 or greater` + `draw` | 11 |
| M3 大身材兑现 | `greatest power` / `total power` | 26 |
| M4 MDFC / 生物地 | `is:mdfc` / 地变生物 | 8 / 13 |
| M5 互斗 / 单体保护 | fight/bite / hexproof/indestructible | 97 / 112 |

可靠的逐系列命中统计本次无法自动生成：现有工作流没有定义“oracle 去重后按首印、当前印刷还是全部印刷归组”的口径，也没有执行器保存原始分页结果。该项记入工作流缺口，不用不可靠数字冒充完成。

### 重点候选

| 模块 | 候选 | 系列 | 结论 |
|---|---|---|---|
| M1 | Lumra, Bellow of the Woods | BLB | 地数身材 + 自磨四张并回收坟场地，加入 2 |
| M1 | Cultivator Colossus | VOW Arena 印刷 | 地数身材、践踏、手牌地转卡差，加入 1 |
| M1 | Harmonious Grovestrider | EOE | 五费纯身材且五费位拥挤，排除 |
| M1 | Multani, Yavimaya's Avatar | DOM Arena 印刷 | 有践踏和复归，但六费位被 Lumra 占用，列可调仓位 |
| M2 | Archdruid's Charm | MKM | 找任意生物/地，兼生物去除和神器结界放逐，加入 2 |
| M2 | Lumbering Worldwagon | DFT | 三费铺地和重复攻击价值，但 crew 4 在落后时不稳定，排除 |
| M3 | Garruk's Uprising | M21 Arena 印刷 | 给地数巨物践踏并持续补牌，加入 2 |
| M3 | Hunter's Talent | BLB | 二费互动，后续补践踏和回合末抓牌，加入 2 |
| M3 | Up the Beanstalk | WOE | 先驱合法且适合高费曲线，但不帮助无践踏巨物过阻挡，列可调仓位 |
| M3 | The Great Henge | ELD Arena 印刷 | 上限高但依赖先有大生物，九费原始费用在落后局较差，排除 |
| M5/SB | Keen-Eyed Curator | BLB | 可响应坟场目标并兼作打手，加入 3 |
| M5/SB | Tranquil Frillback | MAT | 神器/结界、全坟场、回血三种模式，加入 2 |
| M5/SB | The Stone Brain | BRO | 纯绿可用的组合技定点拆解，加入 2 |

## 构筑方向

| 方向 | 做法 | 优点 | 代价 |
|---|---|---|---|
| A 主题保真补强（采用） | 保留 V1 铺地与地数身材，加入卡差和模态互动 | 最接近测试目标，能定位工作流是否漂移 | 竞技上限低于主流獾地鼠套牌 |
| B 竞技换血 | 加入 Llanowar Elves/Elvish Mystic 与 Ouroboroid，减少找地和地数巨物 | 更贴近当前成熟 Badgermole shell | 主轴变成生物产费与全队指示物，不再是原主题 |
| C 长盘资源 | 增加 Up the Beanstalk、The Great Henge、Worldwagon | 卡差更强、抗消耗 | 三费非场面牌与高费组件增多，快攻对局更差 |

## 最终导入牌表

```text
2 Archdruid's Charm
3 Ashaya, Soul of the Wild
4 Badgermole Cub
2 Beanstalk Giant
2 Boseiju, Who Endures
2 Castle Garenbrig
1 Craterhoof Behemoth
1 Cultivator Colossus
3 Emergent Sequence
1 Fabled Passage
3 Flourishing Bloom-Kin
18 Forest
2 Garruk's Uprising
2 Hunter's Talent
1 Lair of the Hydra
2 Lumra, Bellow of the Woods
2 Nissa, Who Shakes the World
4 Studious First-Year
2 Tangled Florahedron
3 Topiary Stomper

Sideboard
2 Heroic Intervention
3 Keen-Eyed Curator
2 Obstinate Baloth
2 Pick Your Poison
2 The Stone Brain
2 Thrun, Breaker of Silence
2 Tranquil Frillback
```

## 主牌功能表

| 数量 | 费用 | 中文名 | English | 定位 |
|---:|---|---|---|---|
| 4 | {G} // {1}{G} | 好学新生 // 徒长 | Studious First-Year // Rampant Growth | 一费站场；预备副本后续找基础地进场 |
| 4 | {1}{G} | 獾地鼠幼兽 | Badgermole Cub | earthbend 地变生物；生物产费额外加 {G} |
| 3 | {1}{G} | 突发后果 | Emergent Sequence | 找基础地进场并变分形；从 4 降至 3 以降低脆弱地生物密度 |
| 3 | {1}{G} / 伪装 {4}{G} | 茁壮花身 | Flourishing Bloom-Kin | 核心树林数身材；伪装翻面可铺地 |
| 2 | {1}{G} // 地 | 杂生花晶石 | Tangled Florahedron // Tangled Vale | 产费生物 / 横置绿地 MDFC |
| 2 | {1}{G} | 捕猎手才能 | Hunter's Talent | 主牌互动；升级后给践踏并持续抓牌 |
| 2 | {2}{G} | 贾路的反抗 | Garruk's Uprising | 大身材补牌并让全队获得践踏 |
| 3 | {1}{G}{G} | 绿雕跺地兽 | Topiary Stomper | 找基础地；七地后成为 4/4 警戒 |
| 2 | {G}{G}{G} | 高位德鲁伊护符 | Archdruid's Charm | 找关键生物/地；兼去除与神器结界放逐 |
| 3 | {3}{G}{G} | 荒野之魂艾莎娅 | Ashaya, Soul of the Wild | 核心地数身材；非衍生生物变树林 |
| 2 | {3}{G}{G} | 撼世妮莎 | Nissa, Who Shakes the World | 树林产费翻倍；地变 3/3 抢血 |
| 2 | {4}{G}{G} | 林间嚎吼卢玛拉 | Lumra, Bellow of the Woods | 地数身材；自磨并回收坟场地 |
| 2 | {6}{G} // 历险 {2}{G} | 豆茎巨人 // 茁壮脚步 | Beanstalk Giant // Fertile Footsteps | 三费铺地后保留七费地数身材 |
| 1 | {4}{G}{G}{G} | 培护巨像 | Cultivator Colossus | 地数践踏；把手牌地转为战场与抓牌 |
| 1 | {5}{G}{G}{G} | 陨蹄贝西摩斯 | Craterhoof Behemoth | 全队践踏斩杀 |
| 18 | - | 树林 | Forest | 基础绿源与找地目标 |
| 2 | - | 历祚母圣树 | Boseiju, Who Endures | 绿源；通道解神器/结界/非基本地 |
| 2 | - | 盖伦碧堡 | Castle Garenbrig | 生物法术/异能的法术力放大 |
| 1 | - | 神奇小径 | Fabled Passage | 基础地转换；配合突发后果与卢玛拉 |
| 1 | - | 多头蛇蜥巢穴 | Lair of the Hydra | 不占咒语位的后期打手 |

地源：24 张真地 + 2 张 MDFC，起手可当地使用的牌共 26；加权地当量 `24 + 2×0.75 = 25.5`。只考虑这 26 张地牌卡位时，七张起手至少两地约 89.55%，到第三回合看九张牌至少三地约 84.63%；找地和调度规则未计入该概率。

## 备牌功能表

| 数量 | 费用 | 中文名 | English | 对局 |
|---:|---|---|---|---|
| 2 | {G} | 挑选毒药 | Pick Your Poison | 低费处理单一神器/结界/飞行生物环境 |
| 2 | {1}{G} | 英勇干预 | Heroic Intervention | 防扫场和多目标去除 |
| 3 | {G}{G} | 锐目鉴物客 | Keen-Eyed Curator | 可响应的单卡坟场放逐，后期成为 6/6 践踏 |
| 2 | {2} | 魔石大脑 | The Stone Brain | 对组合技移除关键同名牌 |
| 2 | {2}{G}（模式另付 {G}） | 安详鳍背龙 | Tranquil Frillback | 神器/结界、全坟场、回血模态针对 |
| 2 | {2}{G}{G} | 顽强巴洛西 | Obstinate Baloth | 对快攻回血、对弃牌免费进场 |
| 2 | {3}{G}{G} | 破诫巨魔图伦 | Thrun, Breaker of Silence | 对蓝黑控制的不可反击、难去除威胁 |

## V1 → V5 改动

### 主牌砍出/减量

- Bushwhack×3 → 0：找地到手不是加速，互斗又依赖先有大生物；改为同样能找牌但模式更完整的高位德鲁伊护符，以及可成长为卡差引擎的捕猎手才能。
- Beanstalk Giant×4 → 2：保留三费铺地/七费回报的双阶段价值，降低七费牌重叠。
- Emergent Sequence×4 → 3、Topiary Stomper×4 → 3：三费动作增加后各减一张，降低地生物被扫场和七地前跺地兽无法攻防的风险。
- Nissa, Who Shakes the World×3 → 2：传奇五费位与艾莎娅重叠，避免多张卡手。
- Forest×18 保持，Fabled Passage×2 → 1：总地牌卡位仅从 27 降至 26，仍保留小径的协同。

### 主牌加入

- Archdruid's Charm×2：补齐 tutor 与主牌互动，一张牌覆盖关键生物、功能地、去除、神器和结界。
- Hunter's Talent×2：早期处理生物，长盘给大身材践踏并每回合抓牌。
- Garruk's Uprising×2：把“只是很大”转成穿透伤害，并补上 V1 的持续卡差缺口。
- Lumra, Bellow of the Woods×2：六费地数回报，回收小径和自磨到的地。
- Cultivator Colossus×1：可被护符找到的终局地数威胁；仅放一张，避免无手牌地时重复抽到。

### 备牌重构

- 移除 Bala Ged Recovery、Khalni Ambush：MDFC 很灵活，但不是针对特定对局的高影响备牌。
- 移除 Carnage Tyrant、Summon: Titan、Tyrranax Rex：昂贵控制威胁过多，改用五费且更难被蓝黑处理的 Thrun。
- 移除 Naturalize：由 Pick Your Poison、Tranquil Frillback 和主牌 Archdruid's Charm 分层替代。
- 移除 Ram Through：V1 缺少常驻践踏，穿脸条件不稳定；主牌 Hunter's Talent/Charm 已提供互动。
- 移除 Scavenger Grounds：换入会损失绿色地源且也会放逐自己的卢玛拉资源，改用 Keen-Eyed Curator/Tranquil Frillback。
- 移除 Snakeskin Veil：单体保护升级为能防全场扫除的 Heroic Intervention。

## 留牌与回合节奏

- 默认留 2-5 张地牌卡位；一地手即使有好学新生也应调度，因为徒长副本仍需第二个绿源。
- 两地 + 好学新生/二费动作 + 三费铺地可留；五费以上牌超过两张且没有早期动作时调度。
- 1 回合：好学新生，或下地空过。
- 2 回合：施放徒长副本、獾地鼠幼兽、突发后果、茁壮花身、花晶石或捕猎手才能。幼兽 earthbend 不会自动重置已横置的地，不应虚构当回合额外法术力。
- 3 回合：跺地兽、豆茎历险面、贾路的反抗或高位德鲁伊护符；优先让卡差引擎先于四力量以上生物落地。
- 4 回合：只要前三回合有一次铺地，就能正常施放艾莎娅/妮莎；没有实际加速时不得按五费计算。
- 5-6 回合：卢玛拉稳定场面，培护巨像/豆茎巨人补充威胁，陨蹄在已有足够生物时终结。
- 艾莎娅令非衍生生物成为树林；它们受召唤失调限制，但之后能与幼兽、妮莎的额外产费叠加。

## 换备简表

| 对局 | 换入 | 换出 |
|---|---|---|
| Izzet/红色快攻 | Obstinate Baloth×2、Tranquil Frillback×2；看到关键飞行/结界再加 Pick Your Poison×2 | Craterhoof×1、Cultivator×1、Lumra×2；再换时减 Beanstalk×2 |
| Greasefang / Cat-Oven | Keen-Eyed Curator×3、Tranquil Frillback×2 | Craterhoof×1、Cultivator×1、Nissa×1、Garruk's Uprising×2 |
| 蓝黑/控制 | Heroic Intervention×2、Thrun×2 | Hunter's Talent×2、Emergent Sequence×1、Topiary Stomper×1 |
| Lotus Field / 单核心组合技 | The Stone Brain×2 | Hunter's Talent×2 |
| 单一神器/结界/飞行威胁 | Pick Your Poison×2 | 按对局移除最慢的两张七至八费牌 |

以上为定性推演，尚未导入 Arena 进行真实对局或基于规则引擎模拟，不应解读为胜率结论。

## 可调仓位

- 主题更纯：Up the Beanstalk、Multani, Yavimaya's Avatar、Ulvenwald Hydra、Lumbering Worldwagon。
- 更偏竞技：Llanowar Elves、Elvish Mystic、Ouroboroid；这会明显改变主轴，应作为独立分支而非静默替换。
- 调整对：Garruk's Uprising×1-2、Hunter's Talent×1-2、Beanstalk Giant×1-2、Lumra×1-2、Fabled Passage 第 2 张。
