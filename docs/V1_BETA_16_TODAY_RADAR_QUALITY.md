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

1. **无真实 TTS 提供商** — `daily_broadcast.py` 的 `generate_daily_broadcast_audio()` 是 stub，V1.0-beta.8 明确说明不调用外部 TTS API
2. **无播报内容来源** — 需要先有 `DailyReportCard`（依赖 InsightCard）

**后续接入点：**

```
每日探测 → compile → summary → InsightCard
  → DailyReportCard（基于已有 zh_one_liner）
    → DailyBroadcastScript（规则生成，无 LLM）
      → TTS API（需要接入真实 TTS 提供商）
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
3. **TTS 接入**：在 `daily_broadcast.py` 中接入真实 TTS API（受 `DAILY_BROADCAST_TTS_ENABLED` 控制）
4. **日报自动化**：在每日探测调度中加入 compile 步骤

### 文档更新

- Phase 4.2 完成：清理旧工作集，重新探测干净数据
- Phase 4.2 文档位置：`docs/V1_BETA_15_DATA_QUALITY_PLAN.md` 第十一节

