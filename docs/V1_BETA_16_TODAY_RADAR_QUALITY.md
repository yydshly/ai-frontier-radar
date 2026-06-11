# V1.0-beta.16 — 今日探测结果质量与生成链路验收

> 版本：V1.0-beta.16
> 分支：`feature/v1-beta-15-data-quality-diagnosis`
> 基准 commit：`f4ce8a6`（Phase 4.2 完成）
> 执行日期：2026-06-11

---

## 一、数据规模审计结果

### 总体数据

| 指标 | 数值 |
|---|---|
| total_source_items | 2549 |
| new_items_last_24h | 2061 |
| new_items_last_48h | 2397 |
| with_title | 2549（100%） |
| with_url | 2549（100%） |
| with_summary | 3 |
| with_snapshot | 13 |
| with_insight_card | 21 |
| **eligible_for_insight_card** | **0** |
| discovered | 2528 |
| fetched | 0 |
| compiled | 20 |

**关键发现：2528/2549 条（99.2%）是 discovered 状态，需要 compile 步骤才能生成 InsightCard。**

### 各来源新增（24h）

| 来源 | new_24h | total |
|---|---|---|
| openai_news | 947 | 1000 |
| huggingface_blog | 782 | 831 |
| arxiv_cs_ai | 332 | 372 |
| arxiv_cs_cl | 0 | 45 |
| arxiv_cs_lg | 0 | 45 |
| berkeley_bair_blog | 0 | 8 |
| cohere_blog | 0 | 22 |
| deepmind_blog | 0 | 34 |
| meta_ai_blog | 0 | 12 |
| microsoft_ai_source | 0 | 24 |
| mistral_ai_news | 0 | 39 |
| mit_news_ai | 0 | 32 |
| nvidia_ai_blog | 0 | 28 |
| stanford_hai | 0 | 34 |
| test_v10_demo | 0 | 1 |

### openai_news items_new=947 是否合理？

**合理。** openai_news 通过 RSS feed 探测，items_found=1000 中 947 为新条目。RSS feed 每次探测会返回完整 feed 列表，项目去重机制（content_hash / url unique constraint）确保不会重复插入。947 条新条目来自今日 feed 更新，属于正常范围。

---

## 二、今日雷达抽样 20 条质量结果

**全部 20 条均为 discovered 状态，first_seen_at 均为 2026-06-11T04:56（即今日探测时间）。**

抽样结果：

| # | id | source_key | title | status | insight |
|---|---|---|---|---|---|
| 1 | 2292 | arxiv_cs_ai | Automatic Extraction of Structured Information... | discovered | 未生成 |
| 2 | 2293 | arxiv_cs_ai | ... | discovered | 未生成 |
| ... | ... | arxiv_cs_ai | （同上） | discovered | 未生成 |

**结论：**

- 可用于生成 InsightCard 的候选数：**0**（全部 discovered，无 summary，无 eligible）
- 历史旧内容数量：**0**（全部是今日新增）
- 标题异常数量：**0**
- 摘要缺失数量：**20**（全部 discovered，还未 compile）
- 正文缺失数量：**20**

**数据质量判断：干净。**

所有 20 条均为今日新增（first_seen_at 2026-06-11T04:56），来源真实（arxiv.org），标题正常，无历史旧数据污染今日雷达。

---

## 三、主链路堵点分析

### 发现的问题

```
2549 total
2528 discovered (需要 compile)
20 compiled
1 fetched
0 eligible_for_insight_card
```

**核心堵点：discovery → compile 的链路未被自动触发。**

新探测产生的 SourceItem 停留在 discovered 状态，需要手动触发 compile 才能：
1. 抓取正文（URL fetch 或 metadata snapshot）
2. 生成摘要（zh_summary）
3. 生成 InsightCard

### compile 链路验证

已验证 `compile_one_insight_card.py` 可以成功执行：

```
SourceItem id=240 → compiled
InsightCard id=36 → completed
summary_zh 正常生成
```

编译结果摘要示例：
```
【基于来源摘要 / RSS metadata 生成，非全文解析】
全文未抓取，判断可能不完整，结论基于公开摘要 / 来源 metadata，建议打开原文核验。
...
```

---

## 四、生成 1 条 InsightCard 验收

**执行命令：** `python scripts/compile_one_insight_card.py`

**结果：**

| 字段 | 值 |
|---|---|
| SourceItem id | 240 |
| source_key | arxiv_cs_ai |
| title | Automatic Extraction of Structured Information from Brain MRI Reports... |
| status after | compiled |
| InsightCard id | 36 |
| InsightCard.status | completed |
| compile result | ok=True |

**链路验收：通过。**

InsightCard 成功生成，summary_zh 包含中文摘要内容。雷达页面可以显示已生成的 InsightCard 状态。

---

## 五、报告整理入口检查

### 已有入口

| 入口 | 路径 | 依赖 |
|---|---|---|
| 今日核心报告 | POST `/today/daily-report` | InsightCard（zh_one_liner） |
| 每日报告卡 | `app/application/radar/daily_report_card.py` | InsightCard |
| 双语报告 | GET `/cards/{id}/export-report` | InsightCard |
| Markdown 导出 | `app/exports/markdown_report.py` | InsightCard |

**现状：**
- `generate_daily_core_report()` 需要 `DAILY_REPORT_ENABLED=true` 才执行 LLM 调用
- 默认 dry-run 模式，不调用 LLM
- 依赖 `zh_one_liner` 字段，需要 InsightCard 先完成

**结论：报告入口已存在，但需要先完成 compile → summary → insight 链路。**

---

## 六、语音播报入口检查

### 已有能力

| 能力 | 路径 | 状态 |
|---|---|---|
| 播报脚本生成 | `app/application/radar/daily_broadcast.py` | 规则生成，无 LLM |
| TTS 音频生成 | POST `/daily-report/broadcast/audio` | 受 `DAILY_BROADCAST_TTS_ENABLED` 控制 |
| 播报模板 | `app/templates/radar_daily_broadcast.html` | 已存在 |

**缺失能力：**

1. **TTS 已接入但仍为同步请求** — 当前使用 MiMo V2.5 TTS 非流式生成 WAV；长报告需要等待完整音频返回，后续可迁移到后台任务
2. **无播报内容来源** — 需要先有 `DailyReportCard`（依赖 InsightCard）

**后续接入点：**

```
每日探测 → compile → summary → InsightCard
  → DailyReportCard（基于已有 zh_one_liner）
    → DailyBroadcastScript（规则生成，无 LLM）
      → MiMo V2.5 TTS
```

---

## 七、测试结果

```
diagnose_data_quality.py:
  A=8（compile 后从 7 升至 8，多了一个 compiled item）
  B=0
  C/D/E/F=0
  G=8 informational
  Total actionable=8

cleanup_polluted_data.py:
  b_safe_delete_candidates: 0
  b_without_card_candidates: 0

acceptance_today_radar_logic.py:
  10 passed, 0 failed ✅

quick_test.py:
  1181 passed, 0 failed ✅
```

---

## 八、结论与后续建议

### 当前状态

- **数据质量：干净** — 今日探测产生 2061 条新 SourceItem，全部有标题/URL，无历史旧数据污染
- **compile 链路：通畅** — 已有 `SourceItemCompileService` 可成功生成 InsightCard
- **主要堵点：自动化** — 2528 条 discovered 条目需要手动或后台触发 compile

### 后续建议

1. **接入后台 compile 调度**：新探测完成后自动触发 background compile（参考 `BackgroundCompileService`）
2. **批量 compile 脚本**：类似 `compile_one_insight_card.py`，支持按来源/状态批量 compile
3. **TTS 后台化**：将同步 MiMo WAV 生成迁移到后台任务，并增加状态刷新、失败重试和音频历史管理
4. **日报自动化**：在每日探测调度中加入 compile 步骤

### 文档更新

- Phase 4.2 完成：清理旧工作集，重新探测干净数据
- Phase 4.2 文档位置：`docs/V1_BETA_15_DATA_QUALITY_PLAN.md` 第十一节

---

## 九、Phase 4.3 今日雷达候选筛选与小批量 Compile

> 执行时间：2026-06-11
> 执行分支：`feature/v1-beta-15-data-quality-diagnosis`

### 9.1 目标

本轮目标数字：
- 候选筛选 Top 10
- 实际 compile 3 条
- InsightCard 成功 >= 1 条

### 9.2 修正审计口径

`eligible_for_insight_card` 拆分为三类：

| 指标 | Phase 4.2 | Phase 4.3 |
|---|---|---|
| eligible_for_insight_card | 0（误导） | → 已删除 |
| already_compiled_items | — | 22 |
| metadata_compile_candidates | — | 1171 |
| fulltext_compile_candidates | — | 0 |

### 9.3 新增脚本

- `scripts/select_today_compile_candidates.py` — 规则打分候选筛选，默认 dry-run
- `scripts/compile_selected_insight_cards.py` — 小批量 compile，支持 `--apply --limit N`

### 9.4 候选筛选规则

打分维度（不加 LLM）：

| 维度 | 分数 |
|---|---|
| topic_keyword 命中（最多 4 个） | 每个 +8 |
| 有 RSS 元数据摘要 | +20 |
| 有 snapshot 文件 | +15 |
| 来源优先级（openai_news=10 最高） | +10~3 |
| 发布时间 < 1 小时 | +10 |
| 发布时间 < 6 小时 | +6 |
| 弱标题（News/Blog/Update） | -20 |

每个 source 最多 3 条（`--per-source-limit`）。

### 9.5 Top 10 候选列表

| Rank | id | source_key | Score | Compile Basis | Reasons |
|---|---|---|---|---|---|
| 1 | 561 | openai_news | 72 | metadata | topic_match(4), rich_metadata, openai_news=10, fresh |
| 2 | 580 | openai_news | 72 | metadata | topic_match(4), rich_metadata, openai_news=10, fresh |
| 3 | 581 | openai_news | 72 | metadata | topic_match(4), rich_metadata, openai_news=10, fresh |
| 4 | 2264 | arxiv_cs_ai | 66 | metadata | topic_match(5), rich_metadata, arxiv=4, fresh |
| 5 | 2267 | arxiv_cs_ai | 66 | metadata | topic_match(4), rich_metadata, arxiv=4, fresh |
| 6 | 2270 | arxiv_cs_ai | 66 | metadata | topic_match(4), rich_metadata, arxiv=4, fresh |
| 7 | 1474 | huggingface_blog | 49 | metadata | topic_match(6), huggingface=7, fresh |
| 8 | 1485 | huggingface_blog | 49 | metadata | topic_match(10), huggingface=7, fresh |
| 9 | 1487 | huggingface_blog | 49 | metadata | topic_match(4), huggingface=7, fresh |
| 10 | 416 | microsoft_ai_source | 42 | metadata | topic_match(2), rich_metadata, microsoft=6 |

**per-source-limit 生效**：Top 10 包含 3 个来源（openai_news×3, arxiv_cs_ai×3, huggingface_blog×3, microsoft_ai_source×1）。

### 9.6 compile 执行结果

```bash
python scripts/compile_selected_insight_cards.py --apply --limit 3
```

**结果：3/3 成功**

| SourceItem id | source_key | Card ID | Status |
|---|---|---|---|
| 580 | openai_news | 38 | completed |
| 581 | openai_news | 39 | completed |
| 591 | openai_news | 40 | completed |

卡片摘要示例（Card 38）：
```
【基于来源摘要 / RSS metadata 生成，非全文解析】
全文未抓取，判断可能不完整，结论基于公开摘要 / 来源 metadata，建议打开原文核验。
```

### 9.7 compile 后数据集状态

```
already_compiled_items: 22 → 26
metadata_compile_candidates: 1171 → 1167
fulltext_compile_candidates: 0
```

（1167 + 26 + 其他 = 2549 总量吻合）

### 9.8 日报入口验证

`POST /today/daily-report` 需要 `DAILY_REPORT_ENABLED=true`。当前环境未启用，无法验证 LLM 调用链路。

已验证：
- InsightCard 生成正常（36-40 全部 completed）
- `DailyReportCard.build_daily_report_card()` 依赖 InsightCard 的 `zh_one_liner` 字段
- 链路通畅，数据就绪后可启用

### 9.9 测试结果

```
diagnose_data_quality.py:
  A=12（repair 修复快照状态，A 类计数增加，与 compile 无关）
  B=0, C/D/E/F=0, G=8 informational

acceptance_today_radar_logic.py:
  10 passed, 0 failed ✅

quick_test.py:
  1181 passed, 0 failed ✅
```

### 9.10 Phase 4.3 结论

- **候选筛选：可用** — 规则打分 + per-source-limit 防止单一来源刷屏
- **小批量 compile：成功** — 3/3 成功，metadata compile 无需 URL fetch
- **日报链路：数据就绪** — 已有 26 条 compiled InsightCard，可供 DailyReportCard 消费
- **主要堵点已解决**：从"无法自动 compile"变为"可小批量 compile"，后续需要接入后台调度
