# Shrine V4（Battlefront Shrine Control / Pioneer / MTGA BO3）

V4 停止把约力昂作为主线，也不再维持独立的全力 Dance 自磨版本。约力昂的闪烁收益不足以覆盖 80 张牌的稀释、一个备牌位和 `{3}` 入手加五费施放的节奏成本；Dance 保留两张，作为控制结界与 Shrine 被处理后的批量恢复。

本版的目标是先存活、再以多个彼此独立的结界回报终结。所有早期防守永久物均可被 `United Battlefront` 直接部署，且大多可被 `Dance of the Manse` 回收。

## 最终导入牌表

```text
2 Archon of Sun's Grace
2 Authority of the Consuls
2 Banishing Light
1 Barkchannel Pathway
4 Botanical Sanctum
3 Branchloft Pathway
1 Brightclimb Pathway
2 Dance of the Manse
1 Darkbore Pathway
1 Depopulate
2 Fabled Passage
2 Forest
1 Hallowed Haunting
2 Hengegate Pathway
1 Indatha Triome
1 Island
1 Kyoshi Island Plaza
1 Mountain
4 Northern Air Temple
2 Omen of the Sun
3 Plains
1 Raffine's Tower
1 Sanctum of All
1 Sanctum of Shattered Heights
3 Sanctum of Stone Fangs
1 Sanctum of Tranquil Light
1 Swamp
3 The Birth of Meletis
4 The Spirit Oasis
2 Trial of Ambition
4 United Battlefront

Sideboard
2 Deafening Silence
2 Depopulate
2 Dovin's Veto
1 Hallowed Haunting
2 Heroic Intervention
2 Leyline Binding
2 Soul-Guide Lantern
2 Tear Asunder
```

机器计数：主牌 `60`，备牌 `15`，地牌 `24`，Shrine `15`，Battlefront 合法命中 `24`，直接扣血地产色 `0`。

## 为什么选这条线

| 旧方向 | 处理 | 原因 |
|---|---|---|
| 80 张约力昂 | 暂停 | 前十张看到 Battlefront 的概率从 60 张的 `52.77%` 降至 80 张的 `42.03%`；约力昂无法直接解决前期场面，闪烁 Go-Shintai 还会错过当回合结束步骤触发 |
| Dance 专职填坟 | 降为 Dance x2 | 填坟资源会进一步压缩主牌控制；两张保留为对抗拆场和中后期回收，而不是套牌唯一主轴 |
| Setessan Champion | 移除 | 三费不立即影响场面，且既不是 Battlefront 目标，也不能被 Dance 回收 |
| Shrine 单张工具箱 | 取消 | Northern、Stone Fangs、Spirit Oasis 等低费非生物 Shrine 提升至 3-4 张，以获得 Battlefront 密度、自然抽取率和 Dance 的坟场冗余 |

## 生存包

| 数量 | 费用 | 中文名 | English | 生存作用 |
|---:|---|---|---|---|
| 2 | `{W}` | 执政官威权 | Authority of the Consuls | 敌方生物横置进场；每有一个敌方生物进场便回 1，拖慢快攻与 haste 回合 |
| 3 | `{1}{W}` | 迈勒提斯创城史 | The Birth of Meletis | 找基本 Plains，之后造 0/4 墙并回 2；Battlefront 可直接放入 |
| 2 | `{2}{W}` | 太阳神的预兆 | Omen of the Sun | 闪现造两个 1/1 阻挡者并回 2；Archon 在场时还会再触发 Pegasus |
| 2 | `{1}{B}` | 野心祀炼 | Trial of Ambition | 对手牺牲一个生物；是两费 Battlefront / Dance 交集互动 |
| 2 | `{2}{W}` | 驱逐明光 | Banishing Light | 放逐任意非地永久物；三费且可由 Battlefront 直接部署 |
| 1 | `{2}{W}{W}` | 扫除人口 | Depopulate | 主牌紧急扫场。主牌普通生物很少，通常能比对手更早重建结界场面 |
| 4 | `{B}` | 北气和寺 | Northern Air Temple | Shrine 进场吸血，后续每张 Shrine 再吸 1；前期也能对冲痛失的节奏 |

`United Battlefront` 顶七可放入的 24 张牌为：Northern x4、Stone Fangs x3、Spirit Oasis x4、Tranquil Light x1、Shattered Heights x1、Authority x2、Birth x3、Omen of the Sun x2、Trial x2、Banishing Light x2。施放一张 Battlefront 后，顶七至少能放两张的简化概率为 `86.61%`。

## 赢点

| 轴线 | 关键牌 | 如何结束对局 | 对控制包的依赖 |
|---|---|---|---|
| 飞行吸血铺场 | Archon of Sun's Grace x2 | 每个结界进场造 2/2 飞马；飞马和 Archon 都有系命。Archon 在场时 Battlefront 一次放两个结界就是两个飞马 | Birth / Omen / Authority 争取到四费窗口 |
| 结界 token 终结 | Hallowed Haunting x1 主、x1 备 | 每次施放结界造随 Spirit 数成长的 Spirit Cleric；七个结界后全军飞行警戒 | 适合对慢速或扫场后的重建；它只计算“施放”，Battlefront / Dance 直接入场不会触发 |
| Shrine 非战斗伤害 | Northern x4、Stone Fangs x3 | Northern 的进场 / 后续触发与 Stone Fangs 第一主阶段吸血叠加，不需要攻击通过 | 以 Authority、墙、token 和去除拖回合，等 Shrine 数量滚起 |
| Shrine 资源与重建 | Spirit Oasis x4、Sanctum of All、Dance x2 | Spirit Oasis 把每张后续 Shrine 转成抓牌；Sanctum 找 Shrine；Dance 将被去除的结界一次回场 | 防守永久物和 Shrine 同时是 Dance 目标，避免重建时只恢复空场 |

`Archon of Sun's Grace` 是生物而非结界，因此不能被 Battlefront 或 Dance 直接部署。它被放为两张是为了让抽到一张的概率足够，同时不牺牲 Battlefront 目标密度；控制阶段应优先保护已落地的 Archon。

## 关键回合

- 第一回合：优先 Authority 或 Northern。没有一费动作时，下未横置的绿 / 白 / 蓝源，为第二回合 Birth、Trial 或 Battlefront 预备。
- 第二回合：Birth 找第三张 Plains 目标，Trial 处理单体威胁；面对横向铺场可先留 Omen of the Sun 闪现阻挡。
- 第三回合：Banishing Light 处理非地永久物，或在对手回合用 Omen 造两个阻挡者并回 2。
- 第四回合：Battlefront 优先拿“一个控制永久物 + 一个 Shrine / 资源永久物”。例如 Authority + Spirit Oasis、Trial + Northern、Birth + Banishing Light。对方生物太多时直接 Depopulate。
- 稳住后：先落 Archon，再用 Battlefront / Shrine / Dance 连续触发飞马；或用 Hallowed Haunting 把后续施放的结界转为飞行警戒 token。
- Dance：通常 X=3（五费）或 X=4（六费）才有价值。不要为了回一张两费牌而牺牲整回合；当坟场内有 Shrine 加控制结界时，它才是重建而非亏节奏。

## 无痛地基

| 数量 | 地 | 作用 |
|---:|---|---|
| 1 | Barkchannel Pathway | 早期绿 / 蓝二选一 |
| 4 | Botanical Sanctum | 前三地内稳定的绿 / 蓝 |
| 3 | Branchloft Pathway | 早期绿 / 白二选一 |
| 1 | Brightclimb Pathway | 白 / 黑二选一，支持 Trial 与 Northern |
| 1 | Darkbore Pathway | 绿 / 黑二选一 |
| 2 | Fabled Passage | 搜索八张基本地；早期横置是零生命成本的代价 |
| 2 | Hengegate Pathway | 白 / 蓝二选一，优先保障 Birth、Battlefront、Archon 与 Dance |
| 1 | Indatha Triome | 横置白 / 黑 / 绿与 domain 类别 |
| 1 | Raffine's Tower | 横置白 / 蓝 / 黑与 domain 类别 |
| 8 | 基本地 | Forest x2、Plains x3、Island / Mountain / Swamp 各 x1；保证 Birth、Fabled 与 Kyoshi 有持续目标 |

白源 13、蓝源 11、黑源 7、红源 3、绿源 14。红色 Shrine 与五色 Sanctum 主要是 Battlefront、Dance 或 Sanctum 链条的后期目标，不能把三张红源当作稳定四费红咒语曲线。起手至少两地概率为 `85.73%`；所有地均无直接生命支付，但 triome、Fabled 与部分慢地会以横置和颜色选择锁定换取生命安全。

## 备牌

- 生物快攻 / 中速：Depopulate x2、Leyline Binding x2 换入；优先换掉最慢的 Dance、Hallowed 与部分高费 Shrine。
- 控制：Dovin's Veto x2、Heroic Intervention x2、第二张 Hallowed Haunting 换入；换出 Trial、部分 Birth 和一张 Depopulate。
- 坟场：Soul-Guide Lantern x2 换入，不使用 Rest in Peace，以免关闭己方 Dance。
- 非生物组合技：Deafening Silence x2、Dovin's Veto x2 换入。Silence 会限制己方非生物咒语，但不限制 Battlefront / Dance 一次直接放入的多个永久物。
- 对手以神器 / 结界阻止 Dance：Tear Asunder x2 与 Leyline Binding x2 换入。

## 验证边界

- 主牌 60、备牌 15、英文名排序、同名牌上限：通过。
- 从实际导入块反向解析的 37 个唯一牌名全部通过 `f:pioneer game:arena date<=2026-08-01`；双面通路按正面可导入名称核对。
- 37 个唯一牌名全部通过 mtgch `items[].translated_name` 精确中文名核对。
- 尚未完成 Arena 客户端导入与真实 BO3 对局；控制强度、Archon 的存活率、Battlefront 双命中实际价值和各赢点转化率都需要日志验证，不能报告胜率。
