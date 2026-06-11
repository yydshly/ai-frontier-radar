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

### 阶段 S3（可靠性回退链）
- RSS 失败 → 依可靠性顺序尝试下一档；记录每档结果；展示"实际成功的探测方式"。

### 阶段 S4（解析可靠性元数据 + 字段收敛）
- `config_loader` 解析 `strategy_notes` / `strategy_status` 进 SourceConfig 并展示。
- 统一两处 SUPPORTED 集合到单一来源；评估 `source_type` 与 `fetch_strategy` 去冗余。

### 阶段 S5（feed 自动发现）
- 对 html_index 源做一次性 feed 探测（`<link rel=alternate type=application/rss+xml>`），
  发现后建议"升级到 RSS"。属后置能力。

## 4. 本次（S1）边界
- 只新增纯函数 + 工作台展示 + 回归护栏。
- 不改抓取流程、不改 due-source、不改 config schema、不调用 LLM、不写库。

参考：[V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)、
[V1_OPTIMIZATION_ROADMAP.md](V1_OPTIMIZATION_ROADMAP.md)
