# HOB 系列骨架

## 结论摘要

HOB 是一套小型、五个明确双色主题的 Universes Beyond 扩展。限制赛的主要结构不是十个传统双色组合，而是五个有清晰金色信号和低稀有度支撑的原型：`WU Recruit / 第二张牌`、`RW Dwarf / Equipment / Storied`、`BR Goblin / Amass`、`BG Wolf / Ferocious`、`GU Elf / Landfall`。其余颜色组合可以靠单色质量拼接，但当前牌表没有同等的金色信号与调色密度。

纸面上白、黑、红的低费互动最完整，绿色在身材和法术力方面回报最高，蓝色更偏抓牌、弹回和墓地法术。限制赛的主要风险是：Storied 的达成需要三张 artifacts / legendaries / Sagas，Equipment 主题会争夺同一批卡位，Recruit 的 loot 价值取决于非地牌密度，Landfall 与额外下地牌需要足够地源，Amass 则容易被单体去除换成低效场面。

当前评级为 `C1`。最先应验证的是五个双色原型的实际密度、RW 与 BR 的生物交换能力，以及 HOB 是否比预期更慢。

## 牌表统计

| 分类 | 数量 |
|---|---:|
| 独立规则牌 | 193 |
| 普通 / 非普通 / 稀有 / 秘稀 | 70 / 55 / 53 / 15 |
| 生物 | 112 |
| 历险牌 | 17 |
| Saga | 8 |
| 传奇牌 | 55 |
| 非地神器 | 18 |
| 非基本地 | 8 |
| 基本地 | 5 |

### 机制密度（按规则文本召回，跨模块可能重复）

| 机制 / 标签 | 总数 | 普通 | 非普通 | 稀有 | 秘稀 |
|---|---:|---:|---:|---:|---:|
| Storied | 9 | 2 | 4 | 3 | 0 |
| Recruit | 10 | 4 | 3 | 2 | 1 |
| Amass Goblins | 14 | 4 | 7 | 3 | 0 |
| Landfall | 10 | 3 | 4 | 2 | 1 |
| Ferocious | 6 | 2 | 4 | 0 | 0 |
| Equipment 相关 | 21 | 7 | 3 | 9 | 2 |
| Dwarf 类型 / 相关文本 | 27 | 9 | 9 | 8 | 1 |
| Goblin 类型 / 相关文本 | 21 | 8 | 8 | 5 | 0 |
| Elf 类型 / 相关文本 | 19 | 7 | 6 | 5 | 1 |
| Wolf 类型 / 相关文本 | 12 | 4 | 4 | 4 | 0 |
| Bear 类型 / 相关文本 | 9 | 4 | 2 | 1 | 2 |

这些是召回数量，不是补充包出现率。Adventure 牌的机制文本在 Scryfall 顶层为空，本次已读取 `card_faces`。

## 机制与规则风险

### Storied

拥有 Storied 的永久物和三张 artifacts、legendaries、Sagas 会让玩家获得不可移除的 enduring story designation。达成后，即使后来失去三张计数永久物，故事仍然存在。限制赛里需要把自身的传奇和 Saga 当作“达成条件”而不是天然价值；构筑里则可用低费神器与传奇密度稳定触发。

### Recruit

先抓一张、再弃一张；只有弃掉非地才造 1/1 Human Soldier。它是滤牌、坟场填充和 token 生产的组合动作。评估 Recruit 牌时必须把“手里是否有可弃非地”与“是否愿意把地留在手里”分开，不能把每次 Recruit 都当作净生物。

### Hone Counters

每个 Equipment 上的 hone counter 直接让被装备生物获得 +1/+0，这是规则定义的计数效果，不是 Equipment 自身额外异能。Dwalin、Sting、Thorin 相关牌的收益需要按实际 Equipment 数量和重复加计数触发核算。

### Adventure、Amass 与多面牌

Adventure 在手牌、牌库和放逐区只具有永久物面，导师必须按永久物类别判断。Amass 先创建或选择 Army，再放置指定数量的 +1/+1 counters；Army 同时获得类型 Goblin，但不能把多个 Army 当成可并存的 token。所有评级都分别记录“低费 Adventure 模式”和“高费永久物模式”。

## 构筑环境基线

官方收集页将 HOB 标为全格式合法，但 HOC 是另一个 Eternal-legal 产品。HOB 预计在 8 月 11 日进入 Arena、8 月 14 日全球桌面发售；本报告把 8 月 14 日作为构筑牌表生效假设，并在测试前重新读取目标赛制合法性与禁牌表。

截至当前仓库基线，Standard / Pioneer / Modern 的主要环境方向仍包括绿色 Badgermole Cub、中速、Izzet 法术和黑色资源战。HOB 初评优先寻找能直接改善这些现有卡位的牌，而不是仅按 IP 主题推荐高费传奇。
