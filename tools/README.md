# tools/mtg_tool.py + tools/forge_tool.py + tools/mtga_log_tool.py

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

# tools/forge_tool.py

Forge 套牌测试 CLI：牌表转换 `.dck`、AI vs AI 无头模拟、GUI 试玩入口。仅 Python 标准库，牌表解析复用 mtg_tool。

## 依赖（一次性安装，均已被 .gitignore 排除）

- 便携 JDK：`tools/jdk/bin/java.exe`（Microsoft OpenJDK 21，`https://aka.ms/download-jdk/microsoft-jdk-21-windows-x64.zip` 解压即得；也可用 JAVA_HOME/PATH 中任意 Java 17+）
- Forge 2.0.13：`tools/forge/`（GitHub release `forge-2.0.13` 的 `forge-installer-2.0.13.tar.bz2` 解压即得；GitHub 直连慢时可经 ghfast.top 代理并校验 sha256 = `df23b237095cfc5ff97a4711946b25ff852da9ff43b916c40783f6b5a41ce855`）

## 用法

```bash
# 1. 牌表 → Forge .dck（输出到 tools/forge/simdecks/）
python tools/forge_tool.py convert deck.txt --name MyDeck

# 2. AI vs AI 模拟：报告写 SimResult/*.md，原始日志 *.log
python tools/forge_tool.py sim deckA.txt deckB.txt --games 20 --quiet
python tools/forge_tool.py sim deckA.txt deckB.txt --matches 3 --format brawl

# 3. 启动 Forge GUI 人工试玩（可选先转换牌表供编辑器导入）
python tools/forge_tool.py play deck.txt
```

## 口径与限制

- Forge AI 快攻/中速尚可，控制一般，组合技严重失真；胜率只是 AI 对局样本，报告页脚固定带此声明。
- 未实现的牌无法导入 .dck；报告会标记疑似加载失败，需核对原始日志。
- sim 不做赛制合法性门禁——合法性仍以 `mtg_tool.py validate` 为准，Forge 只负责实测。
- Windows 下 sim 必须走 `java -jar` 才有控制台输出（`forge.exe` 只写日志文件）；companion 分区无 Forge 对应结构，转换时会警告并跳过。
- sim 的 `-d` 只从 Forge 用户档案目录读牌（Windows 为 `%APPDATA%\Forge\decks\constructed\`；`-D` 自定义目录仅锦标赛模式 `-t` 生效），脚本会自动把 .dck 写入该目录——副作用是 GUI 选牌界面也能直接看到这套牌。
- `forge.exe` 包装器只认系统 Java（注册表/PATH），没有系统 JRE 时弹 "requires a Java Runtime Environment 17"；`play` 因此复刻 `forge.cmd` 的官方 JVM 参数（`-Xmx4096m -Dio.netty.tryReflectionSetAccessible=true -Dfile.encoding=UTF-8`）直接用便携 JDK 启动。同理不要手动双击 `forge.exe` / `forge-adventure.exe`（后者是像素风"冒险模式"RPG，同样需要系统 Java），一律走 `forge_tool.py play`。

## 退出码

- `0` 成功
- `2` 牌表解析失败
- `5` 环境缺失（Java / Forge 主 jar 未找到）
- `6` Forge 进程启动或运行失败

# tools/mtga_log_tool.py

MTGA 对局日志离线解析：比赛结果记录、胜率聚合、提交牌表导出。仅 Python 标准库（arena_id 解析复用 mtg_tool 的 Scryfall 缓存）。

**前置**：MTGA 内 选项 → 账户 → **Detailed Logs (Plugin Support)** 必须开启，否则日志只有客户端高层事件、无比赛数据（Untapped 等追踪器依赖同一开关）。

**手工一键更新**：仓库根目录 `update_matches.bat [牌表名]`——双击执行 scan + report + 最新一场的 opponent/replay/risk --all 全套。

## 用法

```bash
# 1. 扫描日志，新比赛追加到 MatchRecord/matches.json（按 matchId 去重，可反复执行）
python tools/mtga_log_tool.py scan [--prev]          # --prev 同时扫 Player-prev.log
python tools/mtga_log_tool.py scan --deck 牌表名     # 载荷通常不含牌表名，建议手动打标

# 2. 按牌表聚合场/局胜率（Markdown，可直接粘进交付文档）
python tools/mtga_log_tool.py report [--deck 过滤词]

# 3. 导出日志中提交的牌表（MTGA 导入格式，写 MatchRecord/decks/）
python tools/mtga_log_tool.py decks

# 4. 对手已见牌识别（公开物件聚合，写 MatchRecord/opponents/）
python tools/mtga_log_tool.py opponent [--match-id X]

# 5. 逐回合流程复盘（写 MatchRecord/replays/）
python tools/mtga_log_tool.py replay [--match-id X]

# 6. 我方风险点归纳（缺地/调度/卡手，写 MatchRecord/risk_*.md）
python tools/mtga_log_tool.py risk [--match-id X | --all]
```

- 默认日志路径 `%USERPROFILE%\AppData\LocalLow\Wizards of the Coast\MTGA\Player.log`，`--log` 可覆盖。
- 口径：真人对局样本，可信度高于 Forge AI 模拟；对手牌表无法从日志完整还原，不做猜测。
- 本家识别：比赛结果按 AuthenticateResponse 的 `screenName`（seat 1 可能是对手）；对局内座位按 ConnectResp 的 `systemSeatIds` **按场绑定**——ConnectResp 每场一条、紧跟该场开局消息之前，取最近一条的座位绑定到该场（取全日志最后一条会把后续场次的座位错套到前面的比赛上）。
- 三件套口径：`opponent` 只聚合对手**公开可见**物件（进场/堆叠/展示），是"已见牌集合"不是完整牌表；类型列取 Scryfall 印刷类型（type_line），对局内物件类型会被复制/变形改写——不一致时以"（复制/变形：X）"标注，印刷类型才计入类型总计（实测教训：Spark Double 复制鹏洛客后物件类型变 Planeswalker，直接采信会误判套牌属性）；`replay` 是事件重建不是录屏，回合内事件**按施放者归属**——非当前回合方的瞬时/闪出响应标注"对方响应："/"我方响应："（物件不可见时回退当前回合方），ZoneTransfer 未知 category 在文末原样计数；调度次数**按开局手牌数推断**（伦敦调度后手牌 = 7 − 调度次数，取首个 turnInfo 帧之前的最小快照；`players[].mulliganCount` 多数场次缺字段不用），无快照显示"未知"不静默当 0；`risk` 只做事实归纳与阈值标记，不出改动建议。
- grpId→牌名/牌面数据落盘缓存 `MatchRecord/grp_cache.json`；查不到的（新牌/token）显示 `<grpId N>`，不丢弃。
- 回归用合成样本：`tools/testdata/mtga_log_sample.txt`（scan）与 `mtga_log_sample2.txt`（三件套）。

## 退出码

- `0` 成功（含"无新比赛"）
- `2` 日志不存在 / 读取失败
- `4` 无比赛记录（report 无数据可聚合）
