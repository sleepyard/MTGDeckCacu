# HOB 系列评估运行清单

## 运行状态

| 字段 | 值 |
|---|---|
| 系列 | Magic: The Gathering | The Hobbit |
| 系列代码 | `HOB` |
| 运行模式 | `F 全卡表初评` |
| 结论截止 | `2026-08-06`（香港时间） |
| 目标平台 | MTG Arena；同时保留实体牌面语义 |
| 限制赛 | Play Booster Draft、Sealed；纸面分别推演 BO1 / BO3 |
| 构筑赛 | 预期发售后 Standard、Pioneer、Modern；另扫描仓库已有 Pioneer / Modern / Brawl 牌表 |
| 评价目标 | 限制赛可玩性、现有思路补强、新构筑种子并行 |
| 预算 | 不设上限；暂不纳入合成成本 |
| 官方完整牌表 | 是。官方预告称完整 Card Image Gallery 于 2026-07-31 可用 |
| HOB 规则牌覆盖 | 193 张独立规则牌，其中 188 张非基本地 / 非库存牌待评级，5 张基本地排除评级 |
| Scryfall 抓取 | `2026-08-06`，`set:hob unique:cards`，分页完整，193 张 |
| 原始快照 | [scryfall_hob_unique_cards_20260806.json](data/scryfall_hob_unique_cards_20260806.json) |
| 中文名 | 本次未执行逐张 mtgch 名称核对，报告以英文稳定键为准，中文名待补 |
| 对局数据 | 0。系列尚未进入 Arena（官方日期为 2026-08-11），无胜率结论 |

## 来源

- [官方收集与合法性说明](https://magic.wizards.com/en/news/feature/collecting-the-hobbit)：HOB 代码、HOB 全格式合法性、HOC 的独立 Eternal-legal 范围和重要日期。
- [官方机制说明](https://magic.wizards.com/en/news/feature/the-hobbit-mechanics)：Storied、Recruit、Hone Counters、Adventure、Amass 的规则文本。
- [官方卡图集](https://magic.wizards.com/en/products/the-hobbit/card-image-gallery)：完整牌图入口和牌面版本说明。
- [WPN 产品与补充包构成](https://wpn.wizards.com/en/products/the-hobbit)：Play Booster 数量、稀有度槽位、HOB 1–248 可开出范围和 Prerelease 日期。
- [Scryfall Cards API](https://api.scryfall.com/cards/search?q=set%3Ahob%20unique%3Acards)：结构化牌面快照来源。

## 数据状态

| 项目 | 状态 | 说明 |
|---|---|---|
| G1 数据完整性 | 通过 | 官方完整牌表已发布；Scryfall 分页返回 193 张独立规则牌；多面牌使用 `card_faces` |
| G2 全卡覆盖 | 通过 | 188 张非基本地有 Draft、Sealed、构筑用途与置信度；基本地 5 张列入库存但不评级 |
| G3 构筑候选 | 通过（纸面） | 已建立现有牌表补强表、新轴最小组件和 T0/T1 测试队列；未生成完整 60 张牌表 |
| G4 最终交付 | 部分通过 | 缺少 Arena 对局、聚合数据、逐张中文名和发售后合法性再核对，结论保持 C1 |

## 重要限制

1. HOB 尚未到 Arena 上线日；Scryfall 在本基准日把绝大多数新牌标为 `not_legal`，这是时间状态，不是牌力评价。
2. `HOB 1–248` 包含异画、场景、特殊框和可能的重印版本；本报告按规则身份去重，限制赛评价只对 Play Booster 实际可开出的 HOB 牌池负责。
3. 尚未取得 HOB 的实际补充包 collation 统计，因此只报告牌表密度，不把机制命中数换算为 `as-fan` 或抽到概率。
4. 所有强度文字是牌面和当前仓库牌表的纸面推演；没有基于样本的胜率或选牌顺位结论。
