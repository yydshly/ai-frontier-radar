# V1.0-beta.2 Scheduler Checkpoint

## 1. 阶段定位

V1.0-beta.2 的阶段目标是把 AI Frontier Radar 从"人工触发来源探测"推进到"可被外部定时器安全调用的半自动雷达"。

强调：

- 当前仍是单机 MVP。
- 不引入 Celery / Redis / APScheduler。
- 不做企业级任务平台。

---

## 2. 已完成任务

### Task 1：自动调度设计归档 ✅ 已完成

**目标**：归档自动调度设计、决策记录、执行计划，并接入 README / release / project-docs。

**产物**：
- `docs/V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md`
- `docs/V1_BETA_2_EXECUTION_PLAN.md`
- `docs/V1_BETA_2_DECISION_RECORD.md`

**验收结果**：三文档存在、注册入库、quick_test 文档断言通过。

**是否触发真实抓取**：否（设计归档任务）

**是否调用 LLM**：否

---

### Task 2：run_due_sources_once.py dry-run CLI ✅ 已实现

**目标**：实现 CLI 单轮调度器骨架，默认 dry-run，只打印本轮计划，不写库。

**产物**：
- `scripts/run_due_sources_once.py`
- 默认 dry-run
- 复用 `compute_due_sources()`
- 支持 `--max-sources N`、`--show-skipped`、`--show-running`、`--show-unsupported`、`--show-missing`

**验收结果**：dry-run 打印计划且不创建 FetchRun（FetchRun count 不变）；`check_stale_fetch_runs.py` stale_count 仍为 0。

**是否触发真实抓取**：否

**是否调用 LLM**：否

---

### Task 3A：run_due_sources_once.py --apply 安全执行路径 ✅ 已实现

**目标**：为脚本增加显式 `--apply` 安全执行路径，只处理 `plan.due`。

**产物**：
- `scripts/run_due_sources_once.py` 增加 `--apply`
- 两道安全闸门：
  - `RADAR_SCHEDULER_ENABLED=true` 必须显式设置，否则 `[ERROR]` + exit 2
  - `AUTO_SUMMARY_MAX_PER_FETCH_RUN` 必须为 `0`；非 0 则 `[ERROR]` + exit 2
- `--apply` 仅遍历 `plan.due`，逐个调用 `SourceFetchBackgroundService.enqueue_source(source_key, background_tasks=None)`
- 不处理 skipped / running / unsupported / missing
- 不自动 stale recovery

**验收结果**：无 env 的 `--apply` exit 2；`AUTO_SUMMARY_MAX_PER_FETCH_RUN!=0` 的 `--apply` exit 2；安全 apply 在 `due=0` 时 FetchRun count 不变。

**是否触发真实抓取**：仅在 `--apply` + 满足所有安全闸门时触发真实抓取

**是否调用 LLM**：否（`AUTO_SUMMARY_MAX_PER_FETCH_RUN=0` 禁用自动摘要）

---

### Task 3B：isolated DB + local mock RSS 真实 apply 验收 ✅ 已实现

**目标**：在隔离环境中执行真实 `--apply`，证明可创建 FetchRun 并完成 SourceItem 入库。

**产物**：
- `scripts/acceptance_run_due_sources_once_apply.py`
- `docs/V1_BETA_2_SCHEDULING_APPLY_ACCEPTANCE.md`

**真实 apply 验收结果**：

```
验收脚本：scripts/acceptance_run_due_sources_once_apply.py
source_key=openai_news
mock RSS item count=2
scheduler exit=0
due=1
missing=14
started=1
FetchRun count=1
FetchRun status=success
items_found=2
items_new=2
items_updated=0
items_failed=0
SourceItem count=2
auto_summary.enabled=false
auto_summary.reason=AUTO_SUMMARY_MAX_PER_FETCH_RUN=0
InsightCard count=0
running FetchRun count=0
stale_count=0
主 DB 未污染
```

**是否触发真实抓取**：是（isolated 环境下，使用 local mock RSS）

**是否调用 LLM**：否

---

### Task 5：Windows Task Scheduler / cron 操作手册 ✅ 已完成

**目标**：文档化由外部定时器调用 CLI 单轮调度（Phase B）。

**产物**：
- `docs/V1_BETA_2_SCHEDULER_OPERATIONS.md`

**覆盖内容**：
- Windows Task Scheduler 操作步骤
- cron 操作步骤
- dry-run / `--apply` 用法
- 环境变量配置（RADAR_SCHEDULER_ENABLED, AUTO_SUMMARY_MAX_PER_FETCH_RUN）
- 日志建议（logs/scheduler.log）
- due=0 / not_due_yet 排查
- stale running 诊断与人工恢复
- 不默认触发 LLM

**验收结果**：操作文档完整，能让用户按间隔安全调用一次 CLI。

**是否触发真实抓取**：否（文档任务）

**是否调用 LLM**：否

---

## 3. 当前调度链路

```
外部定时器
→ run_due_sources_once.py
→ compute_due_sources()
→ plan.due
→ SourceFetchBackgroundService.enqueue_source(..., background_tasks=None)
→ FetchRun
→ RSS / HTML probe
→ SourceItem upsert
→ auto_summary disabled by AUTO_SUMMARY_MAX_PER_FETCH_RUN=0
```

说明：

- dry-run 不写库
- `--apply` 才会真实执行
- `--apply` 必须通过 env gate（`RADAR_SCHEDULER_ENABLED=true` + `AUTO_SUMMARY_MAX_PER_FETCH_RUN=0`）

---

## 4. 安全边界

必须记录：

- `RADAR_SCHEDULER_ENABLED=true` 才允许 `--apply`
- `AUTO_SUMMARY_MAX_PER_FETCH_RUN=0` 才允许 `--apply`
- 默认 dry-run
- 默认不触发 LLM
- stale recovery 不自动执行
- 只处理 plan.due
- 不处理 skipped / running / unsupported / missing

---

## 5. 真实 apply 验收结果

已在 isolated 环境下验证：

```
验收脚本：scripts/acceptance_run_due_sources_once_apply.py
source_key=openai_news
mock RSS item count=2
scheduler exit=0
due=1
missing=14
started=1
FetchRun count=1
FetchRun status=success
items_found=2
items_new=2
items_updated=0
items_failed=0
SourceItem count=2
auto_summary.enabled=false
auto_summary.reason=AUTO_SUMMARY_MAX_PER_FETCH_RUN=0
InsightCard count=0
running FetchRun count=0
stale_count=0
主 DB 未污染
```

---

## 6. 操作手册状态

`docs/V1_BETA_2_SCHEDULER_OPERATIONS.md` 已覆盖：

- Windows Task Scheduler 操作
- cron 操作
- dry-run / `--apply` 用法
- 环境变量配置
- logs/scheduler.log
- due=0 / not_due_yet 排查
- stale running 诊断
- manual stale recovery
- 不默认触发 LLM

---

## 7. 当前已知限制

1. 真实验收只覆盖 rss 策略。
2. html_index 尚未做 isolated apply 验收。
3. 多 due 来源批量行为尚未做真实验收。
4. 失败退避 / retry policy 尚未实现。
5. TaskRun / JobRun 尚未引入。
6. quick_test 里仍有既有写库测试，主 DB FetchRun 计数可能被测试污染。
7. 外部定时器只提供操作手册，未实际创建系统任务。

---

## 8. 下一步建议

优先级 1：观察真实环境下多轮 scheduler dry-run / apply 输出

优先级 2：补充 failure backoff / retry policy 设计

优先级 3：评估是否把 quick_test 中写库测试迁移到 isolated DB

优先级 4：TaskRun / JobRun 决策复盘

---

## 9. 阶段结论

V1.0-beta.2 已经完成从"手动来源探测"到"可被外部定时器安全调用的半自动雷达"的关键验证。

当前可以进入小规模本地真实运行观察阶段，但不建议继续扩大自动化范围，尤其不建议默认开启 LLM 摘要或自动 stale recovery。

---

## 10. 相关文档

- [V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md](V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md) — 自动调度设计
- [V1_BETA_2_EXECUTION_PLAN.md](V1_BETA_2_EXECUTION_PLAN.md) — 执行计划
- [V1_BETA_2_DECISION_RECORD.md](V1_BETA_2_DECISION_RECORD.md) — 决策记录
- [V1_BETA_2_SCHEDULER_OPERATIONS.md](V1_BETA_2_SCHEDULER_OPERATIONS.md) — 操作手册
- [V1_BETA_2_SCHEDULING_APPLY_ACCEPTANCE.md](V1_BETA_2_SCHEDULING_APPLY_ACCEPTANCE.md) — apply 验收记录
