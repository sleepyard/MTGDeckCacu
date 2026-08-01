> 用途：给定一个套牌主题（如"纯绿种地"），按固定流程完成环境调研、候选牌枚举、构筑、验证与交付。
默认参数：娱乐向但保证强度、MTGA 牌池、无预算上限。如当次需求不同，在阶段 1 覆盖。

---

阶段 0：主题澄清（开工前必须完成）

与用户确认以下参数，写入任务备忘：

1. 主题边界：主题的核心机制是什么？排除什么？（例：本次为"与地相关 Lands Matter"——放地进场、按地数量缩放、地变生物；明确排除纯地落 Landfall，但边缘牌列为候选由用户定夺）
2. 代表牌：让用户举 2–3 张心目中符合主题的牌，作为主题判定的锚点（例：荒野之魂艾莎娅、茁壮花身）
3. 定位：娱乐向 / 竞技向；预算帽；牌池（MTGA / 实体 / MTGO）；颜色约束（纯绿 / 允许混色）
4. 边缘牌策略：不严格符合主题但顺带契合的牌 → 列入候选并打标记（本文用 ◇），由用户最终取舍

---

阶段 1：环境基线确认

1. 赛制时间范围：确认当前日期，通过 Scryfall `/sets` 列出已发售系列，确定赛制覆盖的最新系列（先驱 = RTR 重返拉尼卡起至今）。
2. 禁牌表：Scryfall 查询 `banned:{format}`（如 `banned:pioneer`）+ 网络检索最近一次禁牌公告交叉验证。标注与主题相关的禁牌。
3. 环境粗扫：搜索官方公告 / 环境文章，确认主题思路在当前环境的强度定位（娱乐 / 可行 / 主流），只需大方向。

---

阶段 2：候选牌枚举（核心调研）

2a. 需求分解 → 模块

把套牌拆成功能模块，每个模块一组检索。通用模块模板：

模块	内容	本次实例	
M1 核心回报	主题机制的 payoff 牌	地数量缩放生物	
M2 引擎	让主题机制转起来的牌	放地进场、额外下地	
M3 终结 / 放大器	终结手段与资源放大	大法术力、大生物	
M4 特殊卡位	不占主结构的功能牌	功能地、双面地 MDFC	
M5 互动	去除、保护、反制康	互斗、点杀、辟邪	
M6 备牌	基于主牌弱点的备牌方向	坟场针对、控制针对	

2b. 逐模块 + 逐系列遍历

- 工具：Scryfall API（`/cards/search`），统一过滤条件：
  - 牌池：`f:pioneer game:arena`（先驱合法 ∩ MTGA 有售；实体牌池则去掉 `game:arena`）
  - 结果按 `oracle_id` 去重，保留有 Arena 版本的印刷
- 检索方式：按异能关键词构造 oracle 文本查询（如 `o:"number of lands you control"`、`o:"put a land card" o:"battlefield"`），覆盖赛制内全部系列后按系列分组呈现，等价于逐系列遍历
- 补充检索：对记忆中有印象但未被关键词命中的牌，逐张 `/cards/named` 复核合法性与平台可用性（本次教训：Explore 不合法、Rampant Growth 不合法、Dictate of Karametra 不在 Arena——记忆必须验证）

2c. 双源二次核对（sbwsz.com / mtgch.com API）

每张候选牌执行：

1. 中文名：`GET https://mtgch.com/api/v1/card-names/?q={英文名}` → `translated_name`
2. 平台可用性：`GET /api/v1/result?q={牌名}&view=0&unique=scryfall_id`（分页），任一版本 `arena_id` 非空即在 Arena 有售
3. 判定口径："先驱合法"以 oracle 级 legalities 为准；"MTGA 有售"以任一版本在 Arena 为准（新印版本可能不在 Arena，旧版在即可，例：云游者梓纱 FCA 版）

已知坑位清单：
- PIO（先驱大师赛）2024-12 已登陆 Arena，其独有牌可用
- Scryfall `/cards/named` 返回最新印刷，`games` 字段可能误导（需查全部印刷）
- SBWSZ `/result` 的 `!""` 精确语法不可用；`page_size` 过大需分页；含撇号牌名用片段模糊查
- 大造物者卡恩为先驱禁牌，用户提到"卡恩"时默认引导至可用替代

2d. 候选清单产出格式

按模块列表，每张牌一行：中文名 | English | 系列代码 | 一句定位，边缘牌打 ◇ 标记。附"系列遍历总表"（各系列命中数）。

---

阶段 3：构筑

1. 多方向提议：基于候选池给出 3–5 个构筑方向（思路 / 主轴 / 风格对比表），用户选定 1–2 个（可组合）
2. 初稿：主牌 60 + 备牌 15
   - 逐牌附入选理由；列出"落选候选"及取舍逻辑，便于迭代
   - 地牌数量需给"地当量"计算（真地 + MDFC×0.75 + 引擎找地牌）
   - 给曲线、经典回合节奏、核心配合说明
3. 数字校验：主备牌数量逐张加总复核（本次教训：初稿曾 61 张）

---

阶段 4：验证与迭代

1. 逐牌三重核对打勾：先驱合法 ✓ / MTGA 有售 ✓ / SBWSZ 中文名 ✓
2. 典型对局推演：对快攻 / 对中速 / 对控制的起手、节奏、换备思路
3. 按用户反馈从"可调仓位"迭代，直至锁定

---

阶段 5：交付

牌表格式（MTGO / MTGA 导入兼容）

- 每行 `数量 英文名`，按英文名字母升序混排（不分地/非地）
- 主牌与备牌之间空一行
- MTGA 导入时在备牌块前加 `Sideboard` 行

示例：

```
4 Arboreal Grazer
3 Ashaya, Soul of the Wild
...

1 Bala Ged Recovery
2 Carnage Tyrant
...
```

完整交付文档包含

- 最终牌表（上述格式 + 分功能表格版含中文名对照）
- 留牌指引、打法要点、核心配合、对局注意事项
- 备牌换入换出简表
- 可调仓位清单（后续自行微调的备选池）

---

附：常用 Scryfall 查询模式（种地主题示例）

```
f:pioneer game:arena o:"number of lands you control"     # 地数量缩放
f:pioneer game:arena o:"put a land card" o:"battlefield" # 放地进场
f:pioneer game:arena o:"additional land"                 # 额外下地
f:pioneer game:arena t:land o:"becomes a" o:"creature"   # 生物地
f:pioneer game:arena layout:modal_dfc (ci:g or t:land)   # 双面地
f:pioneer game:arena banned:pioneer                      # 禁牌表
```

SBWSZ API 端点备忘：`/api/v1/card-names/`（中英名）、`/api/v1/result`（搜索）、`/api/v1/card/{set}/{num}/`（单卡详情）、`/api/v1/sets/`（系列列表）、`/api/v1/docs`（完整文档）