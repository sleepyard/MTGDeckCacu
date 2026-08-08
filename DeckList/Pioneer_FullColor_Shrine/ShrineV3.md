# Shrine V3：批量入场、坟场回场与约力昂方向

基准日期：`2026-08-01`。目标赛制 / 平台：Pioneer、MTGA BO3、无预算上限。

V3 根据实测反馈撤销 V2 的三个假设：不再使用 `Setessan Champion`，不再把 Shrine 默认限制为各一张，也不再用大量支付生命的通用五色地。下面给出三套完整方案：A 是建议先测试的 60 张 `United Battlefront` / `Dance of the Manse` 混合版，B 是专职填坟回场版，C 是 `Yorion, Sky Nomad` 80 张行侣版。

## 先纠正一个门禁错误

`Dance of the Manse` 的 ELD 印刷有 `arena_id=70333`，当前为 Pioneer 合法且可在 Arena 使用。此前候选筛选把它排除是平台验证的假阴性，不是牌池问题。本轮精确查询结果如下：

| 中文名 | English | 费用 | 准确用途 |
|---|---|---|---|
| 联合战线 | United Battlefront | `{3}{W}` | 看顶七，把至多两个法术力值不高于 3 的非生物、非地永久物直接放进战场 |
| 全宅起舞 | Dance of the Manse | `{X}{W}{U}` | 从坟场回场至多 X 个法术力值不高于 X 的神器 / 非灵气结界；X 至少 6 时它们额外成为 4/4 生物 |
| 游空牧鸟约力昂 | Yorion, Sky Nomad | `{3}{W/U}{W/U}` | 行侣要求主牌至少 80 张；进场暂时放逐其他非地永久物并在下一结束步骤同时送回 |

行侣当前不是可直接从备牌施放的“第八张手牌”。每局一次，只能在可施放法术的时机支付 `{3}`，把行侣从备牌置入手牌，之后仍需支付正常施放费用。约力昂占用一个备牌位置，因此可自由换备的牌只有 14 张。

## 三方向比较

| 方向 | 主牌 | Shrine | 核心密度 | 优点 | 主要代价 |
|---|---:|---:|---|---|---|
| A Battlefront / Dance 混合（建议先测） | 60 | 17 | 25 个 Battlefront 合法命中；Dance x2 | 批量入场稳定、零直接扣血地、对手首局生物去除目标少 | 高费 Shrine 数量被压低，红色硬施放能力弱 |
| B Dance 填坟 | 60 | 20 | Cache Grab x4、Founding x3、Dance x3 | 能回收 Go-Shintai 与四 / 五费 Shrine，爆发上限最高 | 依赖坟场且需要先投入填坟资源 |
| C Yorion ETB | 80 | 23 | 32 个 Battlefront 命中；固定行侣约力昂 | 约力昂重复 Northern、Spirit Oasis、Omen、Trial 等进场异能 | 关键四张牌的自然抓取率降低，备牌少一个位置，整体更慢 |

简化超几何结果：

- 前十张看到 `United Battlefront`：60 张四张同名为 `52.77%`，80 张四张同名为 `42.03%`。
- 已经施放 Battlefront 后，顶七至少有两个合法目标：A 为 `88.57%`，C 为 `85.98%`。
- 起手至少两地：24/60 为 `85.73%`，32/80 为 `85.32%`。
- 起手至少一个未横置绿源：A 的 12/60 为 `80.94%`，C 的 16/80 为 `80.44%`。
- 看十二张时自然见到 Dance：A 的 2/60 为 `36.27%`，B 的 3/60 为 `49.46%`，C 的 3/80 为 `39.00%`。

这些数字只衡量抽牌结构，不代表对局胜率。

## A：Battlefront / Dance 混合版（推荐）

```text
1 Barkchannel Pathway
4 Botanical Sanctum
3 Branchloft Pathway
1 Brightclimb Pathway
2 Commune with Spirits
1 Crescent Island Temple
2 Dance of the Manse
2 Darkbore Pathway
2 Fabled Passage
2 Forest
2 Founding the Third Path
1 Hengegate Pathway
1 Indatha Triome
1 Island
1 Ketria Triome
1 Kyoshi Island Plaza
1 Mountain
3 Northern Air Temple
2 Omen of the Hunt
4 Omen of the Sea
1 Overgrown Farmland
1 Plains
1 Raffine's Tower
1 Sanctum of All
2 Sanctum of Fruitful Harvest
1 Sanctum of Shattered Heights
3 Sanctum of Stone Fangs
2 Sanctum of Tranquil Light
1 Swamp
1 The Restoration of Eiganjo
3 The Spirit Oasis
2 Trial of Ambition
4 United Battlefront

Sideboard
2 Deafening Silence
2 Depopulate
2 Dovin's Veto
2 Heroic Intervention
3 Leyline Binding
2 Soul-Guide Lantern
2 Tear Asunder
```

### A 的结构

- Battlefront 的 25 个合法命中：14 张三费以下非生物 Shrine，Omen of the Sea x4、Omen of the Hunt x2、Founding x2、Restoration x1、Trial x2。
- `Omen of the Sea` 取代笨重的 Setessan：两费立即调整牌顶并抓一张，之后可牺牲进坟场供 Dance 回收。
- `Omen of the Hunt` 被 Battlefront 放入时直接拉基本地，既补色又从四地跳到五地；它也是 Dance 与约力昂可重复利用的结界。
- `Founding the Third Path` 可 read ahead 到第二章立即磨四，或第一章免费施放手中的 Commune。第三章可以再次施放坟场里的 Battlefront / Dance，但仍需支付被复制咒语的费用。
- `The Restoration of Eiganjo` 第一章找基本 Plains；第二章可以弃一张法术力值不高于 2 的 Shrine，并以反身触发把刚弃的牌横置放回战场。
- `Trial of Ambition` 是 Battlefront / Dance 都能部署的进场牺牲去除。首局主牌几乎没有普通生物，使对手的生物点杀缺少目标。
- `Crescent Island Temple` 是主要战斗终结；Stone Fangs 与 Northern 提供不依赖战斗的吸血终结。

## B：Dance 专职填坟版

```text
1 Barkchannel Pathway
4 Botanical Sanctum
3 Branchloft Pathway
1 Brightclimb Pathway
4 Cache Grab
1 Crescent Island Temple
3 Dance of the Manse
2 Darkbore Pathway
2 Fabled Passage
2 Forest
3 Founding the Third Path
1 Go-Shintai of Ancient Wars
1 Go-Shintai of Hidden Cruelty
1 Go-Shintai of Lost Wisdom
1 Go-Shintai of Shared Purpose
1 Hengegate Pathway
1 Indatha Triome
1 Island
1 Ketria Triome
1 Kyoshi Island Plaza
1 Mountain
3 Northern Air Temple
4 Omen of the Sea
1 Overgrown Farmland
1 Plains
1 Raffine's Tower
1 Sanctum of All
1 Sanctum of Fruitful Harvest
1 Sanctum of Shattered Heights
3 Sanctum of Stone Fangs
2 Sanctum of Tranquil Light
1 Swamp
3 The Spirit Oasis
2 Trial of Ambition

Sideboard
2 Deafening Silence
2 Depopulate
2 Dovin's Veto
2 Heroic Intervention
3 Leyline Binding
2 Soul-Guide Lantern
2 Tear Asunder
```

### B 的结构

- `Cache Grab` 每次磨四并从中拿回一个永久物；通常把地、关键 Shrine 或 Omen 入手，其余牌成为 Dance 目标。
- Founding 第二章再磨四，第三章可重施 Cache Grab；`Go-Shintai of Lost Wisdom` 也可以在需要时以己方为目标继续填坟。
- Dance 的实际总费用：X=2 为 4 费、X=3 为 5 费、X=4 为 6 费、X=5 为 7 费、X=6 为 8 费。通常以 X=3 或 X=4 回收，而不是等待八费模式。
- X=3 能回收 Northern、Stone Fangs、三个三费 Shrine、Omen、Founding 与 Trial；X=4 进一步覆盖四费 Go-Shintai、Crescent 与 Kyoshi；X=5 才能回收 Sanctum of All。
- `Soul-Guide Lantern` 取代 Rest in Peace 作为备牌坟场针对，避免关闭己方 Dance；它本身还是 Dance 能回收的神器。

## C：约力昂 80 张 ETB 版

```text
Companion
1 Yorion, Sky Nomad

Deck
2 Barkchannel Pathway
4 Botanical Sanctum
4 Branchloft Pathway
1 Brightclimb Pathway
3 Commune with Spirits
1 Crescent Island Temple
3 Dance of the Manse
3 Darkbore Pathway
4 Fabled Passage
3 Forest
3 Founding the Third Path
1 Hengegate Pathway
1 Indatha Triome
1 Island
1 Ketria Triome
1 Kyoshi Island Plaza
1 Leyline Binding
1 Mountain
4 Northern Air Temple
3 Omen of the Hunt
4 Omen of the Sea
1 Overgrown Farmland
3 Plains
1 Raffine's Tower
1 Sanctum of All
1 Sanctum of Calm Waters
3 Sanctum of Fruitful Harvest
1 Sanctum of Shattered Heights
4 Sanctum of Stone Fangs
2 Sanctum of Tranquil Light
1 Southern Air Temple
1 Swamp
2 The Restoration of Eiganjo
4 The Spirit Oasis
2 Trial of Ambition
4 United Battlefront

Sideboard
2 Deafening Silence
2 Depopulate
2 Dovin's Veto
2 Heroic Intervention
2 Leyline Binding
2 Soul-Guide Lantern
2 Tear Asunder
```

### C 的结构

- 主牌严格 80 张，32 地；约力昂单独位于行侣栏并计入 15 张备牌，所以 `Sideboard` 块只有 14 张。
- 32 个 Battlefront 命中保持与 A 相近的比例，但四张 Battlefront 本身在 80 张中的自然抓取率更低。
- 约力昂最优先闪烁 Northern、Spirit Oasis、Omen、Omen of the Hunt、Trial、Restoration、Crescent、Kyoshi、Southern 和 Leyline Binding。
- 所有被放逐的永久物在同一个结束步骤同时返回。Shrine 会彼此看见进场；传奇同名仍只能保留一个，但进场触发已经产生。
- Yorion 在主阶段进场后放逐 Go-Shintai，会让它们在结束步骤开始后才返回，错过当回合“结束步骤开始时”的触发。因此 C 版主要使用非生物 Shrine 和进场触发 Shrine，没有强塞 Go-Shintai。
- Yorion 闪烁已经变成 `Architect of Restoration` 的背面时，它会以前面 `The Restoration of Eiganjo` 返回并重新开始 Saga。
- Leyline Binding 被闪烁时，原本放逐的牌会先返回，再由 Binding 的新进场触发选择目标；它不是永久多关一张牌。

## Shrine 重复张数规则

- Shrine 不需要机械地限制为一张。V3 将 Northern、Stone Fangs、Spirit Oasis 等核心低费牌提高到 3–4 张，以保证 Battlefront 密度和自然抽到的概率。
- 同名传奇 Shrine 不能同时长期保留。Battlefront / Dance 同时放入两张同名 Shrine 时，传奇规则会在触发上堆叠前让你保留一张，但它们的进场触发已经触发。
- 对没有进场异能的重复 Sanctum，Battlefront 顶七若只见到两张同名牌，通常只放一张；另一张不要无意义送进坟场，除非明确需要为 Dance 准备目标。
- 重复 Shrine 不再纯粹是废牌：可以被 Restoration / Shattered Heights 弃掉、被 Cache Grab 磨掉，再由 Dance 批量回场；但这不意味着所有 Shrine 都应满编。
- `United Battlefront` 不能放 Go-Shintai，因为它们是生物；也不能放四 / 五费 Shrine。`Dance of the Manse` 可以回收非灵气的结界生物，因此能回收 Go-Shintai。

## 新地基

三版都使用 0 张带“支付生命 / 对你造成伤害”文本的地，完全移除 V2 的 Mana Confluence x4、Starting Town x3、Thran Portal x2 与 Brushland x2。

- A/B 为 24 地，使用 pathway 确定当前需要的颜色，Botanical Sanctum 负责早期绿色 / 蓝色，Fabled Passage、Omen of the Hunt 与基本地负责补齐黑红。
- A/B 有 12 个通常可在第一回合未横置产绿的来源；红源只有 Fabled x2、Ketria 与 Mountain，红色 Shrine 优先由 Battlefront / Dance / Sanctum 部署，不应按普通红色曲线留牌。
- C 按相同比例扩展到 32 地和 16 个早期未横置绿源；行侣不允许简单在 60 张牌表上加 20 张高费牌而不重新计算地牌。
- Pathway 没有生命成本，但进入战场时必须永久选择一面。手牌有 Dance 时优先确保白蓝，已有 Battlefront 和白源时优先补绿色 / 黑色。
- A/B 有 6 张基本地，C 有 9 张；Omen、Fabled、Restoration 与 Kyoshi 会消耗搜索目标，中盘需要记录牌库中剩余基本地。

## 批量入场规则门槛

- Battlefront 的“法术力值不高于 3”读取牌面法术力值，不能因为 Jukai / domain 降低实际支付就把高费牌视为合法目标。
- Battlefront 把两个永久物同时放入战场。Northern / Spirit Oasis 等 Shrine 会计算返回后的实际 Shrine 数并触发彼此的“another Shrine”能力。
- Dance 只回收“artifact and/or non-Aura enchantment”。它能回收 Go-Shintai、Saga、Omen 和 Trial，不能回收普通法术、地或 Aura。
- Dance 的 X 在坟场 / 牌库中为 0，其牌面法术力值为 2。Founding 第一章虽然能免费施放它，但此时 X=0，通常没有意义。
- Dance 的 X 至少 6 时，回来的永久物会持续成为 4/4 生物，并因此额外暴露给生物去除与扫场；这不总是升级。
- `Sanctum of Fruitful Harvest` 第一主阶段产生的 mana 仍不能跨阶段支付结束步骤 Go-Shintai；B 版需要继续保留这项 trigger budget。

## 换备框架

- 生物铺场：换入 Depopulate 与 Leyline Binding。A/C 主牌生物很少，Depopulate 通常接近单边；仍会消灭 Restoration 背面、Monk / Spirit 与 Yorion。
- 控制 / 反击：换入 Dovin's Veto、Heroic Intervention；换出 Trial 与部分 Omen of the Hunt。Heroic 不能保护永久物免于放逐。
- 坟场套牌：换入 Soul-Guide Lantern；它只处理对手坟场，不关闭自己的 Dance。
- 非生物组合技：换入 Deafening Silence 与 Dovin's Veto。Silence 也限制己方非生物咒语，但不会限制 Battlefront / Dance 直接放入战场的永久物数量。
- 永久物针对：换入 Tear Asunder 与 Leyline Binding，优先处理 Rest in Peace、Unlicensed Hearse 等会关闭 Dance 的牌。
- C 版所有换备必须一进一出并保持主牌至少 80 张，才能继续展示约力昂为行侣。

## 当前建议

先用 A 跑第一批 BO3 日志。它最直接验证“Battlefront 一次拉两个 Shrine”是否值得，同时保留两张 Dance 测试坟场回收，不承担 80 张稀释。若日志显示进场异能是主要赢法、对局经常拖到八费总投入，则转 C；若 Dance 经常一次回场三张以上并决定胜负，则转 B。

## 验证结果

- A：主牌 60、备牌 15；B：主牌 60、备牌 15；C：主牌 80、行侣 1、普通备牌 14，三者均满足构筑数量门禁。
- 三个导入块均按英文名排序；没有非基本地同名牌超过四张。
- 从导入块反向解析的 48 个唯一牌名全部通过 `f:pioneer game:arena date<=2026-08-01`，双面通路与 Saga 按正面可导入名称核对。
- 48 个唯一牌名全部通过 mtgch `items[].translated_name` 精确中文名核对。
- 尚未执行 Arena 客户端实际导入、行侣 UI 展示和真实 BO3 对局；三方向强弱仍是结构推演，不能报告胜率。
