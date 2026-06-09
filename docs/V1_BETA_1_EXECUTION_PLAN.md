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

### Task 2：今日雷达更新入口接入 due-source

**范围**：
- 修改 `/radar/today` 的 update 按钮逻辑
- 先调用 due-source 计算
- 只 enqueue due sources
- 页面显示 skipped reason summary

**不修改**：
- FetchRun 探测逻辑本身
- Source 表结构
- config 来源配置

**验收**：
- 未到期来源不会重复探测
- running 来源不会重复 enqueue
- 页面显示跳过数量和原因（如"5 个来源未到期"）

---

### Task 3：单来源工作台 `/sources/{source_key}` 只读版

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

---

### Task 4：单来源手动探测

**范围**：
- `POST /sources/{source_key}/fetch` 触发该来源探测
- 调用 `SourceFetchBackgroundService.enqueue_source()`
- 成功后重定向回工作台或今日雷达

**验收**：
- 从工作台点击"运行探测"可触发 FetchRun
- 重复点击不会创建多个 running FetchRun（due-source 校验）

---

### Task 5：来源概念文案统一

**范围**：
- 页面不再混用"来源"、"雷达来源"、"关注来源"等术语
- 统一为：来源池（SourcePool）、雷达关注源（RadarSource）
- 更新 `/sources` 页面文案
- 更新 `/radar/today` 更新结果展示文案

**验收**：
- 页面术语一致
- 用户能区分"来源池"和"雷达关注源"

---

### Task 6：摘要队列后续设计记录

**范围**：
- 不实现 SummaryJob 表
- 补充 V1_BETA_1_DECISION_RECORD.md 中的摘要演进说明
- 在工作台页面标注"自动摘要为 best-effort，暂不支持重试"

**验收**：
- 文档清楚说明当前 auto_summary 与未来 SummaryQueue 的关系

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
