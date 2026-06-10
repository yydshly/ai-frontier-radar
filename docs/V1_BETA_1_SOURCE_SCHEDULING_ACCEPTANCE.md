# V1.0-beta.1 Source Scheduling Acceptance

## 1. 阶段目标

V1.0-beta.1 **不是**做一个全自动调度系统。

本阶段目标是建立来源调度与单来源排查闭环，让系统从"手动跑通"升级为"可持续运行"：

```
来源调度（due-source）
→ 单来源状态可见（来源工作台）
→ stale running 诊断
→ 人工恢复
→ 单来源手动探测
→ FetchRun 状态追踪
→ SourceItem 增量入库
```

核心价值：
- 不重复探测已在 running 的来源
- 告诉用户为什么某个来源没被更新
- 提供单来源健康视图和手动触发能力

---

## 2. 已完成任务

| Task | 名称 | 状态 |
|------|------|------|
| Task 1 | due-source 计算服务 | ✅ 已实现 |
| Task 2 | /radar/today/update 接入 due-source | ✅ 已实现 |
| Task 3 | 单来源工作台只读版（含 Task 3A.1 UX 调整） | ✅ 已实现 |
| Task 3B | stale running FetchRun 诊断 | ✅ 已实现 |
| Task 3C | stale running 人工恢复脚本（含 Task 3C.1 参数安全校验） | ✅ 已实现 |
| Task 3D | 执行 stale running 本地恢复 | ✅ 已实现 |
| Task 4 | 单来源手动探测入口规范化 | ✅ 已实现 |
| Task 5 | 真实单来源手动探测验收 | ✅ 已实现 |

---

## 3. 核心链路

```
来源列表（/sources）
  → 来源工作台（/sources/{source_key}）
    → due-source 当前判断（冷却期 / 已到期 / running）
    → stale running 诊断（只读）
    → stale running 人工恢复（--apply 才写库）
    → 单来源手动探测（POST /sources/{source_key}/fetch）
      → FetchRun 创建 / 复用
      → 后台抓取
        → SourceItem 增量入库（new / updated / failed）
```

### 关键设计说明

- `/radar/today/update` 是 due-source 自动调度入口，只处理 `plan.due`。
- `/sources/{source_key}/fetch` 是单来源手动探测入口，**POST-only**，会创建或复用 FetchRun。
- stale running 诊断是**只读**。
- stale running 恢复是**人工确认**、默认 dry-run、`--apply` 才写库。
- FetchRun 是当前后台任务治理的核心对象。

---

## 4. 真实验收记录

### stale running 恢复

```
恢复前：running=8, stale_count=8
恢复后：running=0, stale_count=0
```

### 真实单来源手动探测（openai_news）

```
POST /sources/openai_news/fetch
→ 302 → /fetch-runs/1067

run_id=1067
status=success
items_found=50
items_new: 3
items_updated: 47
items_failed: 0

SourceItem count: 50 → 53
```

### HTTP 方法验证

```
GET 405
POST 303
```

### 其他未触发项

```
LLM（生成摘要）：未触发（本次为已有摘要的 SourceItem 抓取）
InsightCard：未生成
/radar/today/update：未执行
```

---

## 5. 当前系统状态

### check_stale_fetch_runs.py

```
total_running: 0
stale_count: 0
```

### check_due_sources.py

```
due: 0
skipped: 15
running: 0
unsupported: 0
missing: 0
```

**注意**：`due=0` 是因为所有来源都处于冷却期（`not_due_yet`），**不是故障**。冷却期结束后才会有 due 来源。

---

## 6. 设计结论

### 6.1 两条不同入口

| 入口 | 路径 | 行为 |
|------|------|------|
| due-source 自动调度 | POST /radar/today/update | 只处理 `plan.due`，展示跳过原因 |
| 单来源手动探测 | POST /sources/{source_key}/fetch | 用户手动触发，绕过冷却期 |

### 6.2 stale running 处理策略

- **诊断**：只读查询，不修改 DB
- **恢复**：人工确认，默认 dry-run，`--apply` 才写库
- **不自动修复**：因为自动判断可能误判，人工确认更安全

### 6.3 POST-only 原则

手动探测入口禁止 GET 请求，防止误触副作用。

### 6.4 FetchRun 是任务治理中心

- 所有探测都通过 FetchRun 记录状态
- running 状态去重（不能重复 enqueue）
- stale 判定基于 `started_at` 时长

---

## 7. 已知限制

1. **暂无定时调度**：当前依赖手动触发 `/radar/today/update`。
2. **暂无队列系统**：使用 FastAPI BackgroundTasks，非持久化队列。
3. **暂无自动 stale recovery**：stale running 需要人工运行恢复脚本。
4. **summary coverage 可能全量扫描**：单来源工作台的 summary 统计在数据量大时可能有性能风险。
5. **手动探测受网络影响**：会真实访问外部来源，受源站可用性影响。
6. **备份文件不进入 git**：数据库备份文件需本地管理。

---

## 8. 下一阶段建议

**下一阶段命名**：V1.0-beta.2：自动调度与轻量任务队列设计

**建议方向**：
- 不要马上上复杂 Celery/Redis
- 先考虑轻量 scheduler / CLI 定时 / 单机队列
- 先定义任务状态和重试策略

**本阶段明确**：
- V1.0-beta.1 已完成来源调度、状态解释、stale 诊断、人工恢复、单来源手动探测和真实抓取验收
- 后续功能应进入 V1.0-beta.2，而不是继续扩大 beta.1 范围

---

## 9. 验收命令

```bash
# 基础编译检查
python -m compileall app scripts

# 快速冒烟测试
python scripts/quick_test.py

# First usable loop 验收
python scripts/acceptance_first_usable_loop.py

# 来源调度诊断（只读）
python scripts/check_due_sources.py
python scripts/check_stale_fetch_runs.py
```
