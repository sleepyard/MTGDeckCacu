# 网页工作台（deck-forge 引入）开发计划

日期：2026-10-11（Asia/Hong_Kong）。依据：`AuditReport/ExternalRef_MtgSkills_20261011.md`（引入评估）、
`AuditReport/MtgSkills_PracticalIntegration_20261011.md`（前三批交付）、上游快照
`Ref/mtg-skills/` @ `eaae97c7b74f016c03a4da99497eb403990a9ee7`。

## 1. 目标与定位

引入上游 `deck-forge` 的**工作台能力**：一个本地网页界面，让组牌过程可视化（牌池、曲线、
法术力、角色缺口、候选对比），同时保持本项目的两条红线：

- **Python 3.7+ 纯标准库**（AGENTS.md Build 节），不引入 FastAPI/uvicorn/Svelte 构建链；
- **确定性内核可点名卡牌，LLM 不凭记忆点名卡牌**——与上游 ADR-0009/0023 同哲学，
  本项目 `draft_advisor.recommend_pick(llm_request=...)` 的回调注入已是同构实现。

定位：**本地 host 提供界面化，最终计算与 LLM 驱动仍依赖 Agent**。网页只做展示与确定性
内核结果的交互；涉及判断、解释、协同提案的环节通过 Agent 桥路由给交互式 Agent 会话
（Kimi Code），由 Agent 调用现有 CLI/技能完成，而非在网页后端内嵌 LLM 客户端。

## 2. 上游架构事实（评估快照实测）

三进程拓扑（`Ref/mtg-skills/mtg-utils/src/mtg_utils/_deck_forge/`）：

- **hub**：FastAPI 进程，`127.0.0.1:8765`，托管权威会话状态、确定性内核、静态 SPA、
  消息总线。分层：传输适配器 `app.py` → `engine.py`（约 70 个自由函数，规则违反抛
  `DeckRuleError` → 400）→ `views.py` 序列化缝。
- **浏览器 SPA**：Svelte 5 + Vite，瘦客户端，30 个组件纯渲染；实时推送走 SSE
  （`/api/events`）。
- **Session-agent**：交互式 Agent 会话通过 HTTP 长轮询挂到 hub（`/api/agent/next`、
  `POST /api/agent/result`），只处理 4 种请求 kind：`next_move`（建议下一步）、
  `explain`（规则解释）、`novel_synergies`（想模式→落地成真卡）、`handoff`（调起其他
  技能）。ADR-0010：刻意用交互式会话而非 Agent SDK（订阅不计费）。

引入障碍（已实测确认）：`deck-forge/src` 等符号链接在 Windows 下失效（实质代码全在
`mtg-utils/`）；Python ≥3.12 + 8 个第三方库；数据层依赖 MTGJSON 全量（数百 MB）+
phase-rs Rust sidecar；CI 无 Windows 矩阵。**结论：不照搬实现，移植协议设计。**

## 3. 架构决策

**决策 A（核心）：自建轻量 hub，沿用本项目既有的"内嵌 HTML + ThreadingHTTPServer +
轮询 JSON"面板模式**（先例：`mtga_auto_tool.py` 的 `start_dashboard` :8642 与
`start_draft_panel` :8643），不引入 Svelte/FastAPI。移植上游的三样协议设计：

1. **快照模型**：后端持有权威状态，每次变更后前端整体拉快照（上游 SSE 推送 → 本项目
   轮询，与现有面板一致；状态小时轮询足够）；
2. **Agent 桥**：`/api/agent/next`（长轮询）+ `/api/agent/result` 的 harness 无关协议，
   curl 即可驱动；kind 集合沿用上游四种，按需裁剪；
3. **铁律契约**：LLM 提案的一切候选必须来自 `/api/find` 或 `mtg_tool search` 的实际
   结果，网页与 Agent 两侧都执行。

**决策 B：引擎层先行，UI 层最薄。** 参照上游 ADR-0013 分层，先写纯函数引擎模块
（操作冻结 `Deck`、返回新状态或抛业务错误），HTTP 层只做 parse→call→serialize。
引擎可被 CLI、MCP、网页三种宿主复用——与 `mcp_server.py` 的"JSON 注册表 + 子进程"
模式并存：MCP 服务聊天型客户端，hub 服务浏览器。

**决策 C：数据层不动。** 继续用 Scryfall 按需缓存（`mtg_tool.py` HTTP 层）+ 新交付的
`mtg_card_facts.py` 证据缓存；不引入 MTGJSON 全量库与 phase-rs。上游 Card IR 能力降级
为 `roles.py` 的 oracle 正则标签（既有）+ 必要时扩展 `roles` 的机制注册表。

**决策 D：双 LLM 通道，按请求性质分流。** LLM 驱动有两条既有通路，工作台都保留：

- **Agent 桥**（主通道）：要调用工具链的判断型请求（`next_move` / `explain` /
  `novel_synergies` / `handoff`）路由给交互式 Agent 会话——烧的是当前会话订阅，
  不新增计费通道，且能调用规则/组合技/指南核验全套技能。上游 ADR-0010 同此考量。
- **嵌入式 LLM**（辅助通道）：高频低智的打分轴（如 RawPower/Synergy）可复用轮抓
  面板的既有模式——hub 直接读 `tools/llm_config.json`（DeepSeek 兼容端点）自行调用，
  无人值守可用，但只有 prompt 里喂的信息、无工具。

本质确认：界面由 Agent 唤起、双方走 HTTP 接口，LLM 计算始终走上述两条既有通道，
工作台不发明第三条 LLM 通路。网页与 Agent 会话是**同一份权威牌表状态的两个操作
界面**：按钮覆盖高频机械操作（原来由 LLM 当中间传话筒逐步调 CLI 的部分），自然
语言覆盖低频复杂判断，两边随时切换；反向通路（Agent 经 API 往工作台写候选/探索
方向）在 Phase 3 随 avenues 一并实现。

**决策 E：重工具轻前端（Legacy 教训的延续）。** `Legacy/MTGCacu` 是重前端形态
（WPF 一排 XAML 窗口 + MVVM + 编译链），业务逻辑困在 UI 层、Agent 无法驱动、改流程
成本压过功能成本。本项目已反转为"能力全沉 CLI/纯函数内核，前端是可抛弃的薄渲染壳"。
工作台守住此线：每个面板一页内嵌 HTML，复杂度只准留在工具侧；界面复杂到内嵌装不下
时，升级路径是静态构建产物（仍无运行时依赖），不回到前端工程栈。

## 4. 内核对接映射

| 工作台功能 | 本项目内核（确定性） | 备注 |
| --- | --- | --- |
| 牌表导入/导出 | `deck_model.parse_text` / `parse_deck` + 适配器 | 覆盖中文段名、坏行记录；导出加 MTGA 格式 |
| 曲线/法术力/地数 | `deck_core.curve_rating` / `land_count` / `mana_base` / `land_check` | 40/41 张限制赛口径与 60+15 构筑口径分分支 |
| 限制赛牌池 seed | `limited_strategy.build_limited_deck` + `enumerate_color_plans` | 最强对应；输出已含 sideboard/cuts/report |
| 构筑组牌 | `constructed_strategy.build_constructed_deck`（M1-M9 配额） | 对应上游 slot budgets |
| 角色/槽位统计 | `roles.classify_card` / `score_tags` / `has_root` | 上游 Card IR 的降级替代 |
| 合法性/门禁 | `mtg_tool check` / `validate`、`rot_audit`、`cn_audit` | 上游没有对应物，是我方增量 |
| 组合技 | `mtg_combo_tool.py` | 与上游 combo_search 同源，直接接入 |
| 造价/收藏 | `tools/newbie/deck_cost.py`、`MatchRecord/inventory.json` | 上游 collection 双槽模型暂不做 |
| LLM 建议 | `draft_advisor.build_prompt` / `parse_llm_scores` + Agent 桥 | prompt 协议已固化，直接复用 |

上游有、本项目无对应物、**本计划不做**的：Card IR/signals/avenues 体系、`_tuner`
诊断换牌、Commander 家族全支持、MTGJSON 离线全量、多 build 持久化。其中 `_tuner`
式"诊断+预算内换牌"列入 Phase 3 的 Agent 桥 `next_move` 语义，由 Agent + 内核
联合实现，不移植其代码。

## 5. 分期计划

### Phase 0：hub 骨架与协议（1 个交付周期）

- `tools/deck_workbench.py`：ThreadingHTTPServer，127.0.0.1，默认端口 8644（避开
  8642/8643）；端点：`GET /`（内嵌页）、`GET /api/snapshot`、`POST /api/builds/import`、
  `GET /api/export`；状态持有 `deck_model.Deck` + 会话元数据。
- 内嵌 HTML 页第一版只做：牌表分区展示、导入/导出、错误展示。风格沿用既有面板的
  单文件内嵌方式。
- 验收：`curl` 全流程导入→快照→导出守恒；`python -m unittest` 新增测试全 mock；
  runlog 留痕接入 CLI 出口；AGENTS.md / tools/README.md 同步。

### Phase 1：限制赛组牌工作台

- 端点：`POST /api/pool`（导入牌池）、`POST /api/seed`（调 `build_limited_deck`，
  含 `--deck-size` 41/40）、`GET /api/stats`（曲线/地数/`land_check`）、
  `POST /api/deck/add|remove|move`（手动微调，内核守恒校验）。
- 页面：牌池网格 + 当前牌表 + 曲线/法术力条形 + seed 方案列表（5 单色 + 10 双色
  枚举的评分摘要）。
- 验收：用 `SetReview/` 既有系列牌池跑通 seed→微调→导出→`mtg_tool validate` 门禁；
  41/40 纪律提示沿用 `draft_methodology.md` §4。

### Phase 2：构筑模式与核验接入

- 端点：`POST /api/seed-constructed`（`build_constructed_deck`）、`GET /api/roles`
  （角色统计）、`GET /api/combos`（`mtg_combo_tool`，明示主备隔离口径）、
  `GET /api/cost`（newbie 造价）、`GET /api/audit`（validate + rot + cn 门禁聚合）。
- 页面：角色缺口视图、组合技候选面板（含 stale/失败状态原样展示）、门禁红绿灯。
- 验收：对 `DeckList/` 一套既有交付做全量体检，输出与 CLI 逐项一致。

### Phase 3：Agent 桥（LLM 驱动回路）

- 端点：`GET /api/agent/next`（长轮询，60s 心跳）、`POST /api/agent/result`、
  `POST /api/agent/request`；kind：`next_move` / `explain` / `novel_synergies` /
  `handoff`（裁剪上游集合）。`handoff` 对应网页上的"一键全流程"按钮（如阶段 0b
  全套体检），等价于一句自然语言指令，但触发点是按钮。
- 反向通路：Agent 可经 API 往工作台写候选与探索方向（avenues 语义），网页侧可见；
  双向操作同一份权威状态。
- 嵌入式 LLM 通道（决策 D）：高频打分轴经 `tools/llm_config.json` 直连，不走 Agent
  桥；两条通道的失败都要显式降级为纯机器模式并标注 offline。
- Agent 侧落 `skills/` 新技能（如 `mtg-workbench`）：教会 Kimi Code 会话轮询协议、
  铁律（提案必须经 `/api/find` 或 `mtg_tool search` 落地）、以及把规则问题路由给
  `skills/mtg-rules`、组合技给 `skills/mtg-combo`。
- 验收：人工驱动一轮完整会话（import→seed→next_move→按建议微调→export），
  Agent 每条建议附内核证据；LLM 双通道均离线时面板明确显示 offline 并保留机器排名
  （沿用 `draft_advisor` 既有口径）。

### Phase 4（可选，另立需求）：上游未覆盖方向

- goldfish 接入（`tools/newbie/goldfish/` 引擎跑当前牌表）、Forge 实测入口
  （`forge_tool.py sim`）、代理牌 PDF（上游 proxy-printer 的用途，评估为低优先级）。
- Cube / 双头巨人 / MTGJSON 离线库：维持评估结论，有明确需求再试点。

## 6. 质量红线（沿用本次审核口径）

1. 禁止无意义回退：失败与零结果分离建模；缓存降级必须标 `stale` + 原因；未知
   一律显式 `unknown`/待核验，不默认放行也不默认拒绝。
2. 引擎层纯函数、无全局态；HTTP 层不含业务规则；LLM 回路可整体离线降级。
3. 测试全 mock（HTTP/文件/子进程边界），断言到字段级；新增工具接 runlog 留痕，
   AGENTS.md 与 tools/README.md 同步更新。
4. Windows 实测为验收必要条件（上游教训：符号链接、路径、端口占用）。

## 7. 前置修复（已审核发现，开工前处理）

来自 2026-10-11 交付审核的中等问题，建议作为 Phase 0 的热身批次：

- `mtg_combo_tool.py`：单组件证据失败应降级该组合技到 `needs_verification` 而非中止
  整个分析（离线模式可用性）；纯文本输出补 `truncated` 提示。
- `mtg_guide_audit.py`：claim 内未知键拒绝（防 typo 走默认值）；捕获 `re.error`
  纳入结构化错误；规则/Oracle 引用的跨章节重复一致性检查或文档明示边界。
- `mtg_rules_tool.py`：缓存损坏与"从未缓存"可区分；`except AttributeError` 收窄；
  缺 Credits 段显式报错。
- `test_mtg_rules_tool.py` 的 `TestSharedHttp` 迁入 mtg_tool 测试文件。

## 8. 风险与开放问题

- **内嵌 HTML 的天花板**：牌池网格 + 拖拽交互复杂后单文件页面会失控；届时按决策 E
  升级为静态构建产物（构建链留在开发侧、运行时仍零依赖），而不是回到 Legacy 式的
  前端工程栈或上游的 Svelte 运行时依赖。
- **Agent 桥的空闲轮询成本**：长轮询挂在交互式会话上，依赖 Agent 主动循环；需要
  技能里写明轮询节奏与退出条件，避免会话空转。
- **多 build 持久化**暂以单会话内存 + 显式导出代替；若实测中频繁丢状态再升级。
- 端口约定：8642 对局监控、8643 轮抓面板、8644 工作台；写进 tools/README.md。
