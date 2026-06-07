# AI Frontier Radar

> AI 前沿知识挖掘工具 — 将英文 AI 前沿文章编译为结构化 InsightCard

## 项目定位

V0.1 是一个**技术探针 MVP**，验证最小闭环：输入 URL → 获取正文 → LLM 生成中文 InsightCard → 保存到 SQLite → Web 查看。

## V0.1 范围

### ✅ 做
- 单 URL 提交
- HTML / PDF 正文提取
- LLM 生成中文 InsightCard（摘要、关键事实、技术洞察、产品机会、风险、相关性判断）
- SQLite 持久化
- 简单 Web 页面（列表 + 详情）
- 去重（基于 content hash）
- 失败链路可见（failed card 保存错误原因）

### ❌ 不做
- 登录注册 / 多用户
- 复杂前端框架（React/Vue/Next.js）
- 全网爬虫 / RSS 聚合
- 推荐系统 / 知识图谱
- 批量导入 / 后台任务
- 向量数据库 / 复杂 Multi-Agent

## 技术栈

```
Backend: FastAPI
Storage: SQLite
ORM: SQLAlchemy
HTML 抓取: httpx
HTML 正文提取: trafilatura（fallback: BeautifulSoup/readability）
PDF 提取: pypdf
模板页面: Jinja2
配置: python-dotenv + YAML profiles
LLM: MiniMax Anthropic Messages API（默认）+ OpenAI-compatible（fallback）
```

## 目录结构

```
ai-frontier-radar/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── config/
│   └── llm_profiles.example.yaml
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── logging_config.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── config_loader.py
│   │   ├── factory.py
│   │   ├── json_utils.py
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── minimax_anthropic.py
│   │       └── openai_compatible.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── insight_card.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── cleaner.py
│   │   ├── deduper.py
│   │   ├── insight_compiler.py
│   │   └── relevance.py
│   ├── templates/
│   │   ├── index.html
│   │   ├── cards.html
│   │   └── card_detail.html
│   └── static/
│       └── style.css
└── scripts/
    └── smoke_test.py
```

## LLM 配置说明

### 为什么默认使用 MiniMax

MiniMax 提供高性价比的 Anthropic Messages API 兼容接口，适合快速验证 InsightCard 编译链路。

### 为什么默认模型不锁死 MiniMax-M3

MVP 阶段优先使用 **MiniMax-M2.7-highspeed** 作为默认模型，原因：
- 推理速度快，适合快速迭代验证
- 成本相对较低
- M3 作为高质量 / 长上下文 / 多模态备用 profile

### Anthropic Messages API vs OpenAI Chat Completions

两种协议参数差异：

| 参数 | Anthropic Messages API | OpenAI Chat Completions |
|------|------------------------|------------------------|
| Token 限制字段 | `max_tokens` | `max_completion_tokens` |
| 系统提示 | `system` | `messages[0].role=system` |
| 用户消息 | `messages` array | `messages` array |
| 认证方式 | `x-api-key` header | `Authorization: Bearer` |

本项目通过 `config/llm_profiles.yaml` 的 `protocol` 字段自动选择正确参数，业务代码无感知。

### 如何配置 LLM Profile

```bash
# 1. 复制配置文件
cp .env.example .env
cp config/llm_profiles.example.yaml config/llm_profiles.yaml

# 2. 编辑 .env，填入 API Key
```

### 默认配置（M2.7-highspeed）

```env
LLM_PROFILE=minimax_m27_highspeed_anthropic
MINIMAX_API_KEY=你的 MiniMax Key
```

### 切换到 MiniMax-M3

```env
LLM_PROFILE=minimax_m3_anthropic
MINIMAX_API_KEY=你的 MiniMax Key
```

### 切换到 OpenAI-compatible

```env
LLM_PROFILE=openai_compatible_default
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=你的 OpenAI Key
LLM_MODEL=gpt-4o-mini
```

### API Key 为什么只放环境变量

- `config/llm_profiles.yaml` 已加入 `.gitignore`，不会提交到版本库
- API Key 通过 `api_key_env` 字段指向环境变量名，配置文件中不出现明文

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_ENV` | 运行环境 | `development` |
| `DATABASE_URL` | SQLite 数据库路径 | `sqlite:///./data/ai_frontier_radar.db` |
| `LLM_PROFILE` | 当前使用的 LLM profile 名称 | `minimax_m27_highspeed_anthropic` |
| `MINIMAX_API_KEY` | MiniMax API Key | `replace-me` |
| `LLM_BASE_URL` | OpenAI-compatible 端点 | `https://api.openai.com/v1` |
| `LLM_API_KEY` | OpenAI-compatible API Key | `replace-me` |
| `LLM_MODEL` | OpenAI-compatible 模型名 | `gpt-4o-mini` |
| `HTTP_TIMEOUT_SECONDS` | HTTP 请求超时 | `20` |
| `FETCH_RETRY_COUNT` | 抓取重试次数 | `2` |
| `MAX_SOURCE_CHARS` | 原文最大字符数 | `60000` |
| `MAX_LLM_INPUT_CHARS` | LLM 输入最大字符数 | `30000` |

## 本地运行

```bash
# 克隆并进入目录
git clone https://github.com/yydshly/ai-frontier-radar.git
cd ai-frontier-radar

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境（Linux/macOS）
source .venv/bin/activate

# 激活虚拟环境（Windows Git Bash）
source .venv/Scripts/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
cp config/llm_profiles.example.yaml config/llm_profiles.yaml
# 编辑 .env 填入真实 API Key

# 启动服务
uvicorn app.main:app --reload

# 访问 http://localhost:8000
```

## 使用流程

### 1. 提交 URL
访问首页 `http://localhost:8000/`，在输入框填入英文 AI 前沿文章 URL，点击提交。

### 2. 等待处理
系统会抓取正文、清洗内容、调用 LLM 生成 InsightCard。

### 3. 查看结果
访问 `http://localhost:8000/cards` 查看所有卡片列表，点击详情查看完整内容。

### 4. 失败排查
如果处理失败，卡片状态为 `failed`，可以在详情页查看错误原因。

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页（URL 输入框） |
| POST | `/compile` | 提交 URL 进行编译 |
| GET | `/cards` | InsightCard 列表 |
| GET | `/cards/{id}` | 卡片详情 |
| GET | `/health` | 健康检查 |
| GET | `/static/style.css` | 样式文件 |

## 异常场景

- **URL 不可达**：卡片状态标记为 `failed`，保存错误信息到详情页
- **正文提取失败**：同上
- **LLM API Key 缺失**：同上
- **LLM 调用失败**：同上
- **JSON 解析失败**：重试一次，仍失败则标记 `failed`
- **重复 URL + 相同内容 hash**：返回已有卡片，不创建新的
- **内容过大**：截断到 `MAX_SOURCE_CHARS`

## 后续路线（V0.2+）

- [ ] RSS 订阅源支持
- [ ] 批量 URL 导入
- [ ] 后台异步任务
- [ ] 全文搜索
- [ ] 标签系统
- [ ] 反馈标记
- [ ] 多用户 / 权限
- [ ] 浏览器插件
- [ ] 公众号发布集成

## License

MIT
