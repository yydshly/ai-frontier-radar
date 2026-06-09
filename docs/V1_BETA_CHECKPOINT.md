# V1.0-beta First Usable Loop Checkpoint

## 阶段定位

当前 checkpoint 不是完整产品发布，不是 SaaS，不是全网爬虫。

它是**第一条可用信息编译闭环**的阶段稳定点：验证从"雷达关注源 → 探测 → 中文摘要 → InsightCard → 导出"链路可以跑通、人工作答可以沉淀。

## 当前完整主链路

```
雷达关注源
  → 更新今日雷达
  → FetchRun 后台探测
  → SourceItem 入库
  → 自动中文一句话概述 / 中文摘要
  → 今日雷达中文目录
  → 智能阅读面板
  → 加入生成 InsightCard
  → InsightCard 洞察预览
  → 完整 InsightCard
  → Markdown 导出
```

## 当前已完成能力

### 1. 来源与探测

- 雷达关注源来自配置中的 enabled sources
- 今日雷达可以手动触发更新
- 更新使用后台 FetchRun
- 今日雷达显示最近探测状态（运行中 / 成功 / 失败 / 部分失败）
- OpenAI RSS 场景已经支持
- 单次 SourceItem 抓取数量有限制（max 50 / source）
- 更新限定在 configured_keys 范围内，不处理测试来源

### 2. 今日雷达工作台

- 左侧分类和控制区（目录 / 更新入口 / 探测状态）
- 中间目录式 SourceItem 列表（分 section / 分页）
- 右侧智能阅读面板（摘要状态 / InsightCard 预览）
- 左右固定，中间独立滚动
- 分类支持 section（全部 / 今日重点 / 细分类）
- 分页和每页数量在中间 toolbar
- 加入生成后 return_to 回当前上下文
- 更新今日雷达保留当前 section / item_id / page / per_page

### 3. 中文摘要

- 支持 zh_one_liner
- 支持 zh_summary
- 今日雷达支持补齐当前页中文摘要
- 支持 fill_missing_summary 修复旧数据
- 轻量摘要优先读取 detail_description
- FetchRun 完成后对本轮 new / updated SourceItem 自动生成中文摘要（最多 AUTO_SUMMARY_MAX_PER_FETCH_RUN=5 条）
- 自动摘要是 best-effort，不影响 FetchRun 抓取状态
- **中间卡片中文概述优先**（zh_one_liner 作为 primary_text）

### 4. InsightCard 生成

- SourceItem 生成 InsightCard 支持 RSS / metadata snapshot 优先
- OpenAI 原文 403 不再阻断轻量 InsightCard（fallback 到 snapshot）
- 右侧面板可以展示 InsightCard 状态和预览
- InsightCard 预览与内容摘要职责分离：内容摘要回答"这篇文章说了什么"，InsightCard 预览回答"为什么值得关注、和我有什么关系、下一步做什么"
- InsightCard 预览优先展示 structured insight 字段（相关性分数、相关方向、为什么值得关注、技术洞察、产品机会、行动建议、风险提醒），只在无洞察字段时才 fallback 到 summary_zh

### 5. 完整 InsightCard 页面

- 完整 InsightCard 页面已统一为：内容摘要 → 洞察判断 → 技术/产品/风险/行动 → 补充阅读 → 个人判断 / 导出
- 页面顶部显示"完整 InsightCard"定位，说明本页面回答的四个核心问题
- 状态总览区展示相关性分数、匹配方向、生成依据、当前判断、创建时间
- 内容摘要明确回答"这篇资料说了什么"，与洞察判断分离
- **生成依据不再显示 unknown**，RSS/metadata 卡片显示"基于来源摘要 / RSS metadata"
- 洞察判断总览区展示相关性分数、匹配方向和判断理由
- 结构化洞察区块：关键事实、技术洞察、产品机会、风险提醒、行动建议
- 双语理解降级为补充阅读，位于洞察区块之后
- 底部保留个人判断和导出能力

### 6. Markdown 导出

- Markdown 下载文件名格式：`YYYY-MM-DD_AI前沿雷达_{id}_{标题}_{行动任务/完整报告}.md`
- 文件名包含日期、项目名、card id、来源标题、导出类型，便于长期整理
- Content-Disposition 支持 UTF-8 filename* 编码，同时提供 ASCII fallback 兼容旧浏览器
- **任务草稿预览页**显示"Markdown 行动任务草稿"定位和即将下载的文件名
- **完整报告预览页**显示"完整 InsightCard Markdown 报告"定位和即将下载的文件名
- Markdown 预览使用自动换行（white-space: pre-wrap），提升可读性

### 7. 状态可观察性

- 探测状态可见（运行中 / 成功 / 失败 / 部分失败）
- InsightCard 生成状态可见
- 中文摘要生成状态可见
- 右侧面板实时反映选中条目的状态

### 8. 文档与验收

- 状态文档：docs/V1_BETA_FIRST_USABLE_LOOP_STATUS.md
- 验收清单：docs/V1_BETA_FIRST_USABLE_LOOP_CHECKLIST.md
- Checkpoint 文档：本文档
- 人工验收记录模板：docs/V1_BETA_MANUAL_ACCEPTANCE_RECORD.md

## 当前非目标

当前不做：

- 多用户 / 登录注册 / 付费
- 全网爬虫 / Twitter-X 抓取
- 复杂推荐算法 / 知识图谱 / Multi-Agent
- 企业权限 / 移动 App / 浏览器插件
- 自动日报 / 定时任务调度（due-source）
- 来源 Web 新增 / 编辑 UI
- Multi-Agent 协作
- DailyRadarReport
- 语音播报
- 长期归档策略

## 已知限制

- 今日雷达更新仍是手动触发，不是定时
- 雷达关注源仍由 config enabled sources 决定，无独立 UI
- 尚未实现 due-source 调度
- 自动摘要每个 FetchRun 默认最多处理 5 条，由 AUTO_SUMMARY_MAX_PER_FETCH_RUN 控制，最大 20，设为 0 可关闭
- 自动摘要是 best-effort，失败不影响 FetchRun 抓取状态
- Source 表可能包含历史测试来源（test_* / orphan_key 被排除在生产视图外）
- 旧 InsightCard 可能缺少结构化洞察字段
- 旧 SourceItem 可能缺少 zh_summary，需要手动补齐
- 当前没有真正的批次 batch_id（追踪一批探测）
- 最近探测状态统计的是最近 FetchRun（limit=30），不是严格本次点击批次

## 推荐下一阶段

V1.0-beta.1 建议优先处理：

1. due-source 调度（定时探测雷达关注源）
2. 单来源工作台 `/sources/{source_key}`
3. 来源池 / 雷达关注源概念分离
4. 摘要队列 / 后台补齐
5. DailyRadarReport 设计

## Checkpoint 判定

如果以下链路人工验收通过，即可视为 **V1.0-beta First Usable Loop checkpoint** 成立：

```
/radar/today
  → 更新今日雷达
  → 自动中文摘要
  → 查看中文目录
  → 加入生成 InsightCard
  → 查看右侧洞察预览
  → 打开完整 InsightCard
  → 导出 Markdown 行动任务 / 完整报告
```

参考：docs/V1_BETA_MANUAL_ACCEPTANCE_RECORD.md
