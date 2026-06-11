# 信息来源链路分析：配置 → 探测 → 展示（基于现有架构）

> 目标期望：配置里记录来源网址；信息探测**以 RSS 为先**，其它方式按可靠性依次标记；
> **以"可靠的探测方式"为准进行展示**，为后续信息获取打基础。
> 本文基于现有代码逐项分析问题与处理方案，**暂以当前架构为准**，分阶段推进。

## 1. 现状链路（实测）

```
config/sources.example.yaml  ──load_sources_config──▶ SourceConfig
        │                                                  │
        │                              sync_sources_config_to_db（只 create/update，不删配置外行）
        ▼                                                  ▼
   每个来源：type / fetch_strategy / homepage_url / feed_url / strategy_notes(仅注释)
        │
        ▼
背景抓取 background_fetch.run_source_fetch_in_background
   strategy = source.fetch_strategy        ← 直接用配置策略，无"有效策略"计算
   if rss → probe_rss_source ; if html_index → probe_html_index_source
        ▼
   SourceItem 入库（不记录"实际用哪种策略成功"）
        ▼
展示：/sources/{key} 用 describe_fetch_strategy(source.fetch_strategy)  ← 展示的是"配置策略"
```

当前 15 个来源：8 个 rss（均有 feed_url）、7 个 html_index（feed_url=null）。
今天**没有违反** RSS 优先约定，但这是人工维护 YAML 的结果，**代码没有任何保障**。

## 2. 问题清单（grounded）

### P-A：RSS 优先只是"文档约定"，代码未实现
- `sources.example.yaml` 头部写了规则：`if feed_url exists: effective_strategy="rss"`。
- 但 `background_fetch.py:337` 与 `fetch_service.py:125` 都是 `strategy = source.fetch_strategy`，
  **直接信任配置策略**，没有"有 feed_url 就优先 RSS"的计算。
- 风险：将来有人把一个有 feed_url 的源配成 `html_index`，系统就会用更不可靠的方式抓，
  且**无人察觉**。

### P-B：可靠性顺序没有落到数据/代码
- `strategy_notes` / `strategy_status`（needs_review 等）在 YAML 注释里存在，但
  `config_loader` **根本没解析**它们 → 应用层完全看不到可靠性标记。
- 没有"策略可靠性排序"的常量或函数，无法按可靠性排序/标记。

### P-C：展示用的是"配置策略"，不是"实际可靠探测方式"
- 工作台展示 `describe_fetch_strategy(source.fetch_strategy)`，是配置值。
- 没有记录"这次 FetchRun 实际用哪种策略、是否回退"，所以无法"以可靠的探测方式为准展示"。

### P-D：没有回退链（fallback chain）
- 期望：RSS 失败 → 尝试 sitemap/feed 发现 → 再 html_index。
- 现状：单一策略，失败即 `failed`，不会自动尝试更低一档的可靠方式。

### P-E：字段冗余与不一致风险
- `Source.source_type` 与 `Source.fetch_strategy` 基本重复（都为 rss/html_index）。
- 两处支持集合 `SUPPORTED_STRATEGIES`（fetch_service）与 `SUPPORTED_FETCH_STRATEGIES`
  （due_sources）各自定义，易漂移。

### P-F：feed 自动发现缺失
- html_index 源若官方后来上线了 RSS，系统无法自动发现并"升级"到更可靠的 RSS。

## 3. 处理方案（分阶段，当前架构内）

### 阶段 S1（本次落地，低风险、只读/展示）
1. 新增**纯函数** `effective_strategy.py`：
   - `RELIABILITY_ORDER`：rss > json_feed > sitemap > api > html_index > single_url > crawler ...
   - `compute_effective_strategy(feed_url, fetch_strategy)`：实现 YAML 约定（有 feed_url 优先 rss）。
   - `reliability_rank(strategy)`：可靠性序号。
   - `check_strategy_consistency(...)`：配置不一致告警（有 feed_url 但策略非 rss / rss 无 feed）。
2. 工作台展示"有效探测方式（按可靠性）"+ 配置不一致时给出**告警**（P-A/P-C 的展示侧）。
3. quick_test 把"当前 config 无 RSS 优先违规"固化为**回归护栏**（P-A 防漂移）。
- **不改抓取行为**，纯展示 + 护栏。

### 阶段 S2（让抓取以有效策略为准）✅ 已落地
- 抓取入口（`background_fetch.run_source_fetch_in_background` 与
  `fetch_service.SourceFetchService.run_source`）改用 `compute_effective_strategy(...)`
  选择 probe（有 feed_url 强制走 RSS）。对当前 15 个来源**行为不变**（effective==configured），
  但堵住"有 feed_url 却配成 html_index 会用弱方式抓"的隐患（P-A 抓取侧）。
- `FetchRun.metadata_json` 新增 `fetch_strategy.{configured, effective, rss_first_applied}`
  记录"实际用哪种策略抓"（P-C 抓取侧）。
- UI：工作台"推荐策略"行标注"实际抓取以此为准"，配置与有效策略漂移时显示"策略提示"告警。
- 验收：隔离 DB + mock RSS 真实抓取通过；background RSS 单测断言 metadata 记录 effective=rss。
- 顺带修正一个测试 fixture（html_index 源误带 feed_url），使其符合 RSS 优先语义。

### 阶段 S3（可靠性回退链）✅ 已落地（默认关闭）
- 纯函数 `build_strategy_chain(...)`（按可靠性排序、只含有可用 URL 的支持策略）+
  `select_succeeding_probe(chain, probe_runner)`（依次尝试直到成功，记录每档结果）。
- `background_fetch` 接入回退链，**由 `RADAR_FETCH_FALLBACK_ENABLED` 显式开启**；
  默认关闭时 = 单次有效策略尝试（与 S2 行为完全一致，零回归）。
- 开启后 RSS 失败自动降级 html_index；`FetchRun.metadata_json.fetch_strategy` 记录
  `succeeded` / `fallback_used` / `attempts`（实际成功的探测方式）。
- 隔离 DB + 探针 monkeypatch 验收 `scripts/acceptance_fetch_fallback_chain.py`：
  开启时 RSS 失败→html_index 成功→success；关闭时 RSS 失败→failed 且不尝试 html。

### 阶段 S4（解析可靠性元数据 + 字段收敛）
- ✅ S4(a)：统一两处 SUPPORTED 集合到单一来源——
  `effective_strategy.SUPPORTED_STRATEGIES` 为唯一真源，`fetch_service.SUPPORTED_STRATEGIES`
  与 `due_sources.SUPPORTED_FETCH_STRATEGIES` 改为复用同一对象（quick_test 固化为护栏）。
- ✅ S4(b)：`SourceConfig` 新增 `strategy_notes` / `strategy_status`（可选，默认空），
  `config_loader` 解析 YAML 已有的可靠性注释；工作台展示"策略说明 / 可靠性状态"。
  仅用于展示/审阅，不影响抓取决策（P-B 落地）。
- ✅ S4(c)：`source_type` 与 `fetch_strategy` 冗余评估（结论：保留双字段，不改 schema）。

#### S4(c) 评估结论
- **不是同一枚举**：`SourceType={rss, html_index, manual_pdf, report_page}`（"来源本质"），
  `FetchStrategy={rss, html_index, manual}`（"抓取方式"）。语义不同。
- **当前实践完全冗余**：15 个来源全部 `type == fetch_strategy`（均 ∈ {rss, html_index}）。
- **Source 注册表的 `source_type` 实为只写字段**：`db_sync` 写入 `cfg.type`，但**没有任何
  逻辑读取它做决策**（main.py / insight_compiler 里读的 `source_type` 是 InsightCard 的
  内容类型枚举 html/pdf/unknown，与来源注册表无关）。
- **决策**：**保留双字段、不删列**（删字段 = schema/config 结构变更，违背"以当前架构为准"纪律）。
  改为：① 文档化两者语义差异；② 加 drift 护栏——对使用受支持策略（rss/html_index）的配置来源，
  锁定 `type == fetch_strategy` 约定，未来漂移即被 quick_test 拦截。
- **后续（非本阶段）**：若引入 manual_pdf / report_page 等真正需要区分 type 与 strategy 的来源，
  再重新评估字段收敛或显式拆分语义。

### 阶段 S5（feed 自动发现）✅ 已落地（只读、suggest-only）
- 纯函数 `feed_discovery.discover_feed_links(html, base_url)`：解析
  `<link rel=alternate type=application/rss+xml|atom+xml|feed+json>`，相对地址转绝对、去重，
  恶意/空输入不抛异常。**无网络 I/O，离线可单测**。
- `scripts/discover_source_feeds.py`：对 html_index 源抓主页、发现 feed 后**建议升级到 RSS**。
  **只读 suggest-only**：不改 config/sources.yaml、不写库、不改抓取行为；网络仅在显式运行时发生，
  CI/quick_test 保持离线。

## 4. 本次（S1）边界
- 只新增纯函数 + 工作台展示 + 回归护栏。
- 不改抓取流程、不改 due-source、不改 config schema、不调用 LLM、不写库。

参考：[V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)、
[V1_OPTIMIZATION_ROADMAP.md](V1_OPTIMIZATION_ROADMAP.md)
