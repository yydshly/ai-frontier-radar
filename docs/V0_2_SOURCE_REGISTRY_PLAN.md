# V0.2 Source Registry 设计文档

> 目标：把"应该关注哪些 AI 前沿信息源"配置化、产品化、可视化
> 阶段：V0.2 规划 / 设计，不含实现代码

---

## 一、产品定位

### V0.1 已验证的能力

```
单篇 URL / PDF
  → 抓取正文
  → 清洗内容
  → 去重判断
  → MiniMax LLM 编译
  → 中文 InsightCard
  → 保存与 Web 查看
```

### V0.2 的核心目标

**V0.2 不是自动爬虫，不是资讯聚合站，不是日报系统。**

V0.2 是**关注来源配置与文章发现模块**：

```
配置关注来源
  → /sources 页面列出所有来源
  → 手动触发某个来源抓取
  → 发现文章 URL，形成 SourceItem 列表
  → 用户选择文章
  → 调用 V0.1 的单篇编译能力生成 InsightCard
```

V0.2 让用户主动决定"我要关注哪些来源"，而不是系统无差别抓取。

---

## 二、V0.2 明确不做什么

以下功能**不进入 V0.2 实施范围**：

| 不做的事 | 原因 | 后续路线 |
|----------|------|----------|
| 自动每日抓取 | 消耗 LLM quota，噪音不可控 | V0.3 |
| 自动日报 | 需要人工审核日报质量 | V0.4 |
| 全网爬虫 | 范围不可控，易触发反爬 | 不做 |
| Twitter / X 抓取 | 需要 API，账号风险 | 不做 |
| YouTube 抓取 | 视频内容非文本目标 | 不做 |
| 登录注册 / 多用户 | V0.1 范围外 | 不做 |
| 复杂推荐算法 | V0.1 范围外 | 不做 |
| 向量数据库 | V0.1 范围外 | 不做 |
| 知识图谱 | V0.1 范围外 | 不做 |
| Celery / Redis | 增加运维复杂度 | V0.3（可选） |
| 复杂调度系统 | 依赖外部定时任务即可 | V0.3 |
| 公众号发布 | 需要微信 API | 不做 |
| 邮件订阅 | 需要邮件服务 | V0.4（可选） |

---

## 三、数据模型

### 1. Source — 信息源定义

表示一个用户关注的信息源（如 OpenAI 官网、arXiv RSS）。

```
id                自增主键
source_key        唯一标识符（英文 slug，如 "openai-news"）
name              显示名称（如 "OpenAI News"）
description       描述（如 "OpenAI 官方产品、模型和研究公告"）
type              来源类型：rss | html_index | manual_pdf | report_page
homepage_url      主站 URL
feed_url          RSS 地址（type=rss 时必须有）
category          分类：company | research | paper | policy | blog | benchmark | funding | open_source
tags              JSON 数组标签
enabled           是否启用（布尔）
fetch_strategy    抓取策略：rss | html_index | manual
relevance_hint    人工撰写的内容相关性提示，供 LLM 参考
fetch_interval_hours 建议抓取间隔（小时），仅供展示
last_fetched_at   上次抓取时间
created_at        创建时间
updated_at        更新时间
```

> **边界说明**：Source 是"信息源定义"，不是具体文章。同一个 OpenAI News 是一个 Source，可以从中发现多篇 Article。

---

### 2. SourceItem — 发现的候选文章

表示从某个 Source 中发现的一篇文章、论文、报告或公告。

```
id                自增主键
source_id         外键关联 Source
title             文章标题
url               文章 URL
url_hash          URL 的 SHA256，用于去重
published_at      发布时间（可为空）
author            作者（可为空）
summary           摘要（RSS item 的 description 或网页 meta description）
content_type      内容类型：html | pdf | unknown
status            状态：discovered | compiled | skipped | failed
insight_card_id   关联的 InsightCard ID（编译成功后填充）
failure_reason    失败原因（编译失败时填充）
created_at        发现时间
updated_at        状态更新时间
```

> **边界说明**：SourceItem 是候选资料。只有用户主动选择编译后，才会进入 InsightCard。系统不会自动批量编译所有 SourceItem。

---

### 3. FetchRun — 单次抓取记录

表示一次来源抓取任务的执行记录。

```
id                自增主键
source_id         外键关联 Source
status            状态：running | completed | failed
started_at        开始时间
finished_at       结束时间（可为空）
discovered_count  本次发现的总数量
new_count         本次新增（之前未出现）的数量
duplicate_count   本次重复（url_hash 已存在）的数量
failed_count      本次失败数量
error_message     错误信息（失败时填充）
```

> **边界说明**：FetchRun 用于排查"某次抓取是否成功、发现了多少新内容"。不直接关联 InsightCard。

---

## 四、配置文件设计

### 4.1 sources.example.yaml（模板，纳入版本控制）

```yaml
# V0.2 Source Registry 配置模板
# 复制为 sources.yaml 并填入真实来源

sources:
  openai_news:
    name: "OpenAI News"
    description: "OpenAI 官方产品、模型和研究公告"
    type: "html_index"
    homepage_url: "https://openai.com/news/"
    feed_url: null
    category: "company"
    tags: ["OpenAI", "frontier-models", "product", "agent"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 OpenAI 模型能力、产品发布、Agent、开发者工具。"
    fetch_interval_hours: 24

  anthropic_news:
    name: "Anthropic News"
    description: "Anthropic 官方公告、Claude、AI Safety 和 Agent 相关内容"
    type: "html_index"
    homepage_url: "https://www.anthropic.com/news"
    feed_url: null
    category: "company"
    tags: ["Anthropic", "Claude", "AI安全", "agent"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 Claude、AI Safety、Agent、企业应用。"
    fetch_interval_hours: 24

  deepmind_blog:
    name: "Google DeepMind Blog"
    description: "DeepMind 研究博客，覆盖 AlphaFold、Gemini、围棋 AI 等"
    type: "html_index"
    homepage_url: "https://deepmind.google/discover/blog/"
    feed_url: null
    category: "research"
    tags: ["DeepMind", "research", "AlphaFold", "Gemini", "multimodal"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 Gemini、多模态、AI for Science 相关研究。"
    fetch_interval_hours: 24

  meta_ai_blog:
    name: "Meta AI Blog"
    description: "Meta AI 研究博客，覆盖 LLaMA、Segment Anything、MusicGen 等"
    type: "html_index"
    homepage_url: "https://ai.meta.com/blog/"
    feed_url: null
    category: "company"
    tags: ["Meta", "LLaMA", "open-source", "multimodal", "research"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注开源模型、多模态、Agents 研究。"
    fetch_interval_hours: 24

  microsoft_research_ai:
    name: "Microsoft Research AI"
    description: "微软研究院 AI 博客，覆盖 GPT-4、Office AI、Azure AI 等"
    type: "html_index"
    homepage_url: "https://www.microsoft.com/en-us/research/blog/"
    feed_url: null
    category: "research"
    tags: ["Microsoft", "research", "GPT-4", "Office AI", "Azure"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 Office AI、产品集成、Azure AI 服务。"
    fetch_interval_hours: 24

  nvidia_ai_blog:
    name: "NVIDIA Technical Blog - AI"
    description: "NVIDIA AI 技术博客，覆盖 GPU 训练、AI 推理、H100 / H200 等"
    type: "html_index"
    homepage_url: "https://developer.nvidia.com/blog/category/ai/"
    feed_url: null
    category: "company"
    tags: ["NVIDIA", "GPU", "H100", "training", "inference", "hardware"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 GPU 训练优化、AI 推理加速、硬件进展。"
    fetch_interval_hours: 24

  huggingface_blog:
    name: "Hugging Face Blog"
    description: "Hugging Face 博客，覆盖开源模型、Transformers、Diffusers 等"
    type: "html_index"
    homepage_url: "https://huggingface.co/blog"
    feed_url: null
    category: "open_source"
    tags: ["HuggingFace", "open-source", "LLM", "Transformers", "community"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注开源模型发布、State-of-the-Art 模型、Transformers 更新。"
    fetch_interval_hours: 24

  arxiv_cs_ai:
    name: "arXiv cs.AI"
    description: "arXiv 人工智能方向最新论文 RSS"
    type: "rss"
    homepage_url: "https://arxiv.org/list/cs.AI/recent"
    feed_url: "https://export.arxiv.org/rss/cs.AI"
    category: "paper"
    tags: ["paper", "research", "agent", "AI", "arXiv"]
    enabled: true
    fetch_strategy: "rss"
    relevance_hint: "重点关注 Agent、推理、RAG、文档理解、AI Safety 相关论文。"
    fetch_interval_hours: 24

  arxiv_cs_cl:
    name: "arXiv cs.CL"
    description: "arXiv 计算语言学方向最新论文 RSS"
    type: "rss"
    homepage_url: "https://arxiv.org/list/cs.CL/recent"
    feed_url: "https://export.arxiv.org/rss/cs.CL"
    category: "paper"
    tags: ["paper", "research", "NLP", "LLM", "arXiv"]
    enabled: true
    fetch_strategy: "rss"
    relevance_hint: "重点关注大语言模型、NLP 架构、推理优化、对话系统相关论文。"
    fetch_interval_hours: 24

  arxiv_cs_lg:
    name: "arXiv cs.LG"
    description: "arXiv 机器学习方向最新论文 RSS"
    type: "rss"
    homepage_url: "https://arxiv.org/list/cs.LG/recent"
    feed_url: "https://export.arxiv.org/rss/cs.LG"
    category: "paper"
    tags: ["paper", "research", "ML", "deep-learning", "arXiv"]
    enabled: true
    fetch_strategy: "rss"
    relevance_hint: "重点关注深度学习理论、训练方法、优化算法相关论文。"
    fetch_interval_hours: 24

  stanford_hai:
    name: "Stanford HAI"
    description: "Stanford Human-Centered AI Institute 博客"
    type: "html_index"
    homepage_url: "https://hai.stanford.edu/news"
    feed_url: null
    category: "research"
    tags: ["Stanford", "HAI", "policy", "AI-society", "research"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 AI 政策、AI 社会影响、人机交互研究。"
    fetch_interval_hours: 24

  mit_news_ai:
    name: "MIT News AI"
    description: "MIT 新闻 AI 板块，覆盖 AI 研究进展"
    type: "html_index"
    homepage_url: "https://news.mit.edu/topic/artificial-intelligence-0807"
    feed_url: null
    category: "research"
    tags: ["MIT", "research", "AI", "robotics", "policy"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "重点关注 AI 机器人研究、AI 政策、AI 安全相关报道。"
    fetch_interval_hours: 24
```

### 4.2 .gitignore 更新

确保以下文件被忽略：

```
config/sources.yaml
```

---

## 五、首批信息源说明

### 为什么关注这些来源

| 来源 | 类型 | 为什么纳入 | 适合策略 |
|------|------|-----------|----------|
| OpenAI News | company | 头号竞品，产品发布直接影响行业 | html_index |
| Anthropic News | company | Claude 发布、AI Safety 权威 | html_index |
| DeepMind Blog | research | AlphaFold / Gemini 等突破性研究 | html_index |
| Meta AI Blog | company | LLaMA 等开源模型重要来源 | html_index |
| Microsoft Research AI | research | Office AI、Azure AI 产品依托 | html_index |
| NVIDIA AI Blog | company | GPU / 训练硬件进展 | html_index |
| Hugging Face Blog | open_source | 开源模型生态核心 | html_index |
| arXiv cs.AI | paper | Agent / RAG / AI Safety 论文 | rss |
| arXiv cs.CL | paper | LLM / NLP 论文 | rss |
| arXiv cs.LG | paper | ML 理论 / 训练方法论文 | rss |
| Stanford HAI | research | AI 政策与社会影响 | html_index |
| MIT News AI | research | AI 机器人 / AI 安全报道 | html_index |

**V0.2 首批不超过 15 个来源**，优先覆盖模型公司 + 论文 + 研究机构。

---

## 六、页面设计

### 6.1 来源列表页 — GET /sources

**页面目标**：让用户清楚知道当前系统关注哪些来源。

**显示内容**：

| 字段 | 说明 |
|------|------|
| 来源名称 | 来自 `Source.name` |
| 类型 | RSS / html_index |
| 分类 | company / research / paper 等 |
| 标签 | 彩色 tag chips |
| 是否启用 | enabled 布尔，显示开关 |
| 抓取策略 | rss / html_index |
| 最近抓取时间 | `last_fetched_at` 或"从未抓取" |
| 最近发现数量 | 最近一次 FetchRun 的 `discovered_count` |
| 操作 | 手动抓取按钮 / 进入详情 |

**交互**：

- 点击来源名称 → 进入来源详情页
- 点击"手动抓取" → 触发 POST `/sources/{source_key}/fetch`
- enabled 切换 → 触发 PATCH `/sources/{source_key}`

---

### 6.2 来源详情页 — GET /sources/{source_key}

**显示内容**：

```
来源基本信息
  name / description / category / tags
  relevance_hint（内容相关性提示）
  fetch_strategy / fetch_interval_hours

最近 FetchRun（最近 5 次）
  时间 / 状态 / discovered / new / duplicate / failed

最近 SourceItem 列表（最近 20 条，可翻页）
  标题 / URL / 发布时间 / 状态
  是否有 InsightCard（显示卡片 ID）
  操作：编译 / 跳过 / 查看失败原因
```

**SourceItem 状态流转**：

```
discovered → compiled（用户点击编译）
discovered → skipped（用户点击跳过）
discovered → failed（编译过程中出错）
```

---

## 七、接口设计

V0.2 预留以下 REST 接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sources` | 列出所有来源（不含 SourceItem） |
| GET | `/sources/{source_key}` | 获取单个来源详情 |
| PATCH | `/sources/{source_key}` | 更新来源启用状态 |
| POST | `/sources/{source_key}/fetch` | 手动触发一次来源抓取 |
| GET | `/source-items` | 列出 SourceItem（支持 source_id / status 过滤） |
| POST | `/source-items/{item_id}/compile` | 编译单个 SourceItem → 复用 V0.1 compile 链路 |
| POST | `/source-items/{item_id}/skip` | 标记 SourceItem 为 skipped |
| GET | `/source-items/{item_id}` | 获取单个 SourceItem 详情 |

**接口说明**：

- `/sources` 只展示配置和状态，**不主动抓取**
- fetch 只发现文章 URL，**不直接批量编译**
- compile 复用 V0.1 的 `compile_url()` 服务层
- skip 用于标记不值得编译的内容（人工过滤噪音）

---

## 八、抓取策略

### 8.1 RSS 抓取

**适用场景**：arXiv、博客 RSS、公司 RSS 订阅。

**依赖**（本轮仅设计，不引入依赖）：`feedparser`

**流程**：

```
1. 读取 Source.feed_url
2. 发送 HTTP GET（timeout=15s，User-Agent 设为项目标识）
3. 解析 RSS XML（feedparser）
4. 对每个 <item> 提取：
   - title（文章标题）
   - link（文章 URL）
   - pubDate / dc:date（发布时间）
   - description（摘要）
5. 计算 url_hash = SHA256(link)
6. 查重：url_hash 是否已存在于 SourceItem 表
7. 未重复的保存为 SourceItem(status=discovered)
8. 记录 FetchRun
```

**去重逻辑**：按 `url_hash` 全局去重，同一 URL 不同来源都出现只保存一条。

---

### 8.2 HTML Index 抓取

**适用场景**：公司新闻页、博客列表页、论文列表页。

**依赖**（本轮仅设计）：`httpx`（已有）+ `BeautifulSoup`（已有）

**流程**：

```
1. 读取 Source.homepage_url
2. 发送 HTTP GET（timeout=20s，User-Agent 设为项目标识）
3. 解析 HTML（BeautifulSoup）
4. 从页面提取所有 <a> 链接
5. 过滤规则（必须全部满足）：
   - 链接是站内链接（host 与 homepage_url 相同）或已知白名单域名
   - 去除包含 /tag/ /category/ /author/ /page/ 的分页/分类链接
   - 去除图片、媒体文件后缀（.jpg .png .mp4 .pdf）
   - 链接文本长度 > 10 字符（避免导航噪音）
   - 保留 /news /blog /paper /research /2024 /2025 等路径
6. 对每个有效链接提取：
   - title（<a> 文本或 <title>）
   - url（绝对 URL）
7. 计算 url_hash，去重，保存 SourceItem
8. 限制：单次最多发现 50 条新链接
9. 记录 FetchRun
```

**V0.2 不做深层递归爬虫**，只抓取 homepage_url 首页可见链接。

---

### 8.3 安全约束

所有抓取引擎必须满足：

| 约束 | 值 |
|------|------|
| timeout | 20s |
| max redirects | 5 |
| user-agent | `AI-Frontier-Radar/0.2 (+https://github.com/yydshly/ai-frontier-radar)` |
| 单次最大发现 | 50 条 |
| 抓取深度 | 1（仅当前页面） |
| 失败可见 | FetchRun.error_message 记录 |
| 重复可见 | FetchRun.duplicate_count 记录 |

---

## 九、和 V0.1 的关系

```
V0.1 InsightCard 编译链路保持不变：
  compile_url(url) → InsightCard

V0.2 只负责发现候选 URL：
  fetch_source(source_key) → [SourceItem]

用户从 SourceItem 列表中选择想编译的文章：
  POST /source-items/{item_id}/compile
    → 内部调用 compile_url(source_item.url)
    → 生成 InsightCard
    → source_item.status = compiled
    → source_item.insight_card_id = new_card.id
```

**关键约束**：抓取来源和 LLM 编译**完全解耦**。用户必须主动选择"哪篇要编译"，系统不会因为发现了新文章就自动消耗 LLM quota。

---

## 十、每日抓取路线（V0.3）

V0.2 完成后，V0.3 可考虑每日自动抓取。

### 10.1 触发方式

```
scripts/daily_fetch.py
  → 读取所有 enabled sources
  → 逐个调用 fetch
  → 记录 FetchRun

触发器（任选其一）：
  Windows Task Scheduler（Windows 用户）
  cron（Linux/macOS）
  GitHub Actions scheduled（免费，无需服务器）
```

### 10.2 每日抓取流程

```
1. 读取 config/sources.yaml 中 enabled=true 的 Source
2. 遍历每个 Source：
   a. 检查距离上次 fetch 是否超过 fetch_interval_hours
   b. 超过则执行 fetch
   c. 记录 FetchRun
3. 发现 SourceItem，但不自动编译
4. 生成抓取报告（发现 N 条，其中 M 条新）
```

### 10.3 为什么 V0.3 不自动编译

```
自动编译所有文章的问题：
  - 消耗 LLM quota 不可控
  - 噪音内容（与用户方向无关的文章）产生大量废卡
  - 无法保证编译质量
  - 用户对自动化结果失去信任

正确做法：
  - 每日发现文章，用户主动选择编译
  - AI 只做推荐（后续 V0.4），不由 AI 决定是否编译
```

---

## 十一、日报路线（V0.4）

日报是二次汇总，不是简单拼接卡片。

### 11.1 DailyReport 模型建议

```
id
report_date              日期
source_count             本日抓取来源数
source_item_count       本日发现文章数
compiled_card_count     本日编译卡片数
top_cards               JSON，Top 5 卡片 ID 列表
summary_zh              今日前沿摘要（人工或 AI 辅助）
trend_insights_zh       技术趋势（AI 辅助）
product_opportunities_zh 产品机会（AI 辅助）
risks_zh                风险提醒（AI 辅助）
action_items_zh          建议行动（AI 辅助）
created_at
```

### 11.2 日报内容要求

```
日报不是卡片列表的复制粘贴。
日报是结构性总结：
  - 今日前沿摘要（3-5 句）
  - 高相关内容 Top 5（附理由）
  - 技术趋势（1-3 条）
  - 产品机会（1-3 条）
  - 风险提醒（1-3 条）
  - 和用户当前项目的关系
  - 建议行动（1-3 条）
  - 原始 InsightCard 列表（附录）
```

### 11.3 日报不是 V0.2 范围的原因

```
1. 日报需要二次 LLM 汇总，成本不可控
2. 日报质量需要人工审核机制
3. 日报发布渠道（邮件/微信/公众号）需要单独对接
4. 日报和日报之间需要去重和对比
```

---

## 十二、分阶段实施计划

### V0.2.1 — Source 配置文件与加载器

**目标**：加载 `config/sources.yaml` 中的来源定义，转换为内存中的 Source 对象。

**输入**：`config/sources.yaml`

**输出**：
- `load_sources()` 函数
- `get_source(source_key)` 函数
- `list_sources()` 函数

**验收标准**：
- `list_sources()` 返回所有 Source 列表
- `get_source("openai_news")` 返回对应 Source
- 不存在的 key 返回 None

**主要风险**：YAML 格式错误导致加载失败 → 单元测试覆盖

---

### V0.2.2 — Source / SourceItem / FetchRun 数据模型

**目标**：在 `app/models.py` 增加三个模型类。

**输入**：无

**输出**：
- `Source` SQLAlchemy 模型
- `SourceItem` SQLAlchemy 模型
- `FetchRun` SQLAlchemy 模型
- 数据库迁移脚本（alembic 或手动 SQL）

**验收标准**：
- 三个模型可以独立 CRUD
- Source 和 SourceItem 通过 source_id 关联
- SourceItem 和 InsightCard 通过 insight_card_id 关联

**主要风险**：迁移脚本在生产环境执行失败 → 必须在本地测试环境验证

---

### V0.2.3 — /sources 页面

**目标**：在 Web UI 展示来源列表。

**输入**：无（纯展示）

**输出**：
- `GET /sources` 路由
- `sources.html` Jinja2 模板
- `/sources/{source_key}` 详情页

**验收标准**：
- 列出所有来源，显示名称/类型/分类/启用状态
- 点击来源名称进入详情
- 详情页显示 FetchRun 列表和 SourceItem 列表

---

### V0.2.4 — RSS 来源手动抓取

**目标**：实现 RSS 抓取逻辑，从 SourceItem 发现文章 URL。

**输入**：用户点击"手动抓取"按钮

**输出**：
- `fetch_rss(source_key) → FetchRun`
- SourceItem 保存到数据库
- 页面刷新显示新发现的文章

**验收标准**：
- arXiv RSS 可以正确解析并保存 SourceItem
- url_hash 去重有效（重复抓取不产生新 SourceItem）
- FetchRun 记录 discover/new/duplicate/failed 数量

---

### V0.2.5 — HTML Index 来源手动抓取

**目标**：实现 HTML 页面抓取逻辑，从页面链接发现文章 URL。

**输入**：用户点击"手动抓取"按钮

**输出**：
- `fetch_html_index(source_key) → FetchRun`
- SourceItem 保存到数据库
- 页面刷新显示新发现的文章

**验收标准**：
- OpenAI News / Anthropic News 等页面可正确提取文章链接
- 链接过滤规则有效（去除分页/分类/导航噪音）
- 单次最多发现 50 条

---

### V0.2.6 — SourceItem → InsightCard 编译

**目标**：用户选择 SourceItem，调用 V0.1 compile 链路生成 InsightCard。

**输入**：用户点击 SourceItem 的"编译"按钮

**输出**：
- `POST /source-items/{item_id}/compile`
- 复用 `compile_url(source_item.url)` 生成 InsightCard
- 更新 SourceItem.status = compiled，insight_card_id 关联

**验收标准**：
- 点击编译后，页面跳转到对应 InsightCard 详情
- SourceItem 状态变为 compiled
- 已有 InsightCard 的 SourceItem 显示卡片 ID，不可重复编译

---

### V0.3 — 每日自动抓取

见第十节。

### V0.4 — 每日报告

见第十一节。

---

## 十三、验收标准核对

本设计文档完成后，应满足：

```
✅ 1. 能看清 V0.2 做什么、不做什么
✅ 2. 能看清 Source / SourceItem / FetchRun 模型边界
✅ 3. 能看清 sources.yaml 配置结构
✅ 4. 能看清 /sources 页面怎么设计
✅ 5. 能看清 RSS 与 HTML index 抓取差异
✅ 6. 能看清和 V0.1 compile_url 的关系
✅ 7. 能看清每日抓取和日报为什么不是 V0.2 范围
✅ 8. 能据此拆下一轮编码任务
```

---

## 十四、术语表

| 术语 | 定义 |
|------|------|
| Source | 用户配置的信息源定义（如"OpenAI News"） |
| SourceItem | 从 Source 中发现的单篇文章（如"OpenAI 发布 GPT-5"） |
| FetchRun | 一次抓取执行记录（跑了多久、发现多少、失败多少） |
| InsightCard | V0.1 已有的中文结构化卡片 |
| compile | 用户主动选择 SourceItem，生成 InsightCard 的过程 |
| RSS 抓取 | 通过 RSS feed 发现文章 URL |
| HTML Index 抓取 | 解析网页链接发现文章 URL |
| url_hash | URL 的 SHA256，用于去重 |
