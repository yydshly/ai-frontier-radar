# V1.0-beta.6 来源发现初始化与每日增量设计

## 目标

已有 YAML 来源仍是个人自用阶段的唯一正式来源入口。系统主链路从“新增报告卡片”开始：

已有 YAML 来源 -> 初始化发现最近内容 -> 每日只发现新增内容 -> 今日雷达展示新增报告卡片 -> 生成中文概述、中文摘要、InsightCard、日报卡片。

本设计只描述发现策略，不实现新抓取器，不改数据库 schema，不调用 LLM。

## 初始化模式

第一次对已有 YAML 来源执行 bootstrap。

- 每个来源取最近 20/50 条内容，具体数量由脚本或配置控制。
- 只处理 `config/sources.yaml` 中 enabled 的来源。
- RSS 来源按 feed 返回顺序或发布时间倒序取最近项。
- HTML index 来源按现有探测策略返回的候选顺序取最近项。
- 写入 `SourceItem` 时，`first_seen_at` 表示系统首次发现时间。
- `published_at` 表示原文发布时间，能解析就写入，不能解析则保留为空。
- 初始化只用于建立本地候选池基线，不代表这些内容都是“今日新增”。

## 每日增量模式

初始化后，后续每天只发现新增内容。

- 每日任务继续读取 enabled YAML sources。
- 每次探测只写入本地尚未见过的 URL / canonical URL。
- 今日雷达默认展示 `first_seen_at` 属于今天或最近 N 小时的 `SourceItem`。
- 保留 fallback：今天没有内容时展示最近内容，避免页面空白。
- 每日增量发现不自动生成日报、不自动生成音频、不自动抓正文。

## 去重规则

按保守顺序去重，避免同一报告重复进入今日雷达：

1. `source_key + url`
2. `canonical_url`
3. 必要时使用 `title + source_key + published_at`

其中 `source_key + url` 继续对应当前 `SourceItem` 唯一约束；`canonical_url` 和标题组合可以作为后续补充策略，先在设计层明确。

## 今日雷达展示口径

今日雷达展示的是“系统今日发现的新报告卡片”，不是来源历史全量内容。

卡片状态从 `SourceItem.status`、`insight_card_id` 和 `raw_metadata_json` 推导：

- 中文概述：`raw_metadata_json.zh_one_liner`
- 中文摘要：`raw_metadata_json.zh_summary`
- 正文状态：`content_fetch_status` 或已有正文快照线索
- InsightCard：`SourceItem.status` / `insight_card_id`

## 本阶段不做

- 不新增来源 UI
- 不做 P-004 F-2 自定义来源写库
- 不全站爬虫
- 不真实正文抓取
- 不自动生成日报
- 不语音播报
- 不改数据库 schema
