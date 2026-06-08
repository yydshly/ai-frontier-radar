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

## V0.2 Source Registry 与来源探测链路

V0.2 在 V0.1 基础上新增了**来源配置 → 探测 → 发现 → 手动编译**的完整闭环。

### ✅ 已完成能力

- Source 配置加载（YAML → DB 同步）
- Source / SourceItem / FetchRun ORM 模型
- `/sources` 来源列表页面
- RSS Source 探测脚本（`probe_rss_sources.py`）
- HTML Index Source 探测脚本（`probe_html_index_sources.py`）
- `/source-items` 发现条目列表页面（含筛选、搜索）
- `/source-items/{item_id}` 发现条目详情页
- 单条 SourceItem 手动编译为 InsightCard（POST `/source-items/{item_id}/compile`）

### 核心命令

```bash
# 验证来源配置
python scripts/check_sources_config.py

# RSS 来源探测（访问真实网络）
python scripts/probe_rss_sources.py

# HTML Index 来源探测（访问真实网络）
python scripts/probe_html_index_sources.py

# 冒烟测试（不访问真实网络，不调用真实 LLM）
python scripts/smoke_test.py
```

> **注意**：`probe_rss_sources.py` 和 `probe_html_index_sources.py` 会访问真实网络；`smoke_test.py` 不依赖真实网络或真实 LLM。

### 页面入口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sources` | 信息来源列表 |
| GET | `/source-items` | 发现条目列表（支持按来源/状态/关键词筛选） |
| GET | `/source-items/{item_id}` | 发现条目详情页 |
| POST | `/source-items/{item_id}/compile` | 手动编译该条目为 InsightCard |
| GET | `/cards` | InsightCard 列表 |
| GET | `/cards/{card_id}` | 卡片详情 |

### V0.2 暂不做

- 批量编译
- 后台调度 / 定时任务
- 探测后自动编译
- 多用户 / 登录注册
- 生产级数据库迁移（Alembic）
- 复杂正文抓取质量治理
- 完整推荐系统

### V0.2 技术债

- 当前仍使用 `Base.metadata.create_all`，暂不使用 Alembic 迁移
- `probe_rss_source` / `probe_html_index_source` 内部存在 `commit`，批量任务前建议统一事务边界
- SourceItem 手动编译是同步请求，长耗时 URL 或 LLM 调用会阻塞请求
- 尚未实现编译中间状态（如 `compiling`）
- 真实网络探测结果尚未纳入 smoke_test

> **V0.2.8** 重点补充了真实链路验收记录、空 URL 编译防护测试、详情页状态提示增强。

## V0.3 精选 AI 前沿来源导航 UI

V0.3 在 V0.2 来源探测链路基础上，新增**精选来源导航 UI**，降低用户发现成本。

### ✅ 已完成能力

- 首页展示精选 AI 前沿来源卡片网格（P0 / P1 / P2 分级）
- 每个来源包含图标、名称、分类、关注重点、操作按钮
- 来源覆盖：OpenAI、Anthropic、DeepMind、Hugging Face、arXiv、NVIDIA、Microsoft、Meta、Stanford HAI、MIT、Berkeley BAIR、Mistral AI、Cohere
- 操作按钮：访问官网、查看系统来源、查看发现条目
- `/sources` 页面增强操作列，可快速跳转发现条目

### 精选来源分级

| 优先级 | 来源 |
|--------|------|
| P0（必看） | OpenAI、Anthropic、DeepMind、Hugging Face、arXiv AI、NVIDIA AI |
| P1（推荐） | Meta AI、Microsoft AI、Stanford HAI、MIT AI、Berkeley BAIR、Mistral AI、Cohere |
| P2（补充） | arXiv NLP、arXiv ML |

### 页面入口

访问首页即可看到精选来源卡片区，无需配置即可了解系统追踪范围。

## V0.3.1 真实来源探测验收

V0.3.1 验证最小真实来源探测链路，确认系统能从已配置来源中稳定发现 SourceItem。

### 本阶段目标

- ✅ 探测脚本支持 `--source-key`、`--limit-sources`、`--timeout` 参数
- ✅ 可针对单个来源做可控验收
- ✅ 重复运行不会重复插入相同 URL
- ✅ 失败来源有明确错误信息

### 核心命令

```bash
# 只探测单个 RSS 来源
python scripts/probe_rss_sources.py --source-key arxiv_cs_cl --timeout 15

# 只探测单个 HTML Index 来源
python scripts/probe_html_index_sources.py --source-key huggingface_blog --timeout 15

# 探测多个 RSS 来源（最多 N 个）
python scripts/probe_rss_sources.py --limit-sources 2 --timeout 15

# 探测多个 HTML Index 来源（最多 N 个）
python scripts/probe_html_index_sources.py --limit-sources 2 --timeout 15

# 运行最小真实验收（默认探测 arxiv_cs_cl + huggingface_blog）
# --isolated-db 使用独立 DB，避免污染主数据
# --repeat 2 验证幂等性
python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15
```

### 说明

- 本阶段**只发现 SourceItem**，不抓取正文，不调用 LLM
- 查看发现结果：访问 `/source-items` 页面
- 失败来源的错误信息可在 `/sources` 页面或数据库 FetchRun 表中查看
- **注意**：`openai_news` 可能返回 403；`arxiv.org` RSS 近期可能返回 0 条目。如遇此类情况，换用 `--html-source deepmind_blog` 或 `--html-source anthropic_news` 验证
- `acceptance_probe_sources.py` 默认使用独立 DB，运行后默认清理；传 `--keep-db` 可保留 DB 方便排查

### 页面入口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/source-items` | 查看已发现的条目 |
| GET | `/source-items?source_key=arxiv_cs_ai` | 按来源筛选 |
| GET | `/sources` | 查看各来源最后探测时间与状态 |

## V0.3.2 SourceItem 编译为 InsightCard

V0.3.2 在 V0.3.1 基础上，将单条 SourceItem 手动编译为 InsightCard 的链路做成可验收、可防重复、可排查的最小闭环。

### 核心链路

```
SourceItem(discovered)
-> 手动触发 POST /source-items/{id}/compile
-> 调用现有 compile_url()
-> 生成 InsightCard(completed 或 failed)
-> 回写 SourceItem.insight_card_id
-> 回写 SourceItem.status = compiled / failed
-> 页面可查看关联 InsightCard
-> 重复点击不会无意义重复编译（幂等）
-> 失败可重试
```

### 验收脚本

```bash
# mock-success 模式：不调用真实 LLM，验证完整链路
python scripts/acceptance_compile_source_item.py --isolated-db --mock-success

# mock-failed 模式：验证失败时仍写入 insight_card_id 和 error_message
python scripts/acceptance_compile_source_item.py --isolated-db --mock-failed

# use-existing-item 模式：使用已有 SourceItem 验证真实编译
# 需要先运行 acceptance_probe_sources.py 生成 SourceItem
python scripts/acceptance_compile_source_item.py --isolated-db --use-existing-item --source-key huggingface_blog
```

### 说明

- 真实编译依赖 URL 可访问、正文可提取、LLM API Key 可用
- API Key 缺失时会生成 failed InsightCard，并回写 `SourceItem.status=failed`
- 已 compiled 的 SourceItem 重复 POST 不会重新调用 `compile_url`（幂等保护）
- failed 状态可重试，重试成功后 `error_message` 会被清空

### 页面入口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/source-items` | 查看 SourceItem 列表（含编译状态提示） |
| GET | `/source-items/{id}` | 查看详情，含编译按钮 |
| POST | `/source-items/{id}/compile` | 手动编译该条目为 InsightCard |
| GET | `/cards/{id}` | 查看生成的 InsightCard |

## V0.3.3 SourceItem 质量过滤

V0.3.3 解决 HTML Index Probe 误收录列表页、分页页、分类页的问题。

### 问题描述

HTML Index Probe 会把博客列表页、新闻分类页、分页导航页误判为文章详情页，例如：

- `https://huggingface.co/blog?p=2` — 博客分页页
- `https://huggingface.co/blog?sort=popular` — 博客筛选页
- `https://huggingface.co/blog?tag=agents` — 博客标签页

这些 URL 可以被编译成 InsightCard，但内容是"聚合摘要"而非单篇文章，不符合系统设计目标。

### 过滤规则

**过滤的 URL 模式：**

```text
/blog              # 列表页本身
/blog?p=2          # 分页参数
/blog?page=3       # 分页参数
/blog?sort=popular # 排序/筛选参数
/blog?tag=agents   # 标签参数
/news              # 列表页
/news?page=2       # 分页参数
/research          # 列表页
/research?topic=...# 话题参数
```

**保留的 URL 模式：**

```text
/blog/open-r1              # 文章详情页
/blog/smolagents           # 文章详情页
/news/model-release         # 文章详情页
/research/agent-safety     # 文章详情页
```

**判断逻辑：**

1. URL 规范化：去除 fragment 和 utm_* 等追踪参数，保留必要的内容参数
2. 列表页 path 判断：单级 path 为 blog/news/research/articles 等时，判定为列表页
3. 分页/筛选参数判断：识别 `p`、`page`、`sort`、`tag`、`search` 等 query 参数
4. 详情页判断：两级以上 path segment（如 `/blog/slug`）或带年份 path（如 `/2025/news`）

### 验收命令

```bash
# 语法检查
python -m compileall app scripts

# 来源配置检查
python scripts/check_sources_config.py

# 质量过滤 smoke test
python scripts/smoke_test.py

# 真实探测验收
python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15 --html-source huggingface_blog
```

### 人工检查要点

acceptance 输出中的 **Top discovered SourceItems** 不应包含：

- `https://huggingface.co/blog?p=2` 等分页 URL
- `https://huggingface.co/blog?page=...` 等分页 URL
- `https://huggingface.co/blog?sort=...` 等筛选 URL
- `https://huggingface.co/blog?tag=...` 等标签 URL

应只出现 `/blog/{slug}` 类型的文章详情页 URL。

### 第二次幂等验证

```bash
python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15 --html-source huggingface_blog
```

第二次运行应满足：

- `items_new = 0`（不产生新条目）
- `items_updated > 0`（更新已有条目时间戳）

## V0.3.4 SourceItem 列表可读性与历史分页数据检查

V0.3.4 解决 `/source-items` 页面可读性问题，并提供历史疑似分页 SourceItem 的检查脚本。

### 页面改进

- 宽屏布局：`main` 容器使用 `wide-page` 类，最大宽度提升到 `min(1600px, calc(100vw - 64px))`
- 横向滚动表格：表格包在 `table-scroll` 容器中，支持 `overflow-x: auto`
- URL 完整显示：URL 不再截断为 80 字符，`<a>` 带 `title="{{ item.url }}"` 鼠标悬停可看完整 URL
- 标题点击进入详情：标题列 `<a href="/source-items/{id}">` 直接跳转详情页
- 状态中文辅助：`discovered` 显示「待编译」，`compiled` 显示「已编译」，`failed` 显示「失败」
- 历史数据提示：页面顶部显示 V0.3.3 历史分页 URL 提示，引导用户使用检查脚本

### 历史数据说明

- V0.3.3 只阻止新分页 URL 入库，不会自动清理旧数据
- 旧数据库中可能仍有 `/blog?p=2`、`/blog?p=1`、`/blog?sort=popular` 这类历史记录
- 本轮提供非破坏性检查脚本 `scripts/check_listing_source_items.py`
- 脚本只检查，不删除，不修改状态

### 检查命令

```bash
# 检查所有来源的疑似分页 SourceItem
python scripts/check_listing_source_items.py

# 只检查 huggingface_blog
python scripts/check_listing_source_items.py --source-key huggingface_blog

# 限制显示条数（默认 200）
python scripts/check_listing_source_items.py --limit 100
```

输出示例：

```text
Potential listing SourceItems:
  #44   huggingface_blog        discovered https://huggingface.co/blog?p=...
  #43   huggingface_blog        compiled  https://huggingface.co/blog?p=2

Total suspected listing items: 4
```

如果数据库中无历史脏数据：

```text
No suspected listing SourceItems found.
```

### 页面手动验收

```bash
uvicorn app.main:app --reload --port 8779
```

打开 `http://127.0.0.1:8779/source-items?source_key=huggingface_blog`，确认：

- 页面主体变宽（容器最大宽度提升）
- 浏览器窗口较窄时，表格支持横向滚动
- URL 单元格可显示完整 URL，不再被截断
- 标题列点击可进入 SourceItem 详情页
- 状态列下方有中文辅助文字
- 页面顶部有 V0.3.3 历史分页 URL 提示

## V0.3.5 中文优先人工验收体验

V0.3.5 不是新增编译能力，而是帮助英语能力有限的中文用户更容易从英文 SourceItem 中选择资料，并完成端到端验收。

### 改动

- `/source-items` 页面增加中文「如何使用这个页面？」引导
- `/source-items` 表格新增「推荐操作」列：
  - `discovered` → 「进入详情并编译」
  - `compiled` → 「查看中文卡片」
  - `failed` → 「查看失败原因 / 重试」
- `/source-items/{id}` 详情页增加「这是什么？」中文说明
- 编译按钮附近增加场景化中文提示（discovered / failed / compiled 三态分别说明）
- 新增 [docs/V0.3.5_MANUAL_ACCEPTANCE.md](docs/V0.3.5_MANUAL_ACCEPTANCE.md) 端到端人工验收文档

### 不做什么

- 不做批量翻译所有 SourceItem
- 不做批量编译
- 不做后台队列
- 不做自动推荐算法
- 不做向量数据库 / 知识图谱
- 不新增 `title_zh` 字段
- 不调用 LLM 批量分析 SourceItem

### 验收命令

```bash
# 探测 huggingface_blog（重复 2 次，确认幂等）
python scripts/acceptance_probe_sources.py --repeat 2 --timeout 15 --html-source huggingface_blog

# 启动 web 服务
uvicorn app.main:app --reload --port 8779
```

浏览器打开 `http://127.0.0.1:8779/source-items?source_key=huggingface_blog`，确认：

- 页面有「如何使用这个页面？」中文引导
- 表格有「推荐操作」列
- `discovered` 条目显示「进入详情并编译」
- `compiled` 条目显示「查看中文卡片」
- `failed` 条目显示「查看失败原因 / 重试」
- 详情页能说明「这是英文前沿资料，可以编译为中文 InsightCard」

完整验收步骤见 [docs/V0.3.5_MANUAL_ACCEPTANCE.md](docs/V0.3.5_MANUAL_ACCEPTANCE.md)。

## V0.4 产品目标闭环：InsightCard 用户决策

V0.4 不是新增抓取能力，而是补齐用户看完 InsightCard 后的处理动作。

### 产品闭环

```text
待编译资料收件箱
→ 单条编译
→ 中文 InsightCard
→ 用户判断（这一步是用户自己的判断，不是模型判断）：
   - 值得关注
   - 与我有关
   - 稍后再看
   - 暂时忽略
   - 转成行动
```

### 新增数据

- 新表 `card_decisions`（由 `init_db()` / `create_all()` 自动创建，不修改 `insight_cards` 现有字段）
- 一张 InsightCard 只保留一条当前决策（`card_id` 唯一）
- 重复提交同一卡片的决策：update，不 insert
- 不调用 LLM，不新增 `title_zh` 字段

### 页面改动

- `/cards/{id}` 详情页底部新增「🧭 看完后的判断」区块
  - 显示当前判断（默认「未处理」）
  - 5 个单选：值得关注 / 与我有关 / 稍后再看 / 暂时忽略 / 转成行动
  - 可选 note 文本框（记下为什么、和哪个项目有关、下一步想做什么）
  - failed 状态会提示「可以先标记「稍后再看」或「暂时忽略」」
- `/cards` 列表新增「处理状态」列，显示每张卡的用户判断

### 验收命令

```bash
# 端到端验收（isolated DB，不污染本地）
python scripts/acceptance_card_decision.py --isolated-db

# Smoke test
python scripts/smoke_test.py
```

### 不做什么

- 不做多用户 / 登录注册
- 不做推荐算法
- 不做自动评分
- 不做批量处理
- 不做任务管理系统
- 不做 Notion 同步

完整产品验收步骤见 [docs/V0.4_PRODUCT_LOOP_ACCEPTANCE.md](docs/V0.4_PRODUCT_LOOP_ACCEPTANCE.md)。

## V0.4.1 按处理状态过滤 InsightCard

V0.4 已允许用户对卡片做判断；V0.4.1 允许用户在 `/cards` 页面按判断结果筛选和回看。

### 支持的过滤值

| Query | 含义 |
|-------|------|
| `?decision=unhandled` | 只看还没有判断的卡片 |
| `?decision=worth_attention` | 只看「值得关注」 |
| `?decision=related_to_me` | 只看「与我有关」 |
| `?decision=read_later` | 只看「稍后再看」 |
| `?decision=ignore` | 只看「暂时忽略」 |
| `?decision=to_action` | 只看「转成行动」 |
| 空 | 显示全部 |

非法 `decision` 值不会 500，会按"全部"显示。

### 页面改动

- `/cards` 页面标题升级为「🗂️ 中文洞察卡工作台」
- 顶部新增处理状态下拉筛选 + 筛选/清空按钮
- 筛选后显示「共找到 X 张卡片（已筛选：xxx）」
- 无结果时显示「当前筛选条件下没有 InsightCard。」
- 顺手消除 N+1：每张卡不再单独查询 `CardDecision`，改为单次 `IN` 查询

### 验收命令

```bash
# 端到端验收（isolated DB，不污染本地）
python scripts/acceptance_card_decision_filter.py --isolated-db

# Smoke test
python scripts/smoke_test.py
```

V0.4.1 polish：筛选结果显示中文处理状态；筛选后 0 结果也显示数量；smoke test 不应污染本地数据库。

### 不做什么

- 不做复杂统计
- 不做推荐算法
- 不做导出
- 不做任务管理
- 不做 dashboard 看板

## V0.5 将"转成行动"的 InsightCard 导出为 Markdown 任务

V0.5 不是任务管理系统，而是把一张中文洞察卡整理成**可复制、可下载、可交给 AI 执行模型继续处理**的 Markdown 任务草稿。

### 产品闭环

```
英文资料
→ 中文 InsightCard
→ 标记"转成行动"
→ 导出 Markdown 任务
→ 复制给 AI 执行模型或保存到本地
```

### 使用路径

```
/cards?decision=to_action
→ 打开卡片详情
→ 点击"导出为 Markdown 任务"
→ 预览页面 → 下载 .md 文件
```

### 新增文件

- `app/exports/__init__.py` — export 模块入口
- `app/exports/markdown_task.py` — `build_action_markdown()` 纯函数
- `app/templates/card_export_markdown.html` — Markdown 预览页面
- `scripts/acceptance_export_action_markdown.py` — V0.5 验收脚本

### 验收命令

```bash
python scripts/acceptance_export_action_markdown.py --isolated-db
python scripts/smoke_test.py
```

### 不做什么

- 不做批量导出
- 不做 Notion / 飞书 / GitHub 同步
- 不做任务管理系统
- 不做 LLM 二次改写

完整产品验收步骤见 [docs/V0.5_ACTION_MARKDOWN_EXPORT_ACCEPTANCE.md](docs/V0.5_ACTION_MARKDOWN_EXPORT_ACCEPTANCE.md)。

## V0.6 首页升级为个人 AI 前沿工作台

V0.6 将首页从普通入口页升级为工作台，让用户打开系统后立即知道当前状态和下一步动作。

### 产品闭环

```
首页
→ 待编译资料
→ 中文洞察卡
→ 用户判断
→ 转成行动
→ Markdown 任务导出
```

### 新增内容

- **统计概览**：待编译资料、未处理卡片、值得关注、转成行动
- **下一步建议**：根据当前数据状态给出规则化行动建议
- **快捷入口**：快速跳转到收件箱、洞察卡、行动任务、信息来源
- **最近待编译资料**：最近 5 条 SourceItem
- **最近中文洞察卡**：最近 5 张 InsightCard（含 to_action 导出入口）
- **保留**：手动 URL 编译入口、精选来源展示

### 验收命令

```bash
python scripts/acceptance_home_workbench.py --isolated-db
python scripts/smoke_test.py
```

### 不做什么

- 不做复杂统计图表
- 不做 ECharts / Chart.js
- 不做多用户 / 登录注册
- 不做后台任务 / 批量编译

完整产品验收步骤见 [docs/V0.6_HOME_WORKBENCH_ACCEPTANCE.md](docs/V0.6_HOME_WORKBENCH_ACCEPTANCE.md)。

## V0.7 真实高价值来源覆盖与探测稳定性

V0.7 验证系统能从多个高价值英文 AI 来源（Anthropic、DeepMind、Mistral）发现真实文章，而不是只依赖单一来源。

### 验收命令

```bash
python scripts/acceptance_real_source_coverage.py --isolated-db --repeat 2 --timeout 15
python scripts/check_source_item_quality.py --source-key anthropic_news
python scripts/check_source_item_quality.py --source-key deepmind_blog
python scripts/check_source_item_quality.py --source-key mistral_ai_news
```

### V0.7.1 加强来源质量判断

V0.7.1 加强了来源质量判断：不仅判断是否列表页，还判断是否符合来源预期内容类型。

- DeepMind `/models/` 页面会被标记为 `suspected_off_topic`，不再算作 `deepmind_blog` 的高质量博客文章
- 配置中的 Mistral source_key 为 `mistral_ai_news`

### 本轮不做什么

- 不批量探测全部来源
- 不做后台调度
- 不做浏览器自动化
- 不调用 LLM

完整产品验收步骤见 [docs/V0.7_REAL_SOURCE_COVERAGE_ACCEPTANCE.md](docs/V0.7_REAL_SOURCE_COVERAGE_ACCEPTANCE.md)。

## V0.7.2 跨来源单条编译质量验收

V0.7.1 验证了 URL 质量（expected_content 判断）；V0.7.2 验证这些高质量 SourceItem 能否进入正文抓取和 InsightCard 编译链路。

### 验收命令

Mock 模式（不调用真实 LLM，验证链路）：

```bash
python scripts/acceptance_cross_source_compile.py --isolated-db --mock-llm
```

真实模式（验证端到端）：

```bash
python scripts/acceptance_cross_source_compile.py --isolated-db --source-key anthropic_news --source-key mistral_ai_news
```

### 验收目标

从 Anthropic / Mistral / DeepMind 各选择 1 条 expected_content SourceItem，完整编译为中文 InsightCard，验证：

1. 不同来源的 expected URL 能否被正文抓取器处理
2. 编译成功时 InsightCard 是否有中文摘要、关键事实、技术洞察、产品机会、行动建议
3. 编译失败时是否能留下明确 error_message
4. SourceItem 是否正确回写 status 和 insight_card_id

### 最低质量标准

`passed_minimum_quality=True` 当且仅当：

- summary_zh 非空
- 至少 2 个结构化字段（key_points / technical_insights / product_opportunities / action_items）非空
- relevance_score > 0

完整产品验收步骤见 [docs/V0.7.2_CROSS_SOURCE_COMPILE_ACCEPTANCE.md](docs/V0.7.2_CROSS_SOURCE_COMPILE_ACCEPTANCE.md)。

## V0.8 中英双语 InsightCard 与原文保真解释

V0.8 不是单纯翻译，而是在中文洞察卡中增加英文核心内容和中文解说。

### 目标
让用户在不强读英文全文的情况下，既能看到英文核心内容，又能获得中文解释。

### 英文部分（保留原文主旨）
- **English Core Summary**：英文核心摘要，忠实概括原文
- **Original Key Claims**：原文主要观点/主张，英文表达
- **Key Evidence Points**：英文证据点/支撑信息
- **Key Terms EN-ZH**：关键术语中英对照表

### 中文部分（帮助理解）
- **中文解说**：通俗中文说明，解释文章在说什么
- **保真提示**：提醒哪些内容来自原文，哪些不应过度解读
- **解读边界**：说明产品机会和行动建议属于模型推论，不等于原文结论

### 边界说明
```
英文核心内容用于保留原文主旨；
中文解说用于帮助理解；
产品机会和行动建议属于模型推论，不等同于原文结论。
```

### 验收命令
```bash
python scripts/acceptance_bilingual_report.py --isolated-db --mock
python scripts/smoke_test.py
```

完整产品验收步骤见 [docs/V0.8_BILINGUAL_INSIGHT_ACCEPTANCE.md](docs/V0.8_BILINGUAL_INSIGHT_ACCEPTANCE.md)。

## V0.8.2 真实 LLM 中英双语报告质量验收

V0.8 验证了中英双语报告的数据结构和页面链路；V0.8.2 验证真实 LLM 输出是否满足保真和语言边界要求。

### 质量标准

英文字段必须为英文，中文字段必须为中文：
- English Core Summary 非空且看起来是英文
- Original Key Claims 至少 2 条且看起来是英文
- 中文解说非空且看起来是中文
- 保真提示非空且看起来是中文
- 解读边界非空且看起来是中文

### 验收命令

Mock 链路验证（不调用真实 LLM）：
```bash
python scripts/acceptance_bilingual_report.py --isolated-db --mock
```

真实 LLM 质量验收（需要 MINIMAX_API_KEY）：
```bash
python scripts/acceptance_real_bilingual_report.py --isolated-db --real
```

> 注意：mock 通过不代表真实模型质量通过。如果没有 API Key，真实模式会输出明确错误。

完整产品验收步骤见 [docs/V0.8.2_REAL_BILINGUAL_QUALITY_ACCEPTANCE.md](docs/V0.8.2_REAL_BILINGUAL_QUALITY_ACCEPTANCE.md)。

## V0.9 中英双语 InsightCard 完整 Markdown 报告导出

V0.9 新增完整 Markdown 报告导出功能，把一张 InsightCard 导出为完整的中英双语资料编译报告。

### 与 V0.5 行动任务导出的区别

- **V0.5 行动任务导出**：面向下一步执行，导出任务草稿
- **V0.9 完整报告导出**：面向知识沉淀、长期复盘和资料保存

### 报告内容

完整报告包含：

```
英文核心摘要（English Core Summary）
原文主张（Original Key Claims）
证据点（Key Evidence Points）
术语中英对照（Key Terms EN-ZH）
中文解说（Chinese Explanation）
中文摘要
关键事实
技术洞察
产品机会
风险
行动建议
保真提示
解读边界
用户判断
后续追问问题
```

### 验收命令

```bash
# 有双语报告的完整验收
python scripts/acceptance_export_full_report.py --isolated-db --with-bilingual

# 无双语报告的完整验收
python scripts/acceptance_export_full_report.py --isolated-db --without-bilingual
```

### 页面入口

- `/cards/{id}` 详情页：「📄 导出完整 Markdown 报告」
- `/cards` 列表：每张卡片的操作列都有「完整报告」链接

完整产品验收步骤见 [docs/V0.9_FULL_MARKDOWN_REPORT_ACCEPTANCE.md](docs/V0.9_FULL_MARKDOWN_REPORT_ACCEPTANCE.md)。

## V1.0-alpha 可演示主流程

V1.0-alpha 固定了一条从资料发现到完整报告导出的演示路径，让用户和后续执行模型都能清楚知道如何从"发现资料"走到"完整报告导出"。

### 主流程

```
首页工作台
→ SourceItem 收件箱（第 2 步）
→ SourceItem 详情
→ InsightCard（第 4～6 步）
→ BilingualReport
→ CardDecision
→ Full Markdown Report
→ Action Markdown Task
```

### 快速演示命令

```bash
python scripts/acceptance_demo_flow.py --isolated-db
```

### 手动演示步骤

1. 启动服务：`uvicorn app.main:app --reload --port 8779`
2. 打开首页：`/`
3. 进入待编译资料收件箱：`/source-items`
4. 选择一条资料并编译
5. 打开 InsightCard
6. 生成中英双语报告
7. 标记用户判断
8. 导出完整 Markdown 报告

### 验收脚本

如果没有真实数据，可以先运行来源探测脚本：

```bash
python scripts/acceptance_real_source_coverage.py --isolated-db --repeat 2 --timeout 15
```

也可以用 `acceptance_demo_flow.py` 验证页面链路是否完整：

```bash
python scripts/acceptance_demo_flow.py --isolated-db
```

详细文档见 [docs/V1.0_ALPHA_DEMO_FLOW.md](docs/V1.0_ALPHA_DEMO_FLOW.md)。

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

### 可访问页面

| 页面 | 路径 |
|------|------|
| 首页 | `/` |
| 待编译资料 | `/source-items` |
| 演示卡片 | 运行 `create_demo_data.py` 后查看脚本输出的 `/cards/{id}` |
| 完整报告 | `/cards/{id}/export-report` |
| 行动任务 | `/cards/{id}/export-markdown` |

首页右侧会出现 **🎬 演示数据入口** 区块，点击即可跳转到对应页面。

### 快速验收命令

```bash
# 创建 demo 数据
python scripts/create_demo_data.py

# 重置 demo 数据（删除后重建）
python scripts/create_demo_data.py --reset-demo

# 验收 demo 数据链路
python scripts/acceptance_demo_data.py --isolated-db
```

详细文档见 [docs/V1.0_ALPHA_1_DEMO_DATA.md](docs/V1.0_ALPHA_1_DEMO_DATA.md)。

## 项目理解与维护文档

如果你是第一次接手项目，建议先阅读 [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md)。

如果你要改代码，先阅读 [docs/IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md)。

如果你要调整模型调用，先阅读 [docs/LLM_PIPELINE_AND_QUALITY.md](docs/LLM_PIPELINE_AND_QUALITY.md)。

如果你要判断产品下一步，先阅读 [docs/PRODUCT_SHAPE_ROADMAP.md](docs/PRODUCT_SHAPE_ROADMAP.md)。

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

## Source Registry 配置

V0.2 新增了信息来源配置模块，可以自定义关注哪些 AI 前沿来源。

### 配置文件

```bash
# 复制示例配置
cp config/sources.example.yaml config/sources.yaml
```

- `config/sources.example.yaml` — 捆绑的示例配置（纳入版本控制）
- `config/sources.yaml` — 用户本地自定义配置（**不提交**，已在 `.gitignore` 中忽略）

### 新增来源

在 `config/sources.yaml` 的 `sources` 节点下新增条目：

```yaml
sources:
  my_source:
    name: "My Source"
    description: "来源描述"
    type: "html_index"
    homepage_url: "https://..."
    feed_url: null
    category: "company"
    tags: ["tag1", "tag2"]
    enabled: true
    fetch_strategy: "html_index"
    relevance_hint: "关注重点..."
    fetch_interval_hours: 24
```

### source_key 命名规则

- 只能包含小写字母、数字、下划线
- 必须以小写字母开头
- 示例：`openai_news`、`anthropic_news`、`arxiv_cs_ai`

### RSS 来源字段要求

```yaml
type: "rss"
feed_url: "https://..."     # 必须有
```

### HTML Index 来源字段要求

```yaml
type: "html_index"
homepage_url: "https://..."  # 必须有
```

### 验证配置

```bash
python scripts/check_sources_config.py
```

应输出：

```
[OK] loaded sources config: config/sources.yaml
[OK] total sources: 10
[OK] enabled sources: 10
[OK] categories: company=3, open_source=1, paper=3, research=3
[OK] strategies: html_index=7, rss=3
```

> **注意**：V0.2 已完整实现来源探测，但探测脚本需要访问真实网络，运行前请确认网络条件。

## 使用流程

### V0.1 — 单篇 URL 手动编译

#### 1. 提交 URL
访问首页 `http://localhost:8000/`，在输入框填入英文 AI 前沿文章 URL，点击提交。

#### 2. 等待处理
系统会抓取正文、清洗内容、调用 LLM 生成 InsightCard。

#### 3. 查看结果
访问 `http://localhost:8000/cards` 查看所有卡片列表，点击详情查看完整内容。

#### 4. 失败排查
如果处理失败，卡片状态为 `failed`，可以在详情页查看错误原因。

### V0.2 — 来源探测链路（推荐）

#### 1. 配置来源
编辑 `config/sources.yaml`，添加或启用要关注的 AI 前沿来源（RSS 或 HTML Index 类型）。

#### 2. 运行探测
```bash
# RSS 来源
python scripts/probe_rss_sources.py

# HTML Index 来源
python scripts/probe_html_index_sources.py
```
探测结果会写入 `source_items` 表，可在 `/source-items` 页面查看。

#### 3. 手动编译
在 `/source-items` 列表页点击感兴趣条目的标题或 ID，进入详情页，点击**编译为 InsightCard**。编译完成后可跳转查看生成的卡片。

#### 4. 查看卡片
访问 `/cards/{id}` 查看编译结果。

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页（URL 输入框） |
| POST | `/compile` | 提交 URL 进行编译 |
| GET | `/sources` | 信息来源列表（V0.2） |
| GET | `/source-items` | 发现条目列表，支持筛选和搜索（V0.2） |
| GET | `/source-items/{item_id}` | 发现条目详情（V0.2） |
| POST | `/source-items/{item_id}/compile` | 手动编译条目为 InsightCard（V0.2） |
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

- [x] RSS 订阅源支持（V0.2.4）
- [x] HTML Index 来源探测（V0.2.5）
- [x] 发现条目列表与详情页（V0.2.6–V0.2.7）
- [x] 真实链路验收与状态增强（V0.2.8）
- [x] 精选 AI 前沿来源导航 UI（V0.3）
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
