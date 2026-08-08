# HOB 测试队列

## 当前状态

截至 2026-08-06，HOB 尚未在 MTG Arena 上线（官方日期 2026-08-11），也没有本运行产生的 Draft、Sealed 或构筑对局。因此本文件只列测试设计和纸面状态，不含胜率。

## Arena 上线前规则测试

| 优先级 | 测试 | 通过条件 | 失败时动作 |
|---|---|---|---|
| P0 | Adventure 牌按永久物面被导师找到，按 Adventure 面施放后进入放逐 | `Bilbo, Luckwearer`、`Beorn`、`Gandalf`、`Glamdring` 的区域和费用显示正确 | 标记规则 / 客户端问题，暂停组合结论 |
| P0 | Storied 达成和 enduring story 不会因失去三张条件永久物而消失 | `Thorin Oakenshield`、`Kíli`、`Dáin` 在前后状态均正确 | 复查 Release Notes 和规则文本 |
| P0 | Recruit 的 draw then discard 与“弃非地才造 token”顺序 | 只在弃非地时创建 Soldier，地牌不创建 | 修正所有 Recruit 牌的纸面收益估算 |
| P0 | Amass 不会制造多个可并存 Army，Army 具有 Goblin 类型 | `Bolg`、`Fearsome Goblin Pair`、`Gathering of Darkness` 状态正确 | 暂停 BR 原型评分 |
| P0 | Hone counter 直接提供 +1/+0，Dwalin / Sting 的重复计数 | Equipment 和装备生物的力量变化正确 | 暂停 Equipment 上限结论 |
| P1 | `The Eagles Are Coming!` 返回 token 后下次维护按返回数量造 Bird | 未踢和踢出模式均按实际拥有的生物处理 | 记录 token 区域处理差异 |
| P1 | `The Master of Lake-town` 生命损失与磨牌触发顺序 | 伤害、失血、Peer / Underworld Dreams 的触发可堆叠 | 单独建立 Peer 版本规则测试 |

## Prerelease 限制赛日志模板

每轮填写完整牌池、最终牌表和下列字段：

`日期 | 队列 | BO | 先后手 | 原型 | 地数 | 双色 / 溅色 | 调度 | 关键牌施放回合 | 失败点 | 是否改变评级`

首批重点不是追求样本量，而是验证：

- 五个双色原型是否有足够普通 / 非普通启用件。
- `Pinecone Strike`、`Bilbo's Deadly Slice`、`Warg Tactics` 等低稀有度互动的实际覆盖。
- RW Equipment 是否因 Equip 费用和承载生物不足而卡手。
- BG Ferocious 是否经常先有四力生物，还是在落后局空转。
- Recruit 在真实 17 至 18 地牌表中的 token 触发率。

## 构筑 A/B 测试

| 候选 | 对照 | 首测外壳 | 观察指标 | 成功条件 |
|---|---|---|---|---|
| Mirkwood Pathmaker | LandPlant 的三费铺地 / 身材牌 | 纯绿地数量身材 | T3/T4 身材、铺地后威胁密度、被去除后的损失 | 至少与基准牌同等稳定，且改善中盘攻击压力 |
| Wood Elves | Topiary Stomper / 其他三费 ramp | LandPlant、Elf Ramp | 进场地是否未横置、基础地目标剩余、Ashaya 联动 | 不降低关键回合绿源，提升四费动作可执行率 |
| Beorn's Hospitality | 非生物三费回报 | LandPlant Landfall 分支 | 每回合 Landfall 次数、指示物转化、对扫场恢复 | 主题边界确认后才纳入主牌 |
| The Great Goblin | 普通三费威胁 | BR Amass / Spells | 每回合 counters 触发、直伤、死亡后可用牌 | 至少有 10 张稳定放 counter 的牌 |
| Thranduil, Sindarin Liege | GU Elf 四费回报 | Elf Landfall | Adventure 找地质量、Landfall token、色源 | 四费时点可稳定提供场面或卡差 |
| Fateful Discovery | 非生物五费引擎 | Artifact / Treasure | Artifact 进场次数、空转回合、被拆后恢复 | 首回合落地后两回合内至少产生可见卡差 |
| Glamdring | 传统装备 / 法术引擎 | Graveyard Spells | 装备目标力量、实际减费、Adventure 回收牌数 | 不能只凭理论减费；需真实施法收益 |
| The Master of Lake-town | 三费黑色永久物 | Peer / Devotion | Peer 后磨牌、Underworld Dreams 触发、死后抽牌 | 明确成为备用赢点而非重复占位 |

## 数据校准要求

每个结论分开记录比赛数、小局数、先后手、BO、对手原型、牌表版本和样本窗口。没有这些字段时只写“样本观察”，不写“胜率提升”。
