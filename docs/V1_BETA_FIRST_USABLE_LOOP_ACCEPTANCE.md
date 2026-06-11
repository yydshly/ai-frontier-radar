# V1.0-beta First Usable Loop 验收报告

> 验收日期：2026-06-11
> 验收分支：`feature/v1-beta-15-data-quality-diagnosis`
> 验收commit：`ea46446 polish: reorganize today radar controls`

---

## 1. 当前目标

验收 V1.0-beta First Usable Loop（首个可日常使用的闭环）是否已达到"可日常使用"的最低标准。

验收范围：今日雷达主流程、摘要生成链路、推荐深入分析链路、洞察卡链路、今日报告链路、右侧阅读面板。

---

## 2. 已验证的用户主链路

```
进入今日雷达 (/radar/today?section=all&page=1)
  → 更新今日新增（POST /radar/today/update）
  → 生成当前页中文摘要（POST /radar/today/generate-summaries）
  → 查看推荐深入分析（compile_candidates 区块）
  → 生成 / 查看洞察卡（POST /source-items/{id}/enqueue-compile 或 GET /cards/{id}）
  → 查看今日报告（GET /radar/daily-report）
  → 生成今日核心报告（POST /radar/today/daily-report）
  → 右侧阅读面板状态联动
```

所有节点均已验证通过。

---

## 3. 页面入口与控件说明

### 3.1 顶部快捷入口

| 入口 | 路由 | 状态 |
|------|------|------|
| 信息来源 | /sources | ✅ |
| 候选池 | /candidate-pool | ✅ |
| 生成队列 | /generation-queue | ✅ |
| 洞察卡 | /cards | ✅ 已改为"洞察卡" |

### 3.2 左侧分组顺序

1. **目录** — 分类筛选（全部/今日重点/各技术分类）
2. **今日操作** — 更新今日新增 / 查看今日报告 / 生成今日核心报告
3. **今日编译概览** — 当日数据摘要
4. **运行状态** — fetch run 状态 / 调度状态
5. **高级 / 运维**（默认折叠）— 初始化来源内容 / 查看运行记录

### 3.3 今日操作区

| 按钮 | 路由 | 说明 |
|------|------|------|
| 更新今日新增 | POST /radar/today/update | 只检查到期来源 |
| 查看今日报告 | GET /radar/daily-report | 规则筛选今日重点，无需 LLM |
| 生成今日核心报告 | POST /radar/today/daily-report | LLM 生成，受 DAILY_REPORT_ENABLED=true 控制 |

**注意**：`生成今日报告卡片` 已从所有入口移除，不再出现。

### 3.4 高级 / 运维

- 默认折叠（`<details class="radar-dev-tools">`）
- `初始化来源内容` 只出现在此处，不在其他位置泄露

---

## 4. 摘要链路验收

### 4.1 按钮与参数

- 按钮文案：`生成当前页中文摘要`
- hidden field：`summary_limit value="20"`
- 副说明：`最多处理 20 条，优先补全推荐候选；已有中文摘要会自动跳过`

### 4.2 优先级逻辑（generate_today_summaries）

源码验证通过以下逻辑：

```
1. compile_candidates 优先（source_item_id 去重）
2. 当前页列表其次（去重）
3. _needs_chinese_summary 优先
4. cap 20
5. 已有 zh_one_liner + zh_summary 的内容被跳过
```

---

## 5. 推荐深入分析链路验收

| 检查项 | 状态 |
|--------|------|
| 区块标题：推荐深入分析 | ✅ |
| 默认折叠（summary_result 存在时展开） | ✅ |
| 副说明：今日推荐 N 条 · 点击条目查看详情 | ✅ |
| 每条优先展示 summary_preview | ✅ |
| 推荐依据默认折叠（查看推荐依据） | ✅ |
| 点击联动右侧阅读面板（item_id） | ✅ |

---

## 6. 洞察卡链路验收

### 6.1 用户可见文案

| 场景 | 按钮文案 | 状态 |
|------|----------|------|
| 未生成卡片 | `生成洞察卡` | ✅ |
| 已有卡片 | `查看洞察卡` | ✅ |
| 顶部快捷入口 | `洞察卡` | ✅ |
| 主列表状态 | 待生成洞察 / 生成中 / 已完成 / 失败 | ✅ |

**顺手修复（本轮）**：
- `radar_today_panel.html`：`加入生成` → `生成洞察卡`
- `radar_today_panel.html`：`InsightCard 状态：` → `洞察卡状态：`

### 6.2 路由

| 路由 | 用途 | 状态 |
|------|------|------|
| POST /source-items/{id}/enqueue-compile | 加入生成队列 | ✅ |
| GET /cards/{id} | 查看洞察卡 | ✅ |
| GET /cards | 洞察卡列表 | ✅ |

---

## 7. 今日报告链路验收

### 7.1 两类报告区分

| 报告 | 入口 | 路由 | LLM |
|------|------|------|-----|
| 规则版日报 | 查看今日报告 | GET /radar/daily-report | ❌ |
| LLM 版核心报告 | 生成今日核心报告 | POST /radar/today/daily-report | ✅（需启用） |

### 7.2 未启用提示

```
今日核心报告未启用。
这是会调用 LLM 的生成动作，需要在环境变量 DAILY_REPORT_ENABLED=true 后启用。
```

✅ 提示清楚，不与规则版混淆。

---

## 8. 右侧阅读面板验收

面板状态堆栈（panel_state）包含：

| 状态字段 | 用户可见标签 | 状态 |
|----------|-------------|------|
| summary_state | 中文概述状态 | ✅ |
| insight_label | 洞察：{label} | ✅ |
| content_state | 正文状态 | ✅ |

处理链路（panel_today_card）包含：

| 字段 | 说明 |
|------|------|
| 中文概述状态 | ✅ |
| 中文摘要状态 | ✅ |
| 正文状态 | ✅ |
| 洞察卡状态 | ✅（已修复原 InsightCard 文案） |
| 下一步建议 | ✅ |

---

## 9. 当前可用结论

**结论：通过（Pass）**

V1.0-beta First Usable Loop 已达到可日常使用的最低标准。用户主链路完整，各入口文案清晰，两类报告（规则版 / LLM 版）不混淆，洞察卡文案已统一为"洞察卡"。

---

## 10. 仍未完成的问题

### P0 未完成项（阻断体验）

无。

### P1 优化建议

1. **InsightCard 内部模板残留**：部分非今日雷达页面（card_detail.html、source_item_detail.html 等）仍使用"InsightCard"作为用户可见标题或说明文案。建议后续统一，但不影响今日雷达闭环验收。

2. **`加入生成`残留**：除 radar_today_panel.html 外的其他页面（source_item_detail.html、fetch_run_detail.html、candidate_pool.html 等）仍有"加入生成"按钮，属于全站统一产品文案，非今日雷达闭环范围。

3. **profile 脚本与生产逻辑一致性**：已确认 profile_today_radar.py 的 `quality_filter_stats` guard 与 today.py 保持一致（均仅在 section=all && page=1 时执行）。

---

## 附录：性能现状

> 以下为本地开发环境下的测试结果，不等同生产环境。

| 页面 | 耗时 |
|------|------|
| all/page=1 | ~92 ms（主要耗时：compile_candidates + quality_filter_stats） |
| all/page=2 | ~6 ms |
| 分类页（ai_coding/page=1） | ~6 ms |

主要耗时阶段：
1. `compile_candidates`（推荐候选计算）
2. `quality_filter_stats`（数据质量过滤统计，仅 all/page=1）
