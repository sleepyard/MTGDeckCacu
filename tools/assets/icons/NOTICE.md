# 图标素材归属说明（NOTICE）

## mana/ 与 type/ 图标

`mana/` 与 `type/` 下的 PNG 图标由开源 **Mana 字体**渲染生成（渲染脚本：
`tools/render_open_icons.py`，固定版本 v1.17.1）。

- 字体作者：Andrew Gioia（https://github.com/andrewgioia/mana）
- 字体许可证：**SIL Open Font License 1.1**（全文见同目录 `LICENSE-OFL.txt`），与 MIT 兼容
- 符号形象版权：法术力符号与卡牌类别图标的图形设计版权归
  **Wizards of the Coast** 所有；本仓库按
  [WotC 粉丝内容政策](https://company.wizards.com/en/legal/fancontentpolicy)
  以非商业性质使用这些符号形象。这些图标不属于本仓库 MIT 许可证的覆盖范围。

## wildcard/ 野卡图标

wildcard 图标（`CDC_Wildcard_*.png`）提取自 MTGA 客户端，版权归
Wizards of the Coast 所有，**不再随仓库分发**。

- 本机已安装 MTGA 客户端的用户可运行 `python tools/extract_mtga_icons.py`
  （需 `pip install UnityPy pillow`）从自己的客户端提取，产物落在
  `tools/assets/icons/wildcard/`（已 gitignore，仅供本机使用）。
- 缺少 wildcard 图标时，`tools/deck_image.py` 的造价行会自动回退为
  程序手绘的稀有度色块，功能不受影响。
