# V1.0-beta First Usable Loop 状态说明

## 1. 阶段定位

当前不是完整 SaaS，不是全网爬虫，不是多用户系统。

当前目标是验证：

```
英文 AI 前沿来源
→ 探测
→ SourceItem
→ 中文摘要
→ 今日雷达阅读
→ InsightCard
→ 初步沉淀
```

## 2. 当前主链路

```
雷达关注源
  → 更新今日雷达
  → FetchRun
  → SourceItem
  → 今日雷达目录
  → 补齐中文摘要
  → 智能阅读面板
  → 加入生成
  → InsightCard
```

## 3. 已完成能力

### 3.1 来源与探测

- 雷达关注源来自配置中的 enabled sources
- 今日雷达可以手动触发更新
- 更新使用后台 FetchRun
- 今日雷达显示最近探测状态（运行中 / 成功 / 失败 / 部分失败）
- OpenAI RSS 场景已经支持
- 单次 SourceItem 抓取数量有限制（max 50 / source）

### 3.2 今日雷达工作台

- 左侧分类和控制区（目录 / 更新入口 / 探测状态）
- 中间目录式 SourceItem 列表（分 section / 分页）
- 右侧智能阅读面板（摘要状态 / InsightCard 预览）
- 左右固定，中间独立滚动
- 分类支持 section（全部 / 今日重点 / 细分类）
- 分页和每页数量在中间 toolbar
- 加入生成后 return_to 回当前上下文
- 更新今日雷达保留当前 section / item_id / page / per_page

### 3.3 中文摘要

- 支持 zh_one_liner
- 支持 zh_summary
- 今日雷达支持补齐当前页中文摘要
- 支持 fill_missing_summary 修复旧数据
- 轻量摘要优先读取 detail_description
- FetchRun 完成后对本轮 new / updated SourceItem 自动生成中文摘要（最多 AUTO_SUMMARY_MAX_PER_FETCH_RUN=5 条，超出可继续用"补齐当前页中文摘要"处理）
- 自动摘要是 best-effort，不影响 FetchRun 抓取状态

### 3.4 InsightCard

- SourceItem 生成 InsightCard 支持 RSS / metadata snapshot 优先
- OpenAI 原文 403 不再阻断轻量 InsightCard（fallback 到 snapshot）
- 右侧面板可以展示 InsightCard 状态和预览
- InsightCard 标注 "非全文解析" 提示
- 右侧 InsightCard 预览与内容摘要职责分离：内容摘要回答"这篇文章说了什么"，InsightCard 预览回答"为什么值得关注、和我有什么关系、下一步做什么"
- InsightCard 预览优先展示 structured insight 字段（相关性分数、相关方向、为什么值得关注、技术洞察、产品机会、行动建议、风险提醒），只在无洞察字段时才 fallback 到 summary_zh

### 3.5 完整 InsightCard 页面

- 完整 InsightCard 页面已统一为：内容摘要 → 洞察判断 → 技术/产品/风险/行动 → 补充阅读 → 个人判断 / 导出
- 页面顶部显示"完整 InsightCard"定位，说明本页面回答的四个核心问题
- 状态总览区展示相关性分数、匹配方向、生成依据、当前判断、创建时间
- 内容摘要明确回答"这篇资料说了什么"，与洞察判断分离
- 洞察判断总览区展示相关性分数、匹配方向和判断理由
- 结构化洞察区块：关键事实、技术洞察、产品机会、风险提醒、行动建议
- 双语理解降级为补充阅读，位于洞察区块之后
- 底部保留个人判断和导出能力

### 3.6 Markdown 导出预览和文件名

- Markdown 下载文件名格式：`YYYY-MM-DD_AI前沿雷达_{id}_{标题}_{行动任务/完整报告}.md`
- 文件名包含日期、项目名、card id、来源标题、导出类型，便于长期整理
- Content-Disposition 支持 UTF-8 filename* 编码，同时提供 ASCII fallback 兼容旧浏览器
- 任务草稿预览页显示"Markdown 行动任务草稿"定位和即将下载的文件名
- 完整报告预览页显示"完整 InsightCard Markdown 报告"定位和即将下载的文件名
- Markdown 预览使用自动换行（white-space: pre-wrap），提升可读性

## 4. 当前非目标

当前不做：

- 多用户 / 登录注册 / 付费
- 全网爬虫 / Twitter-X 抓取
- 复杂推荐算法 / 知识图谱 / Multi-Agent
- 企业权限 / 移动 App / 浏览器插件
- 自动日报 / 定时任务调度（due-source）
- 来源 Web 新增 / 编辑 UI
- Multi-Agent 协作

## 5. 当前已知限制

- 今日雷达更新仍是手动触发，不是定时
- 探测完成后会对本轮 new / updated SourceItem 进行有限数量的自动中文摘要生成；超过限制的条目仍可通过"补齐当前页中文摘要"处理
- AUTO_SUMMARY_MAX_PER_FETCH_RUN 控制每次抓取后的自动摘要数量，默认 5，最大 20，设为 0 可关闭
- 自动摘要是 best-effort，不影响 FetchRun 抓取状态
- 中文摘要补齐是同步 POST，LLM 慢时页面会等待
- 最近探测状态统计的是最近 N 条 FetchRun（limit=30），不是严格 batch_id
- Source 表可能包含历史测试来源（test_* / orphan_key 被排除在生产视图外）
- 当前雷达关注源由 config enabled sources 决定，无独立 UI
- 还没有 due-source 调度
- 还没有来源 Web 新增 / 编辑
- InsightCard 不是自动全量生成
- PDF / 报告页还不是主链路重点

## 6. 下一阶段建议

### P0.5（体验优化）

- 状态文案统一
- 选中卡片滚动逻辑适配 `.radar-main-scroll`
- 今日雷达结果提示文案继续压缩

### P1（核心闭环增强）

- due-source 调度（定时探测雷达关注源）
- 探测完成后自动补中文摘要
- 单来源工作台 `/sources/{source_key}`
- 来源池 / 雷达关注源概念分离
- 更新批次 batch_id（追踪一批探测）

### P2（长期能力）

- DailyRadarReport（每日精选报告）
- 3 分钟中文播报稿
- TTS 语音播报
- 长期归档与数据治理
