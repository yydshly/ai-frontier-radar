# AI Frontier Radar 优化路线图（P-001 ~ P-004）

> 设计先行文档。本文件只做分析与规划，不改功能代码。
> 落地按"小步、受控、设计先行、默认只读 / 低成本"的一贯纪律分阶段进行。

## 0. 目标概述

| 编号 | 问题 | 方向 |
|------|------|------|
| P-001 | 信息来源入口策略不清晰 | RSS 优先，HTML index 补充，API/单 URL 居中，爬虫后置 |
| P-002 | 精品来源详情页能力不足 | 每个 source 的来源工作台展示获取方式、抓取状态、文章列表、摘要与入口 |
| P-003 | 缺少每日信息编译能力 | 今日新增 → 核心摘要 → 今日报告卡片 → 语音播报 |
| P-004 | 来源入口写死 | 支持用户自定义接入 RSS / HTML index / 单篇 URL / PDF，抓取策略受控 |

## 1. 现状盘点（基于代码）

- **抓取策略**：仅 `rss` + `html_index` 受支持（`app/application/sources/fetch_service.py:29`
  `SUPPORTED_STRATEGIES`，`due_sources.py:21` `SUPPORTED_FETCH_STRATEGIES`）。
  `manual` 是字符串但不在受支持集合，会被判 `unsupported`。
  `models.py:79` 注释提到 `manual_pdf / report_page`，但未实现抓取。
- **来源定义**：仅靠 `config/sources.yaml`（缺省回退 `sources.example.yaml`），
  经 `db_sync` 同步进 DB。**没有 UI / API 添加来源**。
- **来源详情页**：`/sources/{source_key}` 已是只读工作台（基础信息、due-source 判断、
  最近 FetchRun、最近 SourceItem、摘要覆盖、InsightCard 覆盖、手动探测、stale 警告）。
- **今日雷达**：`/radar/today` 候选列表 + 中文摘要 / 一句话 + 阅读面板 + InsightCard 入口
  + 摘要生成 + due-source 更新 + 调度状态。
- **每日核心报告 / 语音播报**：均不存在。
- **InsightCard**：单篇编译链路存在（`insight_compiler.py` / `compile_service.py`）。

## 2. 差距与方向

### P-001 信息来源入口策略
现状半成品：rss + html_index 已支持，但没有"优先级阶梯 + 回退"的显式策略，
也没有形式化的能力矩阵。可用获取方式（由轻到重）：

1. **轻量优先**：RSS / Atom / JSON Feed → `sitemap.xml` → 官方 API
   （arXiv API、GitHub Releases、HuggingFace API 等）
2. **中量**：HTML index 解析（已实现）→ 单篇 URL 抓取
3. **重量后置**：渲染型爬虫（Playwright，应对 JS 站）、变更检测
4. **人工 / 外部**：PDF 上传、邮件 newsletter 转 feed

→ 详见 [V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)。

### P-002 精品来源详情页
大部分已存在（`/sources/{source_key}`）。缺"像今日雷达那样"的呈现：
文章列表带中文摘要、获取方式说明、获取日期、阅读入口。属**增强**，不重做页面。

### P-003 今日编译能力
最大空白。今日新增 → 核心摘要 → 今日报告卡片 → 语音播报，全部缺失。
风险点：聚合维度、LLM 成本、TTS 依赖与可关闭性。

### P-004 来源不写死
空白。来源只能改 YAML 文件。需要"用户接入 RSS / HTML / 单 URL / PDF 且策略受控"
的入口（白名单约束 + dry-run 预览 + 写库），爬虫 / PDF 默认后置 / 需显式开启。

## 3. 分阶段路线（每阶段独立任务，设计先行）

| 阶段 | 任务 | 交付 | 风险 | LLM/写库 |
|------|------|------|------|----------|
| Phase A | **P-001 策略阶梯设计**（本轮） | 能力矩阵 + 策略词表 + 回退规则文档 | 低 | 无 |
| Phase B | P-002 来源工作台增强 | 文章列表 + 摘要状态 + 获取方式 + 日期 + 阅读入口 | 低 | 只读 |
| Phase C | P-003-1 每日聚合视图（不调 LLM） | 今日报告卡片**数据结构** + 聚合只读视图 | 中 | 只读 |
| Phase D | P-003-2 核心摘要生成 | 显式触发、成本闸门控制的核心摘要 | 中 | 写库 + LLM（受控） |
| Phase E | P-003-3 语音播报 | TTS 独立可关闭模块 | 中 | 外部 TTS（受控） |
| Phase F | P-004 自定义来源接入 | UI/API 添加来源，白名单策略 + dry-run 预览 | 高 | 写库 |

排序理由：P-001 定义的策略词表是 P-002 / P-004 的依赖；P-002 风险最低先见效；
P-003 拆三步避免一次性引入聚合 + LLM + TTS；P-004 写库 + 安全面最大，放最后。

## 4. 全局边界（所有阶段适用）

- 不引入 Celery / Redis / APScheduler 等重型基础设施。
- 默认不触发 LLM；任何 LLM / TTS 自动化必须可关闭、有成本闸门。
- 爬虫 / PDF 等重量策略默认后置，需显式开启，不进默认自动调度。
- 抓取内容进入 LLM 前的清洗 / prompt injection 防护沿用现有链路，自动化不得绕过。
- 写库类操作设计先行、dry-run 优先、人工确认闸门保留。

## 5. 当前进度

- ✅ Phase A 设计：见 [V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)
- ✅ Phase B 设计：见 [V1_SOURCE_WORKSPACE_ENHANCEMENT_PLAN.md](V1_SOURCE_WORKSPACE_ENHANCEMENT_PLAN.md)
- ✅ Phase B 落地：`/sources/{source_key}` 文章列表新增中文摘要预览、摘要状态、
  首次/最近发现双时间，基础信息新增"获取方式"中文文案（`describe_fetch_strategy`
  helper，复用 P-001 策略词表）。只读、复用 `build_candidate_display_card`。
- ✅ Phase C 第一步（P-003-1）：只读每日聚合 `daily_digest.py` +
  `/radar/today` 侧栏"今日编译概览"小块（今日新增 / 已摘要 / 已生成卡片 / 覆盖来源
  + 至多 5 条已摘要条目）。只读、不调 LLM、SQL 计数、复用 display helper；
  UI 仅追加侧栏小块，不改三栏布局。
- ✅ Phase D 第一步（P-003-2）：今日核心报告生成基础 `daily_report.py` +
  `scripts/run_daily_report_once.py`。**默认 dry-run（不调 LLM）**，`--apply` 需
  `DAILY_REPORT_ENABLED=true`，单次一调、`DAILY_REPORT_MAX_ITEMS` 限量，复用
  `create_llm_client().generate_json`，provider 可注入（测试用 Mock，**CI 不打真实
  LLM**），不持久化、不改布局。设计见
  [V1_DAILY_CORE_REPORT_PLAN.md](V1_DAILY_CORE_REPORT_PLAN.md)。
- ⏳ Phase D 步骤 2：UI 显式"生成今日核心报告"按钮（小调整）。
- ⏳ Phase E~F：语音播报（TTS，可关闭）→ 自定义来源接入（P-004）

## 6. 顺带完成的代码优化

随设计推进同步做的低风险、可验证优化（语义不变，测试覆盖）：

- **来源工作台摘要覆盖统计**：`/sources/{source_key}` 原先把该来源**整表
  SourceItem 载入 Python** 再逐条字符串扫描统计"已有中文摘要"。已改为 SQL
  `COUNT + OR LIKE`，语义一致（实测 openai_news / anthropic_news 计数不变），
  避免大来源下的全表内存加载。

### 已记录、暂不改的观察

- `compute_due_sources()` 对每个配置来源各做一次 Source / FetchRun 查询（N+1，
  N≈15）。当前来源量下开销可接受；它是核心调度逻辑，按纪律不在优化轮里改，
  待来源规模显著增长或调度专项任务再处理。
