# V1.0-beta.15 Plan — 数据质量诊断与安全清理

> 版本：V1.0-beta.15
> 分支：`feature/v1-beta-15-dataquality-diagnosis`
> main 基准 commit：`a91e465`（merge: polish source card layout）
> 规划日期：2026-06-11

---

## 一、阶段定位

beta.14 完成了两件事：

1. 15 个精选来源配置修正和每日抓取链路验证
2. `/sources` 页面 UI 优化

但在 beta.14 开发过程中，诊断脚本发现了数据质量问题：
- 部分 SourceItem 有抓取记录但 snapshot 文件缺失
- 部分 SourceItem 有摘要但 snapshot 缺失
- 存在孤立（orphaned）SourceItem
- 存在重复 URL 条目
- 历史上 stale fetch runs 遗留的 `[stale-timeout]` 标记

本轮目标：**先做诊断增强，不做破坏性清理**。

---

## 二、当前数据质量问题分类

### 2.1 七类问题定义

| 类别 | 问题 | 风险 | 说明 |
|---|---|---|---|
| A | content_exists_but_snapshot_missing | medium | SourceItem status 为 fetched/compiled，但 snapshot 文件不存在。阻塞摘要生成。 |
| B | summary_exists_but_snapshot_missing | medium | SourceItem 的 raw_metadata_json 中有 zh_summary，但 snapshot 文件不存在。摘要存在但内容不可访问。 |
| C | source_item_without_url | high | SourceItem 没有 URL。无法生成 InsightCard。 |
| D | source_item_without_title | medium | SourceItem 没有标题。影响卡片显示。 |
| E | source_item_without_source | high | SourceItem.source_id 引用了不存在的 Source 行。孤立数据，无法通过任何来源访问。 |
| F | duplicate_url_items | low | 同一来源内存在重复 URL。会导致重复 InsightCard。 |
| G | stale_failed_fetch_runs | low | FetchRun 状态为 failed 且 error_message 含 `[stale-timeout]`。属于历史遗留，可通过 `mark_stale_fetch_runs_failed.py --apply` 恢复。 |

### 2.2 哪些问题阻塞主链路

- **C（无 URL）**：完全无法生成 InsightCard，候选池会显示为"无标题"
- **A（content 但无 snapshot）**：摘要生成失败，卡片内容为空
- **B（摘要存在但无 snapshot）**：摘要存在但原始内容不可访问，摘要质量无法核实

### 2.3 哪些是历史遗留

- **G（stale-fetch runs）**：历史上超时自动清理的遗留，可安全恢复
- **F（重复 URL）**：可能来自早期探测 bug，不影响现有卡片，但会污染数量统计
- **D（无标题）**：部分可能是早期 RSS 条目解析失败遗留

---

## 三、本阶段不做什么

明确写出，防止范围蔓延：

```
❌ 不删除任何 SourceItem
❌ 不重建 snapshot 文件
❌ 不调用 LLM 生成摘要
❌ 不修改已有 InsightCard
❌ 不修复 stale fetch runs（仅诊断，不执行 mark_stale_fetch_runs_failed.py --apply）
❌ 不访问网络
❌ 不做批量数据迁移
```

**本阶段只做：增强诊断输出，生成可读分级报告。**

---

## 四、增强后的诊断脚本

`scripts/diagnose_data_quality.py` 已升级为七类诊断输出：

```
A. content_exists_but_snapshot_missing   [MED ] — snapshot 缺失，阻塞摘要
B. summary_exists_but_snapshot_missing  [MED ] — 摘要存在但内容不可访问
C. source_item_without_url             [HIGH] — 无 URL，无法生成卡片
D. source_item_without_title           [MED ] — 无标题，影响显示
E. source_item_without_source          [HIGH] — 孤立数据，无法通过来源访问
F. duplicate_url_items                [LOW ] — 重复 URL，污染统计
G. stale_failed_fetch_runs            [LOW ] — 历史遗留，可安全恢复
```

每类输出：
- count（数量）
- sample 5 条（示例）
- risk level（low / medium / high）
- recommended action（推荐处理方式）

---

## 五、下一步（后续阶段，非本阶段范围）

诊断完成后，可以分阶段处理：

### Phase 2（人工确认后执行）
- 修复 G 类 stale fetch runs：`python scripts/mark_stale_fetch_runs_failed.py --apply`
- 清理 E 类孤立 SourceItem（需人工确认哪些可以删除）
- 清理 C 类无 URL 的 SourceItem（需人工确认是否可删）

### Phase 3（重建 snapshot，可选）
- 对 A 类：重新抓取对应 URL 重建 snapshot
- 对 B 类：尝试从 raw_metadata_json 重建，或重新抓取

### Phase 4（去重，低优先级）
- 对 F 类：人工确认后删除重复条目

---

## 六、本阶段检查清单

- [x] A-G 七类诊断已实现
- [x] 诊断脚本只读，不写 DB
- [x] 每类有 risk level 和 recommended action
- [x] `python scripts/diagnose_data_quality.py` 可正常运行
- [ ] 诊断输出可读性已验证
- [ ] 文档已记录本阶段范围
