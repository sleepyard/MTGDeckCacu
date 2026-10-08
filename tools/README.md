# tools/mtg_tool.py + tools/forge_tool.py + tools/mtga_log_tool.py + tools/mtga_auto_tool.py

MTG 套牌构筑工作流 CLI。数据源：Scryfall API + mtgch.com API。仅 Python 标准库（3.7+）。

赛制字段说明：Scryfall `legalities` 没有 `explorer` 字段；`--format explorer` 会按内置别名表（`FORMAT_LEGALITY_ALIAS`，explorer→pioneer）推导合法性并在备注标注，Explorer = 先驱合法 ∩ Arena 可用 ∩ Explorer 专属禁牌（BO1/队列特例仍需人工查官方公告复核）。

## 通用

- 所有请求带 `User-Agent: NeoMtgDeckCacu/1.0`；Scryfall 节流 ≥100ms；429/5xx 指数退避（遵守 Retry-After），最多重试 5 次。
- 磁盘缓存：`tools/cache/{scryfall|mtgch}/<sha1>.json`（含 fetched_at / http_status / url / payload），重复请求直接命中；各子命令均有 `--no-cache` 绕过读取。mtgch 2026 年改版后中文名走新端点：逐牌 `GET /api/v1/result?q=<名>&view=1`（view=1 才带中文名）；按系列批量 `GET /api/v1/set/<code>/cards/`（`fetch_set_chinese_names`，逐牌风暴会被 429 限流，批量场景必须用这个）。
- 错误分类报告：网络失败 / HTTP 失败 / 查询语法错误（Scryfall error 对象）/ 分页不完整 / 模糊名未精确命中 / 真实零结果，互不混淆；任何失败不会被静默当作"不存在/不合法"。
- 策略参数：`tools/deck_config.py` 集中管理（deck_core 评分/曲线/地数阈值、mtga_log_tool 风险标记、rot_audit 轮替窗口）；默认值内置，复制 `tools/data/config/strategy_params.example.json` → 同目录 `strategy_params.json`（gitignored）可按键覆盖，缺失/损坏自动回退默认并打一条 stderr warning，加载器绝不写回 JSON。
- 牌表解析：`tools/deck_model.py` 是唯一解析层（`CardRef`/`SkippedLine`/`Deck` + `parse_deck`/`parse_text`），tools/ 与 tools/newbie/ 全部 `parse_deck`/`load_deck` 均为其薄委托；新增解析需求扩展 deck_model，不再另起解析器。

## 用法

```bash
# 1. 候选牌枚举（全分页，oracle 去重，MDFC 从 card_faces 拼接 mana_cost/oracle_text）
python tools/mtg_tool.py search "f:pioneer game:arena date<=2026-08-08 ci<=ug o:flash t:creature" --unique oracle --out result.json

# 2. 逐牌三重核对（赛制合法 / Arena 平台可用【遍历全部印刷】/ mtgch 中文名），输出 Markdown 表格
python tools/mtg_tool.py check "Brineborn Cutthroat" "Brazen Borrower" --format pioneer --platform arena --out check.json

# 3. 牌表机器门禁（主牌≥60、备牌≤15、同名≤4（基本地与牌面"any number of cards named"豁免）、逐牌赛制+平台、可选颜色身份）
python tools/mtg_tool.py validate deck.txt --format pioneer --bo3 --colors ug

# 4. 环境基线（已发售系列 + 未发售系列标注 + 禁牌表，Markdown 可直接粘进报告）
python tools/mtg_tool.py baseline --format pioneer --date 2026-08-08
```

- 未发售系列单列一段：Scryfall 对未发售系列所有牌统一标 `not_legal`，legalities 不可作"发售是否入赛制"的依据；`set_type=expansion` 且非 digital 的系列发售即入先驱/摩登等对应赛制，可提前纳入候选。

---

# tools/mcp_server.py

MCP server（stdio，零依赖）：把只读 CLI 能力以 MCP 工具形式暴露给聊天型 Agent 客户端（CherryStudio / WorkBuddy / DeepSeek Harness 等）。协议为换行分隔的 JSON-RPC 2.0，实现 initialize / ping / tools/list / tools/call 最小集；工具执行 = 子进程调用对应 CLI（UTF-8 强制、180s 超时、50K 字符截断），非零退出码映射 `isError`。暴露 6 个只读工具：`mtg_search` / `mtg_check` / `mtg_baseline` / `deck_validate` / `deck_cost` / `rot_audit`。有 Shell 能力的编程 Agent 直接用 CLI + `skills/`，无需经此。

工具注册表外置为 `tools/mcp_tools.json`（接口契约，入库）：启动时 fail-fast 校验（缺字段/重名/未知 builder/script 文件不存在均启动报错退出），argv 构造逻辑保留在 `mcp_server._ARGV_BUILDERS`，JSON 以 builder 名引用（省略 builder 字段时默认取与工具同名）。每次工具执行的出口经 `runlog.log_run` 写一行运行自证到 `tools/data/run_log.jsonl`（gitignored；成功/超时/非零退出各一条，summary 含退出码与输出长度；写失败静默跳过）。

客户端配置（CherryStudio / WorkBuddy 的 MCP JSON 同构，路径换成实际仓库位置）：

```json
{
  "mcpServers": {
    "neomtgdeckcacu": {
      "command": "python",
      "args": ["<仓库绝对路径>/tools/mcp_server.py"]
    }
  }
}
```

冒烟自测：`python tools/mcp_server.py --selftest`；回归测试 `python tools/test_mcp_server.py`（子进程全 mock）。

---

# tools/deck_pooper.py

DeckPooper 的限制赛组牌入口（P1）。它要求本地预生成评分表，并只接受牌池文本或
含 `DraftStatus=Complete/Completed` 的轮抓录样 JSONL；没有终态牌池时不会使用中间态数据。

```bash
python tools/deck_pooper.py limited --pool pool.txt --set HOB \
    --strategy mid --out deck.txt --report report.md --explain

# 轮抓驾驶舱（复用 mtga_auto_tool 的日志管线）
python tools/deck_pooper.py draft --watch --set HOB --llm --port 8643

# 构筑赛套牌（种子必须存在于候选 JSON；门禁失败不写出牌表）
python tools/deck_pooper.py constructed --format pioneer --seed seeds.txt \
    --candidates result.json --bo3 --out deck.txt --report report.md --explain
```

策略层是纯确定性计算：先枚举 5 个单色与 10 个双色方案，再按颜色深度、splash
准入、曲线缺口和生物/去除配额选择 23 张非地，最后计算动态地数、法术力配比和
爆地/卡地检查。评分表缺失、输入格式错误或卡牌查询失败均返回错误码，不静默产出
伪造结果。构筑赛在写入 `--out` 前还会调用 `mtg_tool.py validate`；正式校验失败时
只保留报告并返回门禁错误码。

部族/主题工具包是人工筛选的可能相关牌集合，不是必选清单。每次系列更新后先更新
工具包，再从中挑选本次可能用上的牌作为种子或候选；未选牌只作备查，不会自动进入最终牌表。
版本化实例与模板见 `Toolkits/`：通用部族工具箱为 `Toolkits/Tribal/toolkit.json`，可直接导入的库存预览为 `Toolkits/Tribal/mtga_import.txt`；Dog 构筑示例种子在 `Toolkits/Examples/Dog/selected_seed.txt`；赞美诗主题工具箱为 `Toolkits/Anthem/toolkit.json`，导入预览为 `Toolkits/Anthem/mtga_import.txt`，两者都不附带默认必留种子。实际生成的 Angel 牌表与报告位于 `DeckList/Explorer_Angel_Tribal/`。

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

## 依赖（可选项：仅 forge_tool.py 的 sim/play 需要；convert 与仓库其余工具链均为纯标准库，无此依赖也能用。一次性安装，均已被 .gitignore 排除）

- 便携 JDK：`tools/jdk/bin/java.exe`（Microsoft OpenJDK 21，`https://aka.ms/download-jdk/microsoft-jdk-21-windows-x64.zip` 解压即得；也可用 JAVA_HOME/PATH 中任意 Java 17+）
- Forge 2.0.13：`tools/forge/`（GitHub release `forge-2.0.13` 的 `forge-installer-2.0.13.tar.bz2` 解压即得；GitHub 直连慢时可经 ghfast.top 代理并校验 sha256 = `df23b237095cfc5ff97a4711946b25ff852da9ff43b916c40783f6b5a41ce855`）

## 用法

```bash
# 1. 牌表 → Forge .dck（输出到 tools/forge/simdecks/；双面牌/MDFC 自动取正面名，Forge 不认 "A // B" 全名）
python tools/forge_tool.py convert deck.txt --name MyDeck

# 2. AI vs AI 模拟：报告 + 原始日志默认写 SimResult/；--outdir 可改（约定写入被测套牌的 DeckList 目录，如 .../Golgari/sim/）
python tools/forge_tool.py sim deckA.txt deckB.txt --games 20 --quiet --outdir DeckList/<主题>/<方向>/sim
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
- 新系列（如 FRA）在发布版牌库中不存在时，用 Ref/forge 源码构建的 SNAPSHOT jar：`--jar Ref/forge/forge-gui-desktop/target/forge-gui-desktop-2.0.15-SNAPSHOT-jar-with-dependencies.jar --cwd Ref/forge/forge-gui`。该 jar 不内嵌 cardsfolder，牌库按 cwd 下的 `res/` 加载——不配 `--cwd` 会回退读 tools/forge 的旧牌库造成缺牌（冒烟记录见 `AuditReport/FRA_NewbieSeries/进度.md`）。上游新牌实现用 `forge_tool.py track` 跟踪。

## 退出码

- `0` 成功
- `2` 牌表解析失败
- `5` 环境缺失（Java / Forge 主 jar 未找到）
- `6` Forge 进程启动或运行失败

# tools/goldfish_template.py

金鱼蒙特卡洛模拟器模板（Phase 3 起为薄壳）：标准写法是复用 `tools/newbie/goldfish/` 引擎（engine + data JSON + decks 模块，模板文件内含最小可运行示例与完整建模规范）；双色法术力源等超出单地哨兵马纳基的场景才需全自建（参照 `tools/newbie/sim_dual.py`）。补 Forge 实测之前的构型初筛。仅 Python 标准库。

```bash
python tools/goldfish_template.py   # 运行内置最小示例
```

- 建模规范（文件顶部注释与工作流阶段 3 均有，历史重灾）：每张牌的每个效果都要建模（持续触发逐回合、条件触发条件与效果分别建、减费动态算、免费施放按"看 N 选 1"）；对比"砍 vs 保留"时被对比牌必须在模拟里真的有效果，否则系统性低估保留方。
- 贪心施放排序键必须带牌名 tiebreaker（`key=(-c, name)`），否则结果受 PYTHONHASHSEED 影响不可复现。
- 金鱼是"法术力受限"模型：抓牌/赚牌引擎的分不能被它裁决——引擎 run 的 `curve`（按回合累计伤害）可做 gas 观察，需要更多指标时经 `collect` 钩子聚合；实测反馈优先于模拟分数。
- 报告必须声明模拟局限（去除、应对干扰无法被金鱼衡量）。

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

# 7. 库存快照（StartHook：通配符/金币/钻石/Vault/未开卡包 + 已存套牌并集，写 MatchRecord/inventory.json）
python tools/mtga_log_tool.py inventory
```

- 默认日志路径 `%USERPROFILE%\AppData\LocalLow\Wizards of the Coast\MTGA\Player.log`，`--log` 可覆盖。
- 口径：真人对局样本，可信度高于 Forge AI 模拟；对手牌表无法从日志完整还原，不做猜测。
- 本家识别：比赛结果按 AuthenticateResponse 的 `screenName`（seat 1 可能是对手）；对局内座位按 ConnectResp 的 `systemSeatIds` **按场绑定**——ConnectResp 每场一条、紧跟该场开局消息之前，取最近一条的座位绑定到该场（取全日志最后一条会把后续场次的座位错套到前面的比赛上）。
- 三件套口径：`opponent` 只聚合对手**公开可见**物件（进场/堆叠/展示），是"已见牌集合"不是完整牌表；类型列取 Scryfall 印刷类型（type_line），对局内物件类型会被复制/变形改写——不一致时以"（复制/变形：X）"标注，印刷类型才计入类型总计（实测教训：Spark Double 复制鹏洛客后物件类型变 Planeswalker，直接采信会误判套牌属性）；`replay` 是事件重建不是录屏，回合内事件**按施放者归属**——非当前回合方的瞬时/闪出响应标注"对方响应："/"我方响应："（物件不可见时回退当前回合方），ZoneTransfer 未知 category 在文末原样计数；调度次数**按开局手牌数推断**（伦敦调度后手牌 = 7 − 调度次数，取首个 turnInfo 帧之前的最小快照；`players[].mulliganCount` 多数场次缺字段不用），无快照显示"未知"不静默当 0；`risk` 只做事实归纳与阈值标记，不出改动建议。
- grpId→牌名/牌面数据落盘缓存 `MatchRecord/grp_cache.json`；查不到的（新牌/token）显示 `<grpId N>`，不丢弃。
- `inventory` 口径：已存套牌取并集作"库存下界"，排除 `?=?Loc/` 前缀预组，grpId 按牌名合并计数，stdout 输出 Markdown 摘要；StartHook 可能只回 DeckSummaries 无完整牌表——此时解析到 0 套牌且既有 `inventory.json` 非空则拒绝覆写（退出码 3）；日志无 StartHook 退出码 4。库存快照有时效性，合成 / 开包 / 删改套牌后需重跑刷新。
- 回归用合成样本：`tools/testdata/mtga_log_sample.txt`（scan）与 `mtga_log_sample2.txt`（三件套）。

## 退出码

- `0` 成功（含"无新比赛"）
- `2` 日志不存在 / 读取失败
- `3` inventory 空结果保护拒绝覆写（StartHook 只回 DeckSummaries、0 套牌且既有 inventory.json 非空）
- `4` 无比赛记录（report 无数据可聚合）/ 日志无 StartHook（inventory）

# tools/mtga_auto_tool.py

MTGA 自动化测试：**纯日志驱动**的半自动副驾。实时增量监听 Player.log，场终自动回收、局内决策辅助、N 场采样循环。仅 Python 标准库，解析基建直接复用 mtga_log_tool。

**红线声明**：本工具不做任何鼠标键盘模拟、不代替人对局内操作、不读取对手非公开信息——排队与全部局内决策的执行都是人工，程序只读写日志，规避 WotC 对局内自动化（botting）的协议风险。

## 用法

```bash
# 1. 实时监听：比赛开始/结束即时提示，场终自动 scan + opponent + replay + risk
python tools/mtga_auto_tool.py watch [--deck 牌表名]

# 2. 局内决策辅助：回合/生命/手牌简报 + 起手调度建议 + 未下地提醒
python tools/mtga_auto_tool.py advise --deck DeckList/.../deck.txt
python tools/mtga_auto_tool.py advise --lands 24 --deck-size 60   # 跳过牌表解析
python tools/mtga_auto_tool.py advise --lands 24 --deck-size 60 --land-min 2 --land-max 4

# 2b. LLM 增强分析（需 tools/llm_config.json）：我方决策点 + 日志静默 4s 时
#     拍局面快照发给 LLM 出建议；连续 3 次失败自动回退纯规则模式
python tools/mtga_auto_tool.py advise --deck deck.txt --llm [--llm-quiet 6]

# 2c. Web 监控台：浏览器实时看局面/手牌/事件流/LLM 建议（默认端口 8642）
python tools/mtga_auto_tool.py advise --llm --dashboard [PORT]   # → http://127.0.0.1:8642

# 3. 采样循环：等满 N 场（人工排队与对局），逐场自动回收，结束输出聚合报告
python tools/mtga_auto_tool.py run --games 10 --deck 牌表名 [--timeout 40]

# 4. 轮抓载荷录样：宽匹配含轮抓特征键的载荷整条落盘 tools/auto/draft_samples/
python tools/mtga_auto_tool.py draft --record

# 4b. 实时 pick 排名面板：tail BotDraftDraftStatus，当前包按等级/社区分排序出
#     Web 面板（3s 自刷新；含 curve_fit 缺口提示与已抓牌池/曲线统计）。
#     系列码缺省从 EventName QuickDraft_<SET>_ 解析，--set 可覆盖；
#     默认端口 8643（避开 advise 监控台 8642），可与 advise 并行
python tools/mtga_auto_tool.py draft --watch [--set HOB] [--port 8643]
```

- 通用参数：`--log` 覆盖日志路径（默认同 mtga_log_tool）；`--poll` 轮询间隔秒（默认 2）；`--from-start` 从头处理整个日志（默认只监听新增内容）；`--max-polls N` 轮询 N 次后退出（测试/冒烟用）。
- `run` 的会话产物（动作日志 + 聚合报告）写入 `tools/auto/sessions/<时间戳>/`（已被 .gitignore 排除）。
- `advise` 调度口径：留牌区间按超几何期望推导——期望地数 = 手牌数 × 地当量/牌库数，区间 [期望四舍五入−1, 期望+2]，下限不低于 2，可用 `--land-min/--land-max` 覆盖；牌表地数用 `--deck` 从牌表现算（MDFC 计 0.5 当量，逐牌 Scryfall 判 Land，走 mtg_tool 磁盘缓存）。**不给 `--deck`/`--lands` 时自动从日志最近提交的 courseDeck 识别牌表与地数**（含 LLM 上下文的牌表文本），对局中检测到新提交牌表自动切换口径。**牌表最高优先级事实源是每场比赛 ConnectResp 携带的 deckMessage（本局实际提交牌表）**：一旦出现即覆盖 `--deck` 文件与 courseDeck 口径（实测教训：陈旧的 --deck 文件与局面快照矛盾会直接毒化 LLM 推理）；Bo3 换局（gameNumber 变化）局内状态全量重置，zoneId/instanceId 不跨局残留。
- `advise` 对局结束自动检测：增量载荷出现 finalMatchResult 即播报比分胜负并自动执行 scan+opponent+replay+risk 回收（启动追平的历史载荷不触发，避免重复回收）。
- `advise --llm` 口径：局面快照由日志精确重建（双方战场/堆叠/坟墓场、我方手牌逐牌附费用+类型+oracle 文本、生命、回合阶段、我方未横置地数与本回合是否已下地、**服务器判定的当前合法动作列表**（actionsAvailableReq，含结构化费用，施放/下地/异能/历险施放——LLM 建议只允许从中选择，费用幻觉的事实锚点；Activate_Mana/FloatMana 噪音已过滤）），oracle 文本走 Scryfall 磁盘缓存、战场牌截断 800 字符（截太短会切掉关键异能——The Great Henge 抓牌触发器、Hunter's Talent 三级抓牌条款两次实测踩坑）；历险/MDFC 子物件（带 parentId 的影子物件）一律排除，不污染战场与手牌计数；grpId 未解析的物件按 superTypes/cardTypes/subtypes 降级渲染（如"未解析 Basic Land Forest #100131"），禁止 LLM 安牌名。**对手手牌只报张数并显式标注"身份未知，禁止假设具体牌"**——服务器未下发的信息模型无从得知，prompt 层强制防脑补。LLM 建议连同完整快照落盘 `tools/auto/llm_advice.jsonl`（含 prompt 字段，供赛后诊断 AI 到底"看到"了什么）。LLM 配置 `tools/llm_config.json`（OpenAI 兼容端点，默认 DeepSeek `deepseek-chat`，可改 `deepseek-reasoner` 换推理强度换延迟；`api_key` 可用环境变量 `DEEPSEEK_API_KEY` 覆盖；该文件已被 .gitignore 排除，**不得提交**）。
- Windows 控制台中文输出需 `PYTHONIOENCODING=utf-8`（同既有工具坑位）。
- 轮抓 `draft --watch` 面板口径：启动先回扫日志最后 200KB 恢复当前包状态，抓不到就等下一条；每条 BotDraftDraftStatus 响应更新包号/抓号/当前包/已抓池并在控制台打印 `[draft] P<包>Pick<抓> 包内 N 张 | 已抓 M 张`；排名主键字母等级（S→F，mtga_draft_tool 预生成评分表）、次键社区分，curve_fit（deck_core）作第三参考提示（补 N 费缺口/N 费已溢出）；未评级牌显示 `?` 排最后，grpId 解析失败显示 `<grpId N>`，均不丢牌；DraftStatus 非 PickNext（如 Complete/Completed）时面板只显示对应状态。17Lands 数据（`load_ratings`，Quick/Premier 按 EventName 推导）已进入推荐：signal 轴按真实 ALSA 判定颜色开放（无 ALSA 时降级为本包高等级牌计数快照），LLM 离线 raw_power 锚点按 0.6 等级 + 0.4 GIH 归一化（deck_core.gih_anchor，按系列非空 GIH WR 的 min/max 线性归一到 0..1）混合，LLM prompt 行附 `gih_wr_pct` 百分比，面板两套表在"社区分"后加 GIH 列（无数据显示 `-`）；17Lands 不可用（无网/无缓存/无系列码）时锚点退回纯等级、signal 轴退回等级锚点、GIH 列全 `-`，只告警不阻断轮抓。推荐为九轴 WASPAS（新增确定性 color_fit 主色契合轴：已抓有色 ≥5 张后，牌色 ⊆ 计数前二主色 1.0 / 有交集 0.5 / 完全脱色 0.15 / 无色 0.6 / 方向未明 0.5；权重见 draft_methodology.md §2），离线理由附「贴合主色/脱离主色」。pick 推荐 prompt 已瘦身（oracle_text 截 300 字符、已抓牌池改摘要 JSON：colors/curve/key_cards 封顶 10，并要求脱色牌 synergy ≤0.3），调用强制 `response_format=json_object`（`parse_llm_scores` 兼容裸数组与 {"picks": [...]} 两种顶层形态，防 2026-09 实测的空体解析失败）。LLM 推荐状态为 offline 时（单次失败即锁定，下一抓自动重试），可点面板"重试推荐"按钮（POST `/api/advice/retry`）立即重推当前包。
- 回归测试：`python tools/test_mtga_auto.py`（63 例，覆盖增量读取/截断、分块 JSON 提取、状态跟踪（含 Bo3 局级隔离/deckMessage 牌表事实源/主阶段 step 清理）、调度口径、快照渲染、LLM 客户端与配置加载（含 response_format 透传）、watch/run/draft 录样与 pick 面板状态机（字符串化 Payload 解析/pack-pick 推进/排名渲染/17Lands GIH-ALSA 注入与失败降级/json_object 强制）；网络与子进程全部 mock，不触真实 MTGA/LLM）。

## 退出码

- `0` 成功
- `2` 日志 / 牌表文件不存在或解析失败、advise 缺地数参数
- `5` LLM 配置缺失（`--llm` 时无 llm_config.json / api_key）
- `7` run 单场等待超过 `--timeout` 分钟未完成，中止

---

# tools/mtga_draft_tool.py

快速轮抓（Quick Draft）驾驶舱：逐卡评分锚点 + 包/pick 跟踪 + LLM 推荐（代码已接入，真实 HOB 录样回放已验收，待在线 Quick Draft 验收）。仅 Python 标准库，日志管线/LLM 后端复用 mtga_auto_tool。

```bash
# 1. 预生成逐卡评分表（社区评测 + LLM 综合，离线一次性；缺省只补未评，幂等）
python tools/mtga_draft_tool.py build-ratings --set HOB \
    --context SetReview/HOB_20260806/02_LimitedEnvironment.md

# 2. 17Lands 胜率缓存（直连优先、shiqidi 同源代理兜底，磁盘缓存 3 天）
python tools/mtga_draft_tool.py ratings --set FDN [--format QuickDraft] [--refresh]
```

- 评分表口径：字母等级 S/A/A-/B+/B/B-/C+/C/C-/D/F + ≤40 字中文短评 + 社区分（Draftsim 0-10，有则附）；输入 = Scryfall 集合 JSON（自动找 `SetReview/<SET>_*/data/scryfall_*.json`）+ 社区评分明细（`tools/cache/draft_ratings/<SET>_draftsim.json`）+ 系列环境摘要；分批（25 张/批）调 LLM，逐批落盘 `tools/cache/draft_ratings/<SET>.json`，中断重跑自动续评；LLM 漏评的牌给占位，`--refresh` 重评。
- 数据时效注记：17Lands `card_ratings` 公共端点 2026-08 一度失效（NEO/BLB/ECL 等历史系列全 0），期间由 shiqidi 同源代理维持在线数据；2026-10 复查直连已恢复。代码直连优先、代理兜底、磁盘缓存 3 天；本地预生成评分表仍是轮抓中喂给 LLM 的事实锚点。
- 回归测试：`python tools/test_mtga_draft.py`（10 例，Ratings/缓存降级/评分表生成与合并，网络与 LLM 全 mock）。
- 设计先验：`tools/draft_methodology.md`（评分公式 / 9 轴 WASPAS pick 内核 / 信号读取 / 组牌骨架数字，沉淀自旧项目 MTGCacu 限制赛代码与教学笔记）。
- 纯函数内核：`tools/deck_core.py`——WASPAS 九轴综合（机器轴：曲线契合/主色契合/颜色开放度/信号/调色/去除/稀有度；LLM 只出 RawPower/Synergy）、信号读取（ALSA 顺位比较，无 ALSA 降级为高等级牌计数）、组牌骨架（动态地数/曲线评级/颜色深度/splash 准入/法术力配比/爆地卡地自检）。无 I/O，回归 `python tools/test_draft_core.py`。
- 限制赛策略：`tools/limited_strategy.py` 负责颜色方案、splash、曲线感知选牌、动态地数与报告数据；`tools/roles.py` 负责九根角色标签和 AI 标签五折合并，均无 I/O。
- 轮抓推荐：`tools/draft_advisor.py` 负责机器七轴与 LLM 两轴，`deck_pooper.py draft` 只转发到 `mtga_auto_tool.py`，LLM 失败时显式显示 offline 并保留机器排名。
- 构筑赛策略：`tools/constructed_strategy.py` 按 M1-M9 模块配额保留种子并补位，支持普通 60/15 与 Brawl 1+99；候选缺少目标赛制合法性时门禁失败。

# tools/mtga_db_tool.py

MTGA 客户端卡库直查：读取客户端 SQLite 卡库（`Raw_CardDatabase_*.mtga`），自动嗅探表 / 列结构，按 grpId 反查英文牌名 / 系列 / 编号 / 稀有度，作 Scryfall 查不到 arena_id 时的兜底数据源。仅 Python 标准库。

```bash
# 1. 按 grpId 反查牌名 / 系列 / 编号 / 稀有度
python tools/mtga_db_tool.py "C:\path\to\Raw_CardDatabase_xxx.mtga" 12345 67890

# 2. 无 grpId 时列出库内表名（用于嗅探结构）
python tools/mtga_db_tool.py "C:\path\to\Raw_CardDatabase_xxx.mtga"
```

# tools/deck_version.py

版本化交付脚手架：按 `--format --colors --theme` 生成 `DeckList/{format}_{colors}_{theme}/` 目录与 `{Name}V{n}.txt` + `{Name}V{n}.md` 成对文件（版本 max+1、禁覆盖），并生成设计文档骨架；基础门禁：主牌 ≥60、备牌 0 或 15、同名 >4 报警（基本地与牌面 ANY_NUMBER 豁免）。仅 Python 标准库。

```bash
# 1. 参数直传（纯英文 / 数字参数）
python tools/deck_version.py --format explorer --colors ug --theme Flash \
    --deck-file deck.txt --notes "初稿"

# 2. 在既有方向子文件夹内续版本
python tools/deck_version.py --dir DeckList/Explorer_SlimeAgainstHumanity/Golgari \
    --deck-file deck.txt

# 3. 含中文参数必须走 JSON 传参（控制台编码坑位）
python tools/deck_version.py --config params.json
```

## 退出码

- `0` 成功
- `2` 门禁警告（仍写盘，需人工确认警告项）

# tools/deck_image.py

牌表网格图生成：把 MTGA 导入格式牌表渲染成 Untapped.gg 风格卡牌网格图（默认中文界面，`--lang en` 切英文，造价行标签/明细同步英文化）。版式对齐 Untapped 模板：渐变顶栏 + 颜色身份圆点 + 战绩徽标；顶栏含两行统计——类型计数（中文化，如 "26 生物 · 10 瞬间 · 23 地"）与比率行（生物/非生物/地占比，有色占比按非地口径），造价带右侧附指标释义（物质点/PP核心/PP全量）。牌区中央斜置低透明度 DeckPooper 商标水印（`--no-watermark` 关闭），页脚含 DeckPooper 品牌署名；画布底部留footer 净空带（备牌列再高也不会贴边出血）。每种牌一格（stack）= 卡图顶部切片叠放 + 底部完整卡图——副本 1..N-1 各贡献一条切片（卡图顶部 12.5% 高度，含牌框边与名牌栏，切片底部留 2px 深色缝模拟牌堆阴影），格高 = (N-1)×切片高 + tile_h，>4 张拆多格（4/4/3）；主牌区固定 5 列、行优先填充、行高 = 该行最高格高，类别分组（组内 cmc 升序）连续填充；主牌/备牌各有 "主牌 · 60 张" / "备牌 · 15 张" 分节标头（带分区线），备牌右侧独立列、1–2 列均衡分配（每列 ≤8 格），列数自动选择：优先让右列 ≤ 主牌区高度（不撑高画布），并列取少列保牌格尺寸；Commander / Companion 分区单独解析为独立位（右列顶部，带"指挥官/伙伴"标签与主题色描边，造价核算含独立位、不含备牌）；动态列宽（总宽 ≤1600px）。类型统计中文化（如 "26 生物 · 10 瞬间 · 23 地"），造价行同 deck_cost 口径：MRUC 四稀有度图标 + 数量（野卡卡背贴图不随仓库分发：本机可用 `tools/extract_mtga_icons.py` 从 MTGA 客户端提取至 `tools/assets/icons/wildcard/`（gitignored），其次旧缓存目录，皆缺时回退手绘色块，配色秘稀红橙/稀有金/非普通银/普通灰黑），物质点与 PP 明细随后；基本地不计，快照外牌经 Scryfall 回退补全、双重落空才整行省略；指标定义见根目录 `MtgDeckCostMetric.md`）。卡图简中优先、三级来源：① MTGCH 主源（`mtgch.com/api/v1/result?q=<牌名>&view=1`，display_name 精确匹配/双面牌按正面名，取 webp `image_url` 与 `display_name_zh`，覆盖含未发售新牌）→ ② Scryfall zhs（`cards/search` `!"<牌名>" lang:zhs` unique=prints）→ ③ 英文卡图；某级下载失败顺延下一级，命中统计区分来源（mtgch/scryfall）。缓存按真实扩展名（.webp/.jpg/.png）存 `tools/cache/card_images/`（gitignored，缓存键 mtgch_/zhs_ 前缀区分来源），复用 mtg_tool 的查询缓存、节流与 429 重试。依赖 Pillow（惰性导入，缺失时退出码 3）。

```bash
python tools/deck_image.py deck.txt --title "标题" --subtitle "副标题" --out deck.png
python tools/deck_image.py deck.txt --author 作者 --format standard --record 7-0 --lang en
```

# tools/extract_mtga_icons.py

MTGA 客户端图标提取（按需维护脚本，非工具链常驻环节）：从本机 MTGA 客户端 AssetBundle 提取 UI 图标为本地资源 `tools/assets/icons/`——`wildcard/` 野卡卡背四稀有度（deck_image 造价行用，**产物 gitignored 不入库**，缺失时造价行回退手绘色块）；`mana/`/`type/` 的提取功能已被 `tools/render_open_icons.py` 取代（见下），保留仅供对照。需要本机 MTGA 客户端 + 可选依赖 UnityPy / Pillow（均非常驻依赖）。

```bash
python tools/extract_mtga_icons.py            # 默认 Steam 库路径 → tools/assets/icons/
python tools/extract_mtga_icons.py --mtga-dir "<AssetBundle目录>" --out tools/assets/icons
```

# tools/render_open_icons.py

开源图标渲染：用 Andrew Gioia 的 Mana 字体（SIL OFL 1.1，固定版本 v1.17.1，zip 缓存于 `tools/cache/fonts/`）渲染 `tools/assets/icons/mana/`（46 个法术力符号：五色 + C/S/X/T/E + 数字 0–20 + 混色/双色）与 `tools/assets/icons/type/`（Artifact / Enchantment / Land）PNG，产物提交入库，许可与归属见 `tools/assets/icons/LICENSE-OFL.txt` 与 `NOTICE.md`。字体包变更时用 `--refresh` 强制重下。依赖 Pillow（惰性导入）。

```bash
python tools/render_open_icons.py              # 缓存命中则不重下
python tools/render_open_icons.py --refresh    # 强制重新下载字体
```

# tools/rot_audit.py

标准轮替存活审计：判定牌表在下一次轮替后还剩多少张可用。判定不用 `f:standard`（Scryfall 合法性按 oracle 算，促销印会显示 legal 但救不了牌），按 `set_type ∈ {core, expansion}` 且非 digital 且 `released_at` ≥ 轮替后最旧系列（内置本轮参数：轮替日 2027-02-02，cutoff = FDN 2024-11-15）。仅 Python 标准库。

```bash
# 1. 逐张审计一份牌表（报主牌 x/60、备牌 y/15 存活）
python tools/rot_audit.py deck deck.txt

# 2. 审计指定牌
python tools/rot_audit.py card "Lightning Strike" "Monstrous Rage"
```

# tools/cn_audit.py

中文牌名审计门禁：抓出「英文名正确、中文名手写编造」的牌。从交付 md 中抽出中文牌名候选（表格区硬判定 + 括号清单软候选），逐个反查 mtgch，并与文件内英文牌名交叉比对识别「撞名」；限流（error）与查无此牌（none）分开建模。结果缓存侧车 `tools/cache/_cn_audit_cache.json`（gitignored）。依赖 curl。

```bash
# 1. 主门禁：审计交付文件（编造译名 exit 1；侧车 <文件>.cnignore 可豁免有意展示的旧错译）
python tools/cn_audit.py check report.md

# 2. 批量反查中文名 / 批量取官方中文名 / 查系列官方中文名
python tools/cn_audit.py zh names_zh.txt
python tools/cn_audit.py en names_en.txt
python tools/cn_audit.py set FRA
```

# tools/newbie/（标准新手系列工具组）

标准赛制低造价新手系列（6 副 BO1 套牌，见 `DeckList/Standard_*`）的专属工具，共 32 个纯标准库脚本：造价核算（`deck_cost.py` 造价签名 / 物质点预算 / PP 包数，指标口径与 MRUC 视觉方案见根目录 `MtgDeckCostMetric.md`；快照外牌自动走 Scryfall 回退、各 Arena 印刷取最低稀有度计价，`DECK_COST_NO_FALLBACK=1` 关闭、`mtga_cost.py`、`pack_points.py`）、逐套牌金鱼模拟器（`sim_black.py` / `sim_blue.py` / `sim_green.py` / `sim_red.py` / `sim_red_blind.py` / `sim_white.py` / `sim_mono_white.py` / `sim_blue_spells.py`——Phase 3 起均已收敛为 `goldfish/` 引擎（`goldfish/engine.py` 骨架 + `goldfish/data/*.json` 牌池 + `goldfish/decks/*.py` 回合逻辑 + `goldfish/mechanics.py` 机制注册表），原 sim 文件为兼容 shim，CLI 与模块级 API 不变；`sim_dual.py` 未纳入引擎，已标记过时/冻结，仅作历史参考）、轴线扫描（`*_axis_scan.py`、`axis_layers.py`）与地数扫描（`land_sweep.py`）。共享数据快照在 `tools/data/`（gitignored，约 21MB；rarity_map / std_prints / metagame 等），脚本经 `../data` 相对路径引用。来源与命令对照见 `AuditReport/NewbieSeries/合并说明_20260925.md`。

```bash
# 1. 造价签名一览（brief）/ 单表全口径（sig）
python tools/newbie/deck_cost.py brief DeckList/Standard_MonoBlack_CheapThreatDrain/deck_mono_black.txt
python tools/newbie/deck_cost.py sig <牌表…>

# 2. 金鱼模拟（例：单黑 1000 局，公平均杀基准 4.16）
python tools/newbie/sim_black.py 1000 DeckList/Standard_MonoBlack_CheapThreatDrain/deck_mono_black.txt
```
