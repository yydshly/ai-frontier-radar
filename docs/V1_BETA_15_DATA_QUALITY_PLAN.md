# V1.0-beta.15 Plan — 数据质量诊断与安全清理

> 版本：V1.0-beta.15
> 分支：`feature/v1-beta-15-data-quality-diagnosis`
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

## 六、今日雷达逻辑复核

> 审阅范围：`app/application/radar/today.py`（`RadarTodayService.build_today_view`）和 `app/routes/radar.py`（`_build_radar_today_view_context`）。

### 6.1 今日雷达读取哪些表？

- **SourceItem** — 主表，所有筛选和排序都基于此表
- **InsightCard** — 仅在右侧阅读面板渲染时按需加载（`item.insight_card_id` 外键）
- **FetchRun** — 仅在 `build_fetch_run_summary()` 中加载，用于侧边栏统计

### 6.2 今日雷达按什么时间字段筛选？

**查询层**（`build_today_view`，第 578–590 行）：

```python
cutoff = datetime.utcnow() - timedelta(hours=hours)  # 默认 24 小时
items = db.query(SourceItem).filter(
    or_(
        SourceItem.first_seen_at >= cutoff,
        SourceItem.last_seen_at >= cutoff,
    )
).order_by(order).limit(limit).all()
```

排序字段（第 571–575 行）：

```python
order = desc(func.coalesce(
    SourceItem.published_at,   # 优先 published_at
    SourceItem.last_seen_at,   # 其次 last_seen_at
    SourceItem.first_seen_at,  # 再次 first_seen_at
))
```

**结论**：筛选基于 `first_seen_at` 或 `last_seen_at` ≥ cutoff，排序基于 `published_at` 回退到 `last_seen_at` 再回退到 `first_seen_at`。

### 6.3 今日雷达是否过滤 disabled source？

**否。** 当前 `RadarTodayService.build_today_view` 的 SourceItem 查询中无 Source 表 JOIN，也无 `Source.enabled` 过滤。

在 `_build_radar_today_view_context`（`routes/radar.py:424`）中，`configured_sources` 用于获取 `fetch_run_source_keys`，但该列表**不影响**今日雷达的 SourceItem 查询结果。

### 6.4 今日雷达是否过滤无 URL 的 SourceItem？

**否。** 查询无 `url IS NOT NULL` 条件。空 URL 的 SourceItem（如诊断出的 C 类问题）会被读取。

### 6.5 今日雷达是否过滤无标题的 SourceItem？

**否。** 查询无 `title IS NOT NULL` 条件。无标题的 SourceItem（如诊断出的 D 类问题）会被读取。

### 6.6 今日雷达是否过滤 source_id 不存在的 SourceItem？

**否。** 无 Source FK 验证。孤立 SourceItem（如诊断出的 E 类问题）会被读取。

### 6.7 今日雷达是否会混入 snapshot 缺失但已有摘要的数据？

**是。** 诊断出的 A 类（status=fetched/compiled 但无 snapshot）和 B 类（raw_metadata_json 有 zh_summary 但无 snapshot）都会被读取。这些数据在阅读面板会显示为空内容状态（`content_state` 来自 `build_today_item_card`）。

### 6.8 今日雷达是否会混入已经生成 InsightCard 的数据？

**是。** 这是**预期行为**——已有 InsightCard 的 SourceItem（如 `status=compiled` 且 `insight_card_id` 非空）正常出现在雷达中，右侧面板显示已生成的 InsightCard。

### 6.9 今日雷达和候选池的边界是什么？

今日雷达（`RadarTodayService`）是一个**只读阅读视图**，展示最近 24 小时的 SourceItem，按分类关键词分组。候选池（`candidate_pool`）用于筛选和排序待生成摘要/卡片的候选项目。今日雷达本身不生成任何卡片或摘要。

### 6.10 当前 69 个问题里，哪些会真实影响今日雷达？

| 问题类别 | 数量 | 是否影响雷达 | 原因 |
|---|---|---|---|
| A（content 无 snapshot） | ~53 | 是，但仅显示为空内容 | 数据存在，被读取，右侧面板 content_state=missing |
| B（summary 有但 snapshot 无） | ~8 | 是，内容不可访问 | 数据存在，被读取，摘要字段有值但正文不可用 |
| C（无 URL） | 少量 | 是，会被读取 | 查询不过滤 url |
| D（无标题） | 少量 | 是，会被读取 | 查询不过滤 title |
| E（孤立 source_id） | 少量 | 是，会被读取 | 无 FK 验证 |
| F（重复 URL） | 少量 | 可能重复出现 | 无去重 |
| G（stale fetch runs） | 8 | 否（不影响雷达读取） | 只影响 FetchRun 表，不影响 SourceItem |

### 6.11 结论分类

#### confirmed_behavior（已确认行为）
1. 雷达读取所有 `first_seen_at` 或 `last_seen_at` 在 24 小时窗口内的 SourceItem
2. 排序使用 `published_at` → `last_seen_at` → `first_seen_at` 回退链
3. 已生成 InsightCard 的 SourceItem 正常显示（预期行为）
4. 无 FK 验证：孤立 SourceItem（source_id 无对应 Source）会被读取

#### risk_points（风险点）
1. **disabled source 泄漏**：来自已禁用来源的 SourceItem 出现在雷达中 → **已修复（Phase 3）**
2. **无 URL 项泄漏**：url='' 的 SourceItem 出现在雷达中（无法点击） → **已修复（Phase 3）**
3. **无标题项泄漏**：title='' 的 SourceItem 出现在雷达中（卡片显示为空） → **已修复（Phase 3）**
4. **孤立 source_id 泄漏**：source_id 引用不存在的 Source 的 SourceItem 出现在雷达中 → **已修复（Phase 3）**
5. **snapshot 缺失数据泄漏**：A/B 类问题的数据出现，显示为空内容（后续 Phase 处理）
6. **重复 URL 泄漏**：F 类问题的重复 URL 都出现（后续 Phase 处理）

#### recommended_minimal_guards（推荐最小 guard）

以下 guard 已于 Phase 3 在 `RadarTodayService.build_today_view` 中实现：

```python
items = (
    self.db.query(SourceItem)
    .join(Source, Source.id == SourceItem.source_id)  # 确保 source 存在
    .filter(
        or_(
            SourceItem.first_seen_at >= cutoff,
            SourceItem.last_seen_at >= cutoff,
        ),
        Source.enabled.is_(True),       # guard: 过滤 disabled source
        SourceItem.url.isnot(None),     # guard: 过滤 NULL URL
        SourceItem.url != "",           # guard: 过滤空 URL
        SourceItem.title.isnot(None),  # guard: 过滤 NULL 标题
        SourceItem.title != "",         # guard: 过滤空标题
    )
    ...
)
```

#### not_fixed_yet（本次未修复）
1. A/B 类 snapshot 缺失数据——需 Phase 4 重建 snapshot 或降级处理
2. F 类重复 URL——需 Phase 5 人工 dedup

---

## 七、Phase 3 检查清单

- [x] A-G 七类诊断已实现
- [x] 诊断脚本只读，不写 DB
- [x] 每类有 risk level 和 recommended action
- [x] `python scripts/diagnose_data_quality.py` 可正常运行
- [x] 今日雷达逻辑已复核
- [x] 文档已记录本阶段范围
- [x] `scripts/cleanup_polluted_data.py` dry-run 输出正确
- [x] `scripts/acceptance_today_radar_logic.py` 覆盖关键场景

### Phase 3 新增（数据 guard 修复 + UI 过滤统计）

- [x] `app/application/radar/today.py` 新增 Source join + enabled/url/title guard
- [x] `app/application/radar/today.py` 新增 `QualityFilterStats` dataclass + `compute_quality_filter_stats()` 方法
- [x] `app/routes/radar.py` 透传 `quality_filter_stats` 到模板
- [x] `app/templates/radar_today.html` 新增过滤统计展示（`已隐藏 N 条无效内容`）
- [x] `app/static/style.css` 新增 `.radar-header-filter-stats` 等样式
- [x] `scripts/acceptance_today_radar_logic.py` 新增 `quality_filter_stats` 验证测试（2 个 PASS）
- [x] `scripts/cleanup_polluted_data.py` 新增 `filtered_from_ui` 分类（与 UI guard 口径对齐）
- [x] 今日雷达入口过滤：disabled source、url 空值、title 空值、孤立 source_id
- [x] 不改变时间窗口、排序策略、InsightCard 展示逻辑
- [x] 本轮只增加 guard，不删除历史数据

---

## 八、清理合理性判断标准

本项目的数据清理遵循以下原则，确保每次清理行为可验证、可回滚：

```
1. dry-run 可解释
   → cleanup_polluted_data.py 默认 dry-run，输出人类可读的分类报告

2. apply 前有备份
   → SQLite DB 在 --apply 前自动备份到 data/backups/
   → 备份文件名含时间戳，不覆盖已有备份

3. 今日雷达 guard 防止未来污染
   → RadarTodayService 入口过滤无效数据（disabled source / url / title / orphan source_id）
   → 新数据自动被 guard 拦截，无需重复清理

4. UI 显示过滤统计
   → /radar/today 页面显示"已隐藏 N 条无效内容"
   → 用户可验证 guard 是否生效

5. A/B snapshot 缺失数据暂不删除
   → 这些数据仍可能有标题、URL、摘要，可后续重抓或降级处理
   → 不在 Phase 2/3 自动清理范围

6. cleanup 只处理安全项
   → safe_to_apply_now：仅 stale running FetchRun 重置为 failed
   → manual_review_required：仅列出，不自动删除
   → do_not_touch_in_phase_2：snapshot 缺失、重复 URL，暂不处理
```

