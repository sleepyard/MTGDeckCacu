# 贡献指南

感谢社区反馈。仓库规范以 `AGENTS.md` 为准（结构、风格、测试、提交约定），提交前请通读。

## 反馈与改进的推送方式

- **Bug / 需求**：开 Issue，写明复现命令、输入（牌表/查询式）、期望与实际输出。
- **代码 / 文档改进**：fork + Pull Request。要求：
  - 通过全量回归测试 `python -m unittest discover -s tools -p "test_*.py"`（CI 会自动跑 windows/ubuntu × Python 3.9/3.12 矩阵）；
  - 行为变更须附带确定性测试（`tools/test_*.py` + `tools/testdata/` 夹具，mock 网络/文件/子进程边界）；
  - 保持纯标准库（3.7+），不引入新依赖；commit 用简短祈使句标题。
- **数据类贡献**（工具包 JSON、评分口径修正、测试夹具）：同样走 PR；`Toolkits/` 下的主题/部族工具包遵循 `theme_toolkit.template.json` / `tribal_toolkit.template.json` 结构。
- **Agent 技能改进**：`skills/` 是权威源，先改库内版，本地副本（如 `.kimi-code/skills/`）随后同步。

## 不接受的内容

- 任何需要提交真实 API Key / `tools/llm_config.json` 的改动；
- WotC 客户端提取素材（野卡图标等）入库——开源替代品走 `tools/render_open_icons.py`；
- 本地产出目录（`DeckList/`、`MatchRecord/` 等，见 `.gitignore`）的内容。

## 保持更新

本项目不走自动更新。升级方式：

```bash
git pull
python tools/init_workspace.py   # 补齐新增目录/模板，已存在的配置不会被覆盖
```

版本节点看 `CHANGELOG.md` 与 git tag；破坏性变更会在 CHANGELOG 中显式标注。
