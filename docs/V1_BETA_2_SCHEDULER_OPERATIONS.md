# V1.0-beta.2 Scheduler Operations Manual

## 1. 手册目标

本手册用于把 `run_due_sources_once.py` 从"可手动运行的 CLI"变成"可被外部定时器安全调用的本地调度入口"。

**强调**：这是单机 MVP 操作手册，不是企业任务平台。不引入 Celery / Redis / APScheduler。

---

## 2. 当前调度入口

当前唯一调度入口：

```bash
python scripts/run_due_sources_once.py
```

### 默认行为（dry-run）

```text
- 只读，不创建 FetchRun
- 不触发抓取
- 不调用 LLM
- 输出 due / skipped / running / unsupported / missing 计划
```

### 安全执行（apply）

```bash
RADAR_SCHEDULER_ENABLED=true AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 python scripts/run_due_sources_once.py --apply
```

Windows PowerShell：

```powershell
$env:RADAR_SCHEDULER_ENABLED="true"
$env:AUTO_SUMMARY_MAX_PER_FETCH_RUN="0"
python scripts/run_due_sources_once.py --apply
```

**必须说明**：

- `--apply` 只处理 due sources
- `due=0` 时不会创建 FetchRun（安全 no-op）
- `AUTO_SUMMARY_MAX_PER_FETCH_RUN=0` 禁用自动摘要和 LLM

---

## 3. 推荐运行模式

### 模式 A：手动 dry-run 检查

```bash
python scripts/run_due_sources_once.py --show-skipped --show-running --show-unsupported --show-missing
```

用途：

```text
- 看哪些来源 due
- 看为什么 skipped
- 看是否存在 running
- 看是否存在 missing
```

### 模式 B：手动安全 apply

```bash
RADAR_SCHEDULER_ENABLED=true AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 python scripts/run_due_sources_once.py --apply --max-sources 3
```

用途：

```text
- 手动启动最多 3 个 due source
- 默认不触发 LLM
```

### 模式 C：外部定时器调用

由操作系统定时执行：

```text
Windows Task Scheduler
cron
```

---

## 4. Windows Task Scheduler 操作说明

### 4.1 推荐脚本文件

PowerShell 示例脚本（需要替换路径）：

```powershell
# run_ai_frontier_radar_scheduler.ps1

cd D:\path\to\ai-frontier-radar

$env:RADAR_SCHEDULER_ENABLED="true"
$env:AUTO_SUMMARY_MAX_PER_FETCH_RUN="0"
$env:SOURCE_FETCH_MAX_ITEMS_PER_RUN="5"

python scripts/run_due_sources_once.py --apply --max-sources 3 >> logs\scheduler.log 2>&1
python scripts/check_stale_fetch_runs.py >> logs\scheduler.log 2>&1
```

说明：

```text
- 路径需要替换成本机项目路径
- logs 目录需要提前存在，或脚本中创建
- python 建议使用绝对路径（如 C:\Python311\python.exe）
```

### 4.2 创建任务步骤

```text
1. 打开 Task Scheduler（任务计划程序）
2. 点击"创建基本任务"
3. 设置名称：AI Frontier Radar Scheduler
4. 设置触发器：每天 或 每 6 小时
5. 操作：启动程序
6. 程序/脚本：powershell.exe
7. 添加参数：
   -ExecutionPolicy Bypass -File "D:\path\to\run_ai_frontier_radar_scheduler.ps1"
8. 起始位置：
   D:\path\to\ai-frontier-radar
9. 点击确定保存
```

### 4.3 推荐频率

```text
MVP 阶段：每天 1 次 或 每 6 小时 1 次
不要低于 30 分钟（避免对源站造成压力）
```

### 4.4 Windows 注意事项

必须说明：

```text
- VPN / 代理环境可能影响 RSS 抓取
- Windows 任务运行用户不同，环境变量可能不同
- Python 解释器路径可能需要写绝对路径
- 工作目录必须指向项目根目录
- 日志必须落盘，避免任务失败不可见
- 建议使用 64 位 PowerShell
```

---

## 5. cron 操作说明

Linux/macOS 示例：

```bash
cd /path/to/ai-frontier-radar

RADAR_SCHEDULER_ENABLED=true \
AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 \
SOURCE_FETCH_MAX_ITEMS_PER_RUN=5 \
python scripts/run_due_sources_once.py --apply --max-sources 3 >> logs/scheduler.log 2>&1
```

crontab 示例：

```cron
# 每 6 小时执行一次
0 */6 * * * cd /path/to/ai-frontier-radar && RADAR_SCHEDULER_ENABLED=true AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 SOURCE_FETCH_MAX_ITEMS_PER_RUN=5 python scripts/run_due_sources_once.py --apply --max-sources 3 >> logs/scheduler.log 2>&1
```

说明：

```text
- 需要替换项目路径
- 需要确认 python 指向正确 venv
- logs 目录需要提前创建
- 建议使用绝对路径
```

---

## 6. 日志建议

### 推荐日志文件

```text
logs/scheduler.log
```

### 建议每次记录内容

```text
- 运行时间
- APPLY / DRY-RUN 模式
- due / skipped / running / unsupported / missing 数量
- started / already_running / failed_to_start 来源
- run_id（如有）
- final_status（如有）
- items_found / items_new / items_updated / items_failed（如有）
- stale_count
```

### 日志轮转

**当前系统暂不做日志轮转**，后续可使用 logrotate（Linux）或 PowerShell 脚本实现。

---

## 7. 验证命令

### 手动验证

```bash
# dry-run 查看计划
python scripts/run_due_sources_once.py

# 检查 due sources
python scripts/check_due_sources.py

# 检查 stale running
python scripts/check_stale_fetch_runs.py
```

### 安全 apply 验证

```bash
# 限制来源数，避免一次打满
RADAR_SCHEDULER_ENABLED=true AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 python scripts/run_due_sources_once.py --apply --max-sources 1
```

### 本地 isolated 验收

```bash
# 不污染主库的真实 apply 验收
python scripts/acceptance_run_due_sources_once_apply.py
```

---

## 8. 常见问题

### Q1：为什么 due=0？

```text
来源仍在 fetch_interval_hours 冷却期。
这不是失败，是正常状态。
可以看 skipped reason 是否为 not_due_yet。
冷却期结束后会有 due 来源。
```

### Q2：为什么 --apply 直接失败？

```text
可能原因：
- 缺少 RADAR_SCHEDULER_ENABLED=true
- 或 AUTO_SUMMARY_MAX_PER_FETCH_RUN 不是 0

检查方法：
echo %RADAR_SCHEDULER_ENABLED%   (Windows)
echo $env:RADAR_SCHEDULER_ENABLED   (PowerShell)
echo $RADAR_SCHEDULER_ENABLED   (Linux/macOS)
```

### Q3：为什么不默认触发 LLM？

```text
LLM 成本和 prompt injection 风险敏感。
调度阶段默认只抓取 SourceItem，不自动生成 InsightCard。
当前真实生效的自动摘要控制项是 AUTO_SUMMARY_MAX_PER_FETCH_RUN。
V1.0-beta.2 阶段 --apply 要求 AUTO_SUMMARY_MAX_PER_FETCH_RUN=0。
RADAR_SCHEDULER_AUTO_SUMMARY 目前只是设计中的未来开关，尚未作为真实可用配置实现。
如未来需要自动摘要调度，应另行实现并验收。
```

### Q4：出现 running 卡住怎么办？

```text
1. 先运行 check_stale_fetch_runs.py 诊断
2. 确认是 stale 后，再人工决定是否运行：
   python scripts/mark_stale_fetch_runs_failed.py --apply
3. 不要把 stale recovery 放入自动调度
4. 恢复后 due-source 会重新将该来源纳入调度
```

### Q5：怎么确认没有污染主库？

```text
- 生产调度使用默认 DATABASE_URL
- 验收测试使用 isolated DATABASE_URL
- 运行 isolated acceptance 不会改 data/ai_frontier_radar.db
- 可通过 check_stale_fetch_runs.py 确认 running=0
```

### Q6：日志文件不存在怎么办？

```text
# Linux/macOS
mkdir -p logs
touch logs/scheduler.log

# Windows PowerShell
New-Item -ItemType Directory -Force -Path logs
New-Item -ItemType File -Force -Path logs\scheduler.log
```

---

## 9. 当前不建议做的事

必须列出：

```text
1. 不建议每几分钟跑一次（最低 30 分钟间隔）
2. 不建议打开自动摘要（AUTO_SUMMARY_MAX_PER_FETCH_RUN=0）
3. 不建议自动 stale recovery（必须人工确认）
4. 不建议在 Web 进程里塞 scheduler
5. 不建议直接上 Celery / Redis
6. 不建议对所有来源无限制重抓（使用 --max-sources 限制）
```

---

## 10. 下一步

```text
- 多 due 来源真实运行观察
- 日志归档与轮转
- 失败退避策略设计
- TaskRun / JobRun 是否需要继续复盘
```

---

## 11. 相关文档

- [V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md](V1_BETA_2_AUTOMATED_SCHEDULING_DESIGN.md) — 自动调度设计
- [V1_BETA_2_EXECUTION_PLAN.md](V1_BETA_2_EXECUTION_PLAN.md) — 执行计划
- [V1_BETA_2_DECISION_RECORD.md](V1_BETA_2_DECISION_RECORD.md) — 决策记录
