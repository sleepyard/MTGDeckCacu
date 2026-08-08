# Lantern 第三轮工作流审计（2026-08-01）

## 结论

Modern 大牌池测试证明，现有工作流的日期、颜色和合法性约束能够防止明显越界，但此前仍把“先驱 + MTGA”硬编码进多个验证步骤。修正后可以描述本次实体/MTGO Modern 运行；尚未实现的核心能力是候选二阶段排序、锁状态求解、时点模拟、资源可达性和自冲突检测。

本轮产物：[LanternV2.md](DeckList/Modern_ColorLessBlue_Lantern/LanternV2.md)。

## 新发现

### P0：赛制与平台参数泄漏

1. **格式合法性不能写死为先驱**：同一张 `Karn, the Great Creator` 当前在 Modern 合法、在先驱禁用。工作流若复用先驱结论，会错误排除 Modern 候选。
2. **平台可用性不能写死为 Arena**：V1 明显使用实体/MTGO Modern 牌池。强制 `game:arena` 会删除核心牌并让优化目标失真。
3. **历史禁牌记忆不可靠**：`Mox Opal` 曾被 Modern 禁用，但当前官方 Modern 禁牌表中已不存在。合法性必须带格式和基准日期读取。

### P1：组合状态与自冲突

1. **Lantern 不是二元标签组合**：有效锁至少包含“对手牌顶已知、危险度已评估、当前有足够未横置否决件、对手没有额外抓牌/洗牌窗口”。仅统计 Lantern 与 mill 牌数量不能证明已锁定。
2. **Bridge 需要连续手牌状态**：Bauble 在对手维持抓牌会在其战斗前增加己方手牌，Saga 构装体也可能被自己的 Bridge 禁止攻击。优化器必须逐阶段维护手牌数，而不是只把 Cookbook 标成“弃牌协同”。
3. **导师规则不能只看法术力值**：Urza's Saga 检查印刷费用正好为 `{0}` 或 `{1}`，不能找费用 `{X}` 的 Engineered Explosives；Whir 按牌库中的法术力值检查，可用 X=0 找到它但不会带充电指示物。
4. **improvise 不支付有色符号**：29 个神器不等于 Whir 的 `{U}{U}{U}` 已满足。地源模型需要把固定有色费用与可被 improvise 支付的 X 分开。
5. **对称效应需要对手模型**：Ghoulcaller's Bell 同时磨双方，可能帮助 Goryo's、Living End 或己方 Academy Ruins；Pyxis 避免填坟，但永久放逐自己的牌。没有对局状态时不能给两者固定分数。
6. **银弹会伤害自己**：Vexing Bauble 反制己方零费 Mox/Bauble/Jar；Void Mirror 会反制未花有色费的己方咒语；Damping Sphere 提高己方连续施法成本；Harbinger 会关闭并清除己方 Saga。当前工作流没有双向规则扫描。
7. **保护牌覆盖面不同**：Welding Jar 只处理 destroy，Padeem 只处理取目标，反击可覆盖清场但受费用和时点限制。统一“保护”标签会高估覆盖率。

### P2：大牌池检索和度量

1. **宽查询结果不可直接评审**：本轮牌顶查询命中 374，反击精确到 UB/MV≤3 后仍有 146。系统需要召回层与排序层，不能把长列表交给模型人工扫完。
2. **查询命中数不是覆盖证明**：自然语言模板会同时召回大量与 Lantern 无关的己方牌顶、一次性效果和高费生物。每个模块需要正例、反例和角色必需字段。
3. **缺少锁冗余指标**：本轮手工计算 V1/V2 到 T3 自然见到 Lantern+否决件为 29.73%/35.21%，但未包含调度、Saga、Whir、Bauble 信息、多个否决窗口和对手洗牌地。
4. **缺少 metalcraft 时序求解**：Mox 是否启用取决于手牌中的零/一费神器、地、传奇规则和施放顺序。简单“神器数量≥3”会把不可执行手牌误判成功。
5. **备牌会破坏工具箱密度**：换出神器会降低 Mox、Whir improvise、Saga 构装体和 Tezzeret 回报；换入非神器反击不能只按一换一结束检查。
6. **指定牌名能力需要环境字典**：Needle、Flute、Surgical 的价值取决于对方套牌版本和已见牌。系统需要从对手牌表/日志生成名称优先级，而不是写静态指南。
7. **慢速磨牌需要比赛时钟指标**：理论上能锁住不等于能在 MTGO 对局时钟内完成。工作流目前没有操作次数、平均决策耗时或超时失败标签。

## 建议新增自动化测试

1. 参数测试：同一候选在 `format=pioneer/platform=arena` 与 `format=modern/platform=mtgo` 下应产生不同合法性与平台结论。
2. 自冲突测试：Vexing Bauble + Mox Opal、Void Mirror + 无色支付神器、Cursed Totem + Emry/Spellskite、Harbinger + Urza's Saga 必须生成警告。
3. 导师测试：Saga 可找 Mox/Bauble/Jar，不可找 Engineered Explosives；Whir X=0 可找 Explosives，X=3 可找 Bridge。
4. 费用测试：三个可横置神器只能支付 Whir 的 X，不能替代 `{U}{U}{U}`；River 在不同下地时点返回不同颜色。
5. Bridge 测试：Bauble 在己方回合启动后，对手维持抓牌必须更新 Bridge 攻击阈值；己方构装体也接受同一限制。
6. 锁状态测试：对手有 fetchland、瞬间抓牌、两个危险牌顶或坟场回报时，单一 Shredder 不得判定为硬锁。
7. 备牌测试：每个换备方案重新计算神器数、零费数、蓝源、黑源、Whir 目标、metalcraft 与 Bridge 排空速度。
8. 性能测试：对 300+ 召回结果执行稳定的硬过滤和评分，保存淘汰原因、查询哈希与截断位置。

## 本次已修正文档

- 赛制合法性、官方禁牌表与平台可用性改为读取任务参数，不再硬编码先驱/MTGA。
- Scryfall 基础过滤改为 `f:{format}`，`game:arena` 只在目标平台为 MTGA 时追加。
- 双源验证拆成目标赛制合法、目标平台可用和中文名三个独立字段。
- 增加大牌池二阶段过滤要求，并明确记录原始命中、截断和排序依据。
- “大造物者卡恩为先驱禁牌”改为带格式的示例，防止跨赛制错误复用。

仍需代码实现：牌表 parser、Scryfall/mtgch client、缓存与运行清单、规则图、时点状态机、资源/锁概率模拟、双向冲突扫描、换备重算和对局日志闭环。
