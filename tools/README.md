# tools/mtg_tool.py

MTG 套牌构筑工作流 CLI。数据源：Scryfall API + mtgch.com API。仅 Python 标准库（3.7+）。

## 通用

- 所有请求带 `User-Agent: NeoMtgDeckCacu/1.0`；Scryfall 节流 ≥100ms；429/5xx 指数退避（遵守 Retry-After），最多重试 5 次。
- 磁盘缓存：`tools/cache/{scryfall|mtgch}/<sha1>.json`（含 fetched_at / http_status / url / payload），重复请求直接命中；各子命令均有 `--no-cache` 绕过读取。
- 错误分类报告：网络失败 / HTTP 失败 / 查询语法错误（Scryfall error 对象）/ 分页不完整 / 模糊名未精确命中 / 真实零结果，互不混淆；任何失败不会被静默当作"不存在/不合法"。

## 用法

```bash
# 1. 候选牌枚举（全分页，oracle 去重，MDFC 从 card_faces 拼接 mana_cost/oracle_text）
python tools/mtg_tool.py search "f:pioneer game:arena date<=2026-08-08 ci<=ug o:flash t:creature" --unique oracle --out result.json

# 2. 逐牌三重核对（赛制合法 / Arena 平台可用【遍历全部印刷】/ mtgch 中文名），输出 Markdown 表格
python tools/mtg_tool.py check "Brineborn Cutthroat" "Brazen Borrower" --format pioneer --platform arena --out check.json

# 3. 牌表机器门禁（主牌≥60、备牌≤15、同名≤4（基本地豁免）、逐牌赛制+平台、可选颜色身份）
python tools/mtg_tool.py validate deck.txt --format pioneer --bo3 --colors ug

# 4. 环境基线（已发售系列 + 禁牌表，Markdown 可直接粘进报告）
python tools/mtg_tool.py baseline --format pioneer --date 2026-08-08
```

## 牌表格式（validate）

MTGO/MTGA 导入兼容：每行 `数量 英文名`；`Deck`/`Sideboard`/`Commander`/`Companion` 块头行切换分区；无块头时主牌后的空行分隔主备。兼容 MTGO 导出尾部 `(SET) 123`。

## 退出码

- `0` 成功 / 全部通过
- `1` 网络或 HTTP 失败
- `2` 查询语法错误 / 解析失败
- `3` 分页不完整
- `4` 存在 FAIL 项（check / validate 业务性失败）
