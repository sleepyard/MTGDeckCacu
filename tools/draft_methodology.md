# 轮抓驾驶舱方法论沉淀

来源：旧项目 MTGCacu（WPF 组牌器）限制赛代码与文档（2026-06 冻结）、17Lands 指标口径、B 站中文轮抓教学笔记（JacERROR / 寻水鹿系列）。本文只沉淀**结论与数字**，作为 `mtga_draft_tool.py` 阶段 2（DraftTracker）/ 阶段 3（面板 + LLM 推荐）的设计先验。旧项目路径引用仅供溯源，不要改旧项目。

## 0. 数据源现状

- 17Lands `card_ratings` 公共端点与 S3 公开桶已全灭（2026-08 实测，历史系列也是 0）。旧项目本地仅存 SOS/TDM 两系列 PremierDraft 数据，对新系列无复用价值。
- 当前唯一锚点源 = 本地预生成评分表 `tools/cache/draft_ratings/<SET>.json`（社区 Draftsim 分 + LLM 综合，字母等级 S~F）。**本文所有用到 GIH/IWD/ALSA 的公式，在新仓库里以评分表字母等级映射回数值区间后使用**（建议映射：S≈0.60+ / A≈0.57 / B≈0.55 / C≈0.53 / D≈0.51 / F<0.51 的"等效 GIH"，仅供排序，不对用户展示伪精确胜率）。

## 1. 单卡有效分公式（组牌/比较用基底）

旧项目 `PoolAnalysisService.ComputeEffectiveScore` 的落地公式：

```
score = 5.0 + (GIH_WR−0.5)×100 + IWD×50 + (OH_WR−0.5)×15
      + clamp(7−ALSA, ±5)×0.2 + 标签分(≤4) + 环境相对分(±3)
```

- 样本量 <200 时 GIH 项权重减半（新仓库评分表无样本量概念，可忽略此项）。
- 环境相对分 = 与同角色（removal/threat/...）系列平均比，clamp ±3；新仓库无逐系列 IWD 数据，由 LLM 在预生成评分时一次性吸收，不在局内计算。

### 标签权重（removal 最贵）

| 根标签 | 权重 | 根标签 | 权重 |
|---|---|---|---|
| removal | 1.5 | tempo | 0.6 |
| card_advantage | 1.2 | protection | 0.5 |
| threat | 0.8 | aggro / control | 0.3 |
| mana_development | 0.7 | | |

机制修正：board_wipe / counterspell +0.4，mass_draw / etb_value +0.3；标签分总和封顶 4.0；AI 来源标签打 5 折。

## 2. Pick 推荐内核：8 轴 WASPAS（旧项目未实施的规划，直接采用）

八个轴 + 权重，综合分 = `0.5×加权求和 + 0.5×加权乘积`（λ=0.5，WASPAS 标准式）：

| 轴 | 权重 | 计算方 |
|---|---|---|
| RawPower 单卡强度 | 0.25 | LLM 定性（有评分表先验） |
| Synergy 协同 | 0.20 | LLM 定性（给已 pick 牌池） |
| CurveFit 曲线契合 | 0.15 | **机器**（已 pick 曲线 vs §4 目标） |
| ColorOpenness 颜色开放度 | 0.15 | **机器**（§3 信号算法累计） |
| Signal 本包信号 | 0.10 | **机器**（§3） |
| Fixer 调色 | 0.05 | **机器**（已 pick 法术力基础缺口） |
| Removal 去除 | 0.05 | **机器**（标签命中） |
| Rarity 稀有度 | 0.05 | **机器**（评分表 rarity 字段） |

**职责切分原则（回应"LLM 费用/回合幻觉"实测教训）**：费用、曲线、颜色开放度、张数计数等一切确定性计算全部走纯函数；LLM 只出 RawPower / Synergy 两个定性轴的分（0-1）+ 一句话理由。LLM 调用保持无状态单次、完整 prompt 落盘 jsonl。

## 3. 信号读取算法

对本包内每种颜色，比较该色牌的 ALSA（预期被捡顺位）与实际 pick 号：

- `实际 > ALSA + 1.5` → 该色开放信号 +0.3
- `实际 < ALSA − 1.5` → −0.2
- 逐包累计，clamp 到 [−1, 1]，推荐累计值最高的颜色

**坑 1（旧项目实测）**：解析器里 `alsa` fallback 到 `avg_pick` 是错的——ALSA（平均最后被看到顺位）与 ATA（平均被捡顺位，avg_pick）语义不同，混用会污染信号。评分表只有社区字母等级、没有 ALSA/ATA 时，信号轴降级为"本包该色剩余高等级牌计数"（数 S/A/B 牌张数），不做顺位比较。

## 4. 组牌骨架数字（阶段 3 组牌建议用）

- **40 张 = 23 非地 + 动态地数**，地数 clamp [16, 19]：平均 CMC >4.0 → 18~19；>3.4 → +1；<2.5 → 16；<2.8 → −1；splash 每张 +0.5 上限 +2
- **坑 2（文档/实现分歧，采信教学口径）**：抓牌/加速多应**减**地（抓牌 ≥4 张 → −1 地），旧项目代码写反成了加地，不要照抄
- **健康曲线目标**：1 费 2-4 张 / 2 费 5-7 / 3 费 4-6 / 4 费 3-5 / 5+ 费 2-4；低费(≤2)占比 ≥40% 且中费 ≥3 张评为"优秀"
- **生物/去除配额**：进攻 16 生物 / 控制 10 / 默认 13；去除目标 3-6 张
- **颜色深度**：单色需 14+ 张优质牌；双色各 8-10 张；splash 第三色仅 1-3 张
- **splash 三条件**：强度显著高于主色同费牌 + 只需 1 个异色符号 + 主色法术力基础稳固；有数据口径要求 IWD ≥ 0.03，splash 色法术力需求打 3 折
- 法术力分配按 pip 计数，每主色/splash 色保底 1 张来源，其余按占比分配
- 爆地/卡地自检线：第 3 回合 ≥2 地概率 >90%、第 5 回合 ≥4 地概率 >70%

## 5. 日志事件锚点（2026-08 Quick Draft 实测确认）

旧项目规划标注的事件名（`Draft.DraftStatus` / `Draft.MakePick`）未出现；实测轮抓状态走 **`BotDraftDraftStatus`** 响应，形态：

```
[UnityCrossThreadLogger]==> BotDraftDraftStatus {...request...}
<== BotDraftDraftStatus(940404a0-...)
{"CurrentModule":"BotDraft","Payload":"{\"Result\":\"Success\",\"EventName\":\"QuickDraft_HOB_20260820\",\"DraftStatus\":\"PickNext\",\"PackNumber\":0,\"PickNumber\":0,\"NumCardsToPick\":1,\"DraftPack\":[\"103410\",...],\"PackStyles\":[],\"PickedCards\":[\"103399\",...],\"PickedStyles\":[]}"}
```

- 外层 JSON 的 `Payload` 是**字符串化 JSON**，需 `json.loads` 解一层才拿到内层字段。
- 内层字段：`DraftStatus`（`PickNext` / `Complete` 等）、`EventName`（`QuickDraft_<SET>_<date>`，系列码正则 `QuickDraft_([A-Z0-9]+)_`）、`PackNumber`（0 起，共 3 包）、`PickNumber`（0 起，包内递增）、`DraftPack`（当前包剩余 grpId 字符串列表）、`PickedCards`（已抓 grpId 累计列表）。
- 每条新响应 = 一次状态更新（抓了一张或换包）；无独立"提交 pick"事件需要监听。
- 消费方：`mtga_auto_tool.py draft --watch`（`parse_draft_status` + `DraftPickPanel`）；录样器 `draft --record` 仍保留兜底。
- **PickedCards 中间态不可靠**（2026-08-29 实测）：约第 5 抓起滞后/乱序（快速连抓时 MTGA 批量下发），只有 Completed 态的完整列表可作牌池事实源；"每抓拿了哪张"用前缀自洽段 + 同包转回差集反推（见 `draft_pack_review.py`）。
- **同一包 8 抓后转回**：第 N 抓与第 N+8 抓是同一包（后者为前者子集，张数差恰 8）；机器人吃牌 = 两者差集 − 你的第 N 抓，这是 Quick Draft 信号读取的唯一事实源。
- **跨包同名普通牌**造成归属歧义（commons 多包重复出现），反推多候选时排除"在后续包出现过"的 grpId。

## 6. 备牌/其他

- 换备思路（旧项目 LimitedSideboardAdvisorService）：对快攻时 CMC≥5 换出意愿 +3.0、低费生物换入 +1.5；`hate` 类针对牌只进备牌考量。Quick Draft 是 BO1，此节仅留存给未来 BO3 轮抓。
- 限制赛规则依据：40 张下限、同名牌不限张数（CompRules §100.2a 限制赛豁免）。

## 7. 与驾驶舱阶段的映射

| 阶段 | 状态 | 用本文哪节 |
|---|---|---|
| 0 录样器 `draft --record` | 已完成，等第一场录样 | §5 |
| 1 评分表 build-ratings | 已完成（HOB 188/188） | §0、§1 |
| 纯函数内核 `tools/deck_core.py` | **已完成**（36 例单测）——§2/§4 全部落地 | §2、§3、§4 |
| 2 DraftTracker（包/pick 解析） | **已完成**（`draft --watch` 的 `DraftPickPanel`，schema 实测定型） | §3、§5 |
| 3 面板 + LLM pick 推荐 | `draft_advisor.py` 已完成机器六轴 + LLM 两轴 + WASPAS；`mtga_auto_tool.py draft --watch --llm` 已接入并支持离线机器排名，待真实 Quick Draft 验收 | §2 全节 + §4 |
