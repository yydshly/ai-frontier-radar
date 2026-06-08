# AI Frontier Radar 实现原理说明

## 1. 启动入口

- **主入口**：`app/main.py`
- **Web 框架**：FastAPI + Uvicorn
- **初始化流程**：
  1. `init_db()` 创建所有表（`Base.metadata.create_all`）
  2. `sync_sources_config_to_db()` 将 YAML 来源配置同步到数据库
  3. 挂载 Jinja2 模板和静态文件
  4. 注册路由

启动命令：
```bash
uvicorn app.main:app --reload --port 8779
```

## 2. 数据库模型

### Source（信息来源定义）

用途：定义一个要监控的 AI 前沿信息来源。

关键字段：
- `source_key`：唯一标识符（小写字母+数字+下划线）
- `name`：显示名称
- `description`：描述
- `source_type`：类型（rss / html_index / manual）
- `homepage_url`：来源首页 URL
- `feed_url`：RSS feed URL（rss 类型必须有）
- `category`：分类（company / research / paper / policy / blog / benchmark / funding / open_source）
- `enabled`：是否启用
- `fetch_strategy`：探测策略（rss / html_index）
- `last_checked_at`：最后探测时间
- `last_success_at`：最后成功时间
- `last_error_message`：最后错误信息

关系：一个 Source 有多个 SourceItem 和多个 FetchRun。

### SourceItem（发现的文章条目）

用途：记录从某个 Source 发现的一篇文章。

关键字段：
- `source_id`：关联的 Source
- `source_key`：冗余存储，方便查询
- `url`：文章 URL
- `canonical_url`：规范化后的 URL（去除 fragment 和追踪参数）
- `title`、`author`、`published_at`：文章元数据
- `content_hash`：正文内容的 SHA256（用于去重）
- `status`：处理状态

  当前实际使用状态：
  - `discovered`：已发现，待编译
  - `compiled`：已编译，并关联 InsightCard
  - `failed`：编译或处理失败

  预留状态（未来更细粒度管线可能使用）：
  - `fetched`：未来抓取正文阶段
  - `skipped_duplicate`：未来更细粒度去重流程
- `error_message`：失败原因
- `insight_card_id`：关联的 InsightCard（编译完成后回写）

关系：一个 SourceItem 最多关联一张 InsightCard。

### FetchRun（探测执行记录）

用途：记录每次来源探测的结果。

关键字段：
- `source_id`：关联的 Source
- `run_type`：执行类型（manual / scheduled）
- `status`：执行状态（pending / running / success / partial_failed / failed）
- `items_found`：发现的条目数
- `items_new`：其中新增的条目数
- `items_updated`：其中更新的条目数
- `items_failed`：失败的条目数
- `started_at` / `finished_at`：执行时间
- `error_message`：错误信息

### InsightCard（中文洞察卡）

用途：一张英文文章的中文结构化理解结果。

关键字段：
- `source_url`、`source_type`、`source_title`、`source_author`、`source_published_at`：原文信息
- `content_hash`：正文 hash，用于去重
- `status`：状态（pending / completed / failed）
- `error_message`：失败原因
- `summary_zh`：中文摘要
- `key_points_zh`：关键事实（JSON 列表）
- `technical_insights_zh`：技术洞察（JSON 列表）
- `product_opportunities_zh`：产品机会（JSON 列表）
- `risks_zh`：风险（JSON 列表）
- `action_items_zh`：行动建议（JSON 列表）
- `relevance_score`：相关性评分（0-100）
- `relevance_reasons_zh`：相关性理由（JSON 列表）
- `related_user_directions`：匹配的用户关注方向（JSON 列表）
- `model_name`：生成该卡片的模型名称

关系：一张 InsightCard 最多有一个 BilingualReport 和一个 CardDecision。

### InsightCardBilingualReport（中英双语报告）

用途：V0.8 新增，帮助用户既看懂英文核心内容，又获得中文解说。

关键字段：
- `card_id`：关联的 InsightCard

英文字段（必须为英文）：
- `english_core_summary`：英文核心摘要
- `english_key_claims_json`：原文主要观点（JSON 列表）
- `english_evidence_points_json`：英文证据点（JSON 列表）
- `key_terms_json`：关键术语中英对照（JSON 列表，每项含 en/zh/note_zh）

中文字段（必须为中文）：
- `chinese_explanation`：中文解说
- `fidelity_notes_zh`：保真提示
- `interpretation_boundary_zh`：解读边界

关系：一个 BilingualReport 只属于一张 InsightCard。

### CardDecision（用户判断）

用途：用户读完 InsightCard 后做的判断和备注。

关键字段：
- `card_id`：关联的 InsightCard（唯一约束，一张卡只有一条当前判断）
- `decision`：判断值（worth_attention / related_to_me / read_later / ignore / to_action）
- `note`：用户备注（可选）

关系：一张 InsightCard 最多有一条 CardDecision。

## 3. 来源配置加载

### 配置文件

- `config/sources.example.yaml`：捆绑的示例配置（纳入版本控制）
- `config/sources.yaml`：用户本地自定义配置（不提交到版本控制）

### 配置加载流程

1. `config_loader.py` 的 `_find_config_file()` 优先找 `sources.yaml`，找不到则用 `sources.example.yaml`
2. YAML 解析后经过严格验证（类型检查、必填字段检查）
3. 返回 `list[SourceConfig]`，被 `db_sync.py` 的 `sync_sources_config_to_db()` 使用

### 同步到数据库

`sync_sources_config_to_db(db, force_reload=False)`：
- `force_reload=False`：增量同步，只创建不存在的 Source，不覆盖已有配置
- `force_reload=True`：全量同步，更新所有字段
- 返回 `{"total", "created", "updated", "enabled"}`

## 4. 来源探测

### RSS 探测

入口：`scripts/probe_rss_sources.py`

流程：
1. 从数据库读取所有 `fetch_strategy=rss` 且 `enabled=True` 的 Source
2. 对每个 Source 调用 `probe_rss_source(db, source)`
3. `probe_rss_source` 使用 `feedparser` 解析 RSS XML
4. 对每个 entry，提取 link、title、author、published date
5. 检查 URL 是否重复（基于 URL 本身，不是 content_hash）
6. 写入 SourceItem

关键参数：
- `--source-key`：只探测指定来源
- `--limit-sources`：最多探测 N 个来源
- `--timeout`：HTTP 超时秒数

### HTML Index 探测

入口：`scripts/probe_html_index_sources.py`

流程：
1. 从数据库读取所有 `fetch_strategy=html_index` 且 `enabled=True` 的 Source
2. 对每个 Source 调用 `probe_html_index_source(db, source)`
3. 用 `httpx` 获取 HTML 页面
4. 用 BeautifulSoup 提取所有 `<a href>` 链接
5. 过滤掉列表页、导航页、分页页、静态资源
6. 保留符合来源预期内容类型的 URL（`expected_content` 检查）

过滤规则（`quality.py`）：
- URL path 以 `/blog`、`/news`、`/research` 开头但没有二级 path 的视为列表页
- 带有 `?p=`、`?page=`、`?sort=`、`?tag=` 等分页/筛选参数的视为列表页
- `expected_content` 字段描述来源期望的文章类型，不符合的 URL 会被标记为 `suspected_off_topic`

去重：基于 URL 本身（`canonical_url`），相同 URL 第二次探测会更新 `last_seen_at` 而不是创建新条目。

## 5. SourceItem 编译

### 编译触发

用户从 `/source-items` 列表点击「进入详情并编译」，POST 到 `POST /source-items/{id}/compile`。

### compile_url() 管线

`app/services/insight_compiler.py` 的 `compile_url(db, url)` 执行以下步骤：

**Step 1: fetch_url(url)**
- 使用 `httpx` 发送 HTTP GET 请求
- 根据 `Content-Type` header 判断是 HTML 还是 PDF
- 支持重试（`FETCH_RETRY_COUNT` 次）

**Step 2: extract_content(url, content, content_type)**
- HTML：优先用 `trafilatura` 提取正文，失败时用 BeautifulSoup + readability
- PDF：用 `pypdf` 提取文本
- 返回 `(text, title, author, source_type)`

**Step 3: clean_text(text)**
- 移除多余空白、导航残留、页脚噪音
- 截断超过 `MAX_SOURCE_CHARS`（60,000 字符）的部分

**Step 4: compute_content_hash(cleaned_text) + check_duplicate(db, url, hash)**
- 对清洗后的正文计算 SHA256
- 查重：相同 URL + 相同 hash 的卡片已存在则返回已有卡片

**Step 5: LLM 生成**
- 调用 `create_llm_client()` 创建模型客户端
- 传入 `INSIGHT_SYSTEM_PROMPT` + `build_insight_user_prompt()`
- `client.generate_json()` 返回结构化 JSON

**Step 6: 构建并保存 InsightCard**
- 将 LLM 返回的字段写入数据库
- JSON 列表字段（key_points、technical_insights 等）用 `json.dumps()` 存储

### 幂等保护

- `discovered` 状态：调用 `compile_url()` 执行完整编译
- `compiled` 状态：跳过编译，直接返回已有卡片
- `failed` 状态：允许重新编译（重试）

### 失败处理

任何一步抛出异常，都会创建 `status=failed` 的 InsightCard，记录 `error_message`。不会让用户看到 500 错误。

## 6. InsightCard

### 生成内容

LLM 根据 `INSIGHT_SYSTEM_PROMPT` 和 `build_insight_user_prompt()` 生成：

- `summary_zh`：中文摘要（一段话概括文章主旨）
- `key_points_zh`：关键事实（3-5 条客观事实）
- `technical_insights_zh`：技术洞察（2-4 条技术层面的深度分析）
- `product_opportunities_zh`：产品机会（1-3 条可以做什么）
- `risks_zh`：风险与注意事项（1-3 条）
- `action_items_zh`：行动建议（1-3 条具体可执行的动作）
- `relevance_score`：相关性评分（0-100）
- `relevance_reasons_zh`：为什么评分是这个值
- `related_user_directions`：和用户关注方向的相关性

### 质量检查

`inspect_insight_card_quality(card)` 验证：
- `summary_zh` 非空
- 至少 2 个结构化字段非空
- `relevance_score > 0`
- 中文语言检测（`_looks_chinese()`）

检查失败会记录 warning，但不阻止保存。

## 7. BilingualReport

### 为什么单独建表

V0.8 的中英双语报告是一个独立的数据层，复用 InsightCard 的关联，但单独存储。

这样设计的原因：
- InsightCard 的核心价值是中文摘要，BilingualReport 是增强层，不破坏原有的中文洞察结构
- 一张卡可以只有 InsightCard，没有 BilingualReport
- 后续可以独立重生成 BilingualReport 而不影响 InsightCard

### 生成时机

用户在 `/cards/{id}` 详情页点击「生成中英双语报告」时调用 API 生成。不是编译时自动生成。

### 英文字段必须英文

- `english_core_summary`：英文摘要，必须是英文
- `english_key_claims_json`：原文主张，必须是英文
- `english_evidence_points_json`：证据点，必须是英文
- `key_terms_json`：术语表，en 字段是英文

### 中文字段必须中文

- `chinese_explanation`：中文解说
- `fidelity_notes_zh`：保真提示
- `interpretation_boundary_zh`：解读边界

### 保真原则

原文主张不能混入模型推论。产品机会和行动建议不是原文结论，是模型的推断。解读边界要明确说明这一点。

## 8. CardDecision

### 五种判断

- `worth_attention`：值得关注，值得进一步关注
- `related_to_me`：与我有关，和我的项目/方向相关
- `read_later`：稍后再看，现在没空但以后可能有用
- `ignore`：暂时忽略，对我没用
- `to_action`：转成行动，要做成什么具体事情

### 数据设计

- `card_id` 有唯一约束：一张 InsightCard 只有一条当前决策
- 重复提交同一卡片的决策是 UPDATE，不是 INSERT
- `note` 字段是用户自由文本，可以写"和 XX 项目有关"或"下一步要调研 YY"

### 页面入口

`/cards/{id}` 详情页底部有「🧭 看完后的判断」区块，显示当前判断和 5 个单选按钮。

## 9. Markdown 导出

### build_action_markdown()

`app/exports/markdown_task.py` 的 `build_action_markdown(card, decision, bilingual_report)` 是一个纯函数，无副作用。

构建顺序：
1. 原文信息（标题、链接、作者、时间、相关性分数、用户判断）
2. 中文摘要
3. 为什么值得行动（relevance_reasons）
4. 关键事实、技术洞察、产品机会、风险、行动建议
5. 匹配的关注方向
6. V0.8 中英双语核心理解（English Core Summary、Original Key Claims、Key Evidence Points、Key Terms EN-ZH、 中文解说、保真提示与解读边界）
7. 可交给 AI 执行模型的任务草稿（4 个引导问题）

双语报告注入：传入 `bilingual_report` 参数时才会渲染第 6 部分；否则显示"暂无双语报告"。

## 10. 验收脚本

| 脚本 | 说明 |
|------|------|
| `smoke_test.py` | 冒烟测试：健康检查、页面加载、配置加载、数据库写入 |
| `acceptance_probe_sources.py` | 探测链路验收：验证 RSS 和 HTML Index 探测的幂等性 |
| `acceptance_compile_source_item.py` | 编译链路验收：mock-success、mock-failed、use-existing-item 三种模式 |
| `acceptance_card_decision.py` | 用户判断验收：5 种判断的创建和更新 |
| `acceptance_card_decision_filter.py` | 判断过滤验收：验证 `/cards?decision=xxx` 筛选功能 |
| `acceptance_export_action_markdown.py` | Markdown 导出验收：验证 `build_action_markdown()` 输出 |
| `acceptance_home_workbench.py` | 首页工作台验收：统计数字、下一步建议、快捷入口 |
| `acceptance_real_source_coverage.py` | 真实来源覆盖验收：多来源真实探测 |
| `acceptance_cross_source_compile.py` | 跨来源编译验收：从多个真实来源编译 InsightCard |
| `acceptance_bilingual_report.py` | 双语报告验收（mock 模式） |
| `acceptance_real_bilingual_report.py` | 双语报告验收（真实 LLM 模式） |

注意：所有 acceptance 脚本都支持 `--isolated-db` 使用独立数据库，不污染主数据。

## 11. 常见问题

### feedparser 缺失

运行 `probe_rss_sources.py` 时报错 `No module named 'feedparser'`：
```bash
pip install feedparser
```

### API Key 缺失

运行编译时报错 `MINIMAX_API_KEY is not configured`：
- 确认 `.env` 文件存在且包含 `MINIMAX_API_KEY=你的Key`
- 确认 `config/llm_profiles.yaml` 存在

### source_key 不存在

运行探测时报错 `source_key 'xxx' not found`：
- 检查 `config/sources.yaml` 中是否存在该 source_key
- 检查是否拼写错误（区分大小写）

### HTML 来源返回 403

部分来源（如 OpenAI News）会返回 HTTP 403：
- 这是来源侧的反爬机制，不是代码问题
- 换用其他来源验证，如 `huggingface_blog` 或 `anthropic_news`

### JSON 解析失败

LLM 返回了非 JSON 内容：
- 当前会自动重试一次
- 如果重试仍然失败，创建 failed InsightCard

### SQLite 旧表缺列问题

代码新增字段后，SQLAlchemy 的 `create_all()` 不会自动 ALTER TABLE：
- 当前使用 `Base.metadata.create_all`，不会迁移旧数据库
- 删除旧数据库文件重新初始化：`rm data/ai_frontier_radar.db`
- 后续版本考虑引入 Alembic 迁移
