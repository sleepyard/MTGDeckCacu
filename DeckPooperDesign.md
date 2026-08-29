# DeckPooper 设计方案

> 状态：评审稿 v2（2026-08-29）。产品定名 **DeckPooper**（套牌构造器），基于本仓库工具链与实测教训重写旧项目（MTGCacu WPF）的构造器。本文定设计与范围；评审通过后按 §6 路线开工。
> 与本文冲突的旧口径以本文为准。

## 1. 产品范围

### 首版功能（v1，LLM 驱动）

| # | 功能 | 形态 | 现状 |
|---|---|---|---|
| 1 | **轮抓驾驶舱** | 实时面板（8643 已有简版）+ LLM pick 推荐 | 面板骨架/评分表/纯函数内核已就绪，差 LLM 八轴接入 |
| 2 | **限制模式组牌器** | 牌池 → 40 张 + 构筑报告 | draft_deckbuild.py 是原型，按本文重写为正式版 |
| 3 | **构筑赛套牌构造器** | 主题种子 + 候选池 → 60/15、Brawl 100 | 全新，吃 MtgDeckCacuWorkFlow 调研产出 |

三件套共用同一内核（§3）。LLM 在 v1 全程在场，但只出**定性分**（协同、主题契合、pick 理由），一切确定性计算机器做（D1 幻觉防线，v1 第一天就内建，不是后补）。

### 未来功能（v2+，不在本方案排期）

| # | 功能 | 阻塞原因 |
|---|---|---|
| 1 | 各模式打牌驾驶舱（对局内实时建议） | **LLM 返回时间过长**——advise 实测 deepseek-reasoner 延迟不适配局内节奏；等更快端点或本地小模型 |
| 2 | 算法辅助 LLM + 卡查功能 | 依赖 v1 内核沉淀（角色标签/曲线/法术力全机器化后，LLM 才有可靠的卡查工具可调用） |
| 3 | 悬浮窗 / 更好的监控形态 | 依赖 8642/8643 两个 Web 面板的实测反馈，再定悬浮窗技术选型 |

## 2. 定位与边界

**是什么**：程序化套牌生成与轮抓辅助。输入"候选池 + 约束"，输出"完整牌表 + 构筑报告 + pick 建议"。

**不是什么**：

- 不替代 `MtgDeckCacuWorkFlow.md` 的人工/代理调研流程——构造器吃调研产出（候选池、主题锚点），不负责环境调研与主题澄清
- 不做键鼠模拟；不读对手非公开信息；对局内操作永远是人
- 不重新发明数据层：Scryfall/mtgch 走 `mtg_tool.py` 磁盘缓存，胜率锚点走 `cache/draft_ratings/` 预生成表，grpId 解析走 `mtga_log_tool.py`

## 3. 教训驱动的设计决策（每条都有出处）

| # | 决策 | 实测来源 |
|---|---|---|
| D1 | **LLM 不做确定性计算**：费用、计数、合法性、曲线、法术力配比全部纯函数；LLM 调用无状态单次、prompt 落盘 jsonl 供复盘 | advise 副驾费用/回合幻觉；上下文污染事故 |
| D2 | **评分锚点离线预生成、严格社区分映射**，运行时只查表 | 评分压缩事故（B+ 41 张），收紧映射后 43%→21% |
| D3 | **选牌曲线感知**：等级排序 × 曲线缺口系数 × 角色配额修正 | 首场 HOB 轮抓纯按等级选出 3费×9 "偏慢"曲线 |
| D4 | **法术力基础机器算**：pip 计数、每色保底 1、splash 需求 3 折、动态地数（抓牌多→减地，教学口径） | 旧项目 LimitedDeckBuilderService + 文档/实现分歧裁决 |
| D5 | **角色标签白名单**：removal/card_advantage/threat/mana_development/tempo/protection/aggro/control/hate 九根 + 权重（removal 1.5 最高） | 旧项目 LIMITED_TAG_AUDIT |
| D6 | **中间态日志不可信**：牌池事实源只用终态；pick 归属用同包转回差集反推 | PickedCards 滞后乱序实测（draft_methodology §5） |
| D7 | **门禁后置但必过**：生成结果自动跑 `mtg_tool.py validate`，FAIL 不出货 | 现有牌表机器门禁惯例 |
| D8 | **LLM 定性轴只出两个分**：RawPower（有评分表锚）+ Synergy（给牌池上下文），各 0-1 + 一句话理由；其余六轴机器算，WASPAS 合成 | draft_methodology §2 八轴方案 |

## 4. 架构分层

```
数据层（已有，不重写）
  mtg_tool.py            Scryfall/mtgch 查询 + 磁盘缓存 + validate 门禁
  cache/draft_ratings/   预生成评分表（字母等级+社区分）
  mtga_log_tool.py       grpId 解析（grp_cache）
  mtga_auto_tool.py      日志 tail 管线 + 两个 Web 面板基建 + LLM 后端

纯函数内核（新增/泛化，零 I/O，全单测）
  deck_core.py           ← 由 draft_core.py 泛化：曲线目标、地数、法术力配比、
                           颜色深度、splash 准入、WASPAS、爆地卡地自检
  roles.py               九根标签打标（规则启发式 + 可选 LLM 辅助，AI 标签打 5 折）

策略层（按场景各一）
  limited_strategy.py       40 张骨架：双色组合评估 → splash → 曲线感知选 23 → 地
  constructed_strategy.py   主题模块配额（M1-M9）→ 种子保留 → 候选排序补位
  draft_advisor.py          pick 推荐：机器六轴 + LLM 两轴 → WASPAS → 面板

I/O 层（薄）
  deck_pooper.py         CLI 入口：pool 解析（MTGA 文本/录样 jsonl）、
                         报告渲染、validate 门禁、--out 落盘
```

关键取舍：

- **`draft_core.py` 平移进 `deck_core.py` 后退役**：今天刚定型、35 例单测绿着的轮子不重写、不留双份；测试随同迁移。
- **曲线感知选牌**（D3 落地）：候选分 = 评分表等效分 × 曲线系数（缺口档 ×1.0 / 区间内 ×0.85 / 溢出档 ×0.6）× 角色配额修正（生物/去除未达标 ×1.2/×1.3）；同 CMC≥4 已选 5 张后再选 ×0.7。初值取自旧项目 ApplySelectionModifiers，用录样复盘校准。
- **双色组合评估**：枚举 5 单色 + 10 双色（+splash 变体），top-23 等效分求和 + 曲线评级加减分 + 深度门槛（单色 14+ / 双色各 8+ / splash ≤3）。v1 不做三色（Quick Draft 样本不足）。
- **构筑赛模块配额**：M1 核心回报 / M2 引擎 / M3 终结 / M4 特殊卡位 / M5 互动 / M8 生存为必选；M6 备牌 / M7 行侣 / M9 指挥官按赛制开关。配额初值来自 DeckList 已交付套牌的实测结构统计（P2 开工前先做一次存量统计），每模块"最低/目标/上限"三档。
- **轮抓 LLM pick 推荐**（D8 落地）：每次新 `BotDraftDraftStatus` → 机器算六轴 → 无状态调 LLM 出 RawPower/Synergy → WASPAS 排序 → 面板刷新。LLM 超时/失败降级为评分表纯机器排名（今天用的简版），面板显式标注"LLM 离线"。

## 5. 接口草案

```bash
# 轮抓驾驶舱（对 mtga_auto_tool draft --watch 的升级，面板内嵌 pick 推荐）
python tools/deck_pooper.py draft --watch --set HOB [--port 8643] [--llm]

# 限制模式组牌器（替代 draft_deckbuild.py）
python tools/deck_pooper.py limited --pool 录样|pool.txt --set HOB \
    [--colors gu] [--strategy mid] [--llm-review] [--out deck.txt] [--report report.md]

# 构筑赛套牌构造器
python tools/deck_pooper.py constructed --format pioneer --seed seeds.txt \
    --candidates result.json [--bo3] [--strategy mid] [--llm] [--out deck.txt]
```

报告必含：主色与 splash 判定理由、曲线分布与评级、法术力配比、爆地/卡地自检概率、淘汰清单（每张注明被谁挤掉）。`--explain` 是硬需求——复盘时"为什么砍这张"答不上来的构造器不值得留。

## 6. 路线（v1 三件套）

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | 内核泛化：deck_core + roles + 测试迁移 | 全部回归绿 |
| P1 | 限制模式组牌器正式版（替代 draft_deckbuild.py） | HOB 录样黄金样本对照，曲线不再"偏慢" |
| P2 | 轮抓驾驶舱完整版：LLM 八轴 pick 推荐进面板 | 一场真实 Quick Draft 实测 + 建议落盘可复盘 |
| P3 | 构筑赛构造器：存量牌表结构统计 → 模块配额 → validate/sim 门禁 | 用一个旧主题重建并对照已交付牌表 |

顺序理由：P1 把内核用熟（限制赛数据全、反馈快），P2 复用同一内核接 LLM，P3 走最长的调研链路放最后。

## 7. 明确不做（v1）

- 对局内打牌驾驶舱（LLM 延迟不达标，见 §1 未来功能 1）
- 三色组合评估（等 BO3 轮抓数据）
- 悬浮窗（等两个 Web 面板实测反馈）
- 旧项目 SQLite/标签库兼容（只迁经验数字）
- 备牌自动换备建议（等 BO3 实测）
