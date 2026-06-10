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

### Task 2：run_due_sources_once.py dry-run 设计与脚本骨架

**目标**：实现 CLI 单轮调度器骨架，**默认 dry-run**，只打印本轮计划，不写库。

**改动范围**：
- 新增 `scripts/run_due_sources_once.py`
- 复用 `compute_due_sources()`，只读取 `plan.due`
- 支持 `--max-sources N`
- 新增 quick_test 静态断言（默认 dry-run、不含 enqueue 写路径）

**禁止事项**：默认不得创建 FetchRun、不得调用 LLM、不得改 due-source 逻辑。

**验收标准**：dry-run 打印计划且不创建 FetchRun；`check_stale_fetch_runs.py` stale_count 不变。

**风险**：误把 dry-run 写成真实执行——缓解：apply 必须显式 flag，默认 dry-run。

---

### Task 3：run_due_sources_once.py 真实执行单轮 due sources

**目标**：在 `--apply` 下真实创建 FetchRun，只处理 `plan.due`。

**改动范围**：
- `scripts/run_due_sources_once.py` 增加 `--apply` 写路径
- 通过 `SourceFetchBackgroundService.enqueue_source()` 投递
- `--apply` **不默认触发 LLM**（除非显式开启）

**禁止事项**：不批量重抓全部来源、不绕过 running 去重、不默认 LLM。

**验收标准**：`--apply` 后只对 due 来源创建 FetchRun，不产生 stale running，due-source 可解释。

**风险**：重复抓取 / 卡住——缓解：running 窗口去重 + 每轮来源上限。

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

### Task 5：Windows Task Scheduler / cron 使用文档

**目标**：文档化由外部定时器调用 CLI 单轮调度（Phase B）。

**改动范围**：
- 新增 `docs/V1_BETA_2_SCHEDULER_OPERATIONS.md` 或在设计文档补充操作小节
- 说明 Windows Task Scheduler 与 cron 两种方式及差异

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
