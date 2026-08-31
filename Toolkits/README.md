# Tribal Toolkits

每个部族或主题工具包都是人工筛选后的可能相关牌集合，不是最终牌表，也不是默认必留清单。工具包条目的默认状态是 `reference_only`；只有明确复制到构筑种子或候选池的牌，才会参与一次构筑。

## 使用顺序

1. 新系列、补充产品或牌面/规则更新后，先更新对应工具包的系列快照、牌名、合法性、平台印刷、组件分组、角色和备注。
2. 复核 `selection_policy`，将本次明确采用的条目复制到构筑种子或候选池；只标记为 `consider` 的条目不得自动进入牌表。
3. `selected_seed.txt` 是一次构筑实验的显式输入，不代表完整工具包；不使用时不要把它当作默认牌表。
4. 构筑输出仍须执行 `tools/mtg_tool.py validate`；工具包本身不替代赛制门禁。

每个工具箱可选配 `mtga_import.txt`：文件使用 MTGA/MTGO 的 `Deck` + `数量 英文牌名` 格式，每张参考牌默认列 1 张，便于直接导入后再删改。它是库存预览，不保证导入后满足 60 张、颜色或赛制门禁，也不会替代显式构筑种子。

`tribal_toolkit.template.json` 是通用部族工具包模板，`theme_toolkit.template.json` 是非部族主题模板。实例目录至少包含一个 `toolkit.json`；若有当前构筑，使用 `selected_seed.txt` 明确记录本次选用的子集。当前实例包括 `Tribal` 通用部族工具箱、`Anthem` 赞美诗主题工具箱，以及 `Examples/Dog` 下的 Dog 显式种子示例。已生成的 Angel 牌表与报告统一放在 `DeckList/Explorer_Angel_Tribal/`。

旧的 `Toolkits/Dog/toolkit.json` 已迁移为 `Toolkits/Tribal/toolkit.json`；`Dog` 只保留在 `Toolkits/Examples/Dog/selected_seed.txt` 作为一次具体构筑实验的输入，不再代表工具箱的部族范围。

## 组件分组

组件分组用于构筑时快速筛选：`mana_and_fixing`（部族地与调色）、`anthem`（增益与抽牌）、`tribal_anthem`（指定类别增益）、`global_anthem`（全局增益）、`recursion`（回收）、`type_change`（改变生物类别）、`copy`（复制）、`card_advantage`（牌张优势）、`counters`（指示物）、`token_and_counters`（Token 与指示物引擎）、`combat_burst`（临时战斗增益）、`trigger_amplification`（触发能力放大）、`changeling`（多重生物类别）、`protection`（保护）、`interaction`（互动）和 `tribe_core`（部族核心）。分组是检索标签，不是强度评级。
