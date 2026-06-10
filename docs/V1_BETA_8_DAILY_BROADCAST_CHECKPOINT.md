# V1.0-beta.8 Final Checkpoint

> 版本：V1.0-beta.8
> 分支：`feature/v1-beta-8-daily-broadcast`
> main 基准 commit：`8b11a45`（v1.0-beta.7 merge）
> feature 最新有效 commit：待提交
> checkpoint 创建日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.8 实现**播报文案（DailyReportBroadcast）**，在 DailyReportCard 基础上生成适合朗读的中文播报稿，并预留 TTS 音频生成入口。

核心目标：
1. 基于 DailyReportCard 数据，生成口播友好的中文文案
2. 提供页面查看和复制
3. 预留 TTS 音频生成接口（默认关闭）
4. 不调用 LLM，不调用真实 TTS API

---

## 二、已完成能力

### 2.1 DailyBroadcastScript dataclass

```python
@dataclass(frozen=True)
class DailyBroadcastScript:
    date_label: str
    title: str           # "今日 AI 前沿播报，日期：YYYY-MM-DD。"
    opening: str         # 开场白（0条时：更自然的表述）
    overview: str         # 概览（今日最值得关注 X 条 / 暂无新增内容）
    primary_sections: list[str]  # 每条逐字播报段
    secondary_section: str | None  # 其他值得扫一眼（简短列举）
    closing: str         # 结尾建议
    full_text: str       # 拼接后的完整可朗读文本
```

### 2.2 播报文案生成规则

- **不调用 LLM**，基于 DailyReportCard 规则生成
- **不直接读 source_key**，用 `source_label` 代替
- **不直接读 SourceItem**，通过 DailyReportCard 间接获取
- **不直接读 raw 字段名**，通过 `zh_one_liner` 等属性获取
- **优先读中文概述**，无中文概述时显示"这条内容尚未生成中文概述，建议打开原文查看"
- **次要内容只做简短列举**，不逐条展开

### 2.3 音频生成入口

```python
@dataclass(frozen=True)
class DailyBroadcastAudioResult:
    status: str   # disabled | generated | failed
    message: str
    audio_url: str | None = None
    audio_path: str | None = None
```

- `DAILY_BROADCAST_TTS_ENABLED` 环境变量 gate，默认 `"true"` 以外返回 `status="disabled"`
- 接口已预留，后续可接入 MiniMax / OpenAI / 本地 TTS
- **当前版本不调用任何外部 TTS API**

### 2.4 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/radar/daily-report/broadcast` | 展示播报文案页面 |
| POST | `/radar/daily-report/broadcast/audio` | 生成 TTS 音频（默认 disabled） |

### 2.5 页面设计

`radar_daily_broadcast.html`：
- 标题：今日 AI 前沿播报 + 日期
- 音频状态 banner（初始显示"音频播报入口已预留，当前未启用真实 TTS"）
- 播报文案展示区（`<textarea readonly>`）
- 工具栏：复制文案按钮 + 生成音频按钮 + "当前版本仅预留音频入口，真实 TTS 尚未启用"说明
- 返回今日报告 / 返回今日雷达

### 2.6 TTS disabled 文案（产品化）

> 音频播报入口已预留，当前未启用真实 TTS。配置 TTS 后，可将这份播报文案生成音频。

---

## 三、当前不做

| 能力 | 原因 |
|------|------|
| 真实 TTS API 调用 | 下一版本目标 |
| 音频文件生成和保存 | 依赖 TTS API |
| 多 Provider 支持 | 接口预留，单一 Provider 逐步接入 |
| 语音克隆 | 超出本轮范围 |
| LLM 播报稿润色 | 当前纯规则，后续可探索 |
| DB schema 变更 | 禁止 |

---

## 四、已知限制

1. 播报文案是纯规则生成，无 LLM 润色，可能不够自然
2. 音频入口尚未真实生成，配置 TTS 后方可使用
3. 需要后续接入 MiniMax / OpenAI / 本地 TTS 才能产生真实音频
4. 次要内容只做简短列举，不逐条播报

---

## 五、下一步

1. **接入 MiniMax TTS**：设置 `DAILY_BROADCAST_TTS_ENABLED=true` + `MINIMAX_API_KEY`，实现真实音频生成
2. **真实正文获取**：获取更多中文内容，改善播报文案质量
3. **播报稿 LLM 润色**：可选，接入 LLM 提升文案自然度

---

## 六、文件清单

| 文件 | 操作 |
|------|------|
| `app/application/radar/daily_broadcast.py` | 新增 |
| `app/routes/radar.py` | 修改 |
| `app/templates/radar_daily_broadcast.html` | 新增 |
| `app/static/style.css` | 修改 |
| `app/templates/radar_daily_report.html` | 修改 |
| `scripts/quick_test.py` | 修改 |
| `scripts/acceptance_first_usable_loop.py` | 修改 |
| `docs/V1_BETA_8_DAILY_BROADCAST_PLAN.md` | 新增 |
| `docs/V1_BETA_8_DAILY_BROADCAST_CHECKPOINT.md` | 新增 |
| `docs/NEXT_EXECUTION_PLAN.md` | 修改 |
| `README.md` | 修改 |
