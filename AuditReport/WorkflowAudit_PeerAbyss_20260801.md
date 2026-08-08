# PeerAbyss 第二轮工作流审计（2026-08-01）

## 结论

第二套测试证明，修正后的工作流已经能避免未来牌、颜色身份、最新印刷和简单地当量等第一轮问题，但仍缺少“组合规则图、颜色需求、导师副作用、生命预算、合法范围与优化目标”的可执行模型。自然语言可以发现这些问题，尚不能稳定证明牌表最优。

本轮产物：[PeerAbyssV2.md](DeckList/Pioneer_MonoBlack_PeerIntoAbyssWithDevotion/PeerAbyssV2.md)。

## 新发现

### P0：合法性口径

1. **备牌不是必须正好 15 张**：V1 的 5 张备牌在构筑赛中合法，只是浪费 10 个可用卡位。工作流原先的“60/15 复核”混淆了合法门禁与推荐构筑目标。
2. **换备不要求严格一换一**：规则只要求换备后主牌不少于 60、备牌不多于 15。优化器通常应保持 60 张来维持抽牌一致性，但这不是合法性要求。
3. **BO1 规则会变化**：Arena 自 2026-02-03 起重新允许 BO1 使用至多 15 张 sideboard 供游戏外效果访问，但仍没有传统局间换备。平台规则必须作为带日期的数据源，而不是写死 7 或 15。

参考：[威世智 Sideboard 规则说明](https://magic.wizards.com/en/news/feature/sideboard-2015-08-10)、[Arena 2026-02-02 公告](https://magic.wizards.com/en/news/mtg-arena/announcements-february-2-2026)。

### P1：构筑与规则模型

1. **单色不等于不会卡色**：V1 有 24 地，但四张 Nykthos 前期通常只产无色，三回合 `{B}{B}{B}` 的简化达成率只有 63.78%。需要按每回合有色源和具体符号计算，不能只数“黑色套牌的地”。
2. **缺少组合图**：系统需要把 Peer 与 Dreams/Sheoldred/Bloodletter、Bloodletter 与 Rush/Gray Merchant/Sign/Annex 建成带时点和条件的边，而不是只给每张牌一个粗粒度“终结”标签。
3. **缺少替代效应计算**：Bloodletter 只在己方回合翻倍生命损失；伤害导致的生命损失也会翻倍。没有规则层时，AI 很容易错误地放大对手回合的 Dreams 触发。
4. **缺少导师语义**：Wishclaw 的总费用可以分回合支付，但启动后将控制权交给对手；Beseech 的 bargain 可牺牲不同永久物，并只能免费施放法术力值 4 以下的目标。单纯比较“导师费用”会给出错误替代结论。
5. **缺少模式状态**：Scheming Silvertongue 的 prepared 状态、Room 已解锁门、Tithing Blade transform 后的献力变化，都需要在统一卡牌状态模型中表达。
6. **缺少生命预算**：Thoughtseize、Annex、Grim Tutor、Withering Torment 等牌都消耗生命；Sheoldred、Gray Merchant、Silvertongue、Meathook 又会回血。优化器应比较对快攻的净生命曲线，而非孤立评价卡牌。
7. **模块模板仍过度绑定种地示例**：第二套牌需要动态生成“抓牌惩罚、半血、献力、导师、手牌干扰”模块。固定 M1-M6 名称可保留，但实例与查询词必须由主题模型生成。

### P2：检索和度量

1. **词形仍会漏牌**：`o:"loses"` 没有命中写作 `they lose` 的 Sheoldred；完整模板 `o:"whenever an opponent draws a card"` 才补齐。查询生成器需要词形变体、模板库和已知锚点反查。
2. **缺少组合可达概率**：本轮只能手工计算地源、关键黑色符号、斩杀件/启动件出现率，尚未把导师、调度、Nykthos 献力、法术力与对手干扰放入同一模拟。
3. **缺少“死牌成本”**：Peer、Rush、重复 Dreams、第二张传奇地在组合未齐时价值差异很大；候选评分目前没有手牌滞留和重复抽取惩罚。
4. **没有自动检查备牌非互作**：Damping Sphere 能针对 Lotus，却会关闭己方 Nykthos；系统需要对换入后的完整 60+ 牌重新跑协同/冲突检测。

## 建议新增测试

1. 解析测试：60/5 应判合法但警告未填满；59/15、60/16 应失败；换备后 61/14 应合法但提示偏离 60 张优化目标。
2. 地基测试：Nykthos 无 Urborg 时不计作自然黑源，有 Urborg 时计作沼泽；分别计算 T3 BBB、T4 BBBB、T5 七费。
3. 规则测试：Peer+Bloodletter、Rush+Bloodletter 必须判定己方回合致死；对手回合 Dreams 触发不得被 Bloodletter 翻倍。
4. 导师测试：Beseech 找 Peer 只能入手；bargain 找 Rush 可免费施放但仍需支付 spree；Wishclaw 启动后对手获得控制权。
5. 模式测试：prepared 副本施放后解除 prepared；Room 只计算已解锁门；Tithing Blade 变换后重新计算献力。
6. 冲突测试：换入 Damping Sphere 后标记 Nykthos 失效，禁止把它当成无代价的 Lotus 对策。

## 本次修正

- 工作流已把牌表合法范围改为主牌不少于 60、备牌 0-15；60/15 只作为默认优化交付。
- 换备门禁改为主牌不少于 60、备牌不多于 15；一换一是默认策略而非规则。
- 第一轮审计中的 BO1 与换备描述同步更新。

仍未实现的部分包括验证 CLI、缓存/运行清单、组合图、规则层、概率模拟和对局日志闭环。
