# V1.0-beta.4 摘要语义统一审计与展示规则

> 审计日期：2026-06-10
> 目标：解决"中间卡片显示'待生成中文摘要'，右侧面板却可能显示英文 metadata 摘要"的用户感知混乱

---

## 一、当前摘要字段清单

| 字段 / 对象 | 来源 | 语言 | 是否 LLM 生成 | 当前页面位置 | 建议展示名 |
|-------------|------|------|--------------|-------------|-----------|
| `zh_one_liner` | `CandidateOneLinerService` 写入 `raw_metadata_json.zh_one_liner` | 中文 | **是** | 中间雷达卡片 primary_text；右侧面板 detail_summary 兜底 | `中文概述` |
| `zh_summary` | `InsightCard` 生成后写入 `raw_metadata_json.zh_summary` | 中文 | **是** | 右侧面板 detail_summary 优先来源 | `中文摘要` |
| `detail_description` | 详情页 `og:description` 抓取 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `summary` | RSS `<summary>` 或 metadata | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `description` | RSS `<description>` 或 metadata | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `excerpt` | RSS 或 metadata | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `content_snippet` | 文章内容片段 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `og_description` | `og:description` meta 标签 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `meta_description` | `meta[name=description]` 标签 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `rss_summary` | RSS feed summary 字段 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `rss_description` | RSS feed description 字段 | 不确定 | **否** | 右侧面板 detail_summary fallback | `来源摘要` |
| `summary`（card 字段） | `extract_lightweight_summary()` — 用于列表页 | 不确定 | **否** | 雷达中间卡片 secondary_text | `概述` |
| `insight_preview.fallback_summary` | `InsightCard.summary_zh` | 中文 | **是** | 右侧面板 InsightCard 区块 fallback | `InsightCard 摘要` |
| `insight_preview.*`（结构化） | `InsightCard` 结构化字段 | 中文 | **是** | 右侧面板 InsightCard 区块 | `宏观洞察` |

---

## 二、字段语义分类

### 2.1 LLM 生成的中文摘要（可信内容）

| 字段 | 生成时机 | 存储位置 |
|------|----------|----------|
| `zh_one_liner` | `CandidateOneLinerService` 对单个 SourceItem 生成 | `raw_metadata_json.zh_one_liner` |
| `zh_summary` | `InsightCard` 生成时写入 | `raw_metadata_json.zh_summary` |
| `summary_zh`（InsightCard 字段） | `InsightCard.summary_zh` | `InsightCard` 表 |

### 2.2 来源元数据摘要（非 LLM 生成，内容不确定）

这些字段由外部来源（RSS feed、网站 meta 标签）提供，可能是：
- 英文（大多数英文新闻源）
- 中文（部分中文源）
- 机器翻译
- 编辑撰写

**不能统称为"中文摘要"。**

---

## 三、用户可能产生的误解

### 误解场景 1

```
中间卡片 → 显示"待生成中文摘要"
右侧面板 → 却显示英文 metadata description
```

**原因**：`detail_summary` fallback 链中，任何一个字段存在都会显示，但标题始终是"中文摘要"。

### 误解场景 2

```
zh_one_liner 存在 → 中间卡片显示中文
右侧面板 InsightCard 区块 → 中文内容
但 detail_summary 区块标题叫"中文摘要" → 实际内容可能是英文 metadata
```

### 误解场景 3

```
"中文摘要"标题 + 英文 RSS description → 用户误以为 AI 已翻译
```

---

## 四、V1.0-beta.4 展示规则

### 4.1 右侧面板 detail_summary 区块标题

根据 `detail_summary` 的实际来源，动态显示标题：

| 实际内容来源 | 面板标题 | 说明 |
|-------------|---------|------|
| `zh_summary` 存在 | `中文摘要` | AI 生成，内容可信 |
| `zh_summary` 不存在，但 `zh_one_liner` 存在 | `中文概述` | AI 生成的一句话说明 |
| `detail_description` / `summary` / `description` 等 | `来源摘要` | 来自源站 metadata，不保证是中文 |
| 检测到内容为纯英文 | `英文来源摘要` | 帮助用户识别内容语言 |
| 全部不存在 | 不显示该区块 | — |

### 4.2 中间卡片

| 状态 | primary_text | secondary_text | 显示 |
|------|-------------|----------------|------|
| `zh_one_liner` 存在 | zh_one_liner | title（如果不同于 zh_one_liner） | 中文概述 |
| `zh_one_liner` 不存在 | display_title | `extract_lightweight_summary()` | 标题 + 概述 |

**注意**：中间卡片 primary_text 使用 `zh_one_liner` 时，secondary_text 显示原始标题（不是英文摘要），这是正确的。

### 4.3 InsightCard 区块

始终显示为 `宏观洞察`，其中 `fallback_summary` 使用 `InsightCard.summary_zh`。

---

## 五、暂不改数据库的原因

1. **zh_one_liner 和 zh_summary 已存在**：作为 JSON 字段存储在 `raw_metadata_json` 中，无需 schema 变更。
2. **优先级**：V1.0-beta.4 聚焦展示层澄清，不重构生成链路。
3. **风险控制**：数据库 schema 变更需要完整的 migration 和兼容性测试。
4. **后续判断**：如果 V1.0-beta.5 需要引入独立 `SourceItem.zh_summary` 字段，再评估 schema migration。

---

## 六、后续是否需要 Schema Migration

**当前评估：暂不需要。**

理由：
- `zh_one_liner` 和 `zh_summary` 已存储在 `raw_metadata_json` 中，查询逻辑已适配
- `detail_summary` 在 `CandidateDisplayCard` 中作为派生字段，不需要独立存储
- 唯一收益是将 `zh_summary` 提升为一级字段，改善查询性能，但这是 V1.0-beta.5 以后的优化项

**如果未来需要独立字段的判断标准**：
- 当 `zh_summary` 查询成为性能瓶颈时（大量 item 需要解析 JSON）
- 当需要独立索引或全文搜索 `zh_summary` 时

---

## 七、实现细节

### 7.1 新增字段

在 `RadarPanelState` 中新增：

```python
detail_summary_label: str   # "中文摘要" | "中文概述" | "来源摘要" | "英文来源摘要"
detail_summary_kind: str     # "zh_summary" | "zh_one_liner" | "metadata_summary" | "english_metadata_summary" | "missing"
```

在 `_build_panel_state()` 中计算 `detail_summary_label` 和 `detail_summary_kind`。

### 7.2 面板标题不再写死

模板中使用：

```html
{% if sel_card and sel_card.detail_summary %}
<section class="radar-panel-section">
    <h3>{{ view.panel_state.detail_summary_label }}</h3>
    <div class="radar-panel-summary">{{ sel_card.detail_summary }}</div>
</section>
{% endif %}
```

不再使用 `<h3>中文摘要</h3>` 硬编码。

### 7.3 语言检测（最小化）

使用启发式规则检测纯英文 metadata 摘要：
- 不包含任何中文字符（CJK Unicode range）
- 且来源于 `detail_description` / `summary` / `description` 等非结构化字段

---

## 八、测试验收

### 8.1 静态验收

- [ ] `docs/V1_BETA_4_SUMMARY_SEMANTICS_PLAN.md` 存在
- [ ] 文档包含所有字段分类
- [ ] `radar_today_panel.html` 不再包含硬编码 `<h3>中文摘要</h3>`
- [ ] `RadarPanelState` 包含 `detail_summary_label`

### 8.2 功能验收

- zh_one_liner 存在时，面板标题为"中文概述"
- zh_summary 存在时，面板标题为"中文摘要"
- 英文 metadata 摘要存在时，面板标题为"英文来源摘要"
- 无 zh_one_liner / zh_summary 时，面板标题为"来源摘要"

---

## 九、涉及文件

| 文件 | 修改类型 |
|------|---------|
| `docs/V1_BETA_4_SUMMARY_SEMANTICS_PLAN.md` | 新增 |
| `app/application/radar/today.py` | 修改：`_build_panel_state()` 增加字段 |
| `app/templates/partials/radar_today_panel.html` | 修改：面板标题改为动态 |
| `scripts/quick_test.py` | 修改：增加 [46] 验收 section |
| `README.md` | 修改：V1.0-beta.4 入口 |
| `docs/NEXT_EXECUTION_PLAN.md` | 可选更新 |

---

## 十、禁止修改范围（与任务要求一致）

```
app/models.py          — 不改
app/db.py              — 不改
数据库 schema          — 不改
app/services/insight_compiler.py  — 不改
抓取逻辑               — 不改
LLM 调用逻辑           — 不改
```
