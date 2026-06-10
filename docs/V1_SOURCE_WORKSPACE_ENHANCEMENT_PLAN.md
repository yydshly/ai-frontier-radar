# 精品来源工作台增强设计（P-002 / Phase B）

> 设计先行文档。目标是把 `/sources/{source_key}` 从"健康诊断页"提升为
> "单来源内容工作台"——像今日雷达那样展示该来源抓到了哪些文章、中文摘要状态、
> 获取方式、获取日期与阅读入口。**增强现有页面，不重做布局。**

## 1. 现状

`GET /sources/{source_key}`（`app/main.py` → `source_detail.html`）已展示：

- 基础信息、是否雷达关注源、due-source 调度判断
- 最近 FetchRun（10 条）、最近 SourceItem（20 条）
- 中文摘要覆盖、InsightCard 覆盖、stale 警告、手动探测入口

也就是说"抓取状态 + 文章列表"骨架已具备。本阶段是**字段与呈现增强**。

## 2. 目标增强项

| 需求（P-002） | 现状 | 增强方向 |
|---------------|------|----------|
| 获取方式说明 | 只显示 `fetch_strategy` 原始值 | 用[策略阶梯能力矩阵](V1_SOURCE_INGESTION_STRATEGY.md)翻译成中文文案 |
| 抓取状态 | 已有 FetchRun 列表 | 保留，补"最近成功 / 失败"摘要行 |
| 文章列表 | 已有最近 20 条 | 每条补**中文一句话摘要预览** + 摘要状态标签 |
| 摘要 | 只有"已有/未生成"标签 | 列表内联展示 zh_one_liner 预览（若有） |
| 获取日期 | 有 last_seen_at | 明确"首次发现 / 最近发现"两个时间 |
| 阅读入口 | 有"查看 SourceItem" | 保留原文链接 + SourceItem 详情 + InsightCard（若有） |

## 3. 获取方式文案映射（复用 P-001 词表）

| fetch_strategy | 中文"获取方式" |
|----------------|----------------|
| `rss` | RSS 订阅（结构化、低成本） |
| `html_index` | 网页索引解析 |
| `json_feed` | JSON Feed（预留） |
| `sitemap` | 站点地图（预留） |
| `api` | 官方 API（预留） |
| `single_url` | 单篇文章抓取（预留） |
| `crawler` | 渲染型爬虫（后置，需显式开启） |
| `pdf` | PDF 人工录入 |
| 其他 / 未知 | 未配置 / 暂不支持 |

建议落地为一个只读 helper（如
`app/application/sources/strategy_labels.py: describe_fetch_strategy(key) -> str`），
供来源工作台与未来 P-004 接入表单共用。

## 4. 文章列表条目（增强后字段）

每条 SourceItem 行展示：

```
标题（原文链接）
中文一句话摘要预览（若有 zh_one_liner，截断显示）
摘要状态：已生成中文摘要 / 仅元数据 / 未生成
InsightCard：已生成（链接）/ 未生成
首次发现：YYYY-MM-DD ·  最近发现：YYYY-MM-DD
[查看 SourceItem] [原文]
```

中文摘要预览复用现有 display helper（`app/application/candidates/display.py`），
**不新写摘要解析逻辑**，避免与既有一句话 / 摘要策略漂移。

## 5. 边界

- **只读**：不创建 FetchRun、不触发抓取、不调用 LLM、不生成 InsightCard。
- 不重做 `/sources/{source_key}` 页面布局；只在现有卡片内增列 / 增字段。
- 不改 SourceItem 入库逻辑、不改 due-source、不改抓取流程。
- 新增样式仅少量 `.source-workspace-*` 追加 class，不动全局 / 其他页面。
- 文章列表分页 / 数量上限沿用现有（最近 20 条）；如需更多用 `/source-items?source_key=` 既有入口。

## 6. 性能注意

来源工作台的"中文摘要覆盖"统计已优化为 SQL 计数（避免把整表 SourceItem
载入 Python 再扫描）。增强文章列表预览时，只对**已取出的 20 条**做中文摘要解析，
不得为预览再做全表扫描。

## 7. 验收（落地阶段）

- `/sources/{source_key}` 文章列表显示中文摘要预览 + 摘要状态 + 获取方式中文文案 + 双时间
- 不存在来源仍 404、不 500
- 只读：访问前后 FetchRun / SourceItem 数量不变
- quick_test 增强断言 + acceptance 通过

## 8. 本阶段（设计）不做

- 不实现 helper / 模板改动（留到 Phase B 落地任务）
- 不实现新抓取策略（属 P-001 后续）
- 不做来源接入表单（属 P-004）

参考：[V1_OPTIMIZATION_ROADMAP.md](V1_OPTIMIZATION_ROADMAP.md)、
[V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)
