# 环境变量配置说明

> 本文档帮助你正确配置 AI Frontier Radar 运行环境。

---

## 1. 快速开始

### 步骤 1：复制环境配置文件

```bash
cp .env.example .env
```

**重要**：`.env` 包含你的真实 API Key，永远不要将其提交到版本控制。

### 步骤 2：填写必要的 API Key

打开 `.env`，将 `MINIMAX_API_KEY=replace-me` 替换为你的真实 MiniMax API Key。

### 步骤 3：验证配置

```bash
python scripts/check_env_config.py
```

---

## 2. 最小可用配置

以下配置组合可以让今日雷达在本地正常运行（不调用 LLM 生成摘要 / 报告）：

```env
APP_ENV=development
DATABASE_URL=sqlite:///./data/ai_frontier_radar.db
LLM_PROFILE=minimax_m27_highspeed_anthropic
MINIMAX_API_KEY=你的真实_key
ONE_LINER_ENABLED=true
ONE_LINER_MAX_PER_RUN=20
ONE_LINER_MAX_PER_DAY=50
```

---

## 3. LLM Profile 与 API Key

### 3.1 LLM Profile

`LLM_PROFILE` 指定使用哪个 LLM 配置。配置文件位于：

```
config/llm_profiles.yaml
config/llm_profiles.example.yaml
```

从示例复制配置文件：

```bash
cp config/llm_profiles.example.yaml config/llm_profiles.yaml
```

当前内置 profile：

| Profile Name | Provider | 说明 |
|-------------|----------|------|
| `minimax_m27_highspeed_anthropic` | MiniMax | 默认，中等速度 |
| `openai_compatible` | OpenAI-compatible | 需要配置 LLM_BASE_URL |

### 3.2 API Key 配置

**MiniMax**（用于 minimax_* profiles）：

```env
LLM_PROFILE=minimax_m27_highspeed_anthropic
MINIMAX_API_KEY=你的_minimax_key
```

**OpenAI-compatible**（用于 openai_compatible profile）：

```env
LLM_PROFILE=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=你的_openai_key
LLM_MODEL=gpt-4o-mini
```

---

## 4. 当前页中文摘要配置

生成 SourceItem 的一句话中文概述（one-liner）和轻量中文摘要。

```env
# 是否启用中文摘要生成
ONE_LINER_ENABLED=true

# 使用哪个 LLM profile 生成
ONE_LINER_PROVIDER=llm_profile

# 单次运行最多生成几条（建议 20，与代码默认值一致）
ONE_LINER_MAX_PER_RUN=20

# 每天最多生成几条（配额保护）
ONE_LINER_MAX_PER_DAY=50

# 单次输入最大字符数
ONE_LINER_MAX_INPUT_CHARS=1200
```

**安全说明**：即使 `ONE_LINER_ENABLED=true`，系统也受 `ONE_LINER_MAX_PER_RUN` 和每日配额保护，不会无限调用 LLM。

---

## 5. 今日雷达主链路配置

控制今日雷达时间窗口、候选数量、推荐洞察批次等核心数字。

```env
# ── 时间窗口与数量上限 ──────────────────────────────────────────────
# 滚动时间窗口（小时），默认 24 小时
RADAR_DAILY_WINDOW_HOURS=24

# 今日雷达候选池最大条目数
RADAR_DAILY_ITEM_LIMIT=50

# 今日新增简报最大展示条目数
RADAR_DAILY_BRIEFING_LIMIT=50

# 「最新发现」固定展示条数
RADAR_TODAY_FOCUS_SIZE=5

# 今日核心报告「已就绪」所需最少可读条目数
RADAR_DAILY_REPORT_READY_THRESHOLD=5

# ── 推荐洞察批次 ────────────────────────────────────────────────────
# 推荐深入分析候选数量上限
RADAR_RECOMMENDED_LIMIT=10

# 单个来源最多入选候选数
RADAR_RECOMMENDED_PER_SOURCE_LIMIT=3

# 扫描构建候选池的最大条目数
RADAR_RECOMMENDED_MAX_SCAN=300

# 单次批量生成洞察卡的最大条目数
RADAR_RECOMMENDED_INSIGHT_LIMIT=5

# ── 摘要生成批次 ────────────────────────────────────────────────────
# 单次批量生成中文摘要的最大条目数
RADAR_SUMMARY_BATCH_LIMIT=50
```

**默认值**：所有数字均有安全默认值，环境变量仅用于覆盖。非法值（负数、超范围、非数字）会自动回退到默认值。

---

## 6. HTML 正文摘要配置

基于已保存的 HTML 快照生成完整中文摘要。**默认关闭**。

```env
# 是否启用正文摘要生成（建议确认抓取和成本后再开启）
LLM_SUMMARY_ENABLED=false

# 使用哪个 LLM profile 生成正文摘要
LLM_PROVIDER=openai_compatible

# LLM 调用超时时间（秒）
LLM_TIMEOUT_SECONDS=30

# 单次输入最大字符数
LLM_MAX_INPUT_CHARS=12000

# 摘要最大字符数
LLM_MAX_SUMMARY_CHARS=500
```

**为什么默认关闭？** 正文摘要会基于完整 HTML 内容调用 LLM，成本比 one-liner 更高。建议：

1. 先用今日雷达的"更新今日新增"确认来源抓取正常
2. 用"获取 HTML 正文"确认正文抓取正常
3. 确认每日成本可接受后再开启 `LLM_SUMMARY_ENABLED=true`

---

## 7. 今日核心报告配置

LLM 生成的中文核心报告，汇总当日重点内容。**默认关闭**。

```env
# 是否启用 LLM 生成今日核心报告
DAILY_REPORT_ENABLED=false

# 每次报告最多包含几条今日内容
DAILY_REPORT_MAX_ITEMS=50
```

**为什么默认关闭？** 今日核心报告基于当日所有中文摘要内容调用 LLM，属于高成本操作。

建议：
- 首次使用前先关闭
- 确认覆盖率和成本后开启
- 开启后观察每日消耗

---

## 8. 播报 / TTS 配置

每日播报使用小米 MiMo V2.5 TTS 将核心报告或可读简报转换为 WAV 音频。默认关闭，只有显式启用且配置 API Key 后才会调用外部接口。

```env
DAILY_BROADCAST_TTS_ENABLED=false
MIMO_API_KEY=
MIMO_TTS_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
MIMO_TTS_MODEL=mimo-v2.5-tts
MIMO_TTS_VOICE=冰糖
MIMO_TTS_FORMAT=wav
MIMO_TTS_STYLE=使用清晰、专业、自然的中文新闻播报语气，语速适中，重点明确。
MIMO_TTS_TIMEOUT_SECONDS=180
MIMO_TTS_MAX_TEXT_CHARS=12000
MIMO_TTS_CHUNK_CHARS=3000
DAILY_BROADCAST_AUDIO_DIR=runtime/daily_audio
DAILY_BROADCAST_AUDIO_RETENTION_DAYS=30
DAILY_BROADCAST_AUDIO_MAX_FILES=100
DAILY_BROADCAST_AUDIO_LOCK_MINUTES=30
```

当前使用后台分段 WAV 生成。页面可查看排队、分段进度、完成和失败状态；相同文稿、音色与风格会复用已有结果。音频保存在运行目录，通过受限路由提供播放和下载，不会公开整个 `runtime` 目录。

- `MIMO_TTS_CHUNK_CHARS`：单个 TTS 请求的建议文本长度，长文按自然段和句子拆分。
- `DAILY_BROADCAST_AUDIO_RETENTION_DAYS`：历史音频保留天数。
- `DAILY_BROADCAST_AUDIO_MAX_FILES`：最多保留的语音任务数。
- `DAILY_BROADCAST_AUDIO_LOCK_MINUTES`：跨进程任务锁的过期时间。

Token Plan 中国集群使用 `tp-` 开头的专属 API Key。Token Plan Key 与按量计费的 `sk-` Key 不能混用；其他区域应以订阅管理页面展示的 Base URL 为准。

---

## 9. 安全默认值

下表汇总了各高成本操作的默认状态：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ONE_LINER_ENABLED` | `true` | 低成本的一句话说，，配额保护 |
| `LLM_SUMMARY_ENABLED` | `false` | 高成本正文摘要，默认关闭 |
| `DAILY_REPORT_ENABLED` | `false` | 高成本核心报告，默认关闭 |
| `DAILY_BROADCAST_TTS_ENABLED` | `false` | MiMo TTS 已接入，默认关闭以避免意外调用 |

---

## 10. 常见问题

### Q: 复制 .env.example 后运行报错怎么办？

```bash
# 检查配置是否完整
python scripts/check_env_config.py
```

### Q: 如何确认我的 API Key 是否正确？

```bash
python scripts/check_env_config.py
```

如果输出 `[FAIL] MINIMAX_API_KEY is replace-me`，说明你还没有替换真实的 Key。

### Q: 可以同时使用多个 LLM provider 吗？

可以。`LLM_PROFILE` 指定主 profile，`ONE_LINER_PROVIDER` 和 `LLM_PROVIDER` 可以分别指定不同的 profile。

### Q: `ONE_LINER_MAX_PER_RUN=10` 和代码里默认 20 不一致？

以 `.env.example` 中的 `ONE_LINER_MAX_PER_RUN=20` 为准，代码默认值已对齐。

### Q: .env 文件可以提交到 Git 吗？

**不可以**。`.env` 包含你的真实 API Key。请确保 `.env` 在 `.gitignore` 中。
