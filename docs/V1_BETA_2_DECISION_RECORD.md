# V1.0-beta.2 决策记录：自动调度与轻量任务队列

本文件记录 V1.0-beta.2 自动调度阶段的关键架构决策。每条决策包含背景、决策、
原因、影响和后续复盘条件。

---

## Decision 1：V1.0-beta.2 不直接引入 Celery / Redis

**背景**：自动调度天然让人联想到 Celery + Redis / RQ / Dramatiq 等任务队列栈。

**决策**：本阶段**不直接引入 Celery / Redis / RQ / Dramatiq** 等重型队列。

**原因**：当前是单机技术探针 MVP，来源数量、并发量、任务复杂度都很低；引入
重型队列会带来部署、运维、依赖和心智成本，收益不匹配。

**影响**：调度先用 CLI 单轮 + 外部定时器实现；不新增中间件依赖。

**后续复盘条件**：当出现多机部署、高并发抓取、或需要分布式任务可靠投递时重新评估。

---

## Decision 2：优先 CLI 单轮调度，而不是应用内常驻 scheduler

**背景**：可以在 Web 进程内用 APScheduler 跑常驻定时，也可以做一次性 CLI 调度。

**决策**：优先实现 **CLI 单轮调度器**（`run_due_sources_once.py`），由外部
定时器（Windows Task Scheduler / cron）调用；暂不在 Web 进程内塞常驻 scheduler。

**原因**：CLI 单轮调度生命周期清晰、易测试、易关闭、易观察；常驻 scheduler 会
让 Web 进程生命周期和任务调度耦合，进程重启 / 异常时状态更难解释。

**影响**：调度逻辑留在可独立运行的脚本中；外部定时只负责"按间隔调用一次"。

**后续复盘条件**：当一次性 CLI 无法满足实时性 / 高频需求时，再评估 Phase C 常驻 scheduler。

---

## Decision 3：自动调度默认关闭

**背景**：自动化一旦默认开启，可能在用户不知情时产生抓取流量。

**决策**：自动调度默认关闭（`RADAR_SCHEDULER_ENABLED=false`）。

**原因**：保守优先，避免意外抓取、意外流量、意外源站压力。

**影响**：用户必须显式开启自动调度；默认环境下系统行为与 beta.1 一致（纯手动）。

**后续复盘条件**：当自动调度经过充分验证、稳定可控后，再考虑是否调整默认值。

---

## Decision 4：自动调度默认不触发 LLM

**背景**：抓取后可触发中文摘要 / InsightCard 生成，这些是 LLM 成本敏感操作。

**决策**：自动调度默认**不触发 LLM**（`RADAR_SCHEDULER_AUTO_SUMMARY=false`）。

**原因**：LLM 成本与质量敏感，自动批量触发容易导致成本失控；也避免在
prompt injection 防护尚未针对自动化场景强化前扩大 LLM 暴露面。

**影响**：自动调度只负责抓取与状态记录；摘要 / InsightCard 仍走人工或显式开启。

**后续复盘条件**：当自动摘要有明确成本上限与质量门槛后，再评估默认行为。

---

## Decision 5：stale recovery 不自动执行

**背景**：beta.1 已有 stale running 诊断和人工恢复脚本（`--apply` 才写库）。

**决策**：stale running 恢复**不纳入自动调度**，继续要求人工确认（`--apply`）。

**原因**：恢复是写库操作，会把 running 改为 failed；自动执行有误判风险，必须
保留人工确认这一安全闸门。

**影响**：自动调度只做诊断（只读），不自动改 FetchRun 状态。

**后续复盘条件**：当 stale 判断有足够长的稳定运行历史、且有审计日志后，再评估
是否允许"人工确认策略下的半自动恢复"。

---

## Decision 6：FetchRun 继续作为来源抓取状态核心对象

**背景**：来源抓取已有 FetchRun 记录完整状态；自动调度需要任务状态载体。

**决策**：抓取调度**继续复用 FetchRun**，不为抓取另起一套任务状态模型。

**原因**：FetchRun 已包含 status / started_at / finished_at / items_* /
error_message，足以表达单来源抓取任务的生命周期；复用避免状态双写和不一致。

**影响**：CLI 调度通过 `enqueue_source()` 创建 FetchRun，调度记录引用 FetchRun id。

**Task 3B 验收结果**：isolated DB + local mock RSS 的真实 `--apply` 验收证明，
CLI 单轮调度可以复用 FetchRun 作为抓取任务状态对象（FetchRun success、SourceItem
增量入库、auto_summary 关闭、无 stale running），无需为抓取另起任务表。

**后续复盘条件**：当出现非抓取类自动任务（如健康检查、导出）也需要统一状态时复盘（见 Decision 7）。

---

## Decision 7：TaskRun / JobRun 暂缓设计到实现层

**背景**：长期看可能需要统一任务对象（TaskKind / TaskStatus / idempotency_key /
max_attempts / next_run_at / last_error）。

**决策**：TaskRun / JobRun **只做形状设计，暂不落地为代码或数据库表**；
当前不新增任务表。

**原因**：FetchRun 已覆盖抓取任务；在没有"多类型自动任务需要统一队列"的明确需求前，
新增任务表属于过早抽象，会增加 schema 与维护成本。

**影响**：本阶段不新增数据库表 / 字段；任务队列以设计文档形式预留。

**后续复盘条件**：当出现以下任一情况时，在 beta.2 Task 6 复盘是否引入 TaskRun：
- 需要统一管理多种自动任务类型（抓取之外）
- 需要跨任务的重试 / 退避 / 幂等键统一策略
- 需要任务级审计与执行日志聚合
