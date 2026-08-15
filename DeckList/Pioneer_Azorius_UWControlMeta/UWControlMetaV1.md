# UW Control（外部环境牌表，Forge 对手用 V1）

- 来源：mtgch.com（大学院废墟/sbwsz）牌表 id 140643，MTGO Challenge 32（2026-08-11）第 5-8 名，先驱赛制。
- 拉取日期：2026-08-15；环境快照见 `MatchRecord/meta_mtgch_20260815.md`（当时 UW Control 占先驱 6.1%）。
- 门禁：`mtg_tool.py validate --format pioneer` 全过；全部 65 张（与 URAggroMetaV1 合并去重）Arena 平台可用、Forge 2.0.13 已实现。
- 结构：主 80（约力昂大摞）+ 备 15；备牌中 Yorion, Sky Nomad 为 companion（Forge 无 companion 结构，模拟时忽略不影响）。
- 用途：Forge AI 对战对手（`opp_UWControlMetaV1`），代表控制系环境对局；非本队自构筑，勿按工作流迭代，更新时整表替换并升版本号。
