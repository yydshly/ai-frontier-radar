# AI Frontier Radar — 本地运行手册

## 0. 最快启动方式（TL;DR）

> 下次不知道怎么启动时，看这一节就够了。

**日常启动 Web 服务**（已配置好的机器）：
- 双击根目录 **`start_app.bat`**，或双击桌面 **「启动 AI前沿雷达」** 快捷方式。
- 它会启动服务并自动打开浏览器：http://127.0.0.1:8765
- 想要更多操作（启停/状态/手动跑每日任务）：双击 **`control_panel.bat`** 或 **「AI前沿雷达 控制台」**。

**第一次没有桌面图标？** 双击 **`create_desktop_icon.bat`** 生成带雷达图标的快捷方式（本目录 + 桌面）。

**每日报告会自动生成吗？** 只有装过定时任务的机器才会自动跑（见 [第 8 节](#8-安装每日定时任务)）。本机若已执行过 `install_windows_daily_task.ps1`，则**每天 08:05 自动执行**（关机错过会在开机后补跑）。换台机器/解压便携包后需要**重新安装一次**。

**两种运行形态：**
| 形态 | 适合 | 启动 | 见 |
|------|------|------|----|
| 源码 + .venv | 开发本机 | `start_app.bat` / `scripts\start_local.ps1` | 第 2–7 节 |
| 便携文件夹 | 分发/无 Python 的机器 | 解压后双击 `start_app.bat` | [第 15 节](#15-便携版打包与分发) |

---

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

## 5. 本地控制台（推荐）

双击打开 GUI 控制台，无需记忆命令：

```powershell
.\scripts\launcher.ps1
```

窗口中包含：

- Start Web Service
- Stop Web Service
- Open Home
- Open Local Status
- Show Status
- Open Logs Folder
- Run Daily Cycle Once
- Exit

## 6. 启动 Web 服务

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

## 7. 停止 Web 服务

在新终端中运行：

```powershell
.\scripts\stop_local.ps1
```

或直接按 Ctrl+C 停止 `start_local.ps1`。

## 8. 安装每日定时任务

> **默认会自动执行吗？** 不会——**装了才会**。`install_windows_daily_task.ps1`
> 向 Windows 任务计划程序注册一个任务；**注册之后**才会每天自动跑。这个注册是
> *按机器、按目录*的：换一台机器、或把便携包解压到新位置，都要**重新执行一次**。

```powershell
.\scripts\install_windows_daily_task.ps1
```

- **任务名**：AI Frontier Radar Daily Cycle
- **执行时间**：每天 08:05（登录状态下运行）
- **可靠性**：`StartWhenAvailable` —— 到点时机器关着/睡眠，开机后会尽快补跑，
  每日任务再自行回填错过的日期。失败自动重试 2 次。
- **执行内容**：`python scripts/run_daily_cycle.py --apply`
- **日志输出**：`logs/daily_cycle.log`（追加，UTF-8）

安装完成后会显示任务摘要信息。确认是否已装、下次何时跑：

```powershell
.\scripts\status_local.ps1
# 或
Get-ScheduledTaskInfo -TaskName "AI Frontier Radar Daily Cycle"
```

## 9. 卸载每日定时任务

```powershell
.\scripts\uninstall_windows_daily_task.ps1
```

## 10. 手动运行一次每日任务

```bash
# dry-run（不实际执行）
python scripts/run_daily_cycle.py

# 实际执行
python scripts/run_daily_cycle.py --apply
```

或者通过本地控制台（推荐）：

```powershell
.\scripts\run_daily_cycle_once.ps1
```

### 重要提示

```text
1. Run Daily Cycle Once 可能需要数分钟。
2. 执行中不要关闭窗口。
3. 执行中可以打开 /local-status 查看 current_step。
4. 实时日志在 logs/daily_cycle.live.log。
5. 完整执行报告在 runtime/daily_cycle_runs/latest.json。
6. 当前运行状态在 runtime/daily_cycle_runs/running.json。
7. 如果强制关闭窗口，本次任务可能不会完整写入 latest.json。
8. 下次通常可以重新运行，但应先查看 running.json / live log / latest.json。
```

### 每日任务内部阶段说明

Daily Cycle 运行时会输出内部阶段日志，可在 logs/daily_cycle.live.log 或控制台查看：

| 阶段 | 说明 |
|------|------|
| `cycle_start` | 每日任务开始，显示参数 |
| `finalization_check_start` | 开始检查待结算日期 |
| `finalization_pending_dates` | 找到待结算日期列表 |
| `finalization_date_start` | 开始结算某个日期 |
| `finalization_date_done` | 某个日期结算完成 |
| `fetch_start` | 开始抓取增量来源 |
| `fetch_done` | 来源抓取完成 |
| `summary_select_start` | 开始选择摘要目标 |
| `summary_targets_selected` | 摘要目标已选定 |
| `summary_batch_start` | 开始批量生成摘要 |
| `summary_batch_done` | 批量摘要生成完成 |
| `marker_start` | 开始记录最后运行时间 |
| `marker_done` | 运行标记完成 |
| `cycle_done` | 每日任务全部完成 |

如果窗口长时间停在 `summary_batch_start` 或 `summary_batch_done` 前后，通常表示正在调用模型或修复 JSON，请耐心等待。

## 11. 查看最近每日任务状态

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

## 12. 日志和数据目录说明

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
| `logs/daily_cycle.live.log` | 每日任务实时日志（运行中追加，完成后保留） |

### 每日任务报告

| 文件 | 说明 |
|------|------|
| `runtime/daily_cycle_runs/latest.json` | 最近一次执行报告 |
| `runtime/daily_cycle_runs/<run_id>.json` | 历史执行报告（如 `20260613_080500.json`） |
| `runtime/daily_cycle_runs/running.json` | 当前运行中状态（任务进行中或失败时存在） |

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

## 13. 常见问题

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

## 14. 快速命令汇总

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

## 15. 便携版打包与分发

把整个软件打成一个**自带 Python 运行时**的文件夹，拷到任何 64 位 Windows
机器上双击即用，**目标机无需安装 Python**。

### 15.1 打包

在源码 + .venv 的开发机上运行：

```powershell
.\scripts\make_portable.ps1            # 默认：含现有数据、只放 .env.example（不含密钥）
.\scripts\make_portable.ps1 -Zip       # 顺便压成 dist\AIFrontierRadar.zip
.\scripts\make_portable.ps1 -NoData    # 空库从头跑
.\scripts\make_portable.ps1 -IncludeEnv  # 含真实 .env（仅自己备份用，勿外发）
```

产物在 `dist\AIFrontierRadar\`（约 150MB）：

| 内容 | 说明 |
|------|------|
| `python\` | 内嵌 CPython 3.10 + 全部依赖 |
| `app\ scripts\ config\ data\ assets\` | 应用、脚本、配置、数据、图标 |
| `.env.example` | 配置模板（默认**不含**密钥） |
| `start_app.bat` / `control_panel.bat` | 启动入口 |
| `create_desktop_icon.bat` | 生成带图标的快捷方式 |
| `README_PORTABLE.txt` | 给接收者的使用说明 |

> 构建脚本内置两道冒烟自检（`import feedparser…` 和 `import app.main`），
> 任一失败构建即报错，避免发出跑不起来的包。

### 15.2 接收者使用

1. 解压文件夹。
2. 复制 `.env.example` 为 `.env`，填入自己的 `MINIMAX_API_KEY`。
3. （可选）双击 `create_desktop_icon.bat` 生成桌面图标。
4. 双击 `start_app.bat` 启动。
5. （可选）需要每天自动出报告：在该文件夹内执行
   `powershell -ExecutionPolicy Bypass -File scripts\install_windows_daily_task.ps1`。

### 15.3 图标与快捷方式

`.bat` 文件无法自带图标（永远是系统通用图标）。解决办法是用带图标的
**快捷方式（.lnk）**：

```powershell
.\scripts\create_shortcuts.ps1            # 在本目录创建快捷方式
.\scripts\create_shortcuts.ps1 -Desktop   # 同时放到桌面
```

图标文件是 `assets\app.ico`（雷达主题）。如需重绘：

```bash
python scripts/make_app_icon.py
```

> 快捷方式带的是**绝对路径**，请在软件实际所在的机器上生成，不要把别人机器上
> 生成的 .lnk 直接拷过来。

---

## 16. 分享页视频生成

分享页支持将核心报告生成为 9:16 竖屏 MP4 视频（语音讲解 + 信息卡片）。

### 16.1 前置依赖

**ffmpeg**（必须）：
- 下载地址：https://ffmpeg.org/download.html
- 将 `ffmpeg.exe` 放在项目根目录的 `bin/` 文件夹，或确保系统 PATH 中有 ffmpeg
- 验证：`ffmpeg -version`

**Pillow**（必须，用于渲染场景图片）：
- 已包含在 `requirements.txt` 中：`pip install -r requirements.txt`
- 若手动安装：`pip install Pillow>=10.0.0`
- 验证：`python -c "from PIL import Image; print('Pillow OK')"`

**MiMo TTS**（可选，用于语音）：
- 设置 `MIMO_API_KEY` 环境变量
- 若未配置且 `DEV_FAKE_TTS=true`，系统使用静音音频（可完成 pipeline 测试）

### 16.2 视频生成配置

| 环境变量 | 值 | 说明 |
|---------|-----|------|
| `DEV_FAKE_TTS` | `true` | 开发模式：使用静音音频（不调真实 TTS） |
| `MIMO_API_KEY` | `sk-...` 或 `tp-...` | MiMo V2.5 TTS API Key |
| `MIMO_TTS_VOICE` | 冰糖（默认）| TTS 音色 |
| `MIMO_TTS_STYLE` | （默认播报语气）| TTS 风格 |

### 16.3 视频生成原理

视频数据来自分享页背后的核心报告快照，不是网页截图。流程：

1. 用户点击"生成视频"
2. 构造 `ShareReportSnapshot`（核心报告快照）
3. 转成 `VideoSourceSnapshot`（通用视频数据结构）
4. 计算 `input_hash`（基于内容 + 配置）
5. 检查是否已有成功视频（复用）
6. 后台执行：Scene 图片（Pillow）→ Scene 音频（TTS）→ MP4（ffmpeg）
7. 存储到 `runtime/generated_videos/<source_key>/<input_hash>/`

### 16.4 本地开发测试

```bash
# 启用开发假 TTS（不调真实 API）
export DEV_FAKE_TTS=true

# 启动服务
start_app.bat

# 打开分享页
# http://127.0.0.1:8765/radar/share/today

# 点击"生成视频"，观察状态轮询
```

### 16.5 常见问题

**Q: 点击生成视频后一直显示"生成中"？**
- 检查 ffmpeg 是否可用：`ffmpeg -version`
- 检查服务日志是否有错误

**Q: 视频生成失败？**
- 检查 `runtime/generated_videos/<source_key>/<input_hash>/status.json` 中的 `error` 字段
- 常见原因：TTS 未配置（需要 `MIMO_API_KEY` 或 `DEV_FAKE_TTS=true`）

**Q: 如何重新生成视频？**
- 点击分享页中的"重新生成"按钮（传 `force=true`）

**Q: 视频文件存储在哪里？**
- `runtime/generated_videos/<source_key>/<input_hash>/output.mp4`
- 不同 `input_hash` 不会互相覆盖；同 `input_hash` + `force=True` 会覆盖
