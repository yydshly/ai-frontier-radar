# V1.0-beta.3 Chinese Entry UX Plan

## 1. 本任务定位

本任务是 V1.0-beta.3 的 UI 微调，**不是摘要能力重做**。

### 已有的能力（不变）
- 一句话中文摘要（zh_one_liner）生成能力：`CandidateOneLinerService`
- 中文详细摘要（zh_summary）生成能力：`BackgroundCompileService`
- InsightCard 编译能力：`SourceItemCompileService`
- 右侧智能阅读面板的摘要展示逻辑

### 本任务只调整
- 中间列表卡片的**信息优先级**（中文摘要优先，英文标题降级）
- 右侧面板的**文案细节**（更清晰的中文入口标签）
- 无摘要时的**友好占位**

---

## 2. 产品信息层级

### 中间列表卡片优先级

```
第一优先级：一句话中文摘要（zh_one_liner）
第二优先级：英文原始标题
第三优先级：来源 / 时间 / 状态
第四优先级：操作按钮
```

### 右侧智能阅读面板优先级

```
第一优先级：中文摘要
第二优先级：InsightCard 状态 / 预览
第三优先级：原文链接
第四优先级：来源、时间、状态
```

---

## 3. 中间卡片变化

### 卡片中文入口优先

无 zh_one_liner 时，卡片展示顺序调整为：
- 第一行：待生成中文摘要
- 第二行：英文原始标题（降级为辅助信息）

有 zh_one_liner 时：
- 第一行：中文一句话摘要 + 中文概述 badge
- 第二行：英文原始标题（如果与摘要不同）

### 本轮更新计划中文化

`not_due_yet:15` 等内部原因不再直接显示在 UI。
通过 `_humanize_reason_summary()` 映射为中文：
- `not_due_yet` → "来源仍在冷却中，暂不需要重复检查"
- `max_sources_limit` → "达到本轮检查上限"
- `already_running` → "正在运行中"
- `missing_source_row` → "来源记录缺失"
- `unsupported_fetch_strategy` → "暂不支持的抓取方式"

### 现状
- `display.primary_text` = zh_one_liner（如果有）→ 已是第一优先级
- `display.secondary_text` = 英文标题（如果有 zh_one_liner）→ 已降级

### 变化
- 如果无 zh_one_liner，`secondary_text` 目前为空，卡片只显示英文标题
- 改为：如果无 zh_one_liner，`secondary_text` 显示"待生成中文摘要"
- 英文标题仍在，但更小、更淡

### 视觉结构

**有中文摘要时**：
```
中文一句话摘要
英文原始标题
来源 · 时间 · 状态
[查看] [加入生成/查看洞察] [打开原文]
```

**无中文摘要时**：
```
待生成中文摘要
英文原始标题
来源 · 时间 · 状态
[查看] [加入生成/查看洞察] [打开原文]
```

---

## 4. 右侧面板文案微调

### 变化
- "内容摘要" → "中文摘要"（更直接的中文入口表达）
- "InsightCard 预览" → "宏观洞察"（更符合产品定位）

### 保留不变
- 右侧面板布局
- InsightCard 预览内容结构
- 摘要展示逻辑
- 所有操作按钮

---

## 5. 不做的事

- 不新增全文深度分析能力
- 不新增每日汇总 / 播报能力
- 不改三栏布局
- 不改左侧深色导航
- 不改候选卡片主视觉风格
- 不改右侧智能阅读面板主布局
- 不改摘要生成服务
- 不改 InsightCard 编译服务
- 不暴露技术概念（SourceItem / FetchRun / one_liner / zh_summary / LLM 等）

---

## 6. 后续方向

后续可另起任务探索：
- 每日汇总 / 播报能力
- 跨来源宏观分析
- 多语言界面支持

---

## 8. Task 5：主列表紧凑布局优化

- 目标：提高今日雷达中间列表的信息密度，让用户一屏看到更多内容
- 不改变三栏布局
- 不改变业务逻辑
- 不改变摘要 / InsightCard / 抓取服务
- 保留中文摘要优先的产品语义

具体改动：
- `.radar-card` padding: `0.85rem 1rem` → `0.6rem 0.8rem`
- `.radar-card` gap: `0.5rem` → `0.4rem`
- `.radar-card-list` gap: `0.75rem` → `0.5rem`
- `.radar-section` margin-bottom: `1.5rem` → `1rem`
- `.radar-section-title` margin-bottom: `0.6rem` → `0.4rem`
- `.radar-card-title` margin-bottom: `0.5rem` → `0.2rem`，line-height: `1.5` → `1.35`
- `.radar-card-original-title` margin-bottom: `0.4rem` → `0.25rem`，line-height: `1.4` → `1.35`
- `.radar-card-meta` margin-bottom: `0.5rem` → `0.3rem`

---

## 9. 相关文档

- [V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md](V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md) — V1.0-beta.3 整体规划
