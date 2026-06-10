# V1.0-beta.9 Source Strategy & Workspace Plan

## 一、来源获取策略优先级

来源配置必须遵守以下优先级原则（P0 最高）：

| 优先级 | 策略 | 说明 |
|--------|------|------|
| P0 | RSS / Atom feed | 优先使用结构化 feed，稳定可靠 |
| P1 | 官方 sitemap / structured feed | 官方提供的结构化索引 |
| P2 | HTML index | 解析主页 HTML 列表页，稳定性较低 |
| P3 | 手动 URL | 手动指定单个页面，不自动调度 |

### 策略决策规则

```python
# 有效策略计算逻辑
if feed_url exists:
    effective_strategy = "rss"           # 必须优先使用 RSS
elif fetch_strategy == "html_index":
    effective_strategy = "html_index"    # fallback
else:
    effective_strategy = fetch_strategy  # manual 或其他
```

### 核心原则

1. **有 feed_url 的来源，必须优先使用 RSS**。即使 `fetch_strategy` 字段声明为 `html_index`，代码层也必须以 `feed_url` 为准。
2. `html_index` 只能作为 fallback，不能作为有 feed_url 来源的首选策略。
3. company / research / paper 来源都遵守统一策略。
4. 不确定是否有 RSS 时，不要硬编码，需要标记为 `needs_review`。

---

## 二、来源报告工作台

来源详情页（`/sources/{source_key}`）的默认视图改为「该来源自己的报告列表」。

### 2.1 页面顶部改造

顶部显示：
- 来源名称、说明
- 获取方式标签（RSS / HTML index / 手动）
- 最近探测状态
- 最近新增数量
- 中文概述覆盖
- InsightCard 覆盖

**不**在第一屏显示：
- `source_key`（可折叠）
- `DB enabled` / `Config enabled`（可折叠）
- `FetchRun` 调度诊断（可折叠）

### 2.2 该来源自己的报告列表

数据过滤条件：`SourceItem.source_key == 当前 source_key`

列表字段：
- 标题
- 中文概述 / 中文摘要
- 发布时间
- 首次发现
- 最近发现
- 正文状态
- InsightCard 状态
- 打开原文
- 查看条目
- 查看洞察卡

标题：**最近报告**（不叫"原始资料"）

### 2.3 快速入口带 source_key 过滤

来源详情页的快速入口：
- `/candidate-pool?source_key={source_key}`
- `/source-items?source_key={source_key}`
- `/fetch-runs?source_key={source_key}`

进入后只显示该来源数据。

### 2.4 技术详情折叠

以下内容包裹在 `<details><summary>技术详情</summary>...</details>` 中：
- source_key
- DB enabled
- Config enabled
- fetch_strategy
- due-source reason
- FetchRun raw status

---

## 三、来源卡片状态表达修正

如果 html_index 失败：
```
当前策略需要复核，建议优先查找 RSS / Atom feed。
```

如果来源有 feed_url：
```
当前优先使用 RSS。
```

如果来源没有 feed_url 且 fetch_strategy=html_index：
```
HTML index，稳定性较低，建议后续补 RSS。
```

---

## 四、禁止事项

- 不做 HTML 正文抓取
- 不做 PDF 下载
- 不做全站爬虫
- 不调用 LLM
- 不接 TTS
- 不改 DB schema
- 不合并 main
- 不打 tag

---

## 五、验收标准

1. 文档存在且包含 RSS 优先原则
2. 有 feed_url 的来源优先使用 RSS
3. `check_sources_config.py` 能输出策略分布和 needs_review 列表
4. 来源详情页默认显示该来源自己的报告
5. 报告列表只包含当前 source_key 的条目
6. 精选来源入口进入对应来源页
7. 快速入口带 source_key 过滤
8. 目标页面 source_key 过滤生效
9. 技术详情默认折叠
10. 不改 schema
