# Changelog

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
