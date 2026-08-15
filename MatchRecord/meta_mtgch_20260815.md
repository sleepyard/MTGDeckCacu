# 外部环境快照（mtgch.com / sbwsz，2026-08-15 抓取）

数据来源：mtgch.com（sbwsz.com 现跳转至此站）公开赛事牌表库（赛事结果来自 mtgtop8 收录）。该站无 Explorer 赛制，取**先驱（Pioneer）**作环境代理——与 Explorer 牌池接近；史迹（Historic）在站内无聚类数据。

## 先驱环境构成（近一周赛事上位，样本 171 套 / 12 原型，数据更新至 2026-08-14）

| 占比 | 原型 | 套数 | 示例牌表 id | 示例更新时间 |
|---:|---|---:|---:|---|
| 20.9% | UR Aggro（红蓝快攻） | 41 | 141588 | 2026-08-14 |
| 12.8% | The Rock（黑绿系中速） | 25 | 141179 | 2026-08-12 |
| 11.2% | Greasefang Parhelion（脂牙组合技） | 22 | 141178 | 2026-08-12 |
| 7.1% | Izzet Control（红蓝控制） | 14 | 140650 | 2026-08-11 |
| 7.1% | Red Deck Wins（纯红快攻） | 14 | 141590 | 2026-08-14 |
| 6.1% | Dimir Yorion（黑蓝约力昂） | 12 | 140622 | 2026-08-11 |
| 6.1% | Golgari Aggro（黑绿快攻） | 12 | 141187 | 2026-08-12 |
| 6.1% | UW Control（白蓝控制） | 12 | 140643 | 2026-08-11 |
| 4.1% | Arclight Phoenix（弧光凤凰） | 8 | 141192 | 2026-08-12 |
| 2.5% | Lotus Field（莲花田野组合技） | 5 | 140625 | 2026-08-11 |
| 1.5% | Golgari Sacrifice（黑绿牺牲） | 3 | 141182 | 2026-08-12 |
| 1.5% | Jeskai Control（洁斯凯控制） | 3 | 140637 | 2026-08-11 |

牌表详情接口：`GET https://mtgch.com/api/v1/deck/deck/{deck_id}/`；赛事列表接口：`/api/v1/deck/events/?format_code=pioneer`。

## 近期先驱赛事（截至抓取日）

| 日期 | 赛事 | 收录牌表 |
|---|---|---:|
| 2026-08-10 | Weekly Event | 4 |
| 2026-08-10 | MTGO Challenge 32 | 16 |
| 2026-08-09 | MTGO Challenge 32 ×2 | 16+16 |
| 2026-08-08 | MTGO Challenge 32 / Summer Sun's Zenith Qualifier | 16+4 |
| 2026-08-07 | MTGO Challenge 32 ×2 | 16+16 |

## 对 Forge 对手池的含义（对照现有对手 Sarkhan解印V4 / SimicFlashV1）

- 原型速度分布：**快攻 34%（UR Aggro + RDW + Golgari Aggro）、中速 13%、控制 21%、组合技 14%**——现有对手池（中速 + 节奏各一）只覆盖约 1/5 环境。
- 对照 8/8 真人样本（meta_20260808.md）：控制仍是硬伤；外部数据中 UW/Izzet/Jeskai/Dimir Yorion 合计 21%，优先级最高的补池方向。
- 快攻占 1/3 环境，UR Aggro 单原型 20.9% 一家独大，对手池完全空缺。
- 候选对手（按优先级）：UW Control（id 140643）> UR Aggro（id 141588）> The Rock（id 141179）；Greasefang/Lotus Field 为组合技，Forge AI 组合技失真，不宜作模拟对手。
- 2026-08-15 已入库 6 套外部对手（均通过 pioneer 合法性 + Arena 平台 + Forge 实现度核查，源牌表与说明见各 `DeckList/Pioneer_*Meta/` 目录）：
  - 控制：UW Control（`opp_UWControlMetaV1`）、Dimir Yorion（`opp_DimirYorionMetaV1`，艾斯波配色 80 张约力昂摞）
  - 快攻：UR Aggro（`opp_URAggroMetaV1`）、Red Deck Wins（`opp_RDWMetaV1`）、Golgari Aggro（`opp_GolgariAggroMetaV1`，勇德配色）
  - 中速：The Rock（`opp_TheRockMetaV1`，苏勒台配色）
- 注意：Scryfall 已移除 Explorer 合法性字段（Explorer 已并入 Pioneer），牌表落地走 `mtg_tool.py validate --format pioneer` + `check --platform arena` 双重核对。

## 标准（Standard）环境构成（近一周赛事上位，样本 226 套 / 12 原型，数据更新至 2026-08-14）

| 占比 | 原型 | 套数 | 备注 |
|---:|---|---:|---|
| 14.1% | Izzet Prowess | 42 | 已入库 `opp_IzzetProwessMetaV1`（id 140604，**含标准禁牌 Stormchaser's Talent，禁前冠军构筑**，作历史高压样本） |
| 11.5% | Mono Green Landfall | 34 | 已入库 `opp_MonoGreenLandfallMetaV1`（id 141578） |
| 9.1% | 4/5C Control | 27 | 已入库 `opp_FullColorControlMetaV1`（id 141567，WUBR） |
| 7.1% | Jeskai Tablet | 21 | 未入库 |
| 6.1% | Izzet Spellementals | 18 | 已入库 `opp_IzzetSpellementalsMetaV1`（id 141560，替代被禁的 Izzet Prowess） |
| 5.1% | Orzhov Aggro | 15 | 已入库 `opp_OrzhovAggroMetaV1`（id 141564） |
| 4.7% | UR Aggro | 14 | 与先驱 UR Aggro 同名不同表，未入库 |
| 4.4% | Selesnya Aggro | 13 | 未入库 |
| 4.4% | Superior Doomsday | 13 | 组合技，Forge AI 失真，不入库 |
| 3.7% | Mono Green Aggro | 11 | 未入库 |
| 3.4% | Superior Reanimator | 10 | 组合技，Forge AI 失真，不入库 |
| 2.7% | Dimir Aggro | 8 | 未入库 |

2026-08-15 已入库 4 套标准对手（均通过 standard 合法性 + Arena 平台 + Forge 实现度核查，源牌表与说明见各 `DeckList/Standard_*Meta/` 目录）。标准牌池 ≠ 先驱牌池，跨赛制对局只是压力测试样本，报告解读时注意标注。
