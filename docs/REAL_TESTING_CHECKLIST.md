# 真实测试 / 发布检查清单

把 AI Frontier Radar 打包并在真实环境跑起来的一步步清单。面向"自用 + 分发给少数人",
不是公开 SaaS 部署。

---

## A. 打包便携版

```powershell
# 默认：含现有数据 + 仅 .env.example（安全分发给他人）
.\scripts\make_portable.ps1

# 自用备份：连真实 .env（含密钥）一起打包 —— 切勿外发
.\scripts\make_portable.ps1 -IncludeEnv

# 全新空库（收件人从零开始）
.\scripts\make_portable.ps1 -NoData
```

产物：`dist\AIFrontierRadar\`（约 600 MB，含嵌入式 Python + 全部依赖）。

构建脚本自带两道冒烟测试，必须都通过：
- `bundled imports OK` —— 嵌入解释器能 import feedparser 等。
- `app import OK` —— 从输出根目录能 `import app.main`。

> 已知坑：启动测试会留下占用 SQLite 的子进程 → 下次构建删目录失败。重新构建前先按端口
> 杀进程：`Get-NetTCPConnection -LocalPort <port> | %{ Stop-Process -Id $_.OwningProcess -Force }`。

---

## B. 启动冒烟（本机验证包可用）

```powershell
cd dist\AIFrontierRadar
copy .env.example .env      # 收件人需先填 MINIMAX_API_KEY
.\python\python.exe -m uvicorn app.main:app --port 8766
```

确认：
- [ ] `GET /` 返回 200
- [ ] `GET /radar/today` 返回 200
- [ ] 控制台出现 `Application startup complete.`

验证完务必结束该进程，避免占用 DB。

---

## C. 配置 `.env`（真实运行前）

| 配置 | 必填? | 说明 |
|------|------|------|
| `MINIMAX_API_KEY` | 是 | 摘要 / 日报 LLM |
| `DAILY_REPORT_ENABLED=true` | 按需 | 启用每日核心报告 |
| `LLM_SUMMARY_ENABLED=true` | 按需 | 启用正文中文摘要 |
| `RADAR_DAILY_ANCHOR_HOUR` | 否 | 每日锚点（0–23，默认 8）。改晚上=收"今天"的报告；须与定时时间一致 |
| `RADAR_FETCH_INTERVAL_OVERRIDE_HOURS` | 否 | 强制所有源的抓取间隔（覆盖每源 `fetch_interval_hours`）。配高频抓取任务时设为 3 |
| `RADAR_DEFAULT_FETCH_INTERVAL_HOURS` | 否 | 仅作未设 `fetch_interval_hours` 的源的兜底，默认 24h |
| `RADAR_PUBLIC_BASE_URL` | 否 | 对外域名；邮件/飞书/二维码的可点链接依赖它（本机留空） |
| `RADAR_CYCLE_STALE_HOURS` | 否 | 定时器停跑告警阈值，默认 36h |
| `HEALTH_ALERT_WEBHOOK_URL` | 否 | 健康告警通用 webhook（留空=关闭，仅异常时发） |
| `HEALTH_REPORT_ENABLED` + `HEALTH_REPORT_MODE` | 否 | 每次运行健康回执（邮件/飞书心跳，默认 always） |
| `EMAIL_SHARE_ENABLED` + `EMAIL_*` | 否 | 日报邮件分享（见 E） |
| `FEISHU_SHARE_ENABLED` + `FEISHU_WEBHOOK_URL` | 否 | 日报推送到飞书群机器人 |

> 切勿把真实 `.env` 提交到 git 或外发；分发包默认只带 `.env.example`。
> 完整可配置项与默认值见 [`.env.example`](../.env.example)。

---

## D. 每日自动化（定时任务）

```powershell
# 安装 Windows 定时任务（每天 08:00 调用 run_daily_cycle.py --apply）
.\scripts\install_windows_daily_task.ps1

# 先手动试跑一次：先 dry-run（无副作用），再 --apply
.\scripts\run_daily_cycle.py            # dry-run
.\scripts\run_daily_cycle.py --apply    # 真正执行
```

周期顺序：**结算上一完整周期(含邮件) → 释放卡死源 → 探测新增 → 摘要 → 报告 → 健康检查**。

确认：
- [ ] `coverage:` 行显示 `complete`（或能解释的 partial/no_content）
- [ ] 有异常时打印 `⚠` 健康告警
- [ ] 今日雷达「调度状态」显示「上次自动运行 N 小时前」，停跑超阈值会告警

---

## E. 邮件分享日报（自用，可选）

**触发点：定时周期"结算正式日报"后自动发送**（不是探测后，也不由网页按钮触发）。
只发**首次结算**的那天，重跑不重复发。

```bash
# .env 配置（QQ/163 等，密码用授权码而非登录密码）
EMAIL_SHARE_ENABLED=true
EMAIL_SMTP_HOST=smtp.qq.com
EMAIL_SMTP_SSL=true
EMAIL_SMTP_USER=you@qq.com
EMAIL_SMTP_PASSWORD=授权码
EMAIL_TO=you@qq.com,friend@example.com

# 手动测试（忽略开关；--dry-run 只构造不发）
python scripts/send_daily_report_email.py --dry-run
python scripts/send_daily_report_email.py --date 2026-06-21
```

确认：
- [ ] `--dry-run` 打印主题/收件人正确
- [ ] 真发后收件箱收到邮件，标题+概述+编号要点(带原文链接)显示正常

---

## F. 回归测试（改动后）

```bash
python -m compileall app scripts
python scripts/quick_test.py                       # 全绿
python scripts/acceptance_first_usable_loop.py      # 293 passed, 0 failed
```

> 注：acceptance 的 "Today radar page content" 两条依赖当日窗口有条目，早晨尚无新增时可能
> 暂时失败，属环境性，非回归。

---

## 已知限制
- **RSS 只暴露近期条目**：长时间(>1 天)不运行，间隔期内已滚出 feed 的文章无法补回。
  靠"按时跑 + 定时器停跑告警"规避。
- **无 Web 进程内常驻定时器**：每日任务必须由外部 Windows Task Scheduler / cron 触发。
