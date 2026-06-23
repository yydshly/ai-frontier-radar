# AI Frontier Radar V2 Architecture Proposal

## 1. V2 设计背景

V1.0-beta 已经证明产品方向成立，但 V1 是探索式实现，适合作为行为参考和产品验证，不适合作为长期复杂系统的最终架构。

V2 的目标不是推翻 V1 的价值，而是基于 V1 的经验重新设计一个更可靠、更清晰、更可扩展的信息处理流水线。

## 2. V2 核心目标

V2 要解决的问题：

```
稳定获取全球 AI 前沿资料
  → 明确内容状态
  → 可靠正文快照
  → 可追溯摘要与洞察
  → 个人相关性判断
  → 行动建议沉淀
  → 可扩展到日报、播报、视频、模型状态雷达
```

V2 不以"页面功能堆叠"为中心，而以"信息处理流水线"为中心。

## 3. V2 核心分层

```
1. Source Registry
2. Discovery Engine
3. Content Fetcher
4. Content Store
5. Analysis Pipeline
6. Insight Domain
7. Delivery / Workbench
```

---

## 4. Source Registry

**职责：**

- 管理信息来源
- 记录来源类型
- 记录抓取策略
- 记录抓取频率
- 记录来源可靠性
- 记录是否启用

**不负责：**

- 抓正文
- 调 LLM
- 生成 InsightCard
- 生成日报

**核心对象建议：**

```
Source
SourcePolicy
SourceHealth
SourceFetchStrategy
```

---

## 5. Discovery Engine

**职责：**

- RSS / Atom 发现文章
- HTML index 发现文章
- Sitemap / API 预留
- 去重
- 生成 SourceItem
- 记录 DiscoveryRun / FetchRun

**不负责：**

- 正文清洗
- 摘要
- InsightCard
- 日报

**核心对象建议：**

```
DiscoveryRun
DiscoveredItem
SourceItem
SourceItemIdentity
```

---

## 6. Content Fetcher

**职责：**

- 抓取 HTML 正文
- 抓取 PDF 文本
- 正文清洗
- 内容长度限制
- content-type 检查
- URL 安全检查
- 错误恢复
- 保存正文快照

**核心对象建议：**

```
ContentSnapshot
ContentFetchRun
ContentExtractionResult
```

---

## 7. Content Store

**职责：**

- 保存原文快照
- 保存清洗正文
- 保存正文 hash
- 保存正文版本
- 保存抓取时间
- 保存正文来源

**解决的问题：**

```
摘要基于哪个版本生成？
InsightCard 基于哪个版本生成？
原文是否变化过？
失败后能否重试？
```

---

## 8. Analysis Pipeline

**职责：**

- 生成中文一句话摘要
- 生成中文详细摘要
- 抽取关键事实
- 生成技术洞察
- 生成产品机会
- 生成风险提醒
- 生成行动建议

**要求：**

- LLM 输入输出必须有明确 schema
- 区分事实、原文观点、模型推论、个人建议
- 防止 prompt injection
- 支持失败重试
- 支持幂等
- 支持长文本截断和分段

**核心对象建议：**

```
AnalysisRun
SummaryResult
InsightDraft
StructuredInsight
```

---

## 9. Insight Domain

**职责：**

- 管理 InsightCard
- 管理相关性分数
- 管理个人关注方向匹配
- 管理用户判断
- 管理行动建议沉淀

**核心对象建议：**

```
InsightCard
InsightRelevance
UserDecision
ActionItem
```

---

## 10. Delivery / Workbench

**职责：**

- 今日雷达
- 候选池
- InsightCard 列表与详情
- Markdown 导出
- Daily Report
- 播报稿
- 音频
- 视频
- 邮件 / 飞书 / 公众号等分享

**原则：**

Delivery 层只消费上游结果，不反向污染抓取、正文、分析模块。

---

## 11. V2 状态机建议

**SourceItem 生命周期：**

```
discovered
  → metadata_ready
  → content_pending
  → content_ready
  → summary_pending
  → summary_ready
  → insight_pending
  → insight_ready
  → user_decided
  → archived
```

**失败状态：**

```
content_failed
summary_failed
insight_failed
ignored
unsupported
```

每一步都必须明确：

- 输入
- 输出
- 是否幂等
- 是否可重试
- 失败原因
- 依赖上一步状态

---

## 12. V2 与 V1 的关系

**V1 保留作为：**

- 产品验证样机
- 用户体验参考
- 来源配置参考
- InsightCard 字段参考
- 验收样例参考
- 文档资产
- Demo 资产

**V2 重新设计：**

- Pipeline 状态机
- 数据模型
- 任务执行系统
- 抓取执行器
- ContentSnapshot
- AnalysisRun
- SourceItem 生命周期
- raw_metadata_json 状态拆分

---

## 13. V2 第一阶段范围

V2 不应一开始就做完整产品。

**第一阶段只做：**

```
Source Registry
  → Discovery Engine
  → SourceItem
  → ContentSnapshot
  → Summary
  → InsightCard
```

**暂时不做：**

- 多用户
- 付费
- 复杂推荐
- 视频
- 音频
- 公众号
- 全网爬虫
- Twitter/X
- 复杂 Agent

---

## 14. V2 验收标准

V2 第一阶段验收：

- 可以配置 5-10 个官方来源
- 可以稳定发现 SourceItem
- 可以抓取 HTML 正文
- 可以保存 ContentSnapshot
- 可以生成中文摘要
- 可以生成 InsightCard
- 可以标记用户判断
- 可以导出 Markdown
- 每一步失败可追踪
- 每一步可重试
- 不依赖 raw_metadata_json 作为主状态存储
