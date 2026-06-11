# V1.0-beta.14 Plan — 已有精选来源配置修正与每日获取链路验证

> 版本：V1.0-beta.14
> 分支：`feature/v1-beta-14-source-config-and-daily-loop`
> main 基准 commit：`73519e5`（v1.0-beta.13.1）
> 规划日期：2026-06-11

---

## 一、阶段定位

beta13 完成了信息来源页体验修复，但 15 个精选来源的配置（特别是 feed_url）未经验证，导致：

- 10 个 html_index 来源被标记 needs_review = true（真实原因是 feed_url 未填，而非 RSS 不存在）
- 5 个来源的 RSS feed 实际可用但未填入配置
- 配置与 DB 不同步，运行时 feed_url 为 null 导致仍走 html_index

本轮目标：**人工核查 15 个来源的 feed_url，修正配置，同步 DB，验证每日获取链路**。

---

## 二、为什么不做自动 RSS 探测系统

人工核查 feed_url 比自动探测更可靠，原因：

1. **准确率**：自动探测可能被 robots.txt 拒绝、或返回错误内容类型（如 HTML 而非 XML）
2. **维护成本**：自动探测系统需要持续更新探测规则，且探测本身可能触发反爬
3. **数据新鲜度**：人工核查时可以直接确认 feed 是否正常返回近期条目
4. **已有 probe 脚本**：`probe_feed_url.py` 已具备探测能力，本轮用它做辅助验证

本轮策略：**用 probe 脚本辅助 + 人工判断，记录每个来源的验证结论**。

---

## 三、15 个来源 RSS 核查结果

### 3.1 RSS Feed 可用的来源（8个）

| source_key | feed_url | 验证结果 | 备注 |
|---|---|---|---|
| openai_news | https://openai.com/news/rss.xml | ✅ 可用，~1000 items | Homepage 403（正常，bot 限制） |
| deepmind_blog | https://deepmind.google/discover/blog/feed | ✅ 可用，100 items | 新增 feed_url |
| huggingface_blog | https://huggingface.co/blog/feed.xml | ✅ 可用，797 items | 新增 feed_url |
| arxiv_cs_ai | https://export.arxiv.org/rss/cs.AI | ✅ 可用，407 items | 原有 |
| arxiv_cs_cl | https://export.arxiv.org/rss/cs.CL | ✅ 可用，181 items | 原有 |
| arxiv_cs_lg | https://export.arxiv.org/rss/cs.LG | ✅ 可用，396 items | 原有 |
| nvidia_ai_blog | https://blogs.nvidia.com/blog/category/generative-ai/feed | ✅ 可用，18 items | 新增 feed_url |
| berkeley_bair_blog | https://bair.berkeley.edu/blog/feed | ✅ 可用，10 items | 新增 feed_url |

### 3.2 无可靠 RSS、保留 html_index 的来源（7个）

| source_key | 尝试的 feed 路径 | 结果 | 备注 |
|---|---|---|---|
| anthropic_news | anthropic.com/feed, /news/feed, /index.xml | 全部 404 | 无公开 RSS，HTML fallback |
| stanford_hai | hai.stanford.edu/news/feed, /rss | 返回 HTML（非 RSS） | 无 RSS，HTML fallback |
| mit_news_ai | news.mit.edu/topic/artificial-intelligence2/feed, /rss 等 | 全部 404 | 无公开 RSS，HTML fallback |
| meta_ai_blog | ai.meta.com/blog/feed, /rss | 全部 404 | 无公开 RSS，HTML fallback |
| microsoft_ai_source | news.microsoft.com/source/topics/ai/ | 403 Forbidden | 无公开 RSS，HTML fallback |
| mistral_ai_news | mistral.ai/news/feed, /rss | 全部 404 | 无公开 RSS，HTML fallback |
| cohere_blog | cohere.com/blog/feed, /rss, /feed.xml | 全部 404 或返回 HTML | 无公开 RSS，HTML fallback |

### 3.3 最终配置策略

```
RSS 来源（8个）：openai_news, deepmind_blog, huggingface_blog,
                 arxiv_cs_ai, arxiv_cs_cl, arxiv_cs_lg,
                 nvidia_ai_blog, berkeley_bair_blog
HTML index 来源（7个）：anthropic_news, stanford_hai, mit_news_ai,
                        meta_ai_blog, microsoft_ai_source, mistral_ai_news, cohere_blog
```

needs_review 标志：html_index 来源 → needs_review = true（动态计算）
RSS 来源不再显示"需补充 RSS"badge。

---

## 四、配置修正内容

### 4.1 config/sources.example.yaml 变更

- 新增 `strategy_notes` 字段到全部 15 个来源，记录验证日期和可用性状态
- 将 deepmind_blog、huggingface_blog、nvidia_ai_blog、berkeley_bair_blog 的 fetch_strategy 从 html_index 改为 rss
- 将对应 feed_url 从 null 修正为验证可用的 URL
- type 字段同步修正（html_index → rss）

### 4.2 新增 sync_sources_from_config.py

提供 CLI 工具将 YAML 配置同步到 DB：

```bash
python scripts/sync_sources_from_config.py          # dry-run
python scripts/sync_sources_from_config.py --apply   # 实际同步
```

功能：
- 读取 sources.example.yaml
- 更新 DB Source 表对应字段（feed_url, fetch_strategy 等）
- 不删除 SourceItem、FetchRun 等已有数据
- 默认 dry-run，apply 需要显式 --apply

### 4.3 同步结果

```
Config loaded: 15 sources
Would create: 0
Would update: 15
Would disable: 0
[APPLY] Writing changes to DB...
Done. created=0, updated=15, disabled=0
```

---

## 五、每日获取链路验证

### 5.1 check_due_sources.py 结果

```
total_configured: 15
due: 15
skipped: 0
running: 0
```

所有 15 个来源均到期。

### 5.2 check_stale_fetch_runs.py 结果

```
total_running: 0
stale_count: 0
No stale running FetchRun detected.
```

无 stale 运行。

### 5.3 UI 页面验证

| 页面 | 状态码 | 备注 |
|---|---|---|
| GET /sources | 200 | RSS/网页索引标签正确，无重复 |
| GET /radar/today | 200 | 正常 |
| GET /radar/daily-report | 200 | 正常 |
| GET /radar/daily-report/broadcast | 200 | 正常 |

来源工作台（deepmind_blog）：
- ✅ homepage_url 正确显示
- ✅ feed_url 正确显示
- ✅ 当前策略 / 推荐策略正确
- ✅ RSS 订阅标签（不再显示"需补充 RSS"）

---

## 六、数据质量诊断结果

运行 `python scripts/diagnose_data_quality.py`：

```
Total source_items: 525

[OK] duplicate URLs: 0
[OK] items without title: 0
[OK] items without URL: 0
[WARN] items with content fetched but no snapshot file: 20
[OK] snapshot files with empty text: 0
[OK] items with failed summary: 0
[OK] items with disabled summary: 0
[WARN] summaries present but snapshot missing: 41
[OK] items with invalid insight_card_id: 0

Total quality issues: 61
```

已知问题（建议 V1.0-beta.15 处理）：
1. **20 个条目有 content 但无 snapshot 文件**：可能是旧数据或抓取失败遗留
2. **41 个条目有 summary 但 snapshot 缺失**：可能是 summary 是在 snapshot 生成之前创建的

---

## 七、测试结果

| 测试 | 结果 |
|---|---|
| quick_test.py | 1139 passed, 0 failed |
| acceptance_first_usable_loop.py | 299 passed, 0 failed |
| python -m scripts.acceptance_first_usable_loop | 299 passed, 0 failed |
| check_sources_config.py | config validation passed |
| check_due_sources.py | 15 due, 0 stale |
| check_stale_fetch_runs.py | 0 stale |
| diagnose_data_quality.py | 61 issues (已知，建议下版清理) |

---

## 八、禁止事项检查

| 禁止项 | 是否遵守 |
|---|---|
| 不新增来源数量 | ✅ 未新增 |
| 不做自动 RSS 探测系统 | ✅ 未做 |
| 不做来源配置 UI | ✅ 未做 |
| 不做 ViewModel 重构 | ✅ 未做 |
| 不改 DB schema | ✅ 未改 |
| 不接 TTS | ✅ 未接 |
| 不做 PDF | ✅ 未做 |

---

## 九、后续未完成项

1. **数据清理（V1.0-beta.15）**：处理 20 个无 snapshot 的 content 条目 + 41 个 snapshot 缺失的 summary 条目
2. **HTML index 来源持续观察**：7 个 html_index 来源的抓取成功率待实际运行验证
3. **RSS 来源稳定性监控**：新增的 4 个 RSS 来源（deepmind、huggingface、nvidia、berkeley）需要下次实际运行验证是否稳定返回数据
4. **microsoft_ai_source**：homepage 403，可能需要寻找替代 URL 或确认是否需要切换策略
