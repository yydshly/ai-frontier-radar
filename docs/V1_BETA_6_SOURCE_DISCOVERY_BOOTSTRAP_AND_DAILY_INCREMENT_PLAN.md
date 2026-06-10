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

## V1.0-beta.6.2 实际入口

本轮实现的是已有 YAML 来源的最小发现入口，不实现新抓取器。

- UI：`POST /radar/today/bootstrap`
  - 今日雷达左侧显示“初始化来源内容”。
  - 默认执行 dry-run，只展示会检查多少来源，不写 `FetchRun` / `SourceItem`。
  - apply 需要显式表单参数 `action=apply`，个人手动确认后才会执行。
- UI：`POST /radar/today/update`
  - 文案调整为“更新今日新增”。
  - 继续复用 due-source 逻辑，只处理到期来源。
- CLI：`scripts/run_source_discovery_once.py`
  - `--mode bootstrap --dry-run`：预览初始化最近 20/50 条。
  - `--mode bootstrap --apply`：显式执行 bootstrap。
  - `--mode daily_increment --dry-run`：预览每日增量到期来源。
  - `--mode daily_increment --apply`：显式执行每日增量。

## dry-run / apply 语义

- dry-run：只计算来源计划，不写库、不 enqueue、不创建 `FetchRun`，不触发网络抓取。
- apply：复用 `SourceFetchBackgroundService`，由现有 `FetchRun` / `SourceItem` / 去重逻辑处理写入。
- apply 时设置单来源数量上限，bootstrap 默认最近 20 条，最大 50 条。
- apply 时禁用 fetch 后自动摘要，避免本入口调用 LLM。

## bootstrap 和 daily_increment 差异

- `bootstrap`：用于第一次建立本地候选池基线，读取 enabled YAML 来源，忽略 due-source 冷却时间，只跳过 unsupported / missing / already_running。
- `daily_increment`：用于后续日常更新，复用 `compute_due_sources()`，只处理到期来源，不重复启动 already_running 来源。

## 后续 DailyReportCard 接入

下一步可以在每日增量完成后读取 `first_seen_at` 属于当天的 `SourceItem`，先生成中文概述和中文摘要，再聚合为 DailyReportCard。DailyReportCard 仍应保持显式触发，不在本轮 bootstrap / daily_increment 中自动生成。

## 本阶段不做

- 不新增来源 UI
- 不做 P-004 F-2 自定义来源写库
- 不全站爬虫
- 不真实正文抓取
- 不自动生成日报
- 不语音播报
- 不改数据库 schema
