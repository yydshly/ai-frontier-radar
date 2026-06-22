# Linux 部署指南

应用核心(抓取 → 摘要 → 日报 → 邮件/飞书 → 健康回执)是纯 Python,**Linux 上零代码改动即可运行**。Windows 那套便携包 / `.ps1` / 任务计划换成下面的等价物即可。

两条路线:**A. Docker(推荐)** 或 **B. 裸机 venv + systemd**。

---

## 系统依赖

| 依赖 | 用途 | 是否必装 |
|------|------|---------|
| `ffmpeg` | 音频/视频合成 | 用语音/视频则必装 |
| `fonts-noto-cjk` | 报告图片/视频的中文字体 | 用视频则必装 |
| `nodejs` `npm` | 仅 Remotion 视频路线 | 可选 |

> 找不到中文字体时,可用 `CONTENT_VIDEO_FONT_PATH` / `CONTENT_VIDEO_BOLD_FONT_PATH` 指定字体文件。

---

## 路线 A：Docker(推荐)

`ffmpeg` 与中文字体已打进镜像。

```bash
cp .env.example .env        # 填 MINIMAX_API_KEY 等;链接类功能填 RADAR_PUBLIC_BASE_URL

# 启动 Web 服务(data/ runtime/ logs/ 挂载到宿主机持久化)
docker compose up -d --build

# 验证
curl -s http://127.0.0.1:8765/ -o /dev/null -w "%{http_code}\n"   # 期望 200

# 手动跑一次每日周期
docker compose run --rm daily-cycle
```

**定时执行**(宿主机 cron,时间与 `RADAR_DAILY_ANCHOR_HOUR` 对齐):

```cron
# 锚点 22:00 → 每晚 22:05 结算并推送
5 22 * * *  cd /opt/ai-frontier-radar && /usr/bin/docker compose run --rm daily-cycle >> logs/cron.log 2>&1
```

---

## 路线 B：裸机 venv + systemd

```bash
sudo apt install -y ffmpeg fonts-noto-cjk python3-venv
cd /opt/ai-frontier-radar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # 编辑填入配置
.venv/bin/python -c "from app.db import init_db; init_db()"
```

**Web 服务**(systemd):

```bash
sudo cp deploy/aifrontier-radar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aifrontier-radar
```

**每日周期** —— 二选一:

- systemd timer:
  ```bash
  sudo cp deploy/aifrontier-radar-daily.{service,timer} /etc/systemd/system/
  # 编辑 .timer 的 OnCalendar 与你的锚点一致
  sudo systemctl daemon-reload
  sudo systemctl enable --now aifrontier-radar-daily.timer
  ```
- 或 cron:
  ```cron
  5 22 * * *  cd /opt/ai-frontier-radar && scripts/run_daily_cycle_once.sh --apply >> logs/cron.log 2>&1
  ```

**高频抓取**(可选但推荐,保证日报及时完整) —— 与每日结算并存:

```bash
sudo cp deploy/aifrontier-radar-fetch.{service,timer} /etc/systemd/system/
# 编辑 .timer 的 OnCalendar(默认每 3h)与 .env 的 RADAR_DEFAULT_FETCH_INTERVAL_HOURS 对齐
sudo systemctl daemon-reload
sudo systemctl enable --now aifrontier-radar-fetch.timer
```
或 cron:`0 */3 * * *  cd /opt/ai-frontier-radar && scripts/run_fetch_once.sh >> logs/fetch.log 2>&1`

> ⚠️ 记得在 `.env` 设 `RADAR_FETCH_INTERVAL_OVERRIDE_HOURS=3`(与 timer 间隔一致)。每个源在 `sources.yaml` 钉死了 `fetch_interval_hours: 24`,只调 `RADAR_DEFAULT_FETCH_INTERVAL_HOURS` 不生效——必须用 OVERRIDE 才能对所有源强制高频。原理见 README「信息及时性」。

也可手动起服务:`scripts/start_local.sh`(或 `HOST=0.0.0.0 PORT=8000 scripts/start_local.sh`)。

> 首次使用先给脚本可执行权限:`chmod +x scripts/*.sh`。

---

## 运行时间(锚点)

日报覆盖 `[锚点, 下个锚点)` 整周期,定时器在锚点时刻结算推送。把 `RADAR_DAILY_ANCHOR_HOUR`
与定时(cron/timer)**一起**改到晚上,即可"今晚收到今天的报告"。详见 README「每日周期可靠性与健康监控」。

---

## 与 Windows 的差异速查

| Windows | Linux 等价 |
|---------|-----------|
| `make_portable.ps1` 便携包 | Docker 镜像 / venv |
| `start_local.ps1` | `scripts/start_local.sh` 或 systemd service |
| `run_daily_cycle_once.ps1` | `scripts/run_daily_cycle_once.sh` |
| `install_windows_daily_task.ps1`(任务计划) | systemd timer 或 cron |
| 捆绑的 `bin/ffmpeg.exe` | 系统 `ffmpeg`(apt) |

业务代码、邮件/飞书/健康回执、数据库均无需改动。

---

## CI 验证

`.github/workflows/ci.yml` 的 `docker` job 会在每次 push/PR 时**真实构建镜像**并冒烟:
- `import app.main`(含 `init_db`)
- `load_cjk_font(40)` —— 验证中文字体在镜像里能解析(Linux 路径)
- `ffmpeg -version`
- 启动容器并 `curl http://127.0.0.1:8765/` 期望 **200**
- 容器内 `run_daily_cycle.py` dry-run

所以"在 Linux 上能否构建运行"由 CI 持续把关,不必每次手动验证。
