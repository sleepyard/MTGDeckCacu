# Changelog

## 未发布（底层架构强化 Phase 0–4）

- **解析层统一（Phase 0/1）**：`tools/` 与 `tools/newbie/` 的 9 个 `parse_deck`/`load_deck`
  收敛为 `deck_model.parse_deck` 薄委托（新模块 `tools/deck_model.py`，
  `CardRef`/`SkippedLine`/`Deck` 冻结数据类 + 单一解析语义）；坏行统一记入
  `Deck.skipped` 而不再兜底成 `(1, line)` 假牌；Commander/Companion 牌张正确分派；
  BOM、中文段名、注释行、无段头空行切备牌对所有解析器生效。
- **BASIC_LANDS 统一（Phase 2）**：基本地清单（12 张，含 Snow-Covered Wastes）单一定义于
  `deck_model.BASIC_LANDS`，`mtg_tool`/`deck_version` 各自原名 re-export 兼容。
- **参数外置（Phase 2）**：新模块 `tools/deck_config.py` 集中策略/阈值参数
  （`deck_core` WASPAS 轴线/曲线/信号/骨架目标与地数门槛、`mtga_log_tool` 风险旗标、
  `rot_audit` 轮替日期），各模块 import 时 `load_params()` 加载、旧常量名保留别名；
  用户可复制 `tools/data/config/strategy_params.example.json` → `strategy_params.json`
  （gitignored）覆盖；缺失/损坏回退内置默认并 stderr 警告一次，加载器绝不回写 JSON。
- **金鱼模拟器引擎化（Phase 3）**：`tools/newbie/` 8 个 `sim_*.py` 收敛为
  `tools/newbie/goldfish/` 引擎包（`engine.py` 骨架 + `data/*.json` 牌池 +
  `decks/*.py` 回合逻辑 + `mechanics.py` 机制注册表），原 sim 文件转为兼容 shim
  （CLI 与模块级 API 不变）；`sim_dual.py` 经裁定保留独立。`tools/goldfish_template.py`
  改为指向引擎写法的薄壳模板。
- **修复 sim_red 调度（Phase 3）**：老式"重抓满 7"统一为伦敦调度（7→6→5），
  黄金值重钉（合成牌库 N=8000 均杀 5.4244 → 5.6821）。
- **修复 sim_mono_white 可复现性（Phase 3）**：贪心施放排序补牌名 tiebreaker，
  修复同种子跨进程结果不可复现（PYTHONHASHSEED 敏感）；黄金值重钉为 4.9274。
- **统一 sim_mono_white 调度（Phase 3 收尾）**：调度由老式"重抓满 7"统一为伦敦
  调度（7→6→5），与全系列一致；黄金值再次重钉（合成牌库 N=8000 均杀
  4.9274 → 5.0934）。至此全部 8 套引擎化牌组调度一致。
- **sim_dual 标记过时（Phase 3 收尾）**：`tools/newbie/sim_dual.py` 未纳入 goldfish
  引擎（双色法术力源子系统移植性价比低，经裁定保留独立），标记为过时/冻结，
  仅作历史参考，不再演进；:300 附近 `atk_ping ... and False` 死代码随之冻结不修。
- **MCP 注册表外置（Phase 4）**：`tools/mcp_server.py` 的 6 个工具元数据外置为
  `tools/mcp_tools.json`（接口契约，入库），启动时 fail-fast 校验
  （缺字段/重名/未知 builder/script 文件不存在均启动报错）；argv 构造逻辑保留在
  `mcp_server._ARGV_BUILDERS`，JSON 以 builder 名引用（省略时默认取与工具同名）。
  `tools/list` 输出、`tools/call` 分发、错误码与此前完全一致。
- **运行自证行（Phase 4）**：新模块 `tools/runlog.py`（`log_run` 追加 JSON 行到
  `tools/data/run_log.jsonl`，gitignored，写失败静默跳过）；已接入
  `mcp_server.run_tool` 出口（成功/超时/非零退出各记一条，summary 含退出码与输出长度）。

## v1.0.0（2026-10）

首个公开版本，以 Agent 用户为第一目标：

- **许可证**：代码以 MIT 发布（`LICENSE`）；图标素材独立许可说明见
  `tools/assets/icons/NOTICE.md`（法术力/类型符号改用 SIL OFL 1.1 的 Mana 字体渲染，
  野卡图标不再随仓库分发，`deck_image.py` 自动回退手绘色块，本机可用
  `tools/extract_mtga_icons.py` 自行提取）。
- **Agent 接入**：新增库内权威技能目录 `skills/`（`mtg-deckbuilding` /
  `mtg-set-review` / `mtg-limited-draft`），新增 `CLAUDE.md` 指针；
  `AGENTS.md` 继续作为跨工具单一事实源。
- **MCP server**：新增 `tools/mcp_server.py`（零依赖 stdio MCP，6 个只读工具），
  CherryStudio / WorkBuddy / DeepSeek Harness 等聊天型 Agent 客户端可直接接入，
  配置示例见 `tools/README.md`。
- **初始化契约**：新增 `tools/init_workspace.py`（目录骨架 + LLM 配置模板 +
  `--with-data` 重建造价快照）与 `tools/llm_config.example.json`；
  本地产出目录维持 gitignored。
- **CI**：GitHub Actions 矩阵（windows/ubuntu × Python 3.9/3.12）跑全量回归测试。
- **修复**：`deck_image.py --lang en` 造价行标签与明细的本地化遗漏（原硬编码中文）；
  画布底部净空不足导致高备牌列视觉贴边（FOOTER_H 28→48）。
- **牌表图增强**：比率行（生物/非生物/地/有色）、造价带右侧指标释义、
  DeckPooper 品牌署名与斜置水印（`--no-watermark` 关闭）；
  Commander / Companion 独立展示位（右列顶部标签 + 主题色描边，造价含独立位）；
  备牌区 1–2 列均衡分配、优先不撑高画布（Untapped 口径）。
