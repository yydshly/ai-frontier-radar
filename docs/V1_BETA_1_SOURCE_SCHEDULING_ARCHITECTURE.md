# V1.0-beta.1 来源调度与来源工作台架构说明

## 1. 阶段定位

V1.0-beta 已证明单次 First Usable Loop 可以跑通。

V1.0-beta.1 的目标是让系统从"手动跑通"升级为"可持续运行"。

### V1.0-beta.1 第一阶段实现状态

V1.0-beta.1 分两个阶段推进：

- **第一阶段 ✅ 已实现**：只读 due-source 计算服务 `compute_due_sources()`。
  它判断哪些来源该探测、哪些该跳过、哪些已在运行，但**不触发抓取、不写数据库**。
- **第二阶段 ✅ 已实现**：`/radar/today/update` 接入 due-source 计划。
  用户点击"更新今日雷达"后，后端先计算 due-source 计划，只 enqueue `plan.due` 中的来源。
  `skipped` / `running` / `unsupported` / `missing` 来源不会被 enqueue。
  页面显示本轮更新计划摘要与跳过原因汇总（如 `not_due_yet:8,already_running:2`）。

> `/radar/today/update` 当前仍是手动触发，但已从"全量运行雷达关注源"升级为"运行 due sources"。
> 这不是定时任务，也不是后台调度器，而是手动触发下的调度策略。

### 当前不是做

- 完整 SaaS
- 定时任务平台
- 复杂推荐算法
- 多用户来源管理
- 完整任务队列系统

### 当前要做的是

- 来源调度（due-source）
- 来源状态可见
- 单来源工作台
- 来源池 / 雷达关注源概念分离
- 摘要队列的轻量设计

---

## 2. 当前问题

1. 今日雷达更新仍然偏"手动全量刷新"，每次点击都可能重复 enqueue 已在 running 的来源。
2. 不同来源更新频率不同，但当前缺少 due-source 判断，所有来源一视同仁。
3. 单个来源失败时，只能从 fetch-runs 或日志中排查，缺少统一视图。
4. Source 表中有来源池、测试来源、当前关注源混杂的问题，config enabled sources 和数据库 Source 表边界不清。
5. 自动摘要已经接入 FetchRun 后处理，但还不是独立队列，失败只在 metadata_json 中留痕。
6. 最近探测状态统计的是最近 FetchRun，不是严格批次，连续失败次数等指标缺失。

---

## 3. 目标能力

V1.0-beta.1 最小目标：

1. **due-source 调度**：判断哪些雷达关注源本轮该探测，并展示跳过原因。
2. **单来源工作台**：`/sources/{source_key}` 展示一个来源的状态、FetchRun、SourceItem、摘要、InsightCard 入口。
3. **来源概念分离**：明确 SourcePool、RadarSource、ConfiguredSource 的边界。
4. **摘要队列设计**：暂不实现完整队列表，但明确后续如何从 auto_summary 演进。

---

## 4. 核心概念

### 4.1 SourcePool

**定义**：系统已知的全部来源集合。包括正式来源、候选来源、历史测试来源、临时来源。

**当前承载**：`Source` 表

**注意**：SourcePool 不等于今日雷达会处理的来源。

---

### 4.2 RadarSource

**定义**：当前被纳入"今日雷达更新范围"的来源。

**当前实现**：config enabled sources

**未来可演进为**：
- `RadarSourceProfile`（独立配置）
- `Source` 表上的 `radar_enabled` 字段
- 独立配置文件

**V1.0-beta.1 建议**：先继续使用 config enabled sources 作为雷达关注源，不要急着新增数据库字段。

---

### 4.3 FetchPolicy

**定义**：每个来源的探测策略。

**包含字段**：
- `fetch_strategy`: rss / html_index
- `fetch_interval_hours`
- `max_items_per_run`
- `timeout`
- `retry policy`
- `failure backoff`

**V1.0-beta.1 建议**：优先在 config 层表达 `fetch_interval_hours`，如果 config 没有则使用默认值。

---

### 4.4 DueSource

**定义**：本轮应该被探测的来源。

**判断依据（全部满足）**：
1. 来源启用（enabled）
2. 属于雷达关注源（in radar scope / config enabled）
3. fetch_strategy 支持（supported strategy）
4. 当前没有 running FetchRun（not already running）
5. 距离上次探测已经超过 fetch_interval_hours（past interval）
6. 没有因为连续失败进入冷却（not in failure cooldown）

**跳过原因（need_due_status）**：
- `not_in_radar_scope` — 不在雷达关注范围
- `unsupported_strategy` — 探测策略不支持
- `already_running` — 已有 FetchRun 在运行
- `not_due_yet` — 距上次探测未超过间隔
- `cooldown_after_failure` — 连续失败进入冷却
- `max_sources_limit` — 达到本轮最大来源数限制
- `missing_source_record` — Source 表中无对应记录

---

### 4.5 SourceWorkspace

**定义**：单来源工作台。

**路由建议**：`GET /sources/{source_key}`

**回答问题**：
- 这个来源是什么？
- 最近是否健康？
- 最近何时成功/失败？
- 最近抓到哪些 SourceItem？
- 哪些已有中文摘要？
- 哪些已有 InsightCard？
- 能否单独运行探测？

---

### 4.6 SummaryQueue

**定义**：摘要生成任务队列。

**当前实现**：FetchRun 完成后 best-effort 自动摘要 new / updated SourceItem，默认最多 5 条。

**V1.0-beta.1 建议**：暂不新增 SummaryJob 表，先设计队列边界和状态语义。

**后续演进（SummaryJob 表）**：
- `pending / running / success / failed`
- `retry_count`
- `error_message`
- `source_item_id`
- `created_at / started_at / finished_at`

---

## 5. due-source 调度设计

### 5.1 输入

```
雷达关注源 configured enabled sources
Source 表中的来源记录
最近 FetchRun（按 source_key 分组）
fetch_interval_hours（来自 config 或默认值）
max_sources_per_update（本轮上限）
```

### 5.2 输出

```
due_sources: List[DueSource]
skipped_sources: List[SkippedSource]
running_sources: List[SourceKey]
unsupported_sources: List[SourceKey]
failed_to_enqueue_sources: List[EnqueueFailure]
```

### 5.3 跳过原因展示

需要明确展示每条跳过的原因：

| reason | 说明 |
|--------|------|
| `not_in_radar_scope` | 不在雷达关注范围 |
| `unsupported_strategy` | 探测策略不支持 |
| `already_running` | 已有 FetchRun 在运行 |
| `not_due_yet` | 距上次探测未超过间隔 |
| `cooldown_after_failure` | 连续失败进入冷却 |
| `max_sources_limit` | 达到本轮最大来源数限制 |
| `missing_source_record` | Source 表中无对应记录 |

### 5.4 推荐算法（伪代码）

```python
def compute_due_sources(configured_sources, db_session) -> DueSourceResult:
    due_sources = []
    skipped_sources = []
    running_sources = []
    unsupported_sources = []
    failed_to_enqueue = []

    for source_key in configured_sources:
        source = db_session.query(Source).filter_by(source_key=source_key).first()

        # Check strategy support
        if source and source.fetch_strategy not in SUPPORTED_STRATEGIES:
            unsupported_sources.append(source_key)
            continue

        # Check if already running
        running = db_session.query(FetchRun).filter(
            FetchRun.source_key == source_key,
            FetchRun.status == "running"
        ).first()
        if running:
            running_sources.append(source_key)
            skipped_sources.append(SkippedSource(source_key, "already_running"))
            continue

        # Get latest FetchRun
        latest = db_session.query(FetchRun).filter(
            FetchRun.source_key == source_key
        ).order_by(FetchRun.started_at.desc()).first()

        interval_hours = get_fetch_interval(source_key)  # config or default

        if latest is None:
            due_sources.append(DueSource(source_key))
            continue

        if latest.status == "success":
            hours_since = (now - latest.started_at).total_seconds() / 3600
            if hours_since >= interval_hours:
                due_sources.append(DueSource(source_key))
            else:
                skipped_sources.append(SkippedSource(source_key, "not_due_yet"))
        elif latest.status == "failed":
            # Check consecutive failures
            if latest.consecutive_failures >= MAX_FAILURE_COOLDOWN:
                skipped_sources.append(SkippedSource(source_key, "cooldown_after_failure"))
            else:
                due_sources.append(DueSource(source_key))  # retry allowed
        else:
            # running or other — skip
            skipped_sources.append(SkippedSource(source_key, "already_running"))

    return DueSourceResult(
        due_sources=due_sources,
        skipped_sources=skipped_sources,
        running_sources=running_sources,
        unsupported_sources=unsupported_sources,
        failed_to_enqueue=failed_to_enqueue,
    )
```

### 5.5 当前不做

```
- 不做 cron / 定时任务
- 不做 APScheduler
- 不做 Celery
- 不做分布式队列
- 不做复杂优先级
```

### 5.6 stale running FetchRun 诊断（V1.0-beta.1 Task 3B）

due-source 会把存在 running FetchRun 的来源判定为 `already_running` 并跳过。
如果某条 FetchRun 长期停留在 `running`（进程崩溃、异常退出等历史卡死），那么
该来源会被持续跳过，用户点击"更新今日雷达"也不会为它产生新抓取。

为此 V1.0-beta.1 先提供**只读诊断**，不自动修改状态：

- `app/application/sources/stale_runs.py` 的 `build_stale_fetch_run_report()`
  查询所有 `status=running` 的 FetchRun，按阈值判定 stale：
  - `started_at` 为空 → reason `missing_started_at`
  - `now - started_at` 超过阈值 → reason `running_too_long`
- 阈值由 `RADAR_STALE_RUNNING_MINUTES` 控制，默认 120 分钟，合法范围 10–10080。
- `scripts/check_stale_fetch_runs.py` 可在命令行查看受影响来源。
- 单来源工作台在检测到 stale running 时显示风险提示。

stale running recovery 分两步：

1. **诊断**：`scripts/check_stale_fetch_runs.py` 和来源工作台风险提示（只读）。
2. **人工恢复**：`scripts/mark_stale_fetch_runs_failed.py` 默认 dry-run，
   只有 `--apply` 才写库，将确认为 stale 的 running 标记为 `failed`
   （写入 `[stale-timeout]` error_message，复用现有 `failed` 状态而非新增枚举）。
   apply 前会对每条 run 重新确认仍为 `running` 且仍 stale。

恢复后 due-source 不再因为 `already_running` 跳过该来源，来源可在下一轮 update
中重新进入调度判断。本阶段仍**不做**自动恢复、不接网页按钮、不重试、不重新 enqueue。

---

## 6. 单来源工作台设计

> 实现状态（V1.0-beta.1 Task 3）：单来源工作台先以只读方式实现（模板
> `source_detail.html`），用于排查来源状态和内容覆盖（基础信息、雷达关注源
> 状态、due-source 判断、最近 FetchRun、最近 SourceItem、中文摘要覆盖、
> InsightCard 覆盖）。手动触发单来源探测留到后续任务（Task 4），当前页面
> 不提供"运行探测"按钮。

### 6.1 路由

```
GET /sources/{source_key}
```

### 6.2 页面模块

```
1. 来源基础信息
2. 探测策略
3. 健康状态
4. 最近 FetchRun
5. 最近 SourceItem
6. 中文摘要覆盖情况
7. InsightCard 覆盖情况
8. 操作区：运行探测 / 返回今日雷达
```

### 6.3 来源基础信息

```
source_key
name
url
fetch_strategy
enabled
category
focus
```

### 6.4 探测策略

```
fetch_interval_hours
max_items_per_run
是否到期（is_due）
下次建议探测时间
```

### 6.5 健康状态

```
最近成功时间（last_success_at）
最近失败时间（last_failure_at）
连续失败次数（consecutive_failures）
最近错误信息（last_error_message）
```

### 6.6 最近 SourceItem（最近 10 条）

```
标题（title）
中文一句话概述（zh_one_liner）
中文摘要状态（有/无/处理中）
InsightCard 状态（待处理/生成中/已完成/失败）
发现时间（first_seen_at）
原文链接（url）
```

### 6.7 操作

```
[运行该来源探测] → POST /sources/{source_key}/fetch
[查看该来源候选内容] → /candidate-pool?source={source_key}
[查看该来源 FetchRun] → /fetch-runs?source={source_key}
[返回今日雷达] → /radar/today
```

### 6.8 单来源手动探测 vs due-source 自动调度（V1.0-beta.1 Task 4）

单来源手动探测与 due-source 自动调度是两条不同入口：

- `/radar/today/update`：遵守 due-source，只处理到期来源（`plan.due`）。
- `/sources/{source_key}/fetch`：用户手动触发单来源探测，**POST-only**，仍必须
  防重复 running。

手动探测不会跳过后台任务治理，也不会绕过 FetchRun 状态记录：

- 路由仍通过 `SourceFetchBackgroundService.enqueue_source()` 投递，不在请求线程内抓取。
- `enqueue_source()` 有 running 窗口去重：若该来源已有 running FetchRun，返回
  `already_running` 并重定向到现有 run，不创建新 FetchRun。
- 工作台以 POST 表单暴露入口，并明确说明这是有副作用操作（创建/复用 FetchRun + 后台抓取）。

适用场景：stale running 恢复后来源进入 `not_due_yet` 冷却期，用户想立刻重新抓某个
来源时，走手动探测而非依赖 due-source 自动到期。

---

## 7. 来源池 / 雷达关注源分离

### 当前问题

Source 表可能有大量测试来源。config enabled sources 才是当前雷达关注源。两者边界不清。

### V1.0-beta.1 先采用文档化分离

```
SourcePool     = Source 表全部来源（数据层）
RadarSource    = config enabled sources（业务层/雷达更新范围）
```

暂不新增数据库字段。

### 未来演进选项

#### 方案 A：继续 config 管理（推荐）

**优点**：简单、稳定、适合 MVP，config 即代码

**缺点**：Web UI 不方便编辑

#### 方案 B：Source 表增加 radar_enabled 字段

**优点**：Web UI 容易管理

**缺点**：需要 DB 迁移和治理测试来源

#### 方案 C：新增 RadarSourceProfile 表

**优点**：来源池和关注源清晰分离

**缺点**：复杂度更高，需要额外关联查询

**V1.0-beta.1 推荐**：方案 A，后续再评估方案 C

---

## 8. 摘要队列演进

### 当前

FetchRun 完成后自动摘要前 N 条 new / updated SourceItem。

### 问题

1. 没有独立任务状态
2. 摘要失败只能写入 FetchRun metadata_json
3. 不能全局查看待摘要项
4. 不能集中重试
5. 无法批量补齐历史项

### V1.0-beta.1

先保留当前 auto_summary。只在文档和页面状态中明确它是 best-effort。

### V1.0-beta.2 可做

```
SummaryJob 表（pending / running / success / failed）
后台队列
失败重试（retry_count）
限流（max_concurrent_summaries）
批量补齐（fill_missing_summaries）
```

---

## 9. 验收标准

V1.0-beta.1 完成时应满足：

1. 今日雷达更新不再盲目全跑，而是能解释 due / skipped。
2. 单来源工作台可以查看来源状态（基础信息 + 健康状态 + 最近 SourceItem）。
3. 单来源可以手动触发探测。
4. 用户能知道一个来源为什么没被更新（跳过原因明确）。
5. 来源池和雷达关注源概念在页面和文档中清楚。
6. 自动摘要仍然可用，且不影响 FetchRun 成败。

---

## 10. 非目标

```
- 不做定时任务（cron / scheduler）
- 不做多用户
- 不做来源 Web 编辑（来源 CRUD）
- 不做复杂推荐算法
- 不做完整摘要队列表（SummaryJob）
- 不做 DailyRadarReport
- 不做语音播报
```
