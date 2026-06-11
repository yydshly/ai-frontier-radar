# 条目状态模型收敛设计（C5 / 根债，设计先行）

> 这是分析中反复标记的**核心技术债**。本文件只做设计与分阶段方案，**不改业务代码**。
> 目标：把"一条 SourceItem 现在处于什么状态"收敛成单一可信读取层，消除多处口径漂移，
> 并对"是否升级数据库表示"给出明确决策点。

## 1. 现状（已盘点，grounded）

一条 `SourceItem` 的状态目前散落在三类载体：

1. **列**：`SourceItem.status`（discovered / compiling / compiled / failed）、`insight_card_id`。
2. **`raw_metadata_json` 里的 ~15 个键**（按代码引用次数）：
   - 摘要：`zh_summary`(33)、`zh_one_liner`(32)、`summary_zh`(11)、`auto_summary`(5)
   - 摘要过程：`summary_status`(9)、`summary_basis`(6)
   - 正文：`content_fetch_status`(4)、`content_fetch_error`(2)、`full_text`(3)、`raw_text_path`/`content_text`/`content_snapshot`/`article_text`/`markdown_path`(各 1)
   - 洞察：`insight_status`(4)
3. **多个派生器各自解读**（口径可能不一致）：
   - `today_item_card.py`：`_summary_state` / `_content_state` / `_insight_state`
   - `today.py _build_panel_state`：又算一套 summary/insight 状态
   - `candidates/display.py build_candidate_display_card`：算 `uses_zh_one_liner` 等
   - `daily_digest` / `daily_report`：用 `raw_metadata_json LIKE '%"key"%'` 统计"已摘要"

### 已确认的具体问题
- **键名漂移**：`zh_summary`(33) 与 `summary_zh`(11) 是**同一概念两个键名**——不同代码读不同键，判断会不一致。
- **多真相源**："是否有摘要 / 是否有洞察"在 ≥4 处各判各的，改一处易漏其它（C4 漏 `zh_summary` 就是实例，已修但根因仍在）。
- **JSON blob 当状态库**：状态用 `LIKE` 子串查询，无 schema、无索引、键改名即失效、易误匹配。
- **状态分散**：要判断"这条到了哪一步"，得同时看 `status` + `insight_card_id` + 多个 metadata 键，没有单一入口。

## 2. 目标

- **单一读取层**：任何地方想知道"这条的内容/摘要/洞察处于什么状态"，都调同一个函数，得到结构化结果。
- **单一键集**：摘要/正文/洞察的 metadata 键有唯一规范名（含对历史别名的兼容读取）。
- **不强行改 schema**：先在不动数据库结构的前提下消除漂移；是否升级为列/索引留作显式决策点。

## 3. 分阶段方案

### Phase 1：单一只读状态访问层（低风险、零 schema、零行为变化）
新增 `app/application/source_items/item_state.py`（或 radar 下）：

```python
@dataclass(frozen=True)
class ItemSummaryState:    # missing | source_summary | one_liner | full_summary
    has_one_liner: bool
    has_zh_summary: bool
    basis: str | None       # metadata | html_snapshot | ...
@dataclass(frozen=True)
class ItemContentState:     # not_fetched | queued | fetched | fetch_failed
    state: str
    error: str | None
@dataclass(frozen=True)
class ItemInsightState:     # none | eligible | has_card | generated
    state: str
    insight_card_id: int | None
@dataclass(frozen=True)
class ItemState:
    summary: ItemSummaryState
    content: ItemContentState
    insight: ItemInsightState

def read_item_state(item) -> ItemState: ...   # 纯函数，解析一次 raw_metadata_json
```

- 让 `today_item_card` / `_build_panel_state` / `display` / `daily_digest` / `daily_report` 的状态判断**全部改调 `read_item_state`**（分步替换，每步保持输出不变 + quick_test 守护）。
- 规范摘要键读取：`read_item_state` 内部同时认 `zh_summary` 与历史别名 `summary_zh`（兼容），对外只暴露 `has_zh_summary`。
- 收益：消灭 §1.3 的多真相源与 §1 的键名漂移读取风险；后续任何状态改动只改一处。

### Phase 2：键名规范化（中风险，需一次性数据兼容）
- 定一份**规范键集**（如 `zh_summary` 为准，`summary_zh` 标记为 deprecated 别名）。
- 写入侧统一只写规范键；读取侧（Phase 1 的访问层）兼容旧别名。
- 提供一个只读诊断脚本统计历史数据里别名分布，决定是否做一次性回填。

### Phase 3（决策点，不默认做）：是否把热状态升级为列/索引
- 现状用 `LIKE '%"zh_one_liner"%'` 统计"已摘要"，无法走索引，数据量大时慢。
- 选项 A：保持 JSON blob（个人单机量级，够用）。
- 选项 B：为高频判定（has_summary / insight_state）加**派生列 + 索引**，写入时维护。
- 决策依据：来源/条目规模、今日雷达/报告页的实际查询耗时。**在没有明确性能痛点前，默认 A。**

## 4. 边界
- Phase 1 **不改 schema、不改写入逻辑、不改 UI、不调用 LLM**，纯读取层收敛。
- 不改 `SourceItem.status` 与 `FetchRun` 的既有语义。
- 每步都要有 quick_test 守护"输出与改造前一致"。

## 5. 验收（Phase 1）
- 新增 `read_item_state` 纯函数 + 单测（各状态组合）。
- 至少 `today_item_card` 与 `daily_digest`/`daily_report` 的"已摘要"判定改为复用它，且渲染/计数与改造前一致。
- quick_test / acceptance 全绿。

## 6. 关联
- 已修的相关问题：C4（marker 统一，见 `daily_scope.SUMMARY_MARKERS`）、C3（设置单一来源）、C6（排序）。
- 关联未决：C1（三套分类/排序/相关性关键词表未复用）——可在状态层收敛后单独立项。

参考：[V1_SOURCE_PIPELINE_ANALYSIS.md](V1_SOURCE_PIPELINE_ANALYSIS.md)
