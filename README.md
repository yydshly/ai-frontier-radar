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
配置: python-dotenv + 环境变量
LLM: OpenAI-compatible Chat Completions API
```

## 目录结构

```
ai-frontier-radar/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── logging_config.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── cleaner.py
│   │   ├── deduper.py
│   │   ├── llm_client.py
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

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_ENV` | 运行环境 | `development` |
| `DATABASE_URL` | SQLite 数据库路径 | `sqlite:///./data/ai_frontier_radar.db` |
| `LLM_BASE_URL` | LLM API 端点 | `https://api.openai.com/v1` |
| `LLM_API_KEY` | API Key | `replace-me` |
| `LLM_MODEL` | 模型名称 | `gpt-4o-mini` |
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
# 编辑 .env 填入真实 LLM_API_KEY

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

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页（URL 输入框） |
| POST | `/compile` | 提交 URL 进行编译 |
| GET | `/cards` | InsightCard 列表 |
| GET | `/cards/{id}` | 卡片详情 |
| GET | `/health` | 健康检查 |

## 异常场景

- **URL 不可达**：卡片状态标记为 `failed`，保存错误信息
- **正文提取失败**：同上
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
