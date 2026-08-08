# 工作流新测试审计：Shrine 种子转 MTGA Brawl

基准日期：`2026-08-01`  
输入：`DeckList/Pioneer_FullColor_Shrine/ShrineV1.md`  
输出：`DeckList/Brawl_FullColor_Shrine/ShrineV1.md`

## 结论

本轮按模式 C 将 17 张 Pioneer / MTGA Shrine 主题种子转换为普通 Brawl 的 `1 + 99`。输入不是损坏的完整牌表，因此没有覆盖原文件；输出进入独立 Brawl 目录，避免把 Pioneer 与 Brawl 的合法性、牌数和禁牌语义混在同一版本链中。

最终牌表保留全部 17 张输入牌，补入 5 张 Arena Honden 与 `Go-Shintai of Life's Origin` 指挥官，并以结界中速控制为支援骨架。机器门禁覆盖数量、单卡、颜色身份、禁牌、截止日期、Arena 任一历史印刷和中文名。

## 阶段 0：参数与输入语义

| 参数 | 本次值 |
|---|---|
| 输入类型 | 主题种子，模式 C |
| 主题边界 | Shrine 数量与触发；结界支援允许，五色泛用好牌不得挤掉种子 |
| 代表牌 | Sanctum of All、The Spirit Oasis、Northern Air Temple |
| 平台 / 赛制 | MTGA 普通 Brawl，BO1 |
| 定位 | 娱乐向但保持强度 |
| 颜色 | 五色 |
| 预算 | 无上限 |
| 行侣 | 禁用，不占用构筑与 UI 语义 |

对“MTGA 环境 EDH”的解释：Arena 官方把 Brawl 定义为 Commander-style 的 100 张单卡制 1v1 格式；普通 Brawl 有一次免费调度，Competitive Brawl 没有，且两者禁牌表不同。本次主题目标选择普通 Brawl。

## 阶段 0b：体检

- 输入共 17 张：16 张 Shrine 加 `Aang's Journey`，无地、无指挥官、无备牌。
- 语义是需要补全的种子，不是非法的完整牌表。
- 核心玩法推断：用低费 Shrine 建立计数，以持续抓牌、吸血、直伤、去除和衍生物将每张后续 Shrine 放大；五色支援负责调色、保护和重建。
- 17 张种子全部标记为“必留”。

## 阶段 1：规则基线

官方普通 Brawl 基线：一名来自 Arena 系列的传奇生物或鹏洛客指挥官、99 张同色身份牌、除基本地外单卡、无备牌、25 生命、BO1 和一次免费调度。

本次使用 `2026-08-01` 的官方 Brawl 禁牌表。最终牌表未命中 Agent of Treachery、Ancient Tomb、Demonic Tutor、Mana Drain、Wash Away 等 Brawl 禁牌。Historic、Commander 与 Competitive Brawl 的禁牌结论没有复用到普通 Brawl。

## 阶段 2：分模块检索

所有 Scryfall 查询统一使用 `game:arena date<=2026-08-01`，候选按 oracle 去重；以下统计是原始查询命中，不是最终入选数。

| 模块 | 查询方向 | 原始命中 |
|---|---|---:|
| M1 Shrine | `t:Shrine` 或 oracle 提及 Shrine | 28 |
| M2 结界回报 A | 结界进场 / 施放结界触发 | 10 |
| M2 结界回报 B | 结界咒语加抓牌 | 4 |
| M3 找牌 | 搜索结界 / 传奇牌 | 7 |
| M3 回收 | 返回目标 / 全部结界 | 8 |
| M4 调色 A | 四费及以下五色神器 | 101 |
| M4 调色 B | 绿色基本地 / 额外下地 | 120 |
| M5 互动 A | 四费及以下广域单体去除 | 60 |
| M5 互动 B | 消灭 / 放逐全部生物 | 50 |
| M6 保护 | 己方永久物辟邪 / 不灭、结界帷幕 | 12 |

完整 Shrine 检索得到 22 张 Arena Shrine（含指挥官）与 6 张直接支援。输入覆盖其中 16 张 Shrine 和 `Aang's Journey`；增量补齐五张 Honden、指挥官及直接支援。

## 阶段 3：方向比较

| 方向 | 优先级 | 结论 |
|---|---|---|
| A 完整 Shrine 中速控制 | 主题保真 > 生存 > 稳定性 | 采用；保留全部 Shrine，以互动、保护、回收解决 1v1 节奏 |
| B 精简 Shrine 五色强牌 | 胜率 > 主题保真 | 放弃；会移除慢速 Honden，不符合输入种子的测试目标 |
| C 纯结界连锁 | 组合技 > 互动 | 放弃；100 张单卡制缺少稳定冗余，且早期生存预算不足 |

本次自动选择权重：主题保真 `40%`、生存与互动 `25%`、五色稳定性 `20%`、重建能力 `15%`。

## 阶段 4：双源与机器门禁

### Scryfall

- collection API 首轮以默认印刷返回 95 个 oracle，但 48 个默认印刷没有 `arena_id`。这只说明默认印刷不在 Arena，不能推出 oracle 不可用。
- 改用 `game:arena date<=2026-08-01` 分组精确查询全部历史印刷后，最终 95 个唯一牌名全部命中 Arena 版本并为 Brawl legal。
- `Sisay, Weatherlight Captain` 是唯一未命中 Arena 历史印刷的初选项，替换为 Arena ID `98662`、`TLE #47` 的 `Captain Sisay`。
- 所有牌的颜色身份均为 `Go-Shintai of Life's Origin` 的五色身份子集。

### mtgch

- 单次 `card-names` 查询曾长时间等待，但最终成功；没有把慢响应记作缺失。
- 后续使用每批 15 个受控并发请求查询 `GET /api/v1/card-names/?q={name}&size=50`。
- 最终结果：请求 `95`，完成 `95`，`items[].name` 精确匹配且 `translated_name` 非空 `95`，传输失败 `0`，缺失 / 歧义 `0`。

### 数量与格式

| 门禁 | 结果 |
|---|---|
| Commander | 1 |
| Deck | 99 |
| 总计 | 100 |
| 地 | 38 |
| 牌库 Shrine | 21 |
| Shrine 总数（含指挥官） | 22 |
| 非基本地重复 | 0 |
| 备牌 | 0 |
| V1 种子保留 | 17 / 17 |

## 新发现

### P0：工作流需要独立的 Brawl / EDH 参数组

原工作流的默认 `60/15`、BO3 与同名上限不适用于 Brawl。Brawl 门禁必须改为 `1 commander + 99`、除基本地外单卡、颜色身份、无备牌、25 生命和 BO1；普通 Brawl 与 Competitive Brawl 还必须分别读取禁牌表。

### P0：格式合法性与 Arena 历史印刷仍必须分离

默认印刷的 `arena_id=null` 在本轮产生 48 个假阴性。机器门禁必须先按 oracle 聚合全部印刷，再判断截止日期前是否存在 Arena 版本；请求失败、默认印刷无 ID 与真实零印刷是三种状态。

### P1：重平衡 / 替代版本需要显式处理

初选的 `Sisay, Weatherlight Captain` 没有当前 Arena 历史印刷命中，不能仅凭记忆或旧牌表放行。`Captain Sisay` 提供同角色替代并通过门禁。工作流应记录替代前后 oracle、Arena ID 与能力差异。

### P1：Brawl 的生存预算不能沿用多人 EDH

普通 Brawl 是 1v1、25 生命。主题牌表仍需要一至二费互动、四费扫场和主牌保护；不能用纸质多人 Commander 的较慢节奏为缺少早期动作辩护。

### P1：五色地基必须保留受限色源分类

`White Lotus Hideout` 的免费彩色 mana 只可施放 Lesson / Shrine，`Plaza of Heroes` 的彩色 mana 主要服务传奇咒语，`The World Tree` 要到六地才全局调色。三者均不能直接记作普通五色源。

### P1：Brawl 需要指挥官可访问性模型

指挥官可反复从指挥区施放，但每次增加 `{2}`。它不计入自然抽取概率；构筑评价应分别记录四费首次施放、指挥官税和五色起动式异能，而不是把指挥官混进 99 张曲线统计。

## 已更新工作流

- 模式 C 从硬编码“补成 60/15”改为按目标赛制构筑档案补全。
- 阶段 0 增加目标赛制 / 队列和指挥官策略；阶段 1 强制区分普通 Brawl、Standard Brawl 与 Competitive Brawl。
- 候选模块新增 M9 指挥官，M6 备牌改为仅在目标赛制允许时启用。
- 构筑与机器门禁新增 `Commander + 99`、单卡、颜色身份、无备牌、指挥官税和独立抽牌母体规则。
- 交付格式新增 MTGA `Commander` / `Deck` 两块，并禁止为 Brawl 生成 `Sideboard`。

## 验证边界

- 已完成：规则与禁牌基线、候选检索、100 张构筑、种子保留、Scryfall / mtgch 双源、历史印刷、颜色身份、数量和单卡门禁。
- 未完成：Arena 客户端真实导入、客户端对 TLE / HA3 / HA6 印刷的显示验证、真实 BO1 对局和调度日志。
- 因未执行对局，不输出胜率、指挥官分档或对局强度结论。

来源：[Wizards Brawl format](https://magic.wizards.com/en/formats/brawl)、[Wizards banned and restricted list](https://magic.wizards.com/en/banned-restricted-list)、[Introducing Competitive Brawl](https://magic.wizards.com/en/news/mtg-arena/introducing-ranked-brawl)、Scryfall API、[mtgch API docs](https://mtgch.com/api/v1/docs)。
