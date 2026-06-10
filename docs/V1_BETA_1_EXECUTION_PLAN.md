# V1.0-beta.1 执行计划：来源调度与单来源工作台

## 1. 目标

把系统从"手动更新全部雷达关注源"升级为：

```
判断该探测的来源
→ 只运行 due sources
→ 显示跳过原因
→ 单来源可排查
```

核心价值：

- 不重复探测已在 running 的来源
- 告诉用户为什么某个来源没被更新
- 提供单来源健康视图和手动触发能力

---

## 2. 任务拆分

### Task 1：due-source 计算服务 ✅ 已实现

**范围**：
- 新增 `compute_due_sources()` 函数
- 不改 DB（只读查询）
- 基于 FetchRun 历史计算 last_run / running / skipped
- 输出结构：`DueSourcePlan(due, skipped, running, unsupported, missing)`

**实现产物**：
- `app/application/sources/due_sources.py` — 核心计算服务（只读）
- `scripts/check_due_sources.py` — 诊断脚本（只读，不触发抓取）

**关键数据结构**：
```python
@dataclass(frozen=True)
class DueSourceDecision:
    source_key: str
    source_name: str
    status: str  # "due" | "skipped" | "running" | "unsupported" | "missing"
    reason: str  # never_fetched | interval_elapsed | not_due_yet | already_running | unsupported_strategy | missing_source_record | max_sources_limit

@dataclass(frozen=True)
class DueSourcePlan:
    generated_at: datetime
    total_configured: int
    due: list[DueSourceDecision]
    skipped: list[DueSourceDecision]
    running: list[DueSourceDecision]
    unsupported: list[DueSourceDecision]
    missing: list[DueSourceDecision]
```

**验收**：
- `quick_test` 通过（含新增只读断言）
- `python scripts/check_due_sources.py` 输出 due / skipped / running / unsupported / missing 数量
- 不创建任何 FetchRun，不写数据库，不调用 LLM

---

### Task 2：今日雷达更新入口接入 due-source ✅ 已实现

**范围**：
- 修改 `/radar/today/update` 的 POST 路由
- 先调用 `compute_due_sources()` 计算计划
- 只 enqueue `plan.due` 中的来源
- 页面显示本轮更新计划（due / skipped / running / unsupported / missing）和跳过原因

**实现产物**：
- `app/routes/radar.py`：
  - 新增 `_get_radar_update_max_due_sources()` helper（默认 30，env `RADAR_UPDATE_MAX_DUE_SOURCES`）
  - 新增 `_build_due_source_reason_summary()` helper
  - 新增 `_parse_int_query()` helper（虽然 GET 路由仍用 FastAPI Query 验证，这里备用）
  - `update_today_radar()` 重写为基于 due-source 计划
- `app/templates/radar_today.html`：新增 V1.0-beta.1 本轮更新计划区块
- `app/static/style.css`：新增 `.radar-update-result-title` / `.radar-update-result-grid` / `.radar-update-reasons`

**不修改**：
- FetchRun 探测逻辑本身
- Source 表结构
- `SourceFetchBackgroundService` 抓取逻辑
- 自动中文摘要生成流程

**验收**：
- 未到期来源不会重复 enqueue（reason = `not_due_yet`）
- running 来源不会重复 enqueue（reason = `already_running`）
- 不支持策略来源不会 enqueue（reason = `unsupported_strategy`）
- DB 中无对应 Source 的来源不会 enqueue（reason = `missing_source_record`）
- 页面显示 due / started / skipped / running / unsupported / missing 数量
- 页面显示跳过原因汇总（如 `not_due_yet:8,already_running:2`）

---

### Task 3：单来源工作台 `/sources/{source_key}` 只读版 ✅ 已实现

**实现产物**：
- `GET /sources/{source_key}`（实现于 `app/main.py`，模板为 `app/templates/source_detail.html`）
- `/sources` 页面每个来源卡片新增"工作台"入口
- 展示 Source 基础信息 / 雷达关注源状态 / due-source 当前判断 / 最近 FetchRun /
  最近 SourceItem / 中文摘要覆盖 / InsightCard 覆盖
- 页面只读，不触发探测、摘要或 InsightCard 生成
- source_key 不存在时返回 404 友好页面，不会 500
- 单来源手动探测按钮不在本任务范围（见 Task 4）

**范围**：
- 新增路由 `GET /sources/{source_key}`
- 新增模板 `source_workspace.html`
- 展示 source / FetchRun / SourceItem / summary / InsightCard 状态
- 无操作按钮（纯展示）

**展示内容**：
1. 来源基础信息（key / name / strategy / enabled / category）
2. 探测策略（interval / max_items / is_due / next_suggested_time）
3. 健康状态（last_success / last_failure / consecutive_failures / last_error）
4. 最近 FetchRun 列表（最近 5 条）
5. 最近 SourceItem（最近 10 条，含摘要和 InsightCard 状态）
6. 返回今日雷达链接

**不包含**：运行探测按钮（Task 4 再加）

**验收**：
- `/sources/openai_news` 可访问并返回 200
- 来源信息完整
- SourceItem 列表正确

#### Task 3A.1：来源列表操作区 UX 调整 ✅ 已实现

**已完成目标**：
- `/sources` 页面将"工作台"作为每个来源的第一操作入口。
- "运行探测"保留为 POST 操作，但移动到操作区末尾。
- 产品路径从"先运行"调整为"先查看状态，再决定是否运行"。

**实现细节**：
- `app/templates/sources.html`：操作区顺序为 工作台 → 运行记录 → 候选池 → 原始资料 → 运行探测
- `app/static/style.css`：新增 `.source-workspace-primary-link` / `.source-fetch-secondary-button` / `.source-fetch-inline-form`
- `scripts/quick_test.py`：新增 4 个防回归断言（顺序 / POST / 工作台链接 / 样式类名）

---

### Task 3B：stale running FetchRun 诊断只读版 ✅ 已实现

**背景**：
`check_due_sources.py` 中 `running=8` 表示有一批来源被判为 `already_running`。
若这些 running FetchRun 是历史卡住状态，due-source 会持续跳过这些来源，导致它们
永远不被今日雷达更新处理。本任务先做"诊断"，不做自动修复。

**实现产物**：
- `app/application/sources/stale_runs.py`：
  - `StaleFetchRunDecision` / `StaleFetchRunReport` 数据结构
  - `get_stale_running_threshold_minutes()`（env `RADAR_STALE_RUNNING_MINUTES`，默认 120，合法范围 10–10080，越界回退 120）
  - `build_stale_fetch_run_report()`（只读查询所有 `status=running`，按阈值判定 stale）
  - 原因码：`running_too_long` / `missing_started_at`
- `scripts/check_stale_fetch_runs.py`：只读诊断脚本，支持 `--threshold-minutes`
- 来源工作台（`source_detail.html`）在有 stale running 时显示风险提示
- `app/static/style.css`：新增 `.source-workspace-warning*` 样式

**不做**：
- 不自动把 running 改成 failed
- 不自动重试 / 重新 enqueue
- 不新增修复按钮 / 定时任务
- 不改 due-source 计算逻辑、不改 FetchRun 状态写入

**验收**：
- `python scripts/check_stale_fetch_runs.py` 输出 total_running / stale_count / affected_sources
- 工作台对有 stale running 的来源显示风险提示，无 stale 时不报错
- 全程只读，不新增 FetchRun，不改状态，不调用 LLM

---

### Task 3C：stale running FetchRun 人工恢复脚本 ✅ 已实现

**背景**：
Task 3B 诊断出 8 条长期 stale running FetchRun。它们会让 due-source 持续判为
`already_running`，使对应来源一直被 `/radar/today/update` 跳过。本任务提供人工
确认后的安全恢复工具——不是自动修复系统。

**实现产物**：
- `scripts/mark_stale_fetch_runs_failed.py`：
  - **默认 dry-run**，只打印计划，不写库；只有 `--apply` 才写库
  - 复用 `build_stale_fetch_run_report()` 筛选 stale running
  - 支持 `--threshold-minutes` / `--source-key` / `--run-id` / `--limit`（默认 20）
  - apply 前对每条 run 重新查询并重新确认仍为 `running` 且仍 stale，否则 skip
  - 写入 `status="failed"`、`finished_at=now`、`updated_at=now`，
    `error_message` 含 `[stale-timeout]` 标记
  - 复用现有 `failed` 状态（不引入 `failed_timeout`），保证页面/统计/样式/过滤仍识别
  - 不触发抓取、不重新 enqueue、不调用 LLM、不改 SourceItem / InsightCard

**安全要求**：
- dry-run 不写任何字段（`db.rollback()`）
- 不接到网页按钮，不做自动恢复
- 不一刀切，必须经过 stale 判断

**验收**：
- `python scripts/mark_stale_fetch_runs_failed.py` 默认 dry-run，不改 DB
- `--apply` 后 stale running → failed，due-source 不再因 `already_running` 跳过
- quick_test 第 28 节防回归断言通过

---

### Task 4：单来源手动探测入口规范化 ✅ 已实现

**实现目标**：
- 复用 `POST /sources/{source_key}/fetch`（已存在的 `trigger_source_fetch`）
- 来源工作台提供明确的"手动探测"入口（POST form，按钮非链接）
- 页面说明该操作有副作用，会创建或复用 FetchRun 并触发后台抓取
- 保持 POST-only，禁止 GET 触发（无 `@app.get("/sources/{source_key}/fetch")`）
- 保持 `/sources` 页面"先工作台、后运行探测"的操作顺序

**实现产物**：
- `app/templates/source_detail.html`：新增"手动探测"区域，按状态给出提示
  （stale running / running / not_due_yet / 非雷达关注源）
- `app/templates/sources.html`：运行探测按钮加 `title` 提示（顺序不变）
- `app/static/style.css`：新增 `.source-manual-fetch-panel/-note/-form/-button`
- `app/main.py` 路由保持不变：仍 POST-only，仍走
  `SourceFetchBackgroundService.enqueue_source()`，重定向 `/fetch-runs/{run_id}`
- `scripts/quick_test.py`：新增第 29 节防回归断言

**防重复**：
- `enqueue_source()` 已有 running 窗口去重；存在 running 时返回 `already_running`
  并重定向到现有 run，不创建新 FetchRun

**验收**：
- `/sources/{source_key}/fetch` 仍 POST-only，GET 返回 405
- 工作台手动探测按钮为 POST form，文案说明副作用
- 重复点击不会创建多个 running FetchRun

---

### Task 5：真实单来源手动探测验收 ✅ 已实现

**范围**：
- 执行真实单来源（openai_news）手动探测
- 验证 FetchRun 创建、SourceItem 增量入库
- 验证 HTTP 方法约束（GET 405, POST 302）
- 记录真实验收结果

**验收**：
- run_id=1067, status=success
- items_found=50, items_new=3, items_updated=47, items_failed=0
- SourceItem count: 50 → 53
- GET /sources/openai_news/fetch 返回 405
- POST /sources/openai_news/fetch 返回 302 → /fetch-runs/1067

---

### Task 6：验收归档与阶段总结 ✅ 已实现

**范围**：
- 新增 `docs/V1_BETA_1_SOURCE_SCHEDULING_ACCEPTANCE.md`
- 更新 `docs/V1_BETA_1_EXECUTION_PLAN.md`
- 更新 `docs/V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md`
- 更新 `docs/V1_BETA_RELEASE_PACKAGE.md`
- 更新 `README.md`
- 更新 `app/project_docs/registry.py`
- 新增 quick_test 文档断言

**验收**：
- 文档记录 Task 1-5 全部完成
- 文档记录真实验收数据（stale running 8→0, openai_news run_id=1067）
- quick_test 通过
- acceptance_first_usable_loop 通过

---

## V1.0-beta.1 收束结论

本阶段已完成来源调度、状态解释、stale 诊断、人工恢复、单来源手动探测和真实抓取验收。

后续功能应进入 V1.0-beta.2（自动调度与轻量任务队列设计），而不是继续扩大 beta.1 范围。

---

## 3. 推荐顺序

```
1. Task 1  due-source 计算服务（基础依赖）
2. Task 2  今日雷达更新接入（让用户立刻有感知）
3. Task 3  单来源工作台只读版（信息透明化）
4. Task 4  单来源手动探测（操作能力）
5. Task 5  文案统一（收尾体验）
6. Task 6  摘要队列设计记录（文档补全）
```

---

## 4. 测试策略

### 小任务（Task 1 等纯逻辑）

```bash
python -m compileall app scripts
python scripts/quick_test.py
```

### 业务页面任务（Task 2/3/4）

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/acceptance_first_usable_loop.py
```

### 核心链路任务

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/acceptance_first_usable_loop.py
python scripts/check_sources_health.py
```

---

## 5. 风险

| 风险 | 缓解 |
|------|------|
| due-source 判断错误导致来源不更新 | 先在 Task 1 充分测试，不直接改动生产逻辑 |
| running FetchRun 判断不准导致重复运行 | 基于 DB status 而非 metadata_json |
| fetch_interval_hours 缺省策略不清晰 | 明确默认值（如 24h），并在工作台展示 |
| 单来源工作台与现有 `/sources` 职责重叠 | 工作台是单来源深度视图，/sources 是总览列表 |
| 测试来源污染 Source 表统计 | 先做文档化分离，不做 DB 迁移 |
