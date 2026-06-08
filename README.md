# AI Frontier Radar / AI 前沿雷达

AI Frontier Radar 是一个面向中文 AI 从业者、独立开发者和产品探索者的全球 AI 前沿资料中文编译工作台。

它不是普通 RSS 阅读器、翻译器或资讯聚合站，而是把英文 AI 前沿资料转成中英双语洞察、个人判断和可执行行动的本地工作台。

## 当前阶段

**当前版本：V1.0-alpha 本地演示版**

- 已具备完整本地演示主流程
- 适合个人使用、自测和后续开发
- 暂不定位为公开 SaaS

## 适合谁使用

- 英语阅读成本较高，但需要追踪全球 AI 前沿资料的人
- AI 从业者、独立开发者、产品探索者
- 想把英文报告、研究博客、公司公告沉淀为中文洞察的人
- 想从前沿资料中提取产品机会和行动任务的人

## 5 分钟本地演示

无需联网、无需真实 LLM，即可快速体验完整主流程：

```bash
# 1. 创建演示数据（不联网、不调用 LLM）
python scripts/create_demo_data.py

# 2. 启动服务
uvicorn app.main:app --reload --port 8779

# 3. 打开首页
open http://127.0.0.1:8779/
```

首页会出现 **🎬 演示数据入口** 区块，可以直接打开演示资料、InsightCard、完整报告和行动任务。

## 产品主流程

```
首页工作台 → SourceItem 收件箱 → InsightCard → 中英双语核心理解 → 用户判断 → 完整报告 / 行动任务
```

每一步说明：

| 步骤 | 说明 |
|------|------|
| 首页工作台 | 查看待处理资料和下一步建议 |
| SourceItem 收件箱 | 选择英文资料 |
| InsightCard | 生成中文洞察 |
| 中英双语核心理解 | 保留英文主旨并提供中文解释 |
| 用户判断 | 标记值得关注、稍后再看、转成行动等 |
| 完整报告 | 用于知识沉淀 |
| 行动任务 | 用于继续交给 AI 执行模型拆解 |

## 当前核心能力

- 精选 AI 前沿来源配置
- RSS / HTML Index 来源探测
- SourceItem 收件箱
- 单条 SourceItem 编译为 InsightCard
- 中英双语核心理解
- 用户判断闭环
- 按状态筛选 InsightCard
- Markdown 行动任务导出
- 完整中英双语 Markdown 报告导出
- 首页工作台
- 一键 demo 数据

## 常用命令

### 基础检查

```bash
python -m compileall app scripts
python scripts/check_sources_config.py
python scripts/smoke_test.py
```

### Demo 演示

```bash
python scripts/create_demo_data.py
python scripts/acceptance_demo_data.py --isolated-db
python scripts/acceptance_demo_flow.py --isolated-db
```

### 来源探测

```bash
python scripts/acceptance_real_source_coverage.py --isolated-db --repeat 2 --timeout 15
```

### 编译与双语报告验收

```bash
python scripts/acceptance_cross_source_compile.py --isolated-db --mock-llm
python scripts/acceptance_bilingual_report.py --isolated-db --mock
python scripts/acceptance_real_bilingual_report.py --isolated-db --mock
```

### 导出验收

```bash
python scripts/acceptance_export_action_markdown.py --isolated-db
python scripts/acceptance_export_full_report.py --isolated-db --with-bilingual
python scripts/acceptance_export_full_report.py --isolated-db --without-bilingual
```

### 本地健康检查

```bash
# 快速检查环境、配置、DB、demo 数据和关键页面（不跑 smoke_test）
python scripts/health_check.py

# 完整本地检查，额外运行 smoke_test 和 demo acceptance
python scripts/health_check.py --full

# 跳过 smoke_test，只跑 demo acceptance
python scripts/health_check.py --full --skip-smoke
```

> V1.0-alpha.4.2 修复了 `health_check.py` quick/full 行为：quick 模式不跑 smoke_test，更快；`--full --skip-smoke` 等价于 quick + acceptance。

`health_check.py` 不访问真实网络，不调用真实 LLM，适合作为本地轻量 CI。
详细说明见 [docs/HEALTH_CHECK.md](docs/HEALTH_CHECK.md)。

### GitHub Actions 基础 CI

项目提供基础 CI，用于每次 push / PR 自动检查无外部依赖的基础链路。

CI 检查项：
- compileall
- check_sources_config
- smoke_test
- acceptance_demo_data
- acceptance_demo_flow
- health_check

CI 不访问真实网络，不调用真实 LLM，不需要 MINIMAX_API_KEY。
详细说明见 [docs/CI.md](docs/CI.md)。

### 手动验收效果

创建 demo 数据并启动服务后，建议手动打开以下页面确认效果：

- `/` — 首页工作台，演示数据入口
- `/about` — 项目原理与技术架构说明
- `/source-items/{id}` — 演示资料详情
- `/cards/{id}` — 演示 InsightCard 详情
- `/cards/{id}/export-report` — 完整 Markdown 报告预览
- `/cards/{id}/export-markdown` — Markdown 行动任务预览

详细清单见 [docs/V1.0_ALPHA_4_1_CI_AND_UI_ACCEPTANCE.md](docs/V1.0_ALPHA_4_1_CI_AND_UI_ACCEPTANCE.md)。

V1.0-alpha.4.3 增加真实浏览器与 GitHub Actions 验收记录，详见 [docs/V1.0_ALPHA_4_3_REAL_BROWSER_AND_CI_ACCEPTANCE.md](docs/V1.0_ALPHA_4_3_REAL_BROWSER_AND_CI_ACCEPTANCE.md)。

## V1.0-alpha Release Candidate

V1.0-alpha 已进入 Release Candidate 清理阶段，核心主流程、demo 数据、完整报告导出、本地健康检查和基础 CI 已具备。

正式合并 main 或打 `v1.0-alpha` tag 前，应按 [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) 逐项确认。

**RC 检查命令：**
```bash
python scripts/acceptance_release_candidate.py --skip-smoke
```

**文档入口：**
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — 发布说明、能力清单、演示流程
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — 发布前逐项检查
- [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) — 已知限制详细说明

## 项目理解与维护文档

| 文档 | 用途 |
|------|------|
| [ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) | 整体架构 |
| [IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md) | 代码实现原理 |
| [LLM_PIPELINE_AND_QUALITY.md](docs/LLM_PIPELINE_AND_QUALITY.md) | 模型调用和质量治理 |
| [PRODUCT_SHAPE_ROADMAP.md](docs/PRODUCT_SHAPE_ROADMAP.md) | 产品形态路线 |
| [V1.0_ALPHA_DEMO_FLOW.md](docs/V1.0_ALPHA_DEMO_FLOW.md) | 演示主流程 |
| [V1.0_ALPHA_1_DEMO_DATA.md](docs/V1.0_ALPHA_1_DEMO_DATA.md) | demo 数据和快速启动 |
| [SYSTEM_DESIGN_AND_TECH_DECISIONS.md](docs/SYSTEM_DESIGN_AND_TECH_DECISIONS.md) | 系统设计与技术决策 |
| [INPUT_CLASSIFICATION_AND_SUMMARY_STRATEGY.md](docs/INPUT_CLASSIFICATION_AND_SUMMARY_STRATEGY.md) | URL 类型识别与总结策略 |

## 模型策略

- **默认产品运行模型**：MiniMax-M2.7-highspeed
- **复杂长文、高保真重试**：可使用 M3
- **开发执行、架构审查、复杂问题排查**：更适合 M3

模型输出必须经过结构化解析和质量检查；mock 验收只验证链路，真实 LLM 验收才验证模型输出质量。

## 当前不做什么

- 多用户 / 登录注册
- 付费 / 公开 SaaS
- 浏览器插件 / 移动 App
- 后台定时任务 / 全网爬虫
- 复杂推荐算法 / 知识图谱 / 向量数据库

当前重点是个人本地工作台和资料编译链路，不急着做公开产品形态。

## 版本路线

| 版本 | 内容 |
|------|------|
| V0.1–V0.3 | 单篇编译、来源配置、来源探测 |
| V0.4–V0.5 | 用户判断、行动任务导出 |
| V0.6 | 首页工作台 |
| V0.7 | 真实来源覆盖和跨来源编译 |
| V0.8 | 中英双语 InsightCard 与质量验收 |
| V0.9 | 完整 Markdown 报告导出 |
| V1.0-alpha | 可演示主流程引导 |
| V1.0-alpha.1 | 一键 demo 数据与 5 分钟演示 |

详细版本历史见下方「历史版本记录」。

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

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY

# 初始化数据库
python -c "from app.db import init_db; init_db()"

# 启动服务
uvicorn app.main:app --reload --port 8779

# 打开首页
open http://127.0.0.1:8779/
```

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页工作台 |
| GET | `/about` | 项目原理与技术架构说明 |
| GET | `/sources` | 信息来源列表 |
| GET | `/source-items` | 发现条目列表 |
| GET | `/source-items/{id}` | 发现条目详情 |
| POST | `/source-items/{id}/compile` | 编译为 InsightCard |
| GET | `/cards` | InsightCard 列表 |
| GET | `/cards/{id}` | 卡片详情 |
| POST | `/cards/{id}/decision` | 保存用户判断 |
| POST | `/cards/{id}/bilingual-report` | 生成双语报告 |
| GET | `/cards/{id}/export-report` | 完整报告预览 |
| GET | `/cards/{id}/export-markdown` | 行动任务预览 |
| POST | `/compile` | 手动提交 URL 编译 |

## 诊断脚本

```bash
# 基础冒烟测试
python scripts/smoke_test.py

# 来源配置检查
python scripts/check_sources_config.py

# MiniMax API 连通性验证
python scripts/probe_minimax_anthropic.py

# 数据库文本编码检查
python scripts/check_card_encoding.py

# 卡片详情页 HTML 编码检查
python scripts/check_card_page.py
```

---

# 历史版本记录

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

## V0.2 Source Registry 与来源探测链路

V0.2 在 V0.1 基础上新增了**来源配置 → 探测 → 发现 → 手动编译**的完整闭环。

### ✅ 已完成能力

- Source 配置加载（YAML → DB 同步）
- Source / SourceItem / FetchRun ORM 模型
- `/sources` 来源列表页面
- RSS Source 探测脚本
- HTML Index Source 探测脚本
- `/source-items` 发现条目列表页面（含筛选、搜索）
- `/source-items/{item_id}` 发现条目详情页
- 单条 SourceItem 手动编译为 InsightCard

### 页面入口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sources` | 信息来源列表 |
| GET | `/source-items` | 发现条目列表（支持按来源/状态/关键词筛选） |
| GET | `/source-items/{item_id}` | 发现条目详情页 |
| POST | `/source-items/{item_id}/compile` | 手动编译该条目为 InsightCard |
| GET | `/cards` | InsightCard 列表 |
| GET | `/cards/{card_id}` | 卡片详情 |

## V0.3 精选 AI 前沿来源导航 UI

V0.3 在 V0.2 来源探测链路基础上，新增**精选来源导航 UI**，降低用户发现成本。

### ✅ 已完成能力

- 首页展示精选 AI 前沿来源卡片网格（P0 / P1 / P2 分级）
- 每个来源包含图标、名称、分类、关注重点、操作按钮
- 来源覆盖：OpenAI、Anthropic、DeepMind、Hugging Face、arXiv、NVIDIA、Microsoft、Meta、Stanford HAI、MIT、Berkeley BAIR、Mistral AI、Cohere

### 精选来源分级

| 优先级 | 来源 |
|--------|------|
| P0（必看） | OpenAI、Anthropic、DeepMind、Hugging Face、arXiv AI、NVIDIA AI |
| P1（推荐） | Meta AI、Microsoft AI、Stanford HAI、MIT AI、Berkeley BAIR、Mistral AI、Cohere |
| P2（补充） | arXiv NLP、arXiv ML |

## V0.3.1 真实来源探测验收

V0.3.1 验证最小真实来源探测链路，确认系统能从已配置来源中稳定发现 SourceItem。

### 核心命令

```bash
# 只探测单个 RSS 来源
python scripts/probe_rss_sources.py --source-key arxiv_cs_cl --timeout 15

# 只探测单个 HTML Index 来源
python scripts/probe_html_index_sources.py --source-key huggingface_blog --timeout 15

# 运行最小真实验收
python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15
```

## V0.3.2 SourceItem 编译为 InsightCard

V0.3.2 将单条 SourceItem 手动编译为 InsightCard 的链路做成可验收、可防重复、可排查的最小闭环。

### 验收脚本

```bash
python scripts/acceptance_compile_source_item.py --isolated-db --mock-success
python scripts/acceptance_compile_source_item.py --isolated-db --mock-failed
```

## V0.3.3 SourceItem 质量过滤

V0.3.3 解决 HTML Index Probe 误收录列表页、分页页、分类页的问题。

### 过滤规则

**过滤的 URL 模式：** `/blog`、`/news`、`/research` 配合分页参数（`?p=`、`?page=`、`?sort=`、`?tag=`）

**保留的 URL 模式：** 两级以上 path segment（如 `/blog/slug`）或带年份 path

### 验收命令

```bash
python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15 --html-source huggingface_blog
```

## V0.3.4 SourceItem 列表可读性与历史分页数据检查

V0.3.4 解决 `/source-items` 页面可读性问题，并提供历史疑似分页 SourceItem 的检查脚本。

### 页面改进

- 宽屏布局 + 横向滚动表格
- URL 完整显示（带 title 属性）
- 状态中文辅助

### 检查命令

```bash
python scripts/check_listing_source_items.py --source-key huggingface_blog
```

## V0.3.5 中文优先人工验收体验

V0.3.5 帮助英语能力有限的中文用户更容易从英文 SourceItem 中选择资料。

### 改动

- `/source-items` 页面增加中文引导
- 新增「推荐操作」列
- 详情页增加中文说明

## V0.4 产品目标闭环：InsightCard 用户决策

V0.4 补齐用户看完 InsightCard 后的处理动作。

### 产品闭环

```
待编译资料 → 单条编译 → 中文 InsightCard → 用户判断
```

### 新增数据

- 新表 `card_decisions`
- 一张 InsightCard 只保留一条当前决策
- 重复提交同一卡片的决策：update，不 insert

## V0.4.1 按处理状态过滤 InsightCard

V0.4.1 允许用户在 `/cards` 页面按判断结果筛选和回看。

### 支持的过滤值

`?decision=unhandled`、`worth_attention`、`related_to_me`、`read_later`、`ignore`、`to_action`

## V0.5 将"转成行动"的 InsightCard 导出为 Markdown 任务

V0.5 把中文洞察卡整理成可复制、可下载、可交给 AI 执行模型继续处理的 Markdown 任务草稿。

### 使用路径

```
/cards?decision=to_action → 打开卡片详情 → 导出为 Markdown 任务
```

## V0.6 首页升级为个人 AI 前沿工作台

V0.6 将首页从普通入口页升级为工作台，让用户打开系统后立即知道当前状态和下一步动作。

### 新增内容

- **统计概览**：待编译资料、未处理卡片、值得关注、转成行动
- **下一步建议**：根据当前数据状态给出规则化行动建议
- **快捷入口**：快速跳转到收件箱、洞察卡、行动任务、信息来源
- **最近待编译资料** + **最近中文洞察卡**

## V0.7 真实高价值来源覆盖与探测稳定性

V0.7 验证系统能从多个高价值英文 AI 来源发现真实文章。

### 验收命令

```bash
python scripts/acceptance_real_source_coverage.py --isolated-db --repeat 2 --timeout 15
```

## V0.7.2 跨来源单条编译质量验收

V0.7.2 验证高质量 SourceItem 能否进入正文抓取和 InsightCard 编译链路。

### 验收命令

```bash
python scripts/acceptance_cross_source_compile.py --isolated-db --mock-llm
```

## V0.8 中英双语 InsightCard 与原文保真解释

V0.8 在中文洞察卡中增加英文核心内容和中文解说。

### 英文部分（保留原文主旨）

- English Core Summary
- Original Key Claims
- Key Evidence Points
- Key Terms EN-ZH

### 中文部分（帮助理解）

- 中文解说
- 保真提示
- 解读边界

### 验收命令

```bash
python scripts/acceptance_bilingual_report.py --isolated-db --mock
```

## V0.8.2 真实 LLM 中英双语报告质量验收

V0.8.2 验证真实 LLM 输出是否满足保真和语言边界要求。

### 验收命令

```bash
python scripts/acceptance_real_bilingual_report.py --isolated-db --real
```

## V0.9 中英双语 InsightCard 完整 Markdown 报告导出

V0.9 新增完整 Markdown 报告导出功能，把一张 InsightCard 导出为完整的中英双语资料编译报告。

### 与 V0.5 行动任务导出的区别

- **V0.5 行动任务导出**：面向下一步执行
- **V0.9 完整报告导出**：面向知识沉淀、长期复盘

### 验收命令

```bash
python scripts/acceptance_export_full_report.py --isolated-db --with-bilingual
python scripts/acceptance_export_full_report.py --isolated-db --without-bilingual
```

## V1.0-alpha 可演示主流程

V1.0-alpha 固定了一条从资料发现到完整报告导出的演示路径。

### 主流程

```
首页工作台 → SourceItem 收件箱 → InsightCard → 中英双语核心理解 → 用户判断 → 完整报告 / 行动任务
```

### 验收脚本

```bash
python scripts/acceptance_demo_flow.py --isolated-db
```

## V1.0-alpha.1 一键 demo 数据与 5 分钟演示

V1.0-alpha.1 让用户可以在本地快速创建一套 demo 数据。

### 命令

```bash
python scripts/create_demo_data.py
python scripts/acceptance_demo_data.py --isolated-db
```

## 后续路线

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
