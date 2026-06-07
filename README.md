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

## 系统处理流程

URL 提交后，系统按以下步骤处理：

### 1. URL 抓取
使用 `httpx` 发送 HTTP GET 请求，根据 `Content-Type` header 判断是 HTML 还是 PDF。

### 2. 正文提取
- **HTML**：优先使用 `trafilatura` 提取正文；失败时 fallback 到 BeautifulSoup
- **PDF**：使用 `pypdf` 提取文本

### 3. 正文清洗
移除多余空白、导航残留、页脚噪音，截断超过 `MAX_SOURCE_CHARS`（60,000 字符）的内容。

### 4. 去重
对清洗后的正文计算 SHA256 hash。如果同一 URL + 相同 hash 的卡片已存在，直接返回已有卡片。

### 5. LLM 分析
调用当前 `LLM_PROFILE` 配置的模型，将英文正文编译为中文 InsightCard（摘要、关键事实、技术洞察、产品机会、风险、相关性判断）。

### 6. 保存
生成的 InsightCard 保存到 SQLite，可在 `/cards` 列表和 `/cards/{id}` 详情页查看。

### 失败卡片
任何步骤失败都会创建 `failed` 状态的 InsightCard，保存错误原因到详情页供排查。

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

## 常见问题

### Starlette / Jinja2 / TestClient 异常

如果 `smoke_test.py` 或 `check_card_page.py` 出现类似以下错误：

```
TypeError: unhashable type: 'dict'
```

优先检查依赖版本，这通常是 starlette 版本不兼容导致的。请执行以下步骤重建环境：

**Windows PowerShell：**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt --upgrade --force-reinstall
python scripts/check_dependencies.py
python scripts/smoke_test.py
```

**Linux / macOS / Git Bash：**

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt --upgrade --force-reinstall
python scripts/check_dependencies.py
python scripts/smoke_test.py
```

### 验证依赖版本

```bash
python scripts/check_dependencies.py
```

应输出：

```
[OK] fastapi=0.111.0
[OK] starlette=0.37.2
[OK] jinja2=3.1.4
[OK] httpx=0.27.0
[OK] dependency compatibility passed
```

> **注意**：不要直接修改业务代码来规避 Starlette / Jinja2 兼容性问题。

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

## 诊断脚本

项目提供一组离线诊断脚本，用于验证 LLM 配置和数据库编码：

### smoke_test.py — 基础冒烟测试

```bash
python scripts/smoke_test.py
```

验证：健康检查、页面加载、LLM 配置加载、SQLite 目录创建、API Key 缺失时的失败卡片。

### probe_minimax_anthropic.py — MiniMax API 连通性验证

```bash
python scripts/probe_minimax_anthropic.py
```

验证内容：
- `provider`、`protocol`、`model`、`base_url`、`endpoint`
- `auth_type`（当前 MiniMax 验证通过使用 `x-api-key`）
- `api_key_env` 环境变量是否配置
- 调用 MiniMax Anthropic Messages API，确认返回有效 JSON

**安全提示**：`probe_minimax_anthropic.py` 不会打印 API Key 内容，仅显示 `MINIMAX_API_KEY configured: yes/no`。

### check_card_encoding.py — 数据库文本编码检查

检查 SQLite 中卡片的文本字段是否存在乱码（mojibake）。

```bash
# 检查 smoke test 数据库（默认）
python scripts/check_card_encoding.py 11

# 指定数据库路径
python scripts/check_card_encoding.py 11 --db data/test_smoke.db
python scripts/check_card_encoding.py 11 --db data/ai_frontier_radar.db
```

- 默认读取 `.env` 中 `DATABASE_URL`；未设置时 fallback 到 `data/test_smoke.db`
- `--db` 参数覆盖默认数据库路径
- 不访问网络，不调用 LLM，不需要 API Key

### check_card_page.py — 卡片详情页 HTML 编码检查

使用 TestClient 抓取卡片详情页，验证 HTML 编码和中文内容。

```bash
# 检查 smoke test 数据库（默认）
python scripts/check_card_page.py 11

# 指定数据库路径
python scripts/check_card_page.py 11 --db data/test_smoke.db
python scripts/check_card_page.py 11 --db data/ai_frontier_radar.db
```

- `--db` 参数指定数据库路径
- 不访问网络，不调用 LLM，不需要 API Key

### 数据库说明

| 数据库 | 路径 | 用途 |
|--------|------|------|
| smoke test DB | `data/test_smoke.db` | 冒烟测试使用，由 `smoke_test.py` 创建 |
| 真实运行 DB | `data/ai_frontier_radar.db` | 实际运行数据，由 `uvicorn` 运行时创建 |

## V0.1 真实端到端验证记录

以下验证于 2026-06-07 完成：

### MiniMax Anthropic API

- **鉴权方式**：`x-api-key` header
- **接口**：`https://api.minimaxi.com/anthropic/v1/messages`
- **状态**：已验证可用

### HTML 测试

| 项目 | 值 |
|------|-----|
| 测试 URL | `https://arxiv.org/abs/2303.17760` |
| 结果 | completed |
| 卡片 ID | 11 |
| 相关性分数 | 88 |
| 正文提取 | trafilatura 失败，BeautifulSoup fallback 成功 |
| 提取字符数 | 4,627 |

### PDF 测试

| 项目 | 值 |
|------|-----|
| 测试 URL | `https://arxiv.org/pdf/2303.17760.pdf` |
| 结果 | completed |
| 卡片 ID | 14 |
| 相关性分数 | 85 |
| PDF 页数 | 77 |
| 提取字符数 | 206,443（截断到 60,000） |

### 去重测试

同一 URL + 同一 content_hash 提交两次，第二次返回已有卡片，未重复创建。

### 编码说明

SQLite 存储的 UTF-8 中文数据正常。Windows Git Bash 终端显示 `�` 是终端编码问题，不影响实际数据。

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
