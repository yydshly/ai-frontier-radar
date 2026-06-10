# V1.0-beta.5 摘要写入规范

> 审计日期：2026-06-10
> 目标：定义谁可以写入哪个摘要字段，防止字段覆盖乱序，明确失败记录规则

---

## 一、背景问题

当前摘要相关字段分散在多个层次：

```text
raw_metadata_json.zh_one_liner
raw_metadata_json.zh_summary
raw_metadata_json.description
raw_metadata_json.summary
raw_metadata_json.rss_summary
InsightCard.summary_zh
CandidateDisplayCard.summary
CandidateDisplayCard.detail_summary
RadarPanelState.detail_summary_label
RadarPanelState.detail_summary_kind
```

V1.0-beta.4 已区分展示标签，但底层仍缺少统一写入规范。

风险：

1. 后续开发者不知道 `zh_one_liner` 和 `zh_summary` 的边界
2. 某个模块可能错误覆盖 metadata 字段
3. 英文来源摘要可能被误当成 AI 中文摘要
4. `InsightCard` 摘要和 `SourceItem` 中文摘要的关系不清楚
5. 未来批量摘要、自动摘要、失败重试容易写乱

---

## 二、当前摘要字段总览

| 字段 | 存储位置 | 语言 | 生成者 | 是否 AI 生成 |
|------|----------|------|--------|-------------|
| `zh_one_liner` | `raw_metadata_json` | 中文 | `CandidateOneLinerService` | **是** |
| `zh_summary` | `raw_metadata_json` | 中文 | 待定义服务（或 InsightCard 编译流程间接写入） | **是** |
| `description` | `raw_metadata_json` | 不确定 | 来源抓取（RSS / HTML meta） | 否 |
| `summary` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `rss_summary` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `og_description` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `meta_description` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `detail_description` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `excerpt` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `content_snippet` | `raw_metadata_json` | 不确定 | 来源抓取 | 否 |
| `InsightCard.summary_zh` | `InsightCard` 表 | 中文 | InsightCard 编译流程 | **是** |
| `CandidateDisplayCard.summary` | 内存派生字段 | 不确定 | `build_candidate_display_card()` | 否 |
| `CandidateDisplayCard.detail_summary` | 内存派生字段 | 不确定 | `build_candidate_display_card()` | 否 |
| `RadarPanelState.detail_summary_label` | 内存派生字段 | — | `today.py` | — |
| `RadarPanelState.detail_summary_kind` | 内存派生字段 | — | `today.py` | — |

---

## 三、字段权威性等级

### L0：来源原始摘要（永远不是 AI 中文摘要）

```python
L0_KEYS = (
    "detail_description",
    "summary",
    "description",
    "excerpt",
    "content_snippet",
    "og_description",
    "meta_description",
    "rss_summary",
    "rss_description",
)
```

特点：
- 外部来源提供（RSS feed / HTML meta / og:description 等）
- 不一定是中文，不一定是 AI 生成
- **永远不能被标记为 AI 中文摘要**
- 作为无 AI 摘要时的 fallback

### L1：中文一句话摘要

```text
字段：raw_metadata_json.zh_one_liner
生成者：CandidateOneLinerService
用途：列表主展示（primary_text）和快速理解
生成时机：候选池发现时，按策略限制生成
```

特点：
- AI 生成，40-80 中文字符
- 用于中间雷达卡片 primary_text
- **默认不覆盖已有非空 zh_one_liner，除非显式 force**

### L2：中文详细摘要

```text
字段：raw_metadata_json.zh_summary
生成者：待定义（当前可由 InsightCard 编译流程间接写入）
用途：右侧阅读面板 detail_summary 最高优先级
生成时机：用户主动触发或 InsightCard 生成时
```

特点：
- AI 生成，120-220 中文字符
- 用于右侧面板 detail_summary
- **默认不覆盖已有非空 zh_summary，除非显式 force**

### L3：InsightCard 洞察摘要

```text
字段：InsightCard.summary_zh
生成者：InsightCard 编译流程（insight_compiler.py）
存储位置：InsightCard 表（一级字段）
用途：InsightCard 页面和右侧宏观洞察 fallback
```

特点：
- AI 生成，属于结构化洞察卡内部摘要
- **不自动覆盖 zh_one_liner / zh_summary**
- 重新编译时由 InsightCard 自己控制

---

## 四、生成者 / 写入者 / 消费者矩阵

| 字段 | 生成者 | 写入者 | 消费者 | 是否可覆盖 | 失败记录位置 | 备注 |
|------|--------|--------|--------|-----------|-------------|------|
| `zh_one_liner` | `CandidateOneLinerService` | `CandidateOneLinerService._write_result()` | `build_candidate_display_card()` / `today.py` | 默认不覆盖已有非空值 | `raw_metadata_json.zh_one_liner_error` | 覆盖需显式 `force=True` |
| `zh_summary` | 待定义服务 | 待定义服务（当前 `insight_compiler` 间接写入） | `build_candidate_display_card()` / `today.py` | 默认不覆盖已有非空值 | `raw_metadata_json.zh_summary_error` | 覆盖需显式 `force=True` |
| `description` | 来源抓取（RSS / HTML） | `SourceFetchService` / `background_fetch.py` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0，永远不是 AI 摘要 |
| `summary` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `rss_summary` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `og_description` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `meta_description` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `detail_description` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `excerpt` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `content_snippet` | 来源抓取 | `SourceFetchService` | `build_candidate_display_card()` fallback | 由抓取逻辑决定 | `FetchRun.error_message` | L0 |
| `InsightCard.summary_zh` | `insight_compiler.py` | `insight_compiler.py` | 右侧面板 `insight_preview.fallback_summary` | 由重新编译控制 | `InsightCard.error_message` | L3，InsightCard 内部 |
| `CandidateDisplayCard.summary` | —（派生） | —（只读） | 雷达中间卡片 secondary_text | 只读 | — | 从 L0 字段读取 |
| `CandidateDisplayCard.detail_summary` | —（派生） | —（只读） | 右侧面板 detail_summary | 只读 | — | 优先级：L2 > L1 > L0 |
| `RadarPanelState.detail_summary_label` | —（派生） | —（只读） | 右侧面板区块标题 | 只读 | — | 动态计算 |
| `RadarPanelState.detail_summary_kind` | —（派生） | —（只读） | 逻辑分支判断 | 只读 | — | 动态计算 |

---

## 五、写入规则

### 5.1 zh_one_liner

```python
# 生成者
class CandidateOneLinerService:
    def generate_for_item(self, item: SourceItem, *, force: bool = False) -> OneLinerResult:
        ...

# 写入位置
raw_metadata_json.zh_one_liner

# 覆盖规则
if not force and raw.get("zh_one_liner"):
    # 跳过，已有非空值
    return OneLinerResult(success=False, status="skipped", error="already exists")

# 失败记录
raw["zh_one_liner_error"] = error_message
raw["zh_one_liner_status"] = "failed"
```

### 5.2 zh_summary

```python
# 写入规则
if not force and raw.get("zh_summary"):
    # 跳过，已有非空值
    return

# 失败记录
raw["zh_summary_error"] = error_message
raw["zh_summary_status"] = "failed"
```

### 5.3 L0 字段（来源摘要）

```python
# 写入者：抓取逻辑（SourceFetchService / background_fetch.py）
# 覆盖规则：由抓取逻辑内部决定，一般是追加更新，不清除已有值

# 失败记录
FetchRun.error_message  # 整体抓取失败
SourceItem.error_message  # 单条 item 失败
```

### 5.4 InsightCard.summary_zh

```python
# 写入者：insight_compiler.py
# 覆盖规则：重新编译时由编译器控制，不受外部 force 参数影响

# 失败记录
InsightCard.error_message
InsightCard.status == "failed"
```

---

## 六、覆盖规则

### 6.1 强制覆盖（force）

只有显式传入 `force=True` 时才能覆盖已有非空字段：

```python
# ✅ 正确
service.generate_for_item(item, force=True)

# ❌ 错误
service.generate_for_item(item)  # 不覆盖已有非空 zh_one_liner
```

### 6.2 InsightCard 不反向污染 SourceItem

```python
# InsightCard.summary_zh 不自动覆盖 zh_one_liner / zh_summary
# 除非明确设计，否则两个系统独立运作
```

### 6.3 展示层不写入

```python
# build_candidate_display_card() 是纯函数，只读不写
# today.py 是只读视图，不修改数据库
```

---

## 七、失败记录规则

### 7.1 zh_one_liner 失败

```python
raw_metadata_json = {
    ...,
    "zh_one_liner": "...",           # 成功时写入
    "zh_one_liner_status": "success", # 或 "failed" / "skipped"
    "zh_one_liner_error": None,       # 失败时写入错误信息
    "zh_one_liner_model": "gpt-4o",   # 成功时写入模型名
    "zh_one_liner_generated_at": "2026-06-10T...",  # 成功时写入
}
```

### 7.2 zh_summary 失败

```python
raw_metadata_json = {
    ...,
    "zh_summary": "...",              # 成功时写入
    "zh_summary_status": "success",   # 或 "failed"
    "zh_summary_error": None,         # 失败时写入错误信息
    "zh_summary_model": "gpt-4o",    # 成功时写入模型名
    "zh_summary_generated_at": "2026-06-10T...",  # 成功时写入
}
```

### 7.3 抓取失败

```python
# FetchRun 级别
FetchRun.error_message = "Connection timeout after 30s"
FetchRun.status = "failed"

# SourceItem 级别（如果能孤立到单条）
SourceItem.error_message = "Failed to parse HTML"
```

---

## 八、展示读取规则

### 8.1 右侧面板 detail_summary 读取优先级

```
zh_summary (L2) > zh_one_liner (L1) > L0 字段链
```

```python
# display.py — build_candidate_display_card()
detail_summary = (
    raw_meta.get("zh_summary")
    or raw_meta.get("zh_one_liner")
    or raw_meta.get("detail_description")
    or raw_meta.get("summary")
    or raw_meta.get("description")
    ...
)
```

### 8.2 中间卡片 primary_text 读取

```
zh_one_liner (L1) 存在 → primary_text = zh_one_liner
否则 → primary_text = display_title
```

### 8.3 标签判断（detail_summary_kind）

```python
if has_zh_summary:
    kind = "zh_summary"       # 标签："中文摘要"
elif has_zh_one_liner:
    kind = "zh_one_liner"     # 标签："中文概述"
elif has_cjk(L0_fallback):
    kind = "metadata_summary" # 标签："来源摘要"
else:
    kind = "english_metadata_summary"  # 标签："英文来源摘要"
```

---

## 九、暂不改数据库 schema 的原因

1. `zh_one_liner` 和 `zh_summary` 已作为 JSON 字段存储在 `raw_metadata_json` 中，查询逻辑已在 `one_liner.py` / `display.py` / `today.py` 中适配
2. `CandidateDisplayCard` 和 `RadarPanelState` 是内存派生字段，不需要独立存储
3. 数据库 schema 变更（Alembic migration）需要完整的兼容性测试和回滚方案
4. V1.0-beta.5 聚焦写入规范定义，不做结构性变更

---

## 十、未来 schema migration 判断条件

当满足以下条件时，再评估将 `zh_summary` 提升为 `SourceItem` 一级字段：

1. `zh_summary` 查询成为性能瓶颈（大量 item 需要解析 JSON）
2. 需要对 `zh_summary` 做独立索引或全文搜索
3. 需要对 `zh_summary` 做独立的状态管理（成功 / 失败 / 重新生成）
4. 有明确的 UI 需要直接查询 `zh_summary` 而不经过 JSON 解析

判断流程：
```
是否需要独立索引？ → 否：继续用 JSON，是：评估 migration
是否需要独立状态管理？ → 否：继续用 JSON，是：评估 migration
是否有明确的性能问题？ → 否：继续用 JSON，是：profile 后评估
```

---

## 十一、验收策略

### 11.1 静态验收（quick_test）

- [ ] `docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md` 存在
- [ ] 文档包含 `zh_one_liner`
- [ ] 文档包含 `zh_summary`
- [ ] 文档包含 `InsightCard.summary_zh`
- [ ] 文档包含 L0 / L1 / L2 / L3 定义
- [ ] 文档包含"默认不覆盖"
- [ ] 文档包含"不自动覆盖 zh_one_liner"
- [ ] 文档包含"暂不改数据库 schema"
- [ ] `README.md` 或 `NEXT_EXECUTION_PLAN.md` 包含 `V1.0-beta.5`

### 11.2 静态验收（acceptance）

- [ ] write policy 文档存在
- [ ] 文档定义 L0-L3 字段等级
- [ ] 文档明确 `InsightCard.summary_zh` 不自动覆盖 `zh_one_liner`
- [ ] 文档明确 metadata summary 不是 AI 中文摘要

### 11.3 代码边界验收

- [ ] `one_liner.py` 的 `CandidateOneLinerService._write_result()` 是 `zh_one_liner` 的唯一写入点
- [ ] `display.py` 的 `build_candidate_display_card()` 是纯函数（只读）
- [ ] `today.py` 的 `RadarTodayService` 不修改数据库
- [ ] 无模块在写入 L0 字段时错误标记为 AI 中文摘要

---

## 十二、涉及文件

| 文件 | 修改类型 |
|------|---------|
| `docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md` | **新增** |
| `docs/NEXT_EXECUTION_PLAN.md` | 更新：增加 V1.0-beta.5 条目 |
| `README.md` | 更新：增加 V1.0-beta.5 入口 |
| `scripts/quick_test.py` | 更新：增加 [48] V1.0-beta.5 section |
| `scripts/acceptance_first_usable_loop.py` | 更新：增加 [20] V1.0-beta.5 section |
| `app/application/candidates/summary_policy.py` | 可选新增：纯常量模块 |

---

## 十三、禁止修改范围

```
app/models.py              — 不改
app/db.py                  — 不改
数据库 schema              — 不改
app/services/insight_compiler.py  — 不改
抓取逻辑                   — 不改
LLM 调用逻辑               — 不改
```
