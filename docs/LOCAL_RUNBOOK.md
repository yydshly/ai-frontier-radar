# AI Frontier Radar — 本地运行手册

## 1. 本地运行版定位

本地运行版适合：
- 在本地机器长期运行 Web 服务
- 通过 Windows Task Scheduler 定时执行每日任务
- 无需 Docker，无需云服务

## 2. 第一次启动步骤

### 2.1 克隆项目

```bash
git clone <repo-url>
cd ai-frontier-radar/ai-frontier-radar
```

### 2.2 创建虚拟环境（推荐）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2.3 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 配置 .env

在项目根目录创建 `.env` 文件，至少包含：

```env
# LLM 配置（至少填一项）
ANTHROPIC_API_KEY=sk-...
# 或
MINIMAX_API_KEY=...
LLM_PROFILE=minimax_m27_highspeed_anthropic
```

> 注意：`.env` 包含敏感信息，不要提交到 Git。

## 4. 配置 config/sources.yaml

将 `config/sources.yaml.example`（如有）复制为 `config/sources.yaml`，或自行创建。

## 5. 启动 Web 服务

```powershell
.\scripts\start_local.ps1
```

输出示例：

```
============================================================
AI Frontier Radar — Local Start
============================================================

Project root: D:\path\to\ai-frontier-radar
Python: D:\path\to\ai-frontier-radar\.venv\Scripts\python.exe
  Web address:  http://127.0.0.1:8765
  App log:     D:\path\to\ai-frontier-radar\logs\app.log
```

服务启动后访问：http://127.0.0.1:8765

本地状态页面：http://127.0.0.1:8765/local-status

## 6. 停止 Web 服务

在新终端中运行：

```powershell
.\scripts\stop_local.ps1
```

或直接按 Ctrl+C 停止 `start_local.ps1`。

## 7. 安装每日定时任务

```powershell
.\scripts\install_windows_daily_task.ps1
```

- **任务名**：AI Frontier Radar Daily Cycle
- **执行时间**：每天 08:05
- **执行内容**：`python scripts/run_daily_cycle.py --apply`
- **日志输出**：`logs/daily_cycle.log`（追加）

安装完成后会显示任务摘要信息。

## 8. 卸载每日定时任务

```powershell
.\scripts\uninstall_windows_daily_task.ps1
```

## 9. 手动运行一次每日任务

```bash
# dry-run（不实际执行）
python scripts/run_daily_cycle.py

# 实际执行
python scripts/run_daily_cycle.py --apply
```

## 10. 查看最近每日任务状态

### 方式一：PowerShell 脚本（推荐）

```powershell
.\scripts\status_local.ps1
```

显示：
- Web 服务状态（是否运行中）
- Windows 定时任务状态（是否已安装，下次运行时间）
- 关键目录存在性检查
- 最近每日任务执行结果

### 方式二：Python 脚本

```bash
python scripts/show_daily_cycle_status.py
```

### 方式三：Web 页面

访问：http://127.0.0.1:8765/local-status

## 11. 日志和数据目录说明

### 关键目录

| 目录 | 说明 |
|------|------|
| `.env` | 环境变量配置（API Key 等） |
| `config/sources.yaml` | 来源配置 |
| `data/` | 数据文件存储 |
| `runtime/` | 运行产物存储 |
| `logs/` | 日志文件 |
| `runtime/daily_cycle_runs/` | 每日任务执行报告 |

### 日志文件

| 文件 | 说明 |
|------|------|
| `logs/app.log` | Web 服务（uvicorn）日志 |
| `logs/daily_cycle.log` | 每日任务执行日志（追加） |

### 每日任务报告

| 文件 | 说明 |
|------|------|
| `runtime/daily_cycle_runs/latest.json` | 最近一次执行报告 |
| `runtime/daily_cycle_runs/<run_id>.json` | 历史执行报告（如 `20260613_080500.json`） |

`latest.json` 字段说明：

```json
{
  "run_id": "20260613_080500",
  "mode": "apply",
  "status": "success",
  "exit_code": 0,
  "started_at": "2026-06-13T08:05:00",
  "finished_at": "2026-06-13T08:07:31",
  "duration_seconds": 151,
  "fetch_due": 12,
  "fetch_started": 8,
  "summary_targets": 24,
  "summary_completed": 24,
  "report_status": "finalized",
  "audio_status": "generated",
  "finalized_dates": ["2026-06-12"],
  "steps": ["..."],
  "errors": [],
  "log_path": "logs/daily_cycle.log",
  "command": "python scripts/run_daily_cycle.py --apply"
}
```

### 其他 runtime 产物

| 目录 | 说明 |
|------|------|
| `runtime/daily_reports/` | 日报 JSON 文件 |
| `runtime/daily_audio/` | 音频广播文件 |
| `runtime/content_snapshots/` | 内容快照 |

## 12. 常见问题

### Q: start_local.ps1 提示 ".venv not found"

如果未使用虚拟环境，脚本会自动 fallback 到 PATH 中的 `python`。也可以手动安装虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Q: 定时任务没有执行

1. 检查任务是否安装成功：`schtasks /Query /TN "AI Frontier Radar Daily Cycle"`
2. 检查 `logs/daily_cycle.log` 是否有输出
3. 确认 `.env` 中的 API Key 有效

### Q: daily_cycle.log 显示错误

- 检查 `.env` 配置是否正确
- 检查 `config/sources.yaml` 是否存在
- 查看控制台输出的详细错误信息

### Q: Web 服务端口 8765 被占用

```powershell
.\scripts\stop_local.ps1
```
或手动查找并停止占用端口的进程。

### Q: latest.json 报告"无法读取"

可能是文件损坏或尚未执行过每日任务。手动运行一次：

```bash
python scripts/run_daily_cycle.py
```

### Q: 定时任务执行了但 latest.json 没有更新

检查 `runtime/daily_cycle_runs/` 目录权限，以及 `logs/daily_cycle.log` 中是否有写入错误。

## 13. 快速命令汇总

```powershell
# 启动 Web 服务
.\scripts\start_local.ps1

# 停止 Web 服务
.\scripts\stop_local.ps1

# 安装每日定时任务
.\scripts\install_windows_daily_task.ps1

# 卸载每日定时任务
.\scripts\uninstall_windows_daily_task.ps1

# 查看本地运行状态
.\scripts\status_local.ps1

# 手动运行每日任务（dry-run）
python scripts/run_daily_cycle.py

# 手动运行每日任务（实际执行）
python scripts/run_daily_cycle.py --apply

# 查看每日任务状态（Python）
python scripts/show_daily_cycle_status.py
```
