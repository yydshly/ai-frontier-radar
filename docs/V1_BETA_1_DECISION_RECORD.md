# V1.0-beta.1 架构决策记录

## ADR-001：V1.0-beta.1 先不引入定时任务

**决策**：先做手动触发下的 due-source 调度，不做 cron / scheduler / APScheduler / Celery。

**原因**：
- 当前目标是验证调度逻辑正确性，不是运行一个守护进程
- 定时任务会增加部署复杂度（进程管理、失败重启、分布式一致性）
- 手动触发 + due-source 展示已经能解决"盲目全量刷新"的问题
- 定时任务可在 V1.0-beta.2 按需引入

**后果**：用户需要手动点击"更新今日雷达"，系统智能判断哪些该跑。

---

## ADR-002：继续用 config enabled sources 表示雷达关注源

**决策**：V1.0-beta.1 暂不新增 `radar_enabled` 字段到 Source 表，也暂不新增 RadarSourceProfile 表。

**原因**：
- 避免数据库迁移和测试来源治理
- config 即代码，可 Git 管理，适合当前阶段
- 当前雷达关注源数量可控（15 个），无需动态管理
- 如果未来需要更灵活的雷达来源管理，再评估 RadarSourceProfile 方案

**未来选项**：
- 方案 A（当前）：继续用 config 管理
- 方案 B：Source.radar_enabled 布尔字段
- 方案 C：新增 RadarSourceProfile 表

---

## ADR-003：due-source 基于 FetchRun 历史计算，不新增 SourceState 表

**决策**：不新增 `SourceState` 或 `SourceHealth` 表。通过查询最近 FetchRun 计算 last_attempt / last_success / consecutive_failures / is_running。

**原因**：
- 减少状态冗余，避免多表一致性问题
- FetchRun 本身已经是来源状态的记录载体
- 不需要额外维护一个来源"当前状态"的镜像
- 查询成本可控（FetchRun 有索引）

**注意**：
- 需要对 source_key 建索引
- 如果未来需要高频查询，可加 SourceState 缓存层，但那是后续优化

---

## ADR-004：摘要队列暂不落表

**决策**：保留当前 FetchRun 后处理的 auto_summary best-effort 机制。暂不新增 SummaryJob 表。

**原因**：
- 当前自动摘要已能支撑 First Usable Loop（默认 5 条 best-effort）
- V1.0-beta.1 的核心价值是来源调度，不是队列系统
- SummaryJob 的复杂度（失败重试、限流、批量补齐）可留到 V1.0-beta.2
- 当前摘要失败对用户影响有限（只是没有摘要，不阻断 InsightCard）

**当前标注**：在工作台和文档中明确"自动摘要为 best-effort，暂不支持重试"。

---

## ADR-005：单来源工作台先做只读，再做操作

**决策**：先展示状态（Task 3），再接入单来源运行探测按钮（Task 4）。

**原因**：
- 避免页面和后台操作同时复杂化
- 只读版可以快速验证信息展示是否准确
- 用户先看到状态，再有操作期待，符合认知顺序
- 操作部分可复用已有的 `SourceFetchBackgroundService.enqueue_source()`

---

## ADR-006：来源池与雷达关注源先用文档化分离

**决策**：SourcePool（数据层）和 RadarSource（业务层）先用文档和变量名区分，不新增 DB 字段。

**原因**：
- 当前 Source 表中测试来源较多，不适合直接加 radar_enabled
- config enabled sources 已经表达了"雷达关注源"语义
- 先用文案（来源池 vs 雷达关注源）建立共识，再决定是否需要 DB 表达

**未来演进**：如果 Web UI 需要编辑雷达来源，再评估方案 B（radar_enabled 字段）或方案 C（RadarSourceProfile 表）。
