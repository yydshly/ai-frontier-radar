# V1.0-beta.13 Plan — 来源接入治理与 RSS 优先审计

> 版本：V1.0-beta.13（追加任务）
> 分支：`feature/v1-beta-13-source-experience-polish`
> 追加日期：2026-06-11
> 目标：在 beta13 同一分支补齐来源接入审计与 RSS 优先治理

---

## 一、为什么来源入口是产品命门

AI Frontier Radar 的核心价值在于**来源质量**。如果来源配置错误、RSS 失效、HTML 探测不稳定，雷达将在错误的基础上生成摘要和 InsightCard。

来源入口的产品问题：

1. **配置黑盒**：用户不知道哪些来源用 RSS、哪些用 HTML 索引
2. **接入质量未知**：没有工具审计 15 个精选来源的接入状态
3. **RSS 优先策略未落实**：配置文件中仍有大量来源使用 `html_index` 但可能有 RSS
4. **失败原因不透明**：来源失败时用户无法快速定位是配置问题还是网络问题

---

## 二、RSS 优先策略

来源获取策略优先级（P0 最高）：

```
P0: RSS / Atom feed        — 优先使用，稳定可靠
P1: 官方 sitemap / feed    — 次选
P2: HTML index             — fallback，稳定性较低
P3: 手动 URL              — 不自动调度
```

**策略决策规则：**

```python
if feed_url exists:
    effective_strategy = "rss"  # 必须优先使用
else:
    effective_strategy = fetch_strategy
```

**注意事项：**

- 有 `feed_url` 的来源，必须设置 `fetch_strategy="rss"`
- `html_index` 只作为 fallback
- 不确定是否有 RSS 时，标记 `needs_review: true`

---

## 三、15 个精选来源审计清单

| source_key | 名称 | 分类 | 预期 RSS | 当前 feed_url | 推荐策略 | 需补充 |
|------------|------|------|----------|---------------|----------|--------|
| openai_news | OpenAI News | company | ✅ | ✅ 已配置 | RSS | 否 |
| anthropic_news | Anthropic News | company | 需验证 | ❌ null | HTML index | 是 |
| deepmind_blog | Google DeepMind Blog | research | 需验证 | ❌ null | HTML index | 是 |
| huggingface_blog | Hugging Face Blog | open_source | 需验证 | ❌ null | HTML index | 是 |
| arxiv_cs_ai | arXiv cs.AI | paper | ✅ | ✅ 已配置 | RSS | 否 |
| arxiv_cs_cl | arXiv cs.CL | paper | ✅ | ✅ 已配置 | RSS | 否 |
| arxiv_cs_lg | arXiv cs.LG | paper | ✅ | ✅ 已配置 | RSS | 否 |
| stanford_hai | Stanford HAI | research | 需验证 | ❌ null | HTML index | 是 |
| mit_news_ai | MIT News AI | research | 需验证 | ❌ null | HTML index | 是 |
| meta_ai_blog | Meta AI Blog | company | 需验证 | ❌ null | HTML index | 是 |
| nvidia_ai_blog | NVIDIA AI Blog | company | 需验证 | ❌ null | HTML index | 是 |
| microsoft_ai_source | Microsoft AI Source | company | 需验证 | ❌ null | HTML index | 是 |
| berkeley_bair_blog | Berkeley BAIR Blog | research | 需验证 | ❌ null | HTML index | 是 |
| mistral_ai_news | Mistral AI News | company | 需验证 | ❌ null | HTML index | 是 |
| cohere_blog | Cohere Blog | company | 需验证 | ❌ null | HTML index | 是 |

---

## 四、audit_sources_onboarding.py 用法

```bash
# 默认 dry-run，只输出报告，不写配置
python scripts/audit_sources_onboarding.py

# 使用实际 sources.yaml（而非 example）
python scripts/audit_sources_onboarding.py --use-config-sources-yaml

# 调整超时
python scripts/audit_sources_onboarding.py --timeout 15 --feed-timeout 20
```

**输出示例：**

```
[OK] openai_news
       name: OpenAI News
       category: company
       homepage: reachable (200)
       feed_url: reachable (rss, 20 items)
       recommended_strategy: rss
       action: none

[WARN] anthropic_news
       name: Anthropic News
       category: company
       homepage: reachable (200)
       feed_url: none
       recommended_strategy: html_index
       needs_review: no_feed_url
       action: add feed_url (RSS/Atom recommended)

[FAIL] meta_ai_blog
       name: Meta AI Blog
       homepage: failed (timeout)
       feed_url: none
       recommended_strategy: html_index
       needs_review: homepage:timeout
       action: check homepage reachability
```

**错误码说明：**

- `timeout` — 请求超时
- `http_error` — HTTP 错误（如 404、403）
- `network_error` — 网络错误
- `parse_error` — Feed 解析失败
- `empty_feed` — Feed 为空或格式无法识别

---

## 五、probe_feed_url.py 用法

探测单个 RSS/Atom URL 的可用性。

```bash
# 基本用法
python scripts/probe_feed_url.py --url "https://example.com/feed.xml"

# 调整超时
python scripts/probe_feed_url.py --url "https://example.com/feed.xml" --timeout 15

# JSON 输出（便于程序处理）
python scripts/probe_feed_url.py --url "https://example.com/feed.xml" --json
```

**JSON 输出示例：**

```json
{
  "reachable": true,
  "content_type": "application/rss+xml",
  "feed_type": "rss",
  "item_count": 20,
  "sample_titles": [
    "OpenAI Announces GPT-5",
    "New API Features Released"
  ],
  "error_code": null,
  "error_detail": null
}
```

**支持类型：** RSS 2.0、Atom 1.0

---

## 六、diagnose_data_quality.py 用法

诊断数据库中的数据质量问题。**只读，不写数据库，不删文件。**

```bash
# 诊断所有来源
python scripts/diagnose_data_quality.py

# 只看特定来源
python scripts/diagnose_data_quality.py --source-key openai_news

# 限制扫描数量（大型数据库性能优化）
python scripts/diagnose_data_quality.py --limit 500
```

**检查项：**

| 检查项 | 说明 |
|--------|------|
| duplicate_source_item_urls | 同来源下重复 URL（去重后应只有 1 条） |
| source_items_without_title | 标题为空的 SourceItem |
| source_items_without_url | URL 为空的 SourceItem |
| items_with_content_fetched_but_no_snapshot | 状态为 fetched 但无快照文件 |
| snapshot_exists_but_empty_text | 快照文件存在但 text 为空 |
| summary_failed_count | 摘要生成失败次数 |
| summary_disabled_count | 摘要被禁用的次数 |
| summary_missing_snapshot_count | 有摘要但快照缺失 |
| insight_card_id_missing_card_count | insight_card_id 指向不存在的卡 |

---

## 七、来源工作台展示结构

单个来源工作台（`/sources/{source_key}`）必须显示：

```
来源概览
├── source_key
├── 名称
├── 分类
├── 来源类型
├── 官网 (homepage_url)
├── RSS Feed (feed_url)
├── 推荐策略（effective_strategy_label）
├── 当前策略（fetch_strategy）
└── 抓取间隔

探测状态banner
├── RSS 优先（推荐）  ← 有 feed_url
└── ⚠ HTML 页面探测  ← 无 feed_url，needs_review=true

内容覆盖
├── 总条目
├── 已有中文摘要
├── 已有 InsightCard
└── 覆盖率

建议动作
├── 缺少 feed_url → 建议补充 RSS/Atom
├── HTML index 失败 → 建议检查页面结构或改用 RSS
├── 成功但 0 新增 → 可能近期无更新，可稍后重试
└── 需补充 RSS → 配置 RSS feed 以提升稳定性

技术详情（折叠）
├── 雷达关注源
├── DB enabled
├── Config enabled
├── 抓取策略是否支持调度
└── 最近探测记录（含可读错误）
```

---

## 八、当前不做事项

本 beta13 追加任务**不涉及**：

| 禁止事项 | 说明 |
|----------|------|
| ViewModel 重构 | 不做数据封装层重构 |
| DB schema 变更 | 不新增列、表或索引 |
| TTS 接入 | 不做语音合成 |
| PDF 导出 | 不做 PDF 生成 |
| 新增来源数量 | 保持 15 个精选来源 |
| 全网爬虫 | 不做大规模主动抓取 |
| 批量摘要 | 不做批量内容摘要 |
| 批量 InsightCard | 不做批量卡片生成 |

---

## 九、验收标准

完成本任务后，必须满足：

- [ ] `scripts/audit_sources_onboarding.py` 存在且可运行
- [ ] `scripts/probe_feed_url.py` 存在且可运行
- [ ] `scripts/diagnose_data_quality.py` 存在且可运行
- [ ] 15 个精选来源全部通过审计检查（或有清晰的 WARN/FAIL 报告）
- [ ] RSS 来源（openai_news, arxiv_cs_ai, arxiv_cs_cl, arxiv_cs_lg）显示 RSS 优先
- [ ] HTML index 来源显示 `needs_review` 标签
- [ ] 来源工作台显示推荐策略、当前策略、官网 URL、Feed URL
- [ ] 来源工作台显示失败原因（或"查看运行记录"提示）
- [ ] 成功但 0 新增不显示为失败
- [ ] `config/sources.example.yaml` 保持正确，无乱填不可用 feed_url
- [ ] `quick_test.py` 新增断言全部通过
- [ ] `acceptance_first_usable_loop.py` 新增断言全部通过
- [ ] `docs/V1_BETA_13_SOURCE_ONBOARDING_AUDIT_PLAN.md` 已创建
- [ ] 未做 ViewModel 重构
- [ ] 未改 DB schema
- [ ] 未接 TTS
- [ ] 未做 PDF
- [ ] 保留 beta9/beta10/beta11/beta12 全部能力
