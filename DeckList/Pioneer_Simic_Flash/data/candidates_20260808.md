# Pioneer Simic Flash 候选牌清单（阶段 2 枚举，基准日 2026-08-08）

- 赛制/平台：Pioneer / MTGA（`game:arena`），颜色约束 `ci<=ug`（严格蓝绿+无色）
- 主题：经典蓝绿闪现——闪现生物主轴 + 反制/即时互动，全即时速度在对手回合操作
- 边缘牌（不严格符合主题或与主轴有摩擦但顺带契合）打 ◇，由阶段 3 取舍
- 全部 60 张候选已过三重核对（赛制 legal / Arena 可用 / 中文名），0 FAIL，见 `check_candidates.json`

## 二阶段过滤规则

宽查询只用于召回，候选按以下规则过滤：
1. 先驱实战费用线：主牌候选 cmc 一般 ≤6（M6 终结模块允许到 7），核心低费件 cmc ≤3 优先。
2. 剔除明显限制赛专用件：白板/近似白板闪现生物（Pouncing Cheetah、Vexing Gull、Living Tempest 等）及身材严重亏损且异能无关者。
3. 剔除异能与主题无关或自冲突者：如 Lier, Disciple of the Drowned（“咒语不能被反击”与反制主轴自冲突）、merfolk/spirit 部族组件、仅靠 flashback 字样误中的非闪现牌（Rootcoil Creeper、Slickshot Lockpicker 等）。
4. 拿不准的保留并打 ◇：条件闪现（Fear of Impostors）、窄向备牌（Skylasher、Mystical Dispute 类）、替代终结与法术力水槽。
5. 地模块只保留蓝绿双色地 + 实战级无色功能地，删去门槛以下的 tap 地（Simic Guildgate、Thornwood Falls 等）。

## 模块候选（共 60 张）

### M1 核心回报（奖励对手回合施咒）

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
海生割喉客 | Brineborn Cutthroat | FDN | {1}{U} | 核心打手：对手回合每施一咒放一个 +1/+1 豆
夜群袭狼 | Nightpack Ambusher | M20 | {2}{G}{G} | 绿色主轴顶端：自己不施咒的回合末产 2/2 狼
裂波鱼驹 | Wavebreak Hippocamp | THB | {2}{U} | 每个对手回合你首次施咒抓一牌，滚雪球引擎

### M2 闪现生物主体

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
魂魅船员 | Spectral Sailor | FDN | {U} | 1 费闪现飞兵，{3}{U} 抓牌的法术力水槽
翼蜥 | Pteramander | RNA | {U} | 1 费飞兵，坟场瞬间/法术喂大，后期 adapt 成 5/5
幻境保卫者 | Wildborn Preserver | FDN | {1}{G} | 闪现延势 2/2：非人类生物进场放豆，{X} 保命膨胀
厚颜借物灵 | Brazen Borrower // Petty Theft | ELD | {1}{U}{U} // {1}{U} | 历险弹跳非地 + 闪现 3/1 飞兵，经典核心
褶领秘教徒 | Frilled Mystic | RNA | {G}{G}{U}{U} | 闪现 3/2：进场反制任意咒语，GGUU 色源要求高
仙灵才俊 | Faerie Mastermind | MOM | {1}{U} | 闪现飞兵：对手每回合抓第二张牌时你也抓
人鱼诈术师 | Merfolk Trickster | DOM | {U}{U} | 闪现 2/2：横置目标生物并使其失去异能
提莎娜的缚潮师 | Tishana's Tidebinder | LCI | {2}{U} | 闪现 3/2：反制起动/触发式异能并压制来源
催眠仙子 | Hypnotic Sprite // Mesmeric Glare | ELD | {U}{U} // {2}{U} | 2/1 飞兵 + 历险反制 ≤3 费咒语
冒名惧影 ◇ | Fear of Impostors | DSK | {1}{U}{U} | 闪现 3/2：进场反制任意咒语，代价是对手显化怖惧
空击虫 ◇ | Skylasher | PIO | {1}{G} | 不可被反击 + 反蓝保护 2/2 延势，对蓝系备牌

### M3 反制咒语

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
点破咒语 ◇ | Spell Pierce | DFT | {U} | 1 费反击非生物咒语（付 2），前期节奏
禁言 | Censor | AKR | {1}{U} | 反击付 1，循环 {U} 不卡手，经典 2 费康
熄咒 | Quench | RNA | {1}{U} | 反击付 2，2 费主康
失效 | Negate | TMT | {1}{U} | 反击非生物咒语，备牌标配
菁华离散 | Essence Scatter | SOS | {1}{U} | 反击生物咒语
倨傲击 | Disdainful Stroke | WOE | {1}{U} | 反击 ≥4 费咒语，对中大咒备牌
神秘干扰 | Mystical Dispute | ELD | {2}{U} | 反击付 3，对蓝咒语只要 1 费，蓝系内战备牌
天鹅绝唱 ◇ | Swan Song | HA3 | {U} | 1 费反击结界/瞬间/法术，送 2/2 鸟
恶意破坏 | Sinister Sabotage | GRN | {1}{U}{U} | 3 费硬康 + 占卜 1
爪尔干扰 | Jwari Disruption // Jwari Ruins | ZNR | {1}{U} | 反击付 1 的 MDFC 地，不占地卡位
顽固拒斥 ◇ | Stubborn Denial | KTK | {U} | 1 费反击非生物付 1；有 4 攻生物（袭狼）变硬康
早想三步 ◇ | Three Steps Ahead | OTJ | {U} | 狂潮模牌：加费反击/复制生物/占卜抓牌

### M4 即时去除/节奏

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
顿成杂种 | Rapid Hybridization | PIO | {U} | 1 费点杀生物（对手得 3/3 蛙蜥），拆大威胁
渐失希望 | Fading Hope | MID | {U} | 1 费弹生物，≤3 费目标附占卜 1
消解 ◇ | Unsubstantiate | M21 | {1}{U} | 弹咒语或生物，可当软反制
乙太劲风 ◇ | Aether Gust | M20 | {1}{U} | 弹红/绿咒语或永久物（可压牌库顶），对红绿备牌
定念拒斥 ◇ | Decisive Denial | STX | {G}{U} | 互斗 或 反击非生物咒语，双模
析米克护符 ◇ | Simic Charm | EA3 | {G}{U} | +3/+3 / 己方全体辟邪 / 弹生物，三模保护
回返自然 ◇ | Return to Nature | MID | {1}{G} | 拆神器/结界或挖坟场牌，备牌

### M5 滤牌/抓牌（即时优先）

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
抉择 | Opt | FDN | {U} | 1 费占卜 1 抓 1
详加考虑 | Consider | TLE | {U} | 1 费监视 1 抓 1，填坟配合巨械/翼手龙蝾螈
成长涡旋 | Growth Spiral | RNA | {G}{U} | 即时抓牌 + 从手牌放地，把费用曲线推上去
再次考虑 ◇ | Think Twice | MSC | {1}{U} | 1 抓 1 带返照，对手回合的法术力出口

### M6 终结/放大器

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
汹涌巨械 | Torrential Gearhulk | KLR | {4}{U}{U} | 闪现 5/6：免费重放坟场瞬间，经典终结
碎船惊惧兽 | Hullbreaker Horror | VOW | {5}{U}{U} | 不可被反击 7/8：每施一咒弹咒语或永久物，锁场终结
食梦史芬斯 ◇ | Dream Eater | GRN | {4}{U}{U} | 闪现 4/3 飞：监视 4 并弹对手非地永久物
贪餮硕鲨 ◇ | Voracious Greatshark | FDN | {3}{U}{U} | 闪现 5/4：进场反击神器或生物咒语
黯涡蟹 ◇ | Eddymurk Crab | BLB | {5}{U}{U} | 闪现 5/5：坟场每张瞬间/法术减 1 费

### M7 地（双色地 + 功能地）

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
滋生之池 | Breeding Pool | EOE | — | 震动地，未横置双色源
植物圣所 | Botanical Sanctum | OTJ | — | 快地，前三回合未横置双色
内陆港湾 | Hinterland Harbor | DOM | — | 有树林/海岛即未横置的双色地
亚维马雅海岸 | Yavimaya Coast | DMU | — | 痛地双色，无色模式不痛
幻根瀑布 ◇ | Dreamroot Cascade | SOS | — | 慢地双色（场上有 2 地后未横置）
树渠通路 | Barkchannel Pathway // Tidechannel Pathway | KHM | — | MDFC 通路地，选面进场横置
神奇小径 | Fabled Passage | BLB | — | 找地：调色 + 填坟 + 洗牌
凡翠丝堡 ◇ | Castle Vantress | ELD | — | 蓝源功能地：{2}{U}{U} 占卜 2
神秘圣地 ◇ | Mystic Sanctuary | ELD | — | 有 3 海岛进场时把坟场瞬间/法术放回牌库顶
霄城大田原 | Otawara, Soaring City | NEO | — | 未横置蓝源 + 通道弹跳非地永久物
历祚母圣树 | Boseiju, Who Endures | NEO | — | 未横置绿源 + 通道拆神器/结界
战场遗迹 ◇ | Field of Ruin | MID | — | 炸对手功能地（各找基本地）

### M8 闪现增益/辅助

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
荒野斗士薇薇安 ◇ | Vivien, Champion of the Wilds | WAR | {2}{G} | 鹏洛客：让所有生物咒语获得闪现，-2 找生物
至高仙诈术师 ◇ | High Fae Trickster | FDN | {3}{U} | 闪现 4/2 飞兵：让你所有咒语获得闪现

### 补充检索（无关键字、靠记忆兜底的备牌经典）

中文名 | English | 系列 | 费用 | 定位
---|---|---|---|---
腐食流浆 ◇ | Scavenging Ooze | FDN | {1}{G} | 坟场针对 + 膨胀回血，对坟场套备牌
变幻犄角龙 ◇ | Shifting Ceratops | M20 | {2}{G}{G} | 反蓝保护 + 不可被反击，对蓝系备牌
破雾多头龙 ◇ | Mistcutter Hydra | PIO | {X}{G} | X 费不可被反击 + 反蓝保护，对蓝系备牌
无牌灵车 ◇ | Unlicensed Hearse | SNC | {2} | 坟场针对兼中速威胁，备牌

## 查询命中统计表

统一前缀 `f:pioneer game:arena date<=2026-08-08 ci<=ug`（M7 除外）。

| 模块 | 查询式 | 原始命中(印刷) | oracle 去重 | 入选候选 | 原始 JSON |
|---|---|---|---|---|---|
| M1 | o:flash t:creature | 156 | 122 | 3（主体过滤后归 M2/M6） | raw_m1_flash_creatures.json |
| M1 | o:"opponent's turn" | 9 | 4 | 3（Stinging Lionfish 剔除：过窄） | raw_m1_opponents_turn.json |
| M1 | o:"you didn't cast a spell" | 1 | 1 | 1（夜群袭狼） | raw_m1_didnt_cast.json |
| M2 | o:flash t:creature cmc<=2 | 53 | 38 | 9（剔除白板件后） | raw_m2_flash_cmc2.json |
| M3 | o:"counter target spell" cmc<=3 | 88 | 66 | 11 | raw_m3_counter_spell_cmc3.json |
| M3 | o:"counter target" cmc<=2 | 102 | 65 | 10（与上条去重后合计 12） | raw_m3_counter_target_cmc2.json |
| M4 | t:instant o:"return target" cmc<=3 | 65 | 53 | 5 | raw_m4_bounce.json |
| M4 | t:instant o:"destroy target" | 43 | 23 | 2 | raw_m4_destroy.json |
| M4 | t:instant o:"exile target" | 22 | 15 | 0（Rapid Hybridization 已由 destroy 条覆盖） | raw_m4_exile.json |
| M5 | t:instant o:"draw" cmc<=2 | 70 | 46 | 4 | raw_m5_draw.json |
| M5 | o:"scry" cmc<=1 | 36 | 22 | 0（Opt/Consider 已由上条覆盖；地归 M7） | raw_m5_scry.json |
| M6 | o:flash t:creature cmc>=5 | 38 | 30 | 5 | raw_m6_flash_big.json |
| M6 | o:"instant and sorcery" t:creature | 22 | 14 | 1（Pteramander；其余减费大兽淘汰） | raw_m6_spells_matter.json |
| M7 | f:pioneer game:arena date<=2026-08-08 t:land ci<=ug | 744 | 233 | 12 | raw_m7_lands.json |
| M8 | o:"as though it had flash" | 7 | 7 | 1（High Fae Trickster） | raw_m8_as_though_flash.json |
| M8 | o:"you may cast" o:"instant" | 26 | 24 | 0（Torrential Gearhulk 已由 M6 覆盖；其余放大器淘汰） | raw_m8_you_may_cast.json |

说明：`o:"you didn't cast a spell"` 未出现假性 404（命中 1 张即夜群袭狼），未启用备用措辞 `o:"during your turn"`；M1 宽召回 122 个 oracle 经费用线 + 身材 + 主题相关性过滤后主体进入 M2/M6。

## 补充检索验证结果表（记忆牌逐张 check，23/23 PASS）

| 中文名 | English | 赛制合法 | Arena 可用 | 是否入选 |
|---|---|---|---|---|
| 海生割喉客 | Brineborn Cutthroat | ✓ | ✓ | 是 |
| 魂魅船员 | Spectral Sailor | ✓ | ✓ | 是 |
| 夜群袭狼 | Nightpack Ambusher | ✓ | ✓ | 是 |
| 厚颜借物灵 | Brazen Borrower // Petty Theft | ✓ | ✓ | 是 |
| 幻境保卫者 | Wildborn Preserver | ✓ | ✓ | 是 |
| 褶领秘教徒 | Frilled Mystic | ✓ | ✓ | 是 |
| 汹涌巨械 | Torrential Gearhulk | ✓ | ✓ | 是 |
| 熄咒 | Quench | ✓ | ✓ | 是 |
| 神秘干扰 | Mystical Dispute | ✓ | ✓ | 是 |
| 失效 | Negate | ✓ | ✓ | 是 |
| 倨傲击 | Disdainful Stroke | ✓ | ✓ | 是 |
| 菁华离散 | Essence Scatter | ✓ | ✓ | 是 |
| 顿成杂种 | Rapid Hybridization | ✓ | ✓ | 是 |
| 抉择 | Opt | ✓ | ✓ | 是 |
| 详加考虑 | Consider | ✓ | ✓ | 是 |
| 成长涡旋 | Growth Spiral | ✓ | ✓ | 是 |
| 禁言 | Censor | ✓ | ✓ | 是 |
| 荒野斗士薇薇安 | Vivien, Champion of the Wilds | ✓ | ✓ | 是 |
| 腐食流浆 | Scavenging Ooze | ✓ | ✓ | 是 |
| 变幻犄角龙 | Shifting Ceratops | ✓ | ✓ | 是 |
| 破雾多头龙 | Mistcutter Hydra | ✓ | ✓ | 是 |
| 无牌灵车 | Unlicensed Hearse | ✓ | ✓ | 是 |
| 乙太劲风 | Aether Gust | ✓ | ✓ | 是 |

记忆补检额外提名且通过：Vivien, Champion of the Wilds（`o:"as though they had flash"` 措辞不在 M8 查询覆盖内，靠记忆兜底）、Scavenging Ooze / Shifting Ceratops / Mistcutter Hydra / Unlicensed Hearse / Aether Gust（备牌经典，无闪现关键字）。

## 三重核对剔除记录

最终 60 张候选统一 check：**60/60 PASS，0 FAIL**，无剔除。禁牌表内的复归荒野 / 很久以前 / 夏色帘幕 / 理时泰菲力 / 窃冠瓯柯本就未进入候选。
