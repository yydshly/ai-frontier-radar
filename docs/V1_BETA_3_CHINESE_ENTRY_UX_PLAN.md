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

## 7. 相关文档

- [V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md](V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md) — V1.0-beta.3 整体规划
