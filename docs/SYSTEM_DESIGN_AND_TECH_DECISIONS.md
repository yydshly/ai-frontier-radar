# 系统设计与技术决策

**Date:** 2026-06-08
**Version:** V1.0-alpha.8.4

---

## 1. 项目定位

AI Frontier Radar 是一个面向 AI 从业者和独立开发者的**前沿资料中文编译工作台**。

它的核心价值是：帮助你在海量英文资料中，快速筛选高价值内容，生成结构化的中文洞察，并形成可执行的个人判断。

### AI Frontier Radar 不是

- **普通 RSS 阅读器** — 它不只是订阅和推送
- **普通翻译器** — 它不是逐句翻译，而是结构化洞察编译
- **全网爬虫** — 它只从精选来源获取，不追求全面覆盖

### V1.0-alpha 优先验证

本地个人工作台 + 单篇资料编译链路的完整性。

不追求来源数量和覆盖率，优先确保每一条线索都可信、可追溯、可执行。

---

## 2. 核心数据流

```
精选来源配置 (YAML + DB)
    ↓
来源探测 (RSS probe / HTML index probe)
    ↓
候选资料发现 (SourceItem)
    ↓
URL 类型识别 (app/intake/url_classifier.py)
    ↓
编译路由决策
    ├─ article / pdf → 正文抓取 → LLM 分析 → InsightCard
    └─ listing / pagination / tag / feed → intake blocked (不生成卡片)
    ↓
用户判断 (CardDecision)
    ↓
Markdown 报告 / 行动任务导出
```

---

## 3. 核心数据模型关系

### Source / SourceItem / InsightCard / BilingualReport / CardDecision

| 模型 | 作用 | 关键字段 |
|------|------|---------|
| **Source** | 信息来源配置 | source_key, source_type, fetch_strategy, enabled, category, relevance_hint |
| **SourceItem** | 从来源发现的候选资料 | url, title, status (discovered/compiled/failed), source_id, insight_card_id |
| **InsightCard** | 单篇资料的分析结果 | source_url, status (pending/completed/failed), summary_zh, relevance_score |
| **InsightCardBilingualReport** | 中英双语核心理解 | english_core_summary, chinese_explanation, key_terms |
| **CardDecision** | 用户的个人判断 | decision (worth_attention/related_to_me/read_later/ignore/to_action), note |

### 关系说明

- **Source → SourceItem**: 一对多（一个来源可发现多条资料）
- **SourceItem → InsightCard**: 一对一（一条资料最多生成一张卡片），也可能生成失败
- **InsightCard → CardDecision**: 一对一（每个卡片只有一个当前判断）
- **InsightCard → InsightCardBilingualReport**: 一对一（每张卡片最多一份双语报告）

---

## 4. 来源控制策略

### 当前来源管理

配置文件：`config/sources.example.yaml`，通过 `sync_sources_config_to_db()` 同步到数据库。

每个来源的核心配置：

```yaml
source_key: openai_news          # 唯一标识
name: OpenAI News               # 显示名称
source_type: html_index          # 来源类型：rss / html_index / manual
fetch_strategy: html_index       # 抓取策略
enabled: true                   # 是否启用
category: company               # 分类：company / research / paper / policy
tags: [LLM, 产品]              # 标签
relevance_hint: ""              # 相关性提示词，影响 LLM 判断
fetch_interval_hours: 24         # 探测频率
```

### 产品原则

**优先精选高价值来源，而不是全网乱爬。**

V1.0-alpha 精选来源：

- OpenAI News
- Anthropic News
- Google DeepMind Blog
- Hugging Face Blog
- Stanford HAI
- MIT News AI
- NVIDIA AI Blog
- Microsoft AI Source
- Berkeley BAIR Blog
- Mistral AI News
- Cohere Blog
- arXiv cs.AI / cs.CL / cs.LG

### 未来方向

- 首次接入来源时做有限历史整理
- 后续基于时间游标（SourceCursor）只关注新增资料
- 支持用户自定义来源优先级

---

## 5. 数据获取方式

| 方式 | 作用 | 说明 |
|------|------|------|
| **RSS 探测** | 从订阅源发现候选文章 | 定期探测 RSS feed，提取文章链接、标题、发布时间 |
| **HTML index 探测** | 从新闻/博客列表页发现候选文章 | 抓取列表页，识别正文文章链接，过滤导航/分页/标签页 |
| **手动 URL 输入** | 直接输入单篇文章或报告 | 在首页手动提交 URL，系统进行类型判断后编译 |
| **PDF 解析** | 编译报告类资料 | 识别 PDF 类型 URL，允许直接编译 |
| **Demo 数据** | 不联网、不调用 LLM 的本地演示 | 无需配置 API Key，可完整体验编译链路 |

### 重要：来源探测 ≠ 直接编译

来源探测只负责发现候选资料，不等于直接生成 InsightCard。发现后的资料需要经过 URL 类型识别，才能决定是否允许进入编译环节。

---

## 6. URL 分类与策略路由

### 分类器实现

`app/intake/url_classifier.py` 中的 `classify_url_by_pattern()` 函数，基于规则判断 URL 类型。

**不需要 LLM**，纯规则实现，可解释、可控。

### URL 类型与策略

| 类型 | 示例 | 策略 | 说明 |
|------|------|------|------|
| `article` | `/discover/blog/sima-2-agent/` | ✅ 允许编译 | 单篇博客/新闻/研究文章 |
| `pdf` | `/report.pdf` | ✅ 允许编译 | PDF 报告 |
| `listing` | `/blog/` | 🚫 只用于发现 | 列表页，不是单篇文章 |
| `pagination` | `/blog/page/3/` | 🚫 阻止编译 | 分页页，不是内容页 |
| `tag_or_category` | `?tag=agents` | 🚫 只用于发现 | 标签页/分类页 |
| `feed` | `/feed.xml` | 🚫 只用于发现 | RSS/Atom Feed |
| `unknown` | 无法判断 | ⚠️ 谨慎尝试 | 无法判断时记录日志 |

### 典型反例 — DeepMind 分页页

```
https://deepmind.google/blog/page/3/
```

这是第 3 页的文章列表页，不是单篇文章。系统不应把它直接总结成 InsightCard。正确做法是从中发现具体文章 URL，再选择单篇文章编译。

### intake 模块结构

```
app/intake/
    __init__.py           # classify_url_by_pattern 导出
    models.py             # PageType, RecommendedStrategy, IntakeDecision
    url_classifier.py     # 规则分类器实现
```

---

## 7. 抓取失败和阻塞处理

### 失败类型与处理

| 失败类型 | 原因 | 当前处理 |
|------|------|---------|
| HTTP 403/404 | 页面禁止访问或不存在 | 保存 failed card，显示错误原因 |
| 正文抽取失败 | 页面结构无法解析 | 保存 failed card，允许重试 |
| API Key 缺失 | MINIMAX_API_KEY 未配置 | 保存 failed card，提示配置 |
| LLM 调用失败 | 网络或 API 问题 | 保存 failed card，可重试 |
| URL 类型被拦截 | 列表页/分页页/Feed | 显示"不适合直接编译"，不生成 card |
| 内容过短 | 疑似导航页 | 归类为 failed，提示内容不足 |

### intake blocked vs failed

- **intake blocked**：系统主动识别到 URL 不适合直接编译，这是**预期行为**，不是系统坏了
- **failed**：尝试编译后遇到了**技术问题**（网络、API、结构等），可能值得重试

### 失败时界面处理

- 首页：failed / blocked card 显示为橙色/红色背景，"已拦截"或"处理失败"状态，相关性显示"-"
- 详情页：显示友好文案（"不适合直接编译"而非"处理失败"），提供删除入口
- SourceItem 详情页：提供"返回英文资料收件箱"等导航

### 未来方向

- 更细的状态：`blocked_by_intake` / `needs_discovery` / `failed_fetch` / `failed_llm`
- 失败重试策略（指数退避）
- 候选文章发现入口（从 blocked 的列表页中提取具体文章）

---

## 8. LLM 分析边界

### 分析链路

```
正文清洗（去除广告、导航、HTML 噪声）
    ↓
内容截断（超长文章只取前 N 字符）
    ↓
Prompt 注入防护（去除用户输入干扰）
    ↓
LLM JSON 输出（结构化 InsightCard）
    ↓
JSON 解析失败处理（降级或保存原始文本）
    ↓
InsightCard 保存到数据库
    ↓
可选：中英双语核心理解生成
    ↓
用户做出个人判断
    ↓
Markdown 报告 / 行动任务导出
```

### 保真原则

输出要区分：

- **原文事实**：文章明确描述的事件、数据、结果
- **原文观点**：文章作者表达的立场和判断
- **模型推论**：LLM 基于原文的合理延伸（需标注）
- **个人建议**：你基于理解做出的行动判断

### 中文摘要 vs 中英双语核心理解

| | 中文摘要 | 中英双语核心理解 |
|---|---|---|
| **用途** | 快速看懂资料 | 深度阅读和长期沉淀 |
| **语言** | 中文 | 英文原文 + 中文解说 |
| **内容** | 摘要 + 关键事实 + 技术洞察 | 英文核心观点 + 原文主张 + 关键词汇 + 中文解说 + 保真提示 |
| **生成速度** | 较快 | 较慢（需要更多 LLM 调用） |

### V1.0-alpha 不做什么

- 不做多语言混合输出（始终保留英文原文作为事实锚点）
- 不做实时信息追踪（无后台任务、无定时抓取）
- 不做全网搜索（只从精选来源获取）
- 不追求 LLM 输出的"完整性"（允许 JSON 解析失败降级）

---

## 9. 当前技术选型

| 模块 | 当前选择 | 原因 |
|------|---------|------|
| **后端框架** | FastAPI | 轻量、适合本地工具和快速验证，异步支持好 |
| **页面渲染** | Jinja2 | MVP 阶段避免复杂前端框架，快速迭代 |
| **数据库** | SQLite | 本地个人工作台足够，方便演示，无运维依赖 |
| **来源配置** | YAML + DB 同步 | 便于人工精选和版本管理 |
| **来源抓取** | httpx + RSS/HTML index probe | 先验证稳定获取链路，避免过早引入爬虫复杂度 |
| **正文解析** | HTML / PDF extractor | 覆盖文章和报告两种主要格式 |
| **LLM 输出** | 结构化 InsightCard | 不是翻译，而是洞察编译，保留判断空间 |
| **URL 识别** | rule-based intake classifier | alpha 阶段可解释、可控，避免 LLM 误判 |
| **CI** | GitHub Actions | 远端自动验收，无需本地配置 |

### 选型原则

V1.0-alpha 不追求最终架构，优先验证可信信息处理流水线。

技术选型的核心标准：**可解释、可本地运行、可人工验收**。

---

## 10. V1.0-alpha 不做什么

- **多用户/登录注册** — 单用户本地工具
- **高并发支持** — SQLite 本地数据库
- **数据库迁移系统** — 模型变更后需重建 DB
- **实时信息追踪** — 无后台任务、无定时抓取
- **全网搜索** — 只从精选来源获取
- **复杂归档系统** — 不做批量删除和复杂归档
- **多语言混合输出** — 始终保留英文原文作为事实锚点
- **复杂前端框架** — Jinja2 MVP，快速迭代

---

## 11. V1.0-beta 后续方向

- [ ] SourceCursor：基于时间游标只关注新增资料
- [ ] 更细的失败状态（blocked_by_intake / needs_discovery / failed_fetch / failed_llm）
- [ ] 失败重试策略（指数退避）
- [ ] 候选文章发现入口（从 blocked 的列表页中提取具体文章）
- [ ] 用户自定义来源优先级
- [ ] 完整数据库迁移系统（Alembic）
- [ ] 完整归档系统（批量删除、来源归档）
- [ ] 多来源交叉编译（同一事件跨来源整理）
- [ ] 真实 LLM 质量人工验收

---

## 相关文档

- [产品路线图](PRODUCT_SHAPE_ROADMAP.md)
- [LLM Pipeline 与质量](LLM_PIPELINE_AND_QUALITY.md)
- [输入分类与总结策略](INPUT_CLASSIFICATION_AND_SUMMARY_STRATEGY.md)
- [架构总览](ARCHITECTURE_OVERVIEW.md)
- [最终验收文档](V1.0_ALPHA_FINAL_RELEASE_ACCEPTANCE.md)
