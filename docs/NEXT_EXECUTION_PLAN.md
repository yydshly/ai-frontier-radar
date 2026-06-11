# V1.0-beta 下一阶段执行计划

## 产品方向

- **手动工作流**：作为底层能力保留，用户自主控制何时探测、何时生成
- **每日雷达**：作为上层内容消费入口，每日定时推送精选内容

## 当前已完成（First Usable Loop）

```
信息来源 → 后台运行探测 → FetchRun 结果页 → 候选池 → 加入生成 → 生成队列 → InsightCard
```

- ✅ 信息来源管理（YAML + DB）
- ✅ 后台来源探测（BackgroundTasks）
- ✅ FetchRun 详情页（含失败横幅、错误原因解释）
- ✅ 候选池卡片化展示（弱标题降级、摘要提取、时间标签）
- ✅ 生成队列（compiling / compiled / failed / discovered 分区）
- ✅ InsightCard 深度报告
- ✅ 测试数据降噪（`test_*` / `orphan_key` 不污染生产视图）

---

## 下一阶段优先级

### P0 — 必须做（下一版本核心）

| 序号 | 任务 | 说明 |
|------|------|------|
| P0-1 | 真实来源全量验证 | 验证所有已配置来源能稳定探测，发现并修复失败来源 |
| P0-2 | SourceFetchService 写入层 error_message 兜底 | 写入 FetchRun 时确保 error_message 不为空，避免 null 导致横幅显示不友好 |
| P0-3 | 中文一句话摘要展示与生成模块 | AI 生成中文一句话摘要，作为核心理解层，接入 TTS 预留 |
| P0-4 | 每日雷达 MVP | 定时探测 + 每日精选推送页面，作为内容消费主入口 |

---

### P1 — 重要（体验与扩展性）

| 序号 | 任务 | 说明 |
|------|------|------|
| P1-1 | 单来源工作台 | 按来源维度组织内容，便于聚焦单一来源深度消费 |
| P1-2 | 新增来源入口 | 网页表单新增来源，降低用户添加来源门槛 |
| P1-3 | 分页与数据治理 | `/cards` 和首页统计引入分页，防止大数据量性能问题 |
| P1-4 | 项目文档更新 | 架构图更新、新增功能文档、README 与文档同步 |

---

### P2 — 优化（长期改进）

| 序号 | 任务 | 说明 |
|------|------|------|
| P2-1 | delta 精准化 | 基于 content hash 的精确去重 + 增量更新，替代时间窗口估算 |
| P2-2 | repair 标题产品化入口 | 脏标题批量修复脚本 + UI 入口，不用重新探测即可修复 |
| P2-3 | 语音播报稿 | 中文一句话摘要生成后，整理为播报稿格式 |
| P2-4 | TTS 音频播报 | 接入 TTS API，实现语音播报功能 |

---

## 不在本轮范围

| 能力 | 原因 |
|------|------|
| 持久任务队列（Celery/BullMQ） | 先用 BackgroundTasks 验证产品，再考虑稳定性投入 |
| 多用户 / 登录注册 | MVP 聚焦单用户主链路 |
| 分布式部署 | 单进程部署足够验证产品假设 |
| 向量数据库 / 语义搜索 | 需要先有真实数据积累 |
| 知识图谱 | 需要先有实体和关系数据 |

---

## 执行原则

1. **不做业务功能扩展**：本轮只做 P0，不新增 P1/P2 范围外的功能
2. **不改数据库结构**：不引入新的 ORM 模型或表结构变更
3. **不改抓取策略**：不改变 RSS / HTML Index 探测的核心逻辑
4. **不改生成流程**：不改变 LLM 编译链路
5. **不改状态机**：InsightCard 和 SourceItem 的状态流转保持不变
6. **不引入新依赖**：不新增 pip 包依赖

---

## V1.0-beta.5：摘要写入规范

> 已完成：V1.0-beta.4 摘要语义统一（展示层），V1.0-beta.5 聚焦写入规范（写入层）

### V1.0-beta.5 目标

定义摘要字段写入规范，解决：

- `zh_one_liner` 和 `zh_summary` 的边界定义
- 字段覆盖规则（默认不覆盖已有非空值）
- L0（来源摘要）永远不能标记为 AI 中文摘要
- `InsightCard.summary_zh` 不反向污染 `SourceItem` 摘要
- 失败记录规范

### V1.0-beta.5 完成项

- ✅ `docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md` — 写入规范定义
- ✅ L0 / L1 / L2 / L3 字段权威性等级定义
- ✅ 生成者 / 写入者 / 消费者矩阵
- ✅ `zh_one_liner` 写入规则（`CandidateOneLinerService`）
- ✅ `zh_summary` 写入规则（待定义服务）
- ✅ `InsightCard.summary_zh` 不自动覆盖 `zh_one_liner` / `zh_summary`
- ✅ `quick_test.py` [48] V1.0-beta.5 summary write policy
- ✅ `acceptance_first_usable_loop.py` [20] V1.0-beta.5 summary write policy
- ✅ `NEXT_EXECUTION_PLAN.md` / `README.md` 包含 V1.0-beta.5

### V1.0-beta.5 暂不改

- ❌ 数据库 schema（Alembic / models.py / db.py）
- ❌ 抓取逻辑
- ❌ LLM 调用逻辑
- ❌ `insight_compiler.py`

---

## V1.0-beta.6：今日雷达主链路

> 分支：`feature/v1-beta-6-today-item-content-chain`

### V1.0-beta.6 目标

打通今日雷达主链路：TodayItemCard 中文概述状态 → 内容获取 intent-only → bootstrap/daily_increment 来源发现入口。

### V1.0-beta.6 完成项

- ✅ TodayItemCard 多维状态（zh_one_liner / zh_summary / content / insight）
- ✅ 右侧面板展示各维度状态标签及操作入口
- ✅ 真实正文获取链路（POST fetch-html，保存文本快照）
- ✅ bootstrap / daily_increment 入口设计（bootstrap 独立，daily_increment 复用 due-source）
- ✅ bootstrap dry-run / apply 语义
- ✅ Web apply background（FastAPI BackgroundTasks）
- ✅ CLI apply sync
- ✅ `SourceDiscoveryRunResult.execution_mode`
- ✅ `docs/V1_BETA_6_TODAY_RADAR_MAIN_CHAIN_CHECKPOINT.md`
- ✅ `docs/V1_BETA_6_SOURCE_DISCOVERY_BOOTSTRAP_AND_DAILY_INCREMENT_PLAN.md`

### V1.0-beta.6 暂不改

- ❌ 自定义来源 F-2
- ❌ 真实正文抓取
- ❌ 自动日报
- ❌ 音频播报
- ❌ DB schema

---

## V1.0-beta.7：日报卡片

> 分支：`feature/v1-beta-7-daily-report-card` → 已合并到 main

### V1.0-beta.7 完成项

- ✅ DailyReportCard 两层结构（今日必看 / 其他值得扫一眼）
- ✅ 规则打分排序（来源权重 + 关键词 + 新鲜度）
- ✅ 中文方向标签映射（`_DIRECTION_LABELS`）
- ✅ 3-5 条主次分层语义
- ✅ 防漏提示（"避免错过关键报告"）
- ✅ 每条保留原文链接
- ✅ InsightCard 链接（已有时）
- ✅ `docs/V1_BETA_7_DAILY_REPORT_CARD_CHECKPOINT.md`

### V1.0-beta.7 暂不改

- ❌ LLM 日报总结
- ❌ 音频播报（由 V1.0-beta.8 承接）
- ❌ 真实正文抓取
- ❌ DB schema

---

## V1.0-beta.8：播报文案（进行中）

> 分支：`feature/v1-beta-8-daily-broadcast`

### V1.0-beta.8 目标

在 DailyReportCard 基础上生成口播友好的中文播报稿，预留 TTS 音频生成接口。

### V1.0-beta.8 完成项

- ✅ DailyBroadcastScript dataclass（title/opening/overview/primary_sections/secondary_section/closing/full_text）
- ✅ build_daily_broadcast_script() — 不调用 LLM，基于 DailyReportCard 规则生成
- ✅ DailyBroadcastAudioResult dataclass（status/message/audio_url/audio_path）
- ✅ generate_daily_broadcast_audio() — 已接入 MiMo V2.5 TTS，支持 WAV 缓存与安全落盘
- ✅ GET /radar/daily-report/broadcast — 展示播报文案页面
- ✅ POST /radar/daily-report/broadcast/audio — 音频生成入口，受开关和 API Key 配置控制
- ✅ 页面包含 textarea 展示 full_text，含复制按钮
- ✅ 音频状态 banner（disabled / generated / failed）
- ✅ 页面初始显示"音频播报入口已预留，当前未启用真实 TTS"
- ✅ 音频按钮旁提示"当前版本仅预留音频入口，真实 TTS 尚未启用"
- ✅ `docs/V1_BETA_8_DAILY_BROADCAST_PLAN.md`
- ✅ `docs/V1_BETA_8_DAILY_BROADCAST_CHECKPOINT.md`

### V1.0-beta.8 暂不改

- ❌ 真实 TTS API 调用（MiniMax / OpenAI / 本地 TTS）
- ❌ 多 Provider 支持（接口预留，单一 Provider）
- ❌ 音频文件生成
- ❌ LLM
- ❌ DB schema

### 后续接入方向

- MiniMax TTS（`MINIMAX_API_KEY`）
- OpenAI TTS（`OPENAI_API_KEY`）
- 本地 TTS（Coqui / piper）

---

## V1.0-beta.10：HTML 正文读取与快照备份（进行中）

> 分支：`feature/v1-beta-10-html-content-fetch`

### V1.0-beta.10 目标

实现 HTML 正文抓取 MVP：从 SourceItem.url 获取 HTML 页面，提取干净正文文本，保存快照到 runtime 目录。

### V1.0-beta.10 完成项

- ✅ `app/application/content/` 目录（html_fetcher / content_snapshot / source_item_content_service）
- ✅ `HtmlFetchSettings` + `HtmlFetchResult` dataclass
- ✅ URL 安全校验复用 `is_safe_external_url`
- ✅ timeout / max_bytes / content-type 检查
- ✅ BeautifulSoup 正文清洗（去 nav/header/footer/script/style，最小 300 字符）
- ✅ `runtime/content_snapshots/source_item_<id>.json` 快照保存（项目根目录）
- ✅ `SourceItemContentFetchResult` + `ContentFetchStatus`
- ✅ `POST /radar/today/items/{id}/fetch-html` 同步抓取路由
- ✅ 页面按钮从"标记待获取正文"改为"获取 HTML 正文"
- ✅ `UNTRUSTED_CONTENT_NOTE` prompt injection 边界声明
- ✅ `runtime/` 加入 `.gitignore`
- ✅ Content-Length 前置检查（避免加载大页面到内存）
- ✅ `content_too_large` 专用错误码

### V1.0-beta.10 暂不改

- ❌ LLM 摘要生成（由下一版本承接）
- ❌ PDF 处理
- ❌ 浏览器渲染
- ❌ DB schema 变更
- ❌ 音频相关

### 后续接入方向

- LLM `zh_summary` 生成（使用抓取到的正文）
- PDF 支持（pypdf / pdfplumber）
- 更高质量正文抽取（Trafilatura）

---

## V1.0-beta.11：基于正文快照的中文摘要（进行中）

> 分支：`feature/v1-beta-11-summary-from-snapshot`

### V1.0-beta.11 目标

从 `runtime/content_snapshots/source_item_<id>.json` 读取正文快照，生成高质量中文摘要。

### V1.0-beta.11 完成项

- ✅ `app/application/summary/` 目录（summary_models / summary_prompt / summary_llm_client / source_item_summary_service）
- ✅ `SummaryInput` + `SummaryResult` + `LLMResponse` + `SummarySettings` dataclass
- ✅ `LLM_SUMMARY_ENABLED` 默认 false，未启用时返回 disabled
- ✅ API Key 从环境变量读取，不硬编码
- ✅ `UNTRUSTED_CONTENT_NOTE` prompt injection 防护
- ✅ 严格 JSON 输出要求
- ✅ JSON parse failure 处理
- ✅ `generate_source_item_summary()` 服务函数
- ✅ 写入 `raw_metadata_json.summary_status` + `summary_basis=html_snapshot`
- ✅ 支持 `force=false` 幂等跳过，`force=true` 重新生成
- ✅ `POST /radar/today/items/{id}/generate-summary` 路由
- ✅ 今日雷达卡片和面板的"基于正文生成摘要"按钮
- ✅ `TodayItemCard.can_generate_summary` 字段
- ✅ `DailyReportPrimaryItem.zh_summary` 字段
- ✅ `DailyBroadcast` 优先使用 `zh_summary`（截断 120 字）

### V1.0-beta.11 暂不改

- ❌ PDF 处理
- ❌ 批量自动生成
- ❌ 复杂 RAG
- ❌ 多 Agent
- ❌ TTS
- ❌ DB schema 变更

### 后续接入方向

- 批量正文摘要（用户触发）
- PDF 支持
- InsightCard 质量增强

---

## V1.0-beta.12：基于正文摘要生成 InsightCard（进行中）

> 分支：`feature/v1-beta-12-insightcard-from-summary`

### V1.0-beta.12 目标

从 `SourceItem.raw_metadata_json.summary_json` 生成 InsightCard，打通"来源发现 → 摘要生成 → 洞察卡"完整链路。

### V1.0-beta.12 完成项

- ✅ `app/application/insight/` 目录（insight_models / source_item_insight_service）
- ✅ `InsightBuildInput` + `InsightBuildResult` + `InsightStatus` + `InsightError` dataclass
- ✅ 规则映射 summary_json → InsightCard 字段
- ✅ 规则计算 relevance_score（来源权重+方向+建议数量）
- ✅ `generate_source_item_insight()` 服务函数
- ✅ 写入 `SourceItem.insight_card_id` + `raw_metadata_json.insight_status` + `insight_basis=summary_from_snapshot`
- ✅ 支持 `force=false` 幂等跳过已有卡，`force=true` 更新
- ✅ `POST /radar/today/items/{id}/generate-insight` 路由
- ✅ 今日雷达"生成洞察卡"/"查看洞察卡"按钮
- ✅ `TodayItemCard.can_generate_insight` 字段
- ✅ `DailyReport` / `DailyBroadcast` 识别已有洞察卡
- ✅ 不调用 LLM（复用摘要已有内容）
- ✅ 不改 DB schema

### V1.0-beta.12 暂不改

- ❌ LLM 调用
- ❌ PDF 处理
- ❌ TTS
- ❌ 批量自动生成
- ❌ 多 Agent
- ❌ 复杂 RAG
- ❌ DB schema 变更

### 后续接入方向

- InsightCard 质量增强（可选 LLM 二次加工）
- InsightCard 导出 PDF
- InsightCard 分享功能

---

## V1.0-beta.13：信息来源页与来源工作台体验修复 + 来源接入治理（进行中）

> 分支：`feature/v1-beta-13-source-experience-polish`

### V1.0-beta.13 目标

两个子目标：
1. **体验修复**：优化信息来源入口，让用户能清楚理解每个来源的探测方式、当前状态、失败原因
2. **接入治理**：审计 15 个精选来源的 RSS/HTML 接入质量，确立 RSS 优先策略

### V1.0-beta.13 完成项

**体验修复：**
- ✅ 来源卡片去掉重复标签，统一展示 `effective_strategy_label`
- ✅ `effective_strategy_label` 规则：feed_url 存在时优先显示"RSS 订阅"
- ✅ 来源卡片按钮简化：主按钮"进入工作台"+"运行探测"，其余入"技术详情"折叠
- ✅ `_humanize_fetch_error()` 将原始错误映射为可读中文（超时/404/解析失败等）
- ✅ 来源工作台显示"推荐探测方式"vs"实际探测方式"
- ✅ 来源工作台探测记录显示可读错误原因
- ✅ 来源工作台区分"成功0新增"与"失败"
- ✅ 侧边栏"精选来源"默认显示5个

**接入治理：**
- ✅ `scripts/audit_sources_onboarding.py` — 审计 15 个精选来源的接入质量（dry-run，默认不写配置）
- ✅ `scripts/probe_feed_url.py` — 探测单个 RSS/Atom URL 的可用性
- ✅ `scripts/diagnose_data_quality.py` — 诊断数据质量问题（快照缺失/摘要失败/重复 URL 等）
- ✅ 来源卡片展示 `needs_review` 标签（无 RSS 的 HTML index 来源）
- ✅ 来源卡片展示 `recommended_strategy` 字段
- ✅ 来源工作台展示"推荐策略"/"当前策略"/"最近失败原因"
- ✅ 来源工作台展示"建议动作"（缺少 feed_url/HTML 失败/无新增 等情况）
- ✅ 来源工作台展示 homepage_url 和 feed_url
- ✅ `docs/V1_BETA_13_SOURCE_ONBOARDING_AUDIT_PLAN.md` — 来源接入治理与 RSS 优先审计完整文档

### V1.0-beta.13 暂不改

- ❌ ViewModel 重构
- ❌ DB schema 变更
- ❌ TTS / PDF
- ❌ 新增来源抓取算法
- ❌ 批量摘要 / 批量 InsightCard

### 后续接入方向

- ViewModel 封装（beta13 稳定后可做）
- 来源健康度趋势图
- RSS feed 验证自动化
- TTS 音频播报

---

## 验收标准

- README 准确反映当前能力
- FIRST_USABLE_LOOP_CHECK 与代码能力一致

---

## V1.0-beta.14：精选来源配置修正与每日获取链路验证

> 分支：`feature/v1-beta-14-source-config-and-daily-loop`
> main merge commit：`待合并`
> 完成日期：2026-06-11

### 目标

不新增来源、不做自动探测系统。人工核查 15 个精选来源的 feed_url，修正配置，同步 DB，验证每日获取和展示主链路。

### RSS 核查结果

- **RSS 可用（8个）**：openai_news, deepmind_blog, huggingface_blog, arxiv_cs_ai, arxiv_cs_cl, arxiv_cs_lg, nvidia_ai_blog, berkeley_bair_blog
- **HTML index fallback（7个）**：anthropic_news, stanford_hai, mit_news_ai, meta_ai_blog, microsoft_ai_source, mistral_ai_news, cohere_blog

### 主要变更

- `config/sources.example.yaml`：4 个来源新增 RSS feed_url（deepmind_blog, huggingface_blog, nvidia_ai_blog, berkeley_bair_blog），全部 15 个来源补充 strategy_notes
- `scripts/sync_sources_from_config.py`（新增）：YAML → DB 配置同步 CLI，默认 dry-run，--apply 执行
- `scripts/diagnose_data_quality.py`：修复 Windows GBK 编码错误（emoji → ASCII）
- `app/application/radar/daily_report.py`：修复 generate_daily_report check 顺序（no_input → enabled gate）
- `app/templates/radar_daily_report.html`：空状态也渲染 section 头部
- DB Source 表：15 个来源全部同步

### 数据质量现状

- 525 个 SourceItem
- 20 个条目 content 存在但无 snapshot（建议清理）
- 41 个条目有 summary 但 snapshot 缺失（建议清理）
- 0 个重复 URL、0 个无标题、0 个无 URL、0 个 orphaned insight_card_id

### 后续未完成项

1. 数据清理（V1.0-beta.15）：处理 20 + 41 条脏数据
2. HTML index 来源持续观察：7 个 html_index 来源的抓取成功率待实际运行验证
3. RSS 来源稳定性监控：新增的 4 个 RSS 来源需要下次定时运行验证

- KNOWN_LIMITATIONS 包含真实限制
- NEXT_EXECUTION_PLAN 可见于 /project-docs
- 全部测试通过：compileall / quick_test / smoke_test / acceptance_demo_flow / acceptance_demo_data / health_check --quick
