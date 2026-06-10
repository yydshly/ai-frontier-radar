# V1.0-beta.2 Automated Scheduling Design

## 1. 阶段目标

V1.0-beta.2 的目标**不是**做企业级任务平台，而是在单机 MVP 中验证一个
最小可解释的自动调度闭环：

```
不再每次都手动点"更新今日雷达"
→ 由一个可控的 CLI 单轮调度器读取 due-source plan
→ 只处理本轮到期来源
→ 复用现有 FetchRun 状态记录
→ 默认不触发 LLM
→ 全程可关闭、可观察、可解释
```

明确非目标：

- 不做分布式任务系统
- 不做常驻 worker 集群
- 不做秒级实时调度
- 不做自动恢复 / 自动重写数据
- 不因为"自动化"牺牲安全边界和可解释性

本阶段是设计 + 轻量 CLI，不是上重型基础设施。

---

## 2. 当前基础（V1.0-beta.1 已具备）

V1.0-beta.2 建立在以下已完成能力之上：

- **due-source 计算服务**：`compute_due_sources()`，只读，输出
  `DueSourcePlan(due, skipped, running, unsupported, missing)`。
- **FetchRun**：单来源抓取的状态核心对象（pending / running / success /
  partial_failed / failed），已记录 started_at / finished_at / items_* / error_message。
- **stale running 诊断**：`build_stale_fetch_run_report()` + `check_stale_fetch_runs.py`，只读。
- **stale running 人工恢复**：`mark_stale_fetch_runs_failed.py`，默认 dry-run，`--apply` 才写库。
- **单来源手动探测**：`POST /sources/{source_key}/fetch`，POST-only，复用
  `SourceFetchBackgroundService.enqueue_source()`，有 running 窗口去重。
- **SourceItem 增量入库**：抓取后增量 upsert，记录 items_found / items_new / items_updated。

也就是说，"单来源抓取任务"的状态模型已经存在，本阶段不需要新建任务表来跑通调度。

---

## 3. 核心问题

当前系统在自动化方面仍有缺口：

- **手动触发**：仍依赖人工点击"更新今日雷达"或单来源探测。
- **没有定时检查 due sources**：到期来源不会被自动拾起。
- **BackgroundTasks 非持久化**：FastAPI `BackgroundTasks` 绑定请求生命周期，
  进程重启即丢失，不适合作为长期调度基座。
- **进程重启后 running 可能残留**：异常退出会留下 stale running（已由 beta.1 诊断 + 人工恢复覆盖，但仍是后台任务治理缺口）。
- **没有统一 retry policy**：失败来源不会自动重试，也没有退避策略。
- **没有任务执行日志聚合**：每次运行的计划与结果分散，缺少单轮调度的统一记录。

---

## 4. 设计原则

V1.0-beta.2 自动调度必须遵守：

- **不直接引入重型队列**：本阶段**不直接引入 Celery / Redis / RQ / Dramatiq /
  APScheduler**。这些方案的部署、运维与依赖成本与当前单机 MVP 不匹配，留到 Phase C
  或多机 / 高并发场景再评估。
- **先单机，后分布式**：先在一台机器上把单轮调度跑顺，再谈横向扩展。
- **先 CLI scheduler，后常驻 scheduler**：先做一次性 CLI 单轮调度，由外部定时器调用；
  暂不在 Web 进程内塞常驻 scheduler。
- **先复用 FetchRun，后考虑 TaskRun**：抓取调度复用 FetchRun，不急于引入 TaskRun / JobRun。
- **先状态可解释，后自动恢复**：调度先把状态解释清楚，stale 恢复仍走人工确认。
- **自动任务必须可关闭**：`RADAR_SCHEDULER_ENABLED=false` 为默认值。
- **所有自动任务必须有幂等边界**：复用 due-source + running 窗口去重，避免重复抓取。
- **不因自动化牺牲 prompt injection 防护**：自动调度默认不触发 LLM；抓取内容进入
  LLM 前的清洗 / 边界与现有链路一致，自动化不得绕过。

---

## 5. 最小自动调度方案

分三阶段，本阶段只实现 Phase A，并用 Phase B 文档化外部定时，Phase C 仅评估不实现。

### Phase A：CLI 单轮调度器

```bash
python scripts/run_due_sources_once.py            # dry-run（默认）
python scripts/run_due_sources_once.py --apply    # 真实创建 FetchRun（Task 3 才实现）
```

> **当前进度（Task 2）**：CLI dry-run 骨架已实现。当前脚本只打印本轮 due-source
> 计划（due / skipped / running / unsupported / missing + would_start + reason_summary），
> **不创建 FetchRun**。`--apply` 尚未实现，将在 Task 3 中另行加入。

行为：

- 读取 due-source plan（`compute_due_sources()`）。
- 只处理 `plan.due`，跳过 skipped / running / unsupported / missing。
- `--max-sources N` 限制本轮处理来源数（剩余顺延到下一轮）。
- 默认 dry-run：只打印本轮计划，不创建 FetchRun。
- `--apply`：通过 `SourceFetchBackgroundService.enqueue_source()` 为每个 due 来源创建 FetchRun。
- 默认 **不调用 LLM**，除非显式开启（`RADAR_SCHEDULER_AUTO_SUMMARY=true` 或专用 flag）。
- 输出本轮计划与结果摘要（due / started / skipped 原因汇总）。

幂等边界：复用 due-source 判断 + `enqueue_source()` 的 running 窗口去重，
重复运行不会对同一来源创建多个 running FetchRun。

### Phase B：外部系统定时调用 CLI

由操作系统 / 外部定时器触发 Phase A 的 CLI，而非应用内常驻：

- Windows Task Scheduler（本机首选）
- cron（Linux / macOS）
- 手动 `.bat` / `.ps1` 包装脚本
- GitHub Actions 仅作 CI，不用于本地真实抓取调度

定时器只负责"按间隔调用一次 CLI"，调度逻辑和状态全部留在应用内可解释组件中。

### Phase C：应用内轻量 scheduler（本阶段不实现）

后续再评估是否引入，候选：

- APScheduler（应用内定时）
- 独立 worker 进程
- 轻量队列表（DB 表 + 轮询）

**本阶段不实现 Phase C**，避免过早把单机 MVP 复杂化。

---

## 6. 轻量任务队列设计（设计但不实现）

为未来预留一个任务对象的形状，但**当前不落地为代码或数据库表**：

- `TaskKind`：任务类型（fetch_source / health_check / ...）
- `TaskStatus`：pending / running / success / failed
- `TaskPayload`：任务输入（如 source_key）
- `TaskResult`：任务结果摘要
- `idempotency_key`：幂等键，避免重复入队
- `max_attempts`：最大重试次数
- `next_run_at`：下次执行时间（退避 / 定时）
- `last_error`：最近一次失败原因

关键判断：**当前 FetchRun 已经承担"来源抓取任务"的状态记录职责**
（status / started_at / finished_at / items_* / error_message），
因此**不应立刻新增 TaskRun**。是否需要独立任务表，留到 Phase C 评估或
当出现"非抓取类自动任务需要统一队列"时再决策（见决策记录 Decision 7）。

---

## 7. 自动任务范围

**允许自动执行**（只读或幂等、低成本）：

- due-source 抓取（Phase A CLI 单轮调度）
- stale running 诊断（只读）
- 来源健康检查（只读）

**暂不自动执行**：

- stale running 恢复（写库，必须人工确认）
- InsightCard 生成（成本 / 质量敏感）
- LLM 摘要批量生成（成本敏感）
- 删除 / 重写数据

**必须人工确认**：

- `mark_stale_fetch_runs_failed.py --apply`
- 批量重抓
- 任何 LLM 成本较高的任务

---

## 8. 配置项设计

未来调度相关配置（默认值体现"保守 + 默认关闭"）：

```text
RADAR_SCHEDULER_ENABLED=false            # 默认关闭自动调度
RADAR_SCHEDULER_MAX_SOURCES_PER_RUN=5    # 每轮最多处理来源数
RADAR_SCHEDULER_INTERVAL_MINUTES=60      # 外部定时器调用间隔建议值
RADAR_SCHEDULER_AUTO_SUMMARY=false       # 默认不触发 LLM 摘要
RADAR_FETCH_STALE_MINUTES=120            # stale running 阈值（沿用 beta.1）
```

说明：

- **默认关闭自动调度**：未显式开启不会有任何自动抓取。
- **默认不自动 LLM**：自动调度默认不触发摘要 / InsightCard 生成。
- **默认限制每轮来源数**：避免一次性打爆源站或本机资源。

---

## 9. 风险

- **重复抓取**：缓解——复用 due-source + running 窗口去重 + 每轮来源上限。
- **任务卡住（stale running）**：缓解——沿用 beta.1 stale 诊断 + 人工恢复。
- **DB 锁**：SQLite 单写，缓解——单轮串行调度，避免并发写。
- **网络波动 / 源站封禁**：缓解——每轮来源上限 + 失败记录 + 退避（未来 retry policy）。
- **LLM 成本失控**：缓解——默认不自动 LLM，批量 LLM 任务必须人工确认。
- **运行在 Web 进程内导致生命周期不清晰**：缓解——Phase A 用独立 CLI，不塞 Web 进程。
- **Windows 本地任务调度差异**：缓解——Phase B 文档分别说明 Windows Task Scheduler 与 cron。

---

## 10. 验收标准

V1.0-beta.2 完成标准：

- 有一次 CLI 调度器 **dry-run**（打印计划，不写库）。
- 有一次 CLI 调度器 **真实运行**（`--apply` 创建 FetchRun）。
- 真实运行 **不产生 stale running**（`check_stale_fetch_runs.py` 仍 stale_count=0）。
- due-source 解释正确（due / skipped 原因可追溯）。
- 自动调度 **可关闭**（`RADAR_SCHEDULER_ENABLED=false` 默认）。
- **不默认触发 LLM**（默认 `RADAR_SCHEDULER_AUTO_SUMMARY=false`）。

---

## 11. 相关文档

- 执行计划：[V1_BETA_2_EXECUTION_PLAN.md](V1_BETA_2_EXECUTION_PLAN.md)
- 决策记录：[V1_BETA_2_DECISION_RECORD.md](V1_BETA_2_DECISION_RECORD.md)
- 上一阶段架构：[V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md](V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md)
