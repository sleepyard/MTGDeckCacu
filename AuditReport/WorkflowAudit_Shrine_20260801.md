# 工作流第四轮审计：Pioneer 五色 Shrine 种子补全

基准日期：`2026-08-01`  
输入：`DeckList/Pioneer_FullColor_Shrine/ShrineV1.md`  
输出：`DeckList/Pioneer_FullColor_Shrine/ShrineV2.md`

## 结论

本轮成功从 17 张主题种子补出 Pioneer / MTGA BO3 的 60+15，并验证 V1 已覆盖当前目标牌池全部 16 张 Shrine。工作流原有 A“从零构筑”和 B“完整牌表优化”都不能准确描述这类输入；若强行执行 B，会先把“有意提供的种子池”当成非法牌表，再要求不存在的逐张砍入砍出。应新增 C“主题种子补全”。

## 本轮发现的问题

### P0：缺少“种子池”输入类型

- V1 只有 17 张且没有地 / 备牌，但语义不是失败的 60 张牌表，而是用户希望保留的主题集合。
- 现有阶段 0b 的 `主牌 >= 60` 合法门禁会正确判定它不能参赛，却不能决定后续应走“补全”还是“修复错误导入”。
- 需要把解析结果分类为：完整牌表、主题种子、候选池、导入损坏。种子模式应记录必留 / 可调锚点，再从缺口补足 60+15。

### P0：色源不能只按颜色计数

- `White Lotus Hideout` 的任意色只能施放 Lesson / Shrine；`Plaza of Heroes` 的第一种任意色只施放传奇咒语；二者都不能无条件为 Setessan 或备牌瞬间供色。
- 五色套牌若把它们记成普通五色源，会严重高估曲线可施放性。
- 色源模型至少需要 `unrestricted`、`spell_type_restricted`、`legendary_restricted`、`existing_permanent_colors`、`filter_only` 五类能力，并按具体咒语计算可用源。

### P0：类别系统需要按卡牌类型命名空间校验

- Shrine 是结界类别，不是生物类别。Go-Shintai 的类型栏含 `Enchantment Creature — Shrine`，仍不能为“选择一个生物类别”的效应选择 Shrine。
- 只做字符串匹配会错误推荐 `Secluded Courtyard` / `Unclaimed Territory`。
- 候选引擎应保存 subtype 所属 card type，并在部族 / 类别地搜索时验证目标效应要求的是 creature type、land type 还是其他 subtype。

### P1：全印刷平台校验仍需要统一实现

- `Jukai Naturalist`、`Destiny Spinner`、`Heroic Intervention`、`Tear Asunder`、`Plaza of Heroes` 等牌的最新印刷不一定带 Arena 标记，但较早印刷可用。
- `/cards/named` 或 collection 的默认印刷不能承担 oracle 级平台结论。本轮通过 `f:pioneer game:arena` 的全印刷搜索复核。
- 工作流已有文字要求，但缺一个统一的 `any_print_available(oracle_id, platform, cutoff_date)` 可执行门禁和通过印刷记录。

### P1：触发式 Shrine 需要“异能预算”而不只是曲线

- Go-Shintai 在结束步骤还需 `{1}`；`Sanctum of Fruitful Harvest` 第一主阶段产生的 mana 不能跨阶段保留。
- Weaver 复制异能另需 `{G}` 和横置；Shared Purpose 与另外四张 Go-Shintai 的 `If you do` / `When you do` 模板不同。
- 只检查咒语曲线会得到“本回合可全横置”的错误建议。节奏模块应记录未来步骤的保留 mana 与触发支付窗口。

### P1：找地引擎需要剩余目标状态

- Aang 从牌库找基本地到手；Kyoshi 会一次找 X 张并在后续 Shrine 进场时继续找。
- 本表 6 张基本地足够启动，但中盘可能耗尽；之后 Kyoshi 触发仍会上堆叠但找不到牌。
- 基本地目标校验不能只做 `> 0`，应估算搜索次数、目标消耗和不同基本地颜色需求。

### P2：Windows 查询传输层需要结构化封装

- 本轮 PowerShell `Invoke-RestMethod` 直连 Scryfall 多次返回 400；同一查询使用带默认 User-Agent 的 `curl` 正常。
- 含精确牌名、引号、撇号和日期过滤时，宿主 shell 拼接也容易产生二次转义错误。
- 应使用统一 HTTP 客户端、显式 User-Agent 和参数编码，不把查询 DSL 手工拼成 shell 字符串；原始 URL、状态与响应体应进入运行日志。

## 缺少的自动化能力

1. 输入分类器：完整牌表 / 主题种子 / 候选池 / 损坏导入。
2. 逐咒语色源矩阵：计算某张地是否能为某张具体咒语或异能支付。
3. subtype 命名空间验证：阻止把结界类别当生物类别。
4. trigger budget：记录主阶段 mana、结束步骤 `{1}`、Weaver `{G}` 等保留费用。
5. 搜索目标消耗模型：跟踪基本地 / 指定类型目标的剩余数量。
6. 任一历史印刷平台门禁：输出实际通过的 set / collector number / arena_id。
7. MTGA 客户端导入验证：当前只能校验文本格式，不能证明客户端已接受全部 TLA / 历史印刷牌。
8. 实战数据回流：按对局、先后手、调度、卡色、备牌换入和关键牌表现更新可调仓位。

## 已更新工作流

- 新增模式 C“主题种子补全”，避免把 17 张锚点误作损坏的完整套牌。
- 阶段 0b 增加输入语义分类与种子锚点处理。
- 构筑阶段增加逐咒语受限色源矩阵、subtype 命名空间、跨阶段触发支付和搜索目标消耗检查。
- 机器门禁增加“受限色源不得计作无条件色源”和“选择生物类别时只能使用 creature subtype”。

## 本轮验证状态

- 候选检索：完成，含 16 张 Shrine 全集与七类支援模块宽召回。
- 最终牌表 Pioneer / Arena：全部通过任一历史印刷口径。
- mtgch 中文名：44 个最终唯一牌名全部精确命中。
- 数量 / 同名牌 / 导入文本：通过。
- 官方规则交叉检查：Shrine subtype 结论通过 NEO 官方发行说明。
- 未执行：Arena 客户端实际导入与真实 BO3 对局；不能输出胜率结论。
