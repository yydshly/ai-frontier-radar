# V1.0-beta.8 Plan — DailyReportBroadcast

> 版本：V1.0-beta.8
> 分支：`feature/v1-beta-8-daily-broadcast`
> main 基准 commit：`8b11a45`（v1.0-beta.7 merge）
> 规划日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.8 实现**播报文案（DailyReportBroadcast）**，在 DailyReportCard 基础上生成适合朗读的中文播报稿，并预留 TTS 音频生成入口。

核心目标：
1. 基于 DailyReportCard 数据，生成口播友好的中文文案
2. 提供页面查看和复制
3. 预留 TTS 音频生成接口（默认关闭）
4. 不调用 LLM，不调用真实 TTS API

---

## 二、DailyReportCard 到 DailyBroadcastScript 的关系

```
DailyReportCard (已有点)
    ├── date_label
    ├── overview (total_items, covered_sources, with_zh_one_liner, with_insight_card)
    ├── primary_items[] (item_id, source_label, zh_one_liner, title, url, related_directions, insight_card_id)
    └── secondary_items[] (item_id, source_label, title, url)

           ↓ build_daily_broadcast_script()

DailyBroadcastScript
    ├── date_label
    ├── title           "今日 AI 前沿播报，日期：YYYY-MM-DD。"
    ├── opening         "今天系统共发现 N 条 AI 前沿内容，覆盖 X 个来源，其中 Y 条已有中文概述，Z 条已有洞察卡。"
    ├── overview        "今天最值得关注的内容有 N 条。" / "今天暂无新增内容。"
    ├── primary_sections[]  每条: "第X条，来自 SOURCE。中文概述。涉及方向。可以打开原文或查看洞察卡。"
    ├── secondary_section  "此外，今天还有其他值得扫一眼的内容，包括……。" / None
    ├── closing          今日建议：优先查看……；如果时间有限……；已有洞察卡的条目……
    └── full_text        各字段拼接成的完整可朗读文本
```

**设计原则**：
- 不直接读取 `source_key`（用 `source_label`）
- 不直接读取 `SourceItem`
- 不直接读取 `raw` 字段名
- 优先读中文概述，无中文概述时显示"这条内容尚未生成中文概述，建议打开原文查看"
- 次要内容只做简短列举，不逐条展开

---

## 三、音频生成入口

### 3.1 TTS gate

```python
# DAILY_BROADCAST_TTS_ENABLED=true 时才启用
enabled = os.getenv("DAILY_BROADCAST_TTS_ENABLED", "").strip().lower() == "true"
```

### 3.2 接口预留

```python
@dataclass(frozen=True)
class DailyBroadcastAudioResult:
    status: str   # disabled | generated | failed
    message: str
    audio_url: str | None = None
    audio_path: str | None = None

def generate_daily_broadcast_audio(
    script: DailyBroadcastScript
) -> DailyBroadcastAudioResult:
    # 未来接 MiniMax / OpenAI / 本地 TTS
```

### 3.3 当前实现

默认返回 `status="disabled"` + "音频播报尚未启用，请配置 TTS 后再生成。"，不访问外部 API。

---

## 四、路由设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/radar/daily-report/broadcast` | 展示播报文案页面 |
| POST | `/radar/daily-report/broadcast/audio` | 生成 TTS 音频（默认 disabled） |

---

## 五、页面设计

页面 `radar_daily_broadcast.html`：
- 标题：今日 AI 前沿播报 + 日期
- 播报文案展示区（`<textarea readonly>`）
- 工具栏：复制文案按钮 + 生成音频按钮
- 音频状态 banner（disabled / generated / failed）
- 返回今日报告 / 返回今日雷达

---

## 六、后续如何接入真实 TTS

V1.0-beta.8 接口已预留，后续可在 `generate_daily_broadcast_audio()` 中接入：

1. **MiniMax TTS**：环境变量 `MINIMAX_API_KEY`，调用 MiniMax TTS API
2. **OpenAI TTS**：环境变量 `OPENAI_API_KEY`，调用 OpenAI TTS API
3. **本地 TTS**：调用本地部署的 TTS 服务（如 Coqui、piper）

接入步骤：
1. 设置 `DAILY_BROADCAST_TTS_ENABLED=true`
2. 在 `generate_daily_broadcast_audio()` 中实现对应 provider
3. 将生成的音频文件保存到 `data/audio/` 目录
4. 在 `DailyBroadcastAudioResult` 中返回 `audio_url` 或 `audio_path`

---

## 七、禁止事项

- 不调用真实 TTS API
- 不调用 LLM
- 不改 DB schema
- 不生成真实音频文件
- 不做语音克隆
- 不做多 Provider（接口预留，单一 Provider 接入）
- 不做视频
- 不做真实正文抓取

---

## 八、文件清单

| 文件 | 操作 |
|------|------|
| `app/application/radar/daily_broadcast.py` | 新增 |
| `app/routes/radar.py` | 修改：新增 2 个路由 |
| `app/templates/radar_daily_broadcast.html` | 新增 |
| `app/static/style.css` | 修改：新增 broadcast 样式 |
| `app/templates/radar_daily_report.html` | 修改：增加播报入口链接 |
| `scripts/quick_test.py` | 修改：新增 section [52] |
| `scripts/acceptance_first_usable_loop.py` | 修改：新增 section [26] |
| `docs/V1_BETA_8_DAILY_BROADCAST_PLAN.md` | 新增 |
| `docs/NEXT_EXECUTION_PLAN.md` | 修改 |
| `README.md` | 修改 |
