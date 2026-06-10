# V1.0-beta.12 Plan — 基于正文摘要生成 InsightCard

> 版本：V1.0-beta.12
> 分支：`feature/v1-beta-12-insightcard-from-summary`
> main 基准 commit：`90a894a`（v1.0-beta.11 merge）
> 规划日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.11 已实现从 HTML 正文快照生成中文摘要，写入 `SourceItem.raw_metadata_json.summary_json`。

本轮（V1.0-beta.12）目标：**将摘要沉淀为 InsightCard**，打通"来源发现 → 摘要生成 → 洞察卡"的完整链路。

---

## 二、为什么摘要之后要沉淀 InsightCard

摘要（summary_json）是 LLM 输出的结构化文本，包含：
- 事实要点（fact_points）
- 行动建议（action_suggestions）
- 风险提示（risk_notes）
- 相关方向（related_directions）

InsightCard 是系统内的结构化知识单元，可被：
- 今日必看排序加分
- 日报/播报优先展示
- 来源工作台快速查阅
- 用户后续参考和决策

没有 InsightCard，摘要只能查看不能复用。

---

## 三、InsightCard 与 summary_json 的字段映射

InsightCard 现有字段 → summary_json 来源：

| InsightCard 字段 | summary_json 字段 | 说明 |
|---|---|---|
| source_url | url | 来源 URL |
| source_title | zh_title / title | 优先用中文标题 |
| summary_zh | zh_summary | 正文摘要全文 |
| key_points_zh | fact_points + source_claims | 合并为 JSON 列表 |
| product_opportunities_zh | action_suggestions + personal_relevance | 行动建议+个人相关性 |
| risks_zh | risk_notes | 风险提示列表 |
| action_items_zh | action_suggestions | 行动建议 |
| technical_insights_zh | model_inferences | 模型推断 |
| related_user_directions | related_directions + key_terms | 相关方向+关键词 |
| relevance_score | 规则计算 | 见第四章 |

---

## 四、相关性分数规则

不调用 LLM，使用规则计算 relevance_score：

```
score = 50
+ min(len(related_directions), 5) * 8
+ min(len(action_suggestions), 3) * 5
+ source_weight_bonus
- min(len(risk_notes), 3) * 2
```

分数限制：0 <= score <= 100

来源权重（source_weight_bonus）：
- openai_news / anthropic_news: +10
- deepmind_blog: +8
- huggingface_blog / meta_ai_blog / nvidia_ai_blog: +7
- microsoft_ai_source: +6
- stanford_hai / mit_news_ai: +5
- arxiv_cs_ai: +4
- mistral_ai_news / cohere_blog: +5
- berkeley_bair_blog: +4
- arxiv_cs_cl / arxiv_cs_lg: +3

---

## 五、幂等规则

### force=false（默认）
- 如果 `SourceItem.insight_card_id` 已存在 → 返回 `skipped`
- 不重复创建

### force=true
- 如果已有卡片 → 更新已有卡片内容，保留同一 `insight_card_id`
- 如果没有卡片 → 创建新卡片

---

## 六、与 Today / Source workspace / DailyReport / Broadcast 的关系

### Today 页面
- 如果 `summary_status == generated` 且 `summary_basis == html_snapshot` 且 `insight_card_id == null`：
  显示"生成洞察卡"按钮
- 如果 `insight_card_id` 存在：
  显示"查看洞察卡"按钮

### 来源报告工作台
- 显示 InsightCard 状态
- 已有卡显示入口，无卡且有摘要显示可生成

### DailyReport
- `has_insight = bool(insight_card_id)` → suggested_action = "查看洞察卡"
- 有洞察卡的条目在排序中获得 +1.0 加权

### DailyBroadcast
- 有洞察卡时提示："你可以查看洞察卡，里面已经整理了事实、机会、风险和行动建议。"
- 无洞察卡有摘要时提示："你可以阅读正文摘要，必要时再生成洞察卡。"

---

## 七、不调用 LLM 的原因

InsightCard 的内容（事实要点、行动建议等）已经在 summary_json 中由 LLM 生成过了。

本轮只是把已有的结构化数据映射到 InsightCard 字段，不需要再次调用 LLM。

未来如果有需要，可以对 InsightCard 做进一步 LLM 增强，但那不是本轮的范围。

---

## 八、当前不做 PDF / TTS / schema 变更

- 不生成 PDF：InsightCard 数据在数据库中，不需要导出 PDF
- 不接 TTS：播报文案由 DailyBroadcast 生成，TTS 能力已预留
- 不改 DB schema：使用现有的 InsightCard 字段，不新增列

---

## 九、禁止事项

- 不调用 LLM
- 不接 TTS
- 不做 PDF
- 不改 DB schema
- 不新增 migration
- 不批量自动生成
- 不做多 Agent
- 不做复杂 RAG
- 不删除 V1.0-beta.11 摘要能力
- 不删除 V1.0-beta.10 正文快照能力
- 不删除 V1.0-beta.9 来源策略工作台能力
