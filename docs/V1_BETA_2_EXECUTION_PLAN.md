# V1.0-beta.2 执行计划：自动调度与轻量任务队列

## 1. 目标

把系统从"人工触发"推进到"轻量自动调度设计 + CLI 单轮调度"：

```
设计自动调度边界
→ 实现 CLI 单轮调度器（默认 dry-run）
→ 真实执行单轮 due sources
→ 输出调度运行记录并验收
→ 文档化外部定时调用
→ 复盘是否需要 TaskRun 表
```

核心约束：默认关闭、默认不触发 LLM、不引入 Celery / Redis / APScheduler。

---

## 2. 任务拆分

### Task 1：V1.0-beta.2 自动调度设计归档

**目标**：归档自动调度设计、决策记录、执行计划，并接入 README / release / project-docs。

**改动范围**：
- 新增 `docs/V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md`
- 新增 `docs/V1_BETA_2_EXECUTION_PLAN.md`
- 新增 `docs/V1_BETA_2_DECISION_RECORD.md`
- 更新 `README.md` / `docs/V1_BETA_RELEASE_PACKAGE.md` / `app/project_docs/registry.py`
- 更新 `scripts/quick_test.py`（文档断言）

**禁止事项**：不实现调度代码、不触发抓取、不调用 LLM、不改功能代码。

**验收标准**：三文档存在、注册入库、quick_test 文档断言通过。

**风险**：文档与后续实现脱节——缓解：执行计划与决策记录绑定明确的验收口径。

---

### Task 2：run_due_sources_once.py dry-run 设计与脚本骨架 ✅ 已实现

**目标**：实现 CLI 单轮调度器骨架，**默认 dry-run**，只打印本轮计划，不写库。

**实现产物**：
- `scripts/run_due_sources_once.py`
- 默认 dry-run（无 `--apply`，Task 3 才实现真实执行）
- 复用 `compute_due_sources()`，只读取计划
- 支持 `--max-sources N`（校验 N >= 1，非法 exit 2）
- 支持 `--show-skipped / --show-running / --show-unsupported / --show-missing` 明细
- 不创建 FetchRun、不触发真实抓取、不调用 LLM
- 不导入 `SourceFetchBackgroundService`，不调用 `enqueue_source`
- `scripts/quick_test.py` 新增第 32 节断言（静态 + 轻量运行：dry-run exit 0、非法 max-sources exit 2）

**禁止事项**：默认不得创建 FetchRun、不得调用 LLM、不得改 due-source 逻辑。

**验收标准**：dry-run 打印计划且不创建 FetchRun（实测 FetchRun count 947→947 不变）；
`check_stale_fetch_runs.py` stale_count 仍为 0。

**风险**：误把 dry-run 写成真实执行——缓解：本任务不实现 `--apply`，默认 dry-run。

---

### Task 3A：run_due_sources_once.py --apply 安全执行路径 ✅ 已实现

**目标**：为脚本增加 **显式 `--apply`** 安全执行路径，只处理 `plan.due`。

**实现产物**：
- `scripts/run_due_sources_once.py` 增加 `--apply`（默认仍 dry-run）
- 两道安全闸门：
  - `RADAR_SCHEDULER_ENABLED=true` 必须显式设置，否则 `[ERROR]` + exit 2
  - `AUTO_SUMMARY_MAX_PER_FETCH_RUN` 必须为 `0`（未设置则脚本默认设为 `0`）；
    非 0 则 `[ERROR]` + exit 2，避免同步抓取触发 LLM 摘要
- `--apply` 仅遍历 `plan.due`，逐个调用
  `SourceFetchBackgroundService.enqueue_source(source_key, background_tasks=None)`（同步执行）
- 不处理 skipped / running / unsupported / missing，不自动 stale recovery
- 输出 `apply_result`（started / already_running / failed_to_start），并对 started 二次查询最终状态
- `due=0` 时安全 no-op，不创建 FetchRun
- `scripts/quick_test.py` 新增第 33 节断言（只测安全失败路径，不跑真实成功 apply）

**说明**：
- Task 3A 只实现安全 apply 路径。如果当前 `due=0`，`--apply` no-op 不创建 FetchRun。
- 真实创建 FetchRun 的验收放到 Task 3B。

**禁止事项**：不批量重抓全部来源、不绕过 running 去重、不默认 LLM、不改 due-source 逻辑。

**验收标准**：无 env 的 `--apply` exit 2；`AUTO_SUMMARY_MAX_PER_FETCH_RUN!=0` 的 `--apply` exit 2；
安全 apply 在 `due=0` 时 FetchRun count 不变（实测 963→963），stale_count 仍为 0。

**风险**：重复抓取 / 卡住——缓解：running 窗口去重 + 每轮来源上限。

---

### Task 3B：isolated DB + local mock RSS 真实 apply 验收 ✅ 已实现

**目标**：在隔离环境中执行真实 `--apply`，证明可创建 FetchRun 并完成 SourceItem 入库。

**实现产物**：
- `scripts/acceptance_run_due_sources_once_apply.py`：
  - 临时目录 + isolated SQLite（import `app.*` 前设 `DATABASE_URL`）
  - 标准库 `ThreadingHTTPServer` 提供 local mock RSS（无外网）
  - seed `openai_news`（never_fetched → due），其余 14 源进 missing
  - 子进程执行 `run_due_sources_once.py --apply --max-sources 1 --show-missing`
  - 验证 FetchRun / SourceItem / auto_summary / InsightCard / stale
  - 默认清理临时目录，`--keep-temp` 保留
- `docs/V1_BETA_2_SCHEDULING_APPLY_ACCEPTANCE.md` 验收记录
- `scripts/quick_test.py` 第 34 节静态断言（不在 quick_test 跑真实 apply）

**实测结果**：scheduler exit 0；due=1 / started=1；FetchRun=1 success，items_found=2
items_new=2；SourceItem=2；auto_summary.enabled=false；InsightCard=0；
running=0；stale_count=0；主库未污染（FetchRun/SourceItem 数量不变）。

**禁止事项**：不默认 LLM、不自动 stale recovery、不绕过安全闸门、不访问外网。

**验收标准**：`ACCEPTANCE_OK`，全部检查通过，主 DB 不变。

**风险**：真实抓取受网络 / 源站影响——缓解：本验收使用 local mock RSS，仅回环访问。

---

### Task 4：调度运行记录输出与验收

**目标**：为单轮调度输出统一的运行记录（计划 + 结果），并归档一次真实验收。

**改动范围**：
- 调度脚本输出结构化摘要（due / started / skipped 原因）
- 新增 `docs/V1_BETA_2_SCHEDULING_ACCEPTANCE.md`（验收记录）

**禁止事项**：不引入新数据库表、不改 FetchRun 模型。

**验收标准**：一次 dry-run + 一次 `--apply` 的运行记录可追溯，stale_count=0。

**风险**：运行记录与 FetchRun 重复——缓解：记录引用 FetchRun id，不复制状态。

---

### Task 5：Windows Task Scheduler / cron 使用文档 ✅ 已完成

**目标**：文档化由外部定时器调用 CLI 单轮调度（Phase B）。

**实现产物**：
- `docs/V1_BETA_2_SCHEDULER_OPERATIONS.md`
- 说明 Windows Task Scheduler 与 cron 两种方式及差异
- 环境变量配置（RADAR_SCHEDULER_ENABLED, AUTO_SUMMARY_MAX_PER_FETCH_RUN）
- 日志建议、常见问题、下一步

**说明**：本任务仅文档化外部定时器调用方式，不创建系统任务，不运行真实定时调度。

**禁止事项**：不在 Web 进程内塞常驻 scheduler。

**验收标准**：操作文档能让用户按间隔安全调用一次 CLI。

**风险**：Windows / Linux 调度差异——缓解：分平台分别给命令示例。

---

### Task 6：是否需要 TaskRun 表的决策复盘

**目标**：在跑过若干轮 CLI 调度后，复盘是否需要独立 TaskRun / JobRun 表。

**改动范围**：
- 更新 `docs/V1_BETA_2_DECISION_RECORD.md`（Decision 7 复盘结论）

**禁止事项**：在没有明确需求前不新增任务表。

**验收标准**：给出"继续复用 FetchRun"或"引入 TaskRun"的明确判断与触发条件。

**风险**：过早抽象——缓解：以"出现非抓取类自动任务需统一队列"为触发条件。

---

## 3. 推荐顺序

```
1. Task 1  设计归档（本次）
2. Task 2  CLI dry-run 骨架
3. Task 3  CLI 真实单轮执行
4. Task 4  运行记录与验收
5. Task 5  外部定时操作文档
6. Task 6  TaskRun 决策复盘
```

特别强调：

- **Task 2 默认 dry-run。**
- **Task 3 才允许真实创建 FetchRun。**
- **Task 3 不默认触发 LLM。**

---

## 4. 测试策略

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/acceptance_first_usable_loop.py
```

诊断（只读，建议运行）：

```bash
python scripts/check_due_sources.py
python scripts/check_stale_fetch_runs.py
```

不要在设计阶段运行 `/radar/today/update`、`/sources/{source_key}/fetch`、
`mark_stale_fetch_runs_failed.py --apply` 或任何真实抓取 / LLM 脚本。

---

## 5. 风险总览

| 风险 | 缓解 |
|------|------|
| 自动调度默认开启导致意外抓取 | 默认 `RADAR_SCHEDULER_ENABLED=false` |
| 自动触发 LLM 导致成本失控 | 默认 `RADAR_SCHEDULER_AUTO_SUMMARY=false` |
| 过早引入重型队列 | 不引入 Celery / Redis / APScheduler，先 CLI 单轮 |
| 过早新增 TaskRun 表 | 复用 FetchRun，Task 6 再复盘 |
| 进程内 scheduler 生命周期不清晰 | Phase A 用独立 CLI，外部定时器调用 |
