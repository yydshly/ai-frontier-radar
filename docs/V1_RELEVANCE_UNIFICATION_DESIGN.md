# 相关性统一设计（C1，设计先行 / 不改代码）

> 今日雷达里有三套"相关性"逻辑各自硬编码关键词与来源权重。它们**目的不同**，
> 不能简单合并；但其中的**来源重要性**与**主题词表**是同一份判断被抄了多份，会漂移。
> 本文界定"哪些该统一、哪些保持独立"，并给出分阶段、带行为差异度量的落地路线。
> **本阶段只设计，任何会改变可见行为（归类/排序/推荐结果）的改动都需你确认后再做。**

## 1. 现状（grounded）

| 系统 | 文件 | 目的 | 关键词 | 来源权重 |
|------|------|------|--------|----------|
| 分类 | `today.py _CATEGORIES` | 把每条**归入一个目录**（首次匹配子串） | 11 主题 / 122 词 | 无 |
| 报告卡排序 | `daily_report_card.py` | "今日必看/扫一眼"**分层** | `_STRONG_SIGNAL`+`_INTEREST`(~60) | `_SOURCE_WEIGHTS`（float 1.0–2.0） |
| 推荐打分 | `compile_candidates.py` | 选**推荐生成洞察的 top-N** | `_TOPIC_KEYWORDS` | `_SOURCE_PRIORITY`（int） |

### 真正的重复（值得统一）
- **来源重要性表 ×2**：`_SOURCE_WEIGHTS`（float）与 `_SOURCE_PRIORITY`（int）对同一批来源各打一套分。改一个忘改另一个就会出现"报告里很重要、推荐里却不优先"。
- **主题词表 ×3**：三份关键词彼此重叠又不一致（如"agent"在三处都有，但"stargate/devtool"只在分类里），同一篇文章在分类/排序/推荐里"算不算相关"口径不同。

### 应保持独立（不是重复）
- **三个用途不同**：分类是"归一类"，报告是"分两层"，推荐是"排 top-N"。**打分/归类公式各自保留**，不强行合一。

## 2. 目标
- **单一来源重要性**：一份 `source_importance`（来源→重要度），三处都从它派生各自所需的数值。
- **单一主题词表**：一份 `topic_keywords`（主题→关键词），分类直接用；排序/推荐的"主题命中"也用它。
- **公式不动**：分层阈值、top-N 选取、新鲜度衰减等各自保留。

## 3. 分阶段路线（每阶段标注行为影响）

### Phase A — 抽取单一真相源（零行为变化）
- 新增 `app/application/radar/relevance.py`：
  - `SOURCE_IMPORTANCE: dict[str, float]`（规范的来源重要度，0–1 或 1–10 任一刻度）
  - `TOPIC_KEYWORDS: list[(topic_key, title, keywords)]`（= 现有 `_CATEGORIES` **逐字搬入**）
- **此阶段无人切换使用** → 行为完全不变。仅把"权威数据"集中。

### Phase B — 分类改读统一词表（零行为变化，需验证）
- `today._CATEGORIES` 改为从 `relevance.TOPIC_KEYWORDS` 读取（**逐字相同**）。
- 验证：写一个只读 diff 脚本，对当前全部条目跑"改前 vs 改后归类"，**断言 100% 一致**。
- 风险：低（同一份数据，只是搬家）。

### Phase C — 来源权重统一（**会改数值，需你确认**）
- 让 `_SOURCE_WEIGHTS` / `_SOURCE_PRIORITY` 都从 `SOURCE_IMPORTANCE` 派生（各自线性映射到原刻度）。
- **行为影响**：若映射不能 100% 复现两套旧数值，报告分层与推荐排序的**结果会变**。
- 做法：先出 diff 报告（改前 vs 改后的"今日必看"集合、推荐 top-N 集合），你看过差异再决定是否接受。

### Phase D — 评分主题词统一（**更大行为变化，可选**）
- 让报告/推荐的"主题命中"也用 `TOPIC_KEYWORDS`（替掉 `_STRONG_SIGNAL/_INTEREST/_TOPIC_KEYWORDS`）。
- 行为影响最大（排序/推荐都变），同样先出 diff、再定。

## 4. 验证方法（每个会改行为的阶段都要先做）
- 只读 diff 脚本：对当前 DB 的条目，输出"改前/改后"的：
  - 分类分布（每类条数）
  - "今日必看" primary 集合
  - 推荐 top-N 集合
- 用差异量化"这次改动到底改了什么"，让你基于真实数据决定。

## 5. 边界
- Phase A/B 零行为变化（可直接做，带 diff 断言）。
- Phase C/D 改可见行为，**必须先出 diff、你确认**。
- 不改抓取/调度/写入/UI 布局；纯相关性逻辑层。

## 6. 建议执行顺序
1. **Phase A**（抽取，零风险）→ 2. **Phase B**（分类搬家，带 100% 一致断言）→ 停下给你看
   → 3. Phase C 先出 diff 报告 → 你确认 → 实施 → 4. Phase D 同理。

参考：[V1_SOURCE_PIPELINE_ANALYSIS.md](V1_SOURCE_PIPELINE_ANALYSIS.md)、
[V1_ITEM_STATE_MODEL_DESIGN.md](V1_ITEM_STATE_MODEL_DESIGN.md)
