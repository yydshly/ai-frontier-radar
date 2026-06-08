# AI Frontier Radar 架构总览

## 1. 项目定位

本项目不是普通 RSS 阅读器、不是机器翻译工具、不是资讯聚合站。

它的定位是：**全球 AI 前沿资料中文编译工作台**。

核心能力：
- 自动发现英文 AI 前沿来源的最新文章（RSS / HTML Index）
- 将英文文章编译为结构化中文 InsightCard
- 生成中英双语对照报告，帮助用户既保留学英文原文精髓，又能获得中文解说
- 用户判断后，将值得行动的卡片导出为 Markdown 任务草稿

目标用户：英语阅读能力有限、但关注全球 AI 前沿进展的个人用户。

## 2. 当前产品主链路

```
英文来源（RSS / HTML Index）
    ↓
SourceItem（被发现但未编译）
    ↓
编译（POST /source-items/{id}/compile）
    ↓
InsightCard（中文洞察卡）
    ↓
BilingualReport（中英双语报告）
    ↓
CardDecision（用户判断）
    ↓
Markdown Action Task（行动任务导出）
    ↓
首页工作台
```

## 3. 三层产品架构

### 发现层（Discovery）

负责从外部来源抓取文章 URL，不抓正文。

- **Source**（数据库模型）：一个信息来源的定义，包含 source_key、名称、类型（rss/html_index）、配置参数
- **SourceItem**（数据库模型）：从某个 Source 发现的一篇文章 URL，包含标题、作者、发布时间
- **FetchRun**（数据库模型）：一次探测执行的记录，包含成功数、失败数、错误信息
- **RSS 探测**：`scripts/probe_rss_sources.py` / `app/sources/rss_probe.py`
- **HTML Index 探测**：`scripts/probe_html_index_sources.py` / `app/sources/html_index_probe.py`

发现层不去重、不调用 LLM，只负责把文章 URL 写入 `source_items` 表。

### 理解层（Understanding）

负责把 SourceItem 变成用户能看懂的中文 InsightCard。

- **InsightCard**（数据库模型）：中文洞察卡，包含摘要、关键事实、技术洞察、产品机会、风险、行动建议、相关性评分
- **InsightCardBilingualReport**（数据库模型）：中英双语报告，包含英文核心摘要、原文主张、证据点、术语对照、中文解说、保真提示、解读边界
- **compile_url**（`app/services/insight_compiler.py`）：完整编译管线，fetch → extract → clean → dedup → LLM → save
- **SourceItem URL 质量分类**（`app/sources/quality.py`）：
  - `classify_source_item_url()`、`is_expected_content_url()`、`is_suspected_listing_url()`
- **InsightCard / BilingualReport 质量检查**（`app/services/insight_quality.py`）：
  - `inspect_insight_card_quality()`、`inspect_bilingual_report_quality()`

理解层是整个系统的核心价值：把英文原文变成结构化中文理解材料。

### 行动层（Action）

负责用户判断后的处理。

- **CardDecision**（数据库模型）：用户的判断结果，worth_attention / related_to_me / read_later / ignore / to_action
- **Markdown 导出**（`app/exports/markdown_task.py`）：将 InsightCard + CardDecision + BilingualReport 组合成 Markdown 文件
- **首页工作台**（`app/main.py` + 模板）：统计概览、下一步建议、快捷入口、最近待编译资料、最近洞察卡

## 4. 数据流说明

```
config/sources.example.yaml / config/sources.yaml
    ↓
sync_sources_config_to_db()  (app/sources/db_sync.py)
    ↓
probe_rss_sources.py / probe_html_index_sources.py
    ↓
SourceItem (status=discovered)
    ↓
POST /source-items/{id}/compile
    ↓
compile_url() (app/services/insight_compiler.py)
    ↓
InsightCard (status=completed/failed)
    ↓
InsightCardBilingualReport (可选)
    ↓
用户判断 CardDecision
    ↓
build_action_markdown() (app/exports/markdown_task.py)
    ↓
Markdown 文件
```

## 5. 页面流转

| 路径 | 说明 |
|------|------|
| `/` | 首页工作台：统计概览、下一步建议、快捷入口 |
| `/sources` | 信息来源列表 |
| `/source-items` | 发现条目列表（待编译资料收件箱） |
| `/source-items/{id}` | 发现条目详情页，含编译按钮 |
| `/cards` | InsightCard 列表（中文洞察卡工作台） |
| `/cards/{id}` | 卡片详情，含用户判断区 |
| `/cards/{id}/export-markdown` | Markdown 导出预览 |

## 6. 模块边界

### app/sources/

来源配置加载与数据库同步（不访问网络）：
- `config_loader.py`：YAML 配置解析、验证、SourceConfig 模型
- `db_sync.py`：`sync_sources_config_to_db()` 将 YAML 配置写入 Source 表
- `models.py`：SourceConfig Pydantic 模型
- `rss_probe.py`：RSS 探测实现（访问真实网络）
- `html_index_probe.py`：HTML Index 探测实现（访问真实网络）
- `quality.py`：InsightCard 和 BilingualReport 的质量检查函数

### app/services/

内容处理管线（不直接处理 HTTP 请求）：
- `fetcher.py`：`fetch_url()` HTTP 抓取
- `extractor.py`：`extract_content()` 正文提取（trafilatura / BeautifulSoup / pypdf）
- `cleaner.py`：`clean_text()` 文本清洗
- `deduper.py`：`compute_content_hash()` / `check_duplicate()` 去重
- `relevance.py`：`get_user_directions()` 获取用户关注方向
- `insight_compiler.py`：`compile_url()` 编译管线编排

### app/llm/

LLM 调用封装（不处理业务逻辑）：
- `base.py`：LLM 基类
- `factory.py`：`create_llm_client()` 工厂函数
- `config_loader.py`：LLM profile 加载
- `json_utils.py`：JSON 解析工具
- `providers/minimax_anthropic.py`：MiniMax Anthropic Messages API 实现
- `providers/openai_compatible.py`：OpenAI-compatible 协议实现

### app/exports/

导出功能（无状态、无网络）：
- `markdown_task.py`：`build_action_markdown()` 纯函数，构建 Markdown 文档

### app/prompts/

Prompt 模板（无状态）：
- `insight_card.py`：InsightCard 和 BilingualReport 的 Prompt 构建函数

### scripts/

命令行工具（不通过 Web 访问）：
- `probe_rss_sources.py`：RSS 来源探测入口
- `probe_html_index_sources.py`：HTML Index 来源探测入口
- `smoke_test.py`：冒烟测试
- `acceptance_*.py`：各版本验收脚本

### docs/

项目维护文档（本目录）：
- `ARCHITECTURE_OVERVIEW.md`：架构总览（本文件）
- `IMPLEMENTATION_GUIDE.md`：实现原理说明
- `LLM_PIPELINE_AND_QUALITY.md`：LLM 管线和质量治理
- `PRODUCT_SHAPE_ROADMAP.md`：产品形态路线

## 7. 当前阶段

当前是**个人本地 MVP / 可演示工作台雏形**，不是公开 SaaS。

现状：
- 单用户本地 SQLite 数据库
- 手动触发编译（非定时任务）
- 需要手动配置 API Key
- 验收靠脚本而非自动化流水线

不适合做的方向：
- 多用户权限系统
- 公开注册
- 浏览器插件（当前阶段）
- 移动 App（当前阶段）

