# tools/mtg_tool.py + tools/forge_tool.py + tools/mtga_log_tool.py + tools/mtga_auto_tool.py

MTG 套牌构筑工作流 CLI。数据源：Scryfall API + mtgch.com API。仅 Python 标准库（3.7+）。

赛制字段说明：Scryfall `legalities` 没有 `explorer` 字段；`--format explorer` 会按内置别名表（`FORMAT_LEGALITY_ALIAS`，explorer→pioneer）推导合法性并在备注标注，Explorer = 先驱合法 ∩ Arena 可用 ∩ Explorer 专属禁牌（BO1/队列特例仍需人工查官方公告复核）。

## 通用

- 所有请求带 `User-Agent: NeoMtgDeckCacu/1.0`；Scryfall 节流 ≥100ms；429/5xx 指数退避（遵守 Retry-After），最多重试 5 次。
- 磁盘缓存：`tools/cache/{scryfall|mtgch}/<sha1>.json`（含 fetched_at / http_status / url / payload），重复请求直接命中；各子命令均有 `--no-cache` 绕过读取。mtgch 2026 年改版后中文名走新端点：逐牌 `GET /api/v1/result?q=<名>&view=1`（view=1 才带中文名）；按系列批量 `GET /api/v1/set/<code>/cards/`（`fetch_set_chinese_names`，逐牌风暴会被 429 限流，批量场景必须用这个）。
- 错误分类报告：网络失败 / HTTP 失败 / 查询语法错误（Scryfall error 对象）/ 分页不完整 / 模糊名未精确命中 / 真实零结果，互不混淆；任何失败不会被静默当作"不存在/不合法"。

## 用法

```bash
# 1. 候选牌枚举（全分页，oracle 去重，MDFC 从 card_faces 拼接 mana_cost/oracle_text）
python tools/mtg_tool.py search "f:pioneer game:arena date<=2026-08-08 ci<=ug o:flash t:creature" --unique oracle --out result.json

# 2. 逐牌三重核对（赛制合法 / Arena 平台可用【遍历全部印刷】/ mtgch 中文名），输出 Markdown 表格
python tools/mtg_tool.py check "Brineborn Cutthroat" "Brazen Borrower" --format pioneer --platform arena --out check.json

# 3. 牌表机器门禁（主牌≥60、备牌≤15、同名≤4（基本地与牌面"any number of cards named"豁免）、逐牌赛制+平台、可选颜色身份）
python tools/mtg_tool.py validate deck.txt --format pioneer --bo3 --colors ug

# 4. 环境基线（已发售系列 + 禁牌表，Markdown 可直接粘进报告）
python tools/mtg_tool.py baseline --format pioneer --date 2026-08-08
```

---

# tools/deck_pooper.py

DeckPooper 的限制赛组牌入口（P1）。它要求本地预生成评分表，并只接受牌池文本或
含 `DraftStatus=Complete` 的轮抓录样 JSONL；没有终态牌池时不会使用中间态数据。

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
伪造结果。

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
- 轮抓 `draft --watch` 面板口径：启动先回扫日志最后 200KB 恢复当前包状态，抓不到就等下一条；每条 BotDraftDraftStatus 响应更新包号/抓号/当前包/已抓池并在控制台打印 `[draft] P<包>Pick<抓> 包内 N 张 | 已抓 M 张`；排名主键字母等级（S→F，mtga_draft_tool 预生成评分表）、次键社区分，curve_fit（deck_core）作第三参考提示（补 N 费缺口/N 费已溢出）；未评级牌显示 `?` 排最后，grpId 解析失败显示 `<grpId N>`，均不丢牌；DraftStatus 非 PickNext（如 Complete）时面板只显示对应状态。
- 回归测试：`python tools/test_mtga_auto.py`（47 例，覆盖增量读取/截断、分块 JSON 提取、状态跟踪（含 Bo3 局级隔离/deckMessage 牌表事实源/主阶段 step 清理）、调度口径、快照渲染、LLM 客户端与配置加载、watch/run/draft 录样与 pick 面板状态机（字符串化 Payload 解析/pack-pick 推进/排名渲染）；网络与子进程全部 mock，不触真实 MTGA/LLM）。

## 退出码

- `0` 成功
- `2` 日志 / 牌表文件不存在或解析失败、advise 缺地数参数
- `5` LLM 配置缺失（`--llm` 时无 llm_config.json / api_key）
- `7` run 单场等待超过 `--timeout` 分钟未完成，中止

---

# tools/mtga_draft_tool.py

快速轮抓（Quick Draft）驾驶舱：逐卡评分锚点 + 包/pick 跟踪 + LLM 推荐（代码已接入，待真实录样验收）。仅 Python 标准库，日志管线/LLM 后端复用 mtga_auto_tool。

```bash
# 1. 预生成逐卡评分表（社区评测 + LLM 综合，离线一次性；缺省只补未评，幂等）
python tools/mtga_draft_tool.py build-ratings --set HOB \
    --context SetReview/HOB_20260806/02_LimitedEnvironment.md

# 2. 17Lands 胜率缓存（历史遗留：公共端点 2026 年已关闭，仅在有缓存/镜像时可用）
python tools/mtga_draft_tool.py ratings --set FDN [--format QuickDraft] [--refresh]
```

- 评分表口径：字母等级 S/A/A-/B+/B/B-/C+/C/C-/D/F + ≤40 字中文短评 + 社区分（Draftsim 0-10，有则附）；输入 = Scryfall 集合 JSON（自动找 `SetReview/<SET>_*/data/scryfall_*.json`）+ 社区评分明细（`tools/cache/draft_ratings/<SET>_draftsim.json`）+ 系列环境摘要；分批（25 张/批）调 LLM，逐批落盘 `tools/cache/draft_ratings/<SET>.json`，中断重跑自动续评；LLM 漏评的牌给占位，`--refresh` 重评。
- 数据时效注记：17Lands `card_ratings` 公共端点与 S3 公开桶均已关闭（2026-08 实测 NEO/BLB/ECL 等历史系列也全 0），本地预生成表是当前唯一锚点源。
- 回归测试：`python tools/test_mtga_draft.py`（10 例，Ratings/缓存降级/评分表生成与合并，网络与 LLM 全 mock）。
- 设计先验：`tools/draft_methodology.md`（评分公式 / 8 轴 WASPAS pick 内核 / 信号读取 / 组牌骨架数字，沉淀自旧项目 MTGCacu 限制赛代码与教学笔记）。
- 纯函数内核：`tools/deck_core.py`——WASPAS 八轴综合（机器轴：曲线契合/颜色开放度/信号/调色/去除/稀有度；LLM 只出 RawPower/Synergy）、信号读取（ALSA 顺位比较，无 ALSA 降级为高等级牌计数）、组牌骨架（动态地数/曲线评级/颜色深度/splash 准入/法术力配比/爆地卡地自检）。无 I/O，回归 `python tools/test_draft_core.py`。
- 限制赛策略：`tools/limited_strategy.py` 负责颜色方案、splash、曲线感知选牌、动态地数与报告数据；`tools/roles.py` 负责九根角色标签和 AI 标签五折合并，均无 I/O。
- 轮抓推荐：`tools/draft_advisor.py` 负责机器六轴与 LLM 两轴，`deck_pooper.py draft` 只转发到 `mtga_auto_tool.py`，LLM 失败时显式显示 offline 并保留机器排名。
- 构筑赛策略：`tools/constructed_strategy.py` 按 M1-M9 模块配额保留种子并补位，支持普通 60/15 与 Brawl 1+99；候选缺少目标赛制合法性时门禁失败。
