# V1.0-beta.3 Release Notes: 今日雷达体验闭环

## 版本信息

- **版本名**：V1.0-beta.3
- **当前分支**：`feature/v1-beta-3-radar-status-ui`
- **base commit**：`2f1d970`（Task 8.2 完成后）
- **发布日期**：2026-06-10
- **本阶段定位**：今日雷达（`/radar/today`）阅读体验闭环

---

## 本阶段定位

V1.0-beta.3 聚焦 `/radar/today` 的可用性体验，将"能跑通"提升为"用起来舒服"。

核心改进方向：

1. 中文摘要优先展示，弱标题友好降级
2. 卡片紧凑布局，减少视觉噪音
3. 卡片主体可点击，右侧面板局部刷新，减少页面跳转打断感
4. 目录栏可收起，释放主列表空间
5. 调度状态和探测状态可见，减少黑盒焦虑

---

## 已完成能力清单

### 核心页面

| 能力 | 路径 | 说明 |
|------|------|------|
| 今日雷达三栏工作台 | `/radar/today` | 左侧目录 + 中间列表 + 右侧智能阅读面板 |
| 左侧目录分类 | `/radar/today` | 全部 / 今日重点 / 各分类 |
| 最近探测状态展示 | `/radar/today` | 运行中/成功/失败统计、新增/更新条数 |
| 调度状态展示 | `/radar/today` | 待检查来源/冷却中/疑似卡住/来源缺失 |
| 探测结果更新时间线 | `/radar/today` | 最近启动时间 |

### 列表与卡片

| 能力 | 说明 |
|------|------|
| 中文摘要优先展示 | 优先使用 `zh_one_liner`，显示「中文概述」badge |
| 无中文摘要时英文标题展示 | fallback 到 `primary_text` 或 `item.title`，不暴露弱标题 |
| 卡片紧凑布局 | `.radar-card` 优化为紧凑单行 meta + actions |
| 卡片底部 meta/actions 同行 | 状态 badge、来源、时间、编号 与 操作按钮在同一行 |
| 卡片主体可点击 | 整个卡片主体区域为链接，点击不触发actions区域 |

### 右侧智能阅读面板

| 能力 | 说明 |
|------|------|
| 智能阅读面板 | `/radar/today` 右侧面板，id=`radar-panel` |
| 局部刷新 | 点击卡片只刷新右侧面板，不整页跳转 |
| Partial endpoint | `GET /radar/today/panel` 返回 HTML fragment |
| 面板状态显示 | 显示摘要状态（待生成/生成中/已完成）和 InsightCard 状态 |
| 面板宏观洞察预览 | 展示「为什么值得关注」「技术洞察」「行动建议」等 InsightCard 内容 |
| 面板操作按钮 | 加入生成 / 查看 InsightCard / 打开原文 / 详情 |

### 目录栏

| 能力 | 说明 |
|------|------|
| 目录栏可收起/展开 | 点击「收起目录」按钮，目录缩成 ~52px 窄条 |
| 主列表空间扩展 | 收起后主列表向左扩展，目录栏宽度让出 |
| 状态持久化 | 收起状态保存到 `localStorage`，刷新后保持 |
| 按钮文案切换 | 收起时显示「展开」，展开时显示「收起目录」 |

### 摘要与生成

| 能力 | 说明 |
|------|------|
| 当前页前 5 条摘要生成 | POST `/radar/today/generate-summaries`，优先处理无摘要条目 |
| 按页面顺序处理 | 不按 `last_seen_at` 倒序，而是当前视觉顺序 |
| 错误信息用户化 | 显示「中文摘要生成失败，可稍后重试」而非技术错误 |

### 工程验收

| 能力 | 说明 |
|------|------|
| acceptance 脚本支持直接执行 | `python scripts/acceptance_first_usable_loop.py` |
| acceptance 脚本支持 module 执行 | `python -m scripts.acceptance_first_usable_loop` |
| TestClient 实际渲染验收 | 验证 `/radar/today/panel` 真实 item_id 的 fragment |

---

## 未完成能力清单

以下能力属于后续版本，V1.0-beta.3 **刻意不做**：

| 能力 | 原因 |
|------|------|
| 全站无刷新导航 | 当前保持 SSR + 页面级跳转，局部刷新仅限今日雷达内部卡片点击 |
| 多用户 / 登录注册 | MVP 聚焦单用户本地工作台 |
| 付费 / 公开 SaaS | 当前不做商业化 |
| 浏览器插件 / 移动 App | 当前不做客户端扩展 |
| 全网爬虫 | 当前只做配置的雷达关注源探测 |
| Twitter/X 抓取 | 暂不支持 |
| 复杂推荐算法 | 当前基于分类的固定排序 |
| 完整知识图谱 | 需要先有实体和关系数据积累 |
| 复杂 Multi-Agent | 当前单 Agent 链路已够用 |

---

## 不属于本阶段的能力

以下能力虽然可能与「体验」相关，但经决策暂时搁置：

| 能力 | 搁置原因 |
|------|----------|
| 右侧面板内直接编辑备注 | MVP 阶段不需要 |
| 卡片批量选择 | MVP 阶段单条处理足够 |
| 多语言界面 | 当前中文优先 |
| 暗色模式 | 当前保持浅色主题 |
| 推送/通知 | 当前轮询够用 |

---

## 验收命令

### 自动验收

```bash
# 编译检查
python -m compileall app scripts

# 快速自检
python scripts/quick_test.py

# 今日雷达完整验收（直接执行）
python scripts/acceptance_first_usable_loop.py

# 今日雷达完整验收（module 执行）
python -m scripts.acceptance_first_usable_loop

# 来源健康检查
python scripts/check_due_sources.py

# stale running 检查
python scripts/check_stale_fetch_runs.py
```

### 禁止在验收时运行的命令

```bash
# 以下命令会触发真实抓取或 LLM 调用，不要在验收时运行：
POST /radar/today/update
POST /radar/today/generate-summaries
GET  /sources/{source_key}/fetch
python scripts/run_due_sources_once.py --apply
```

---

## 人工浏览器验收场景

### 场景 1：目录收起/展开

1. 打开 `/radar/today`
2. 观察左侧目录栏宽度（约 220px）
3. 点击「收起目录」按钮
4. 确认目录栏缩成约 52px 窄条，显示「展开」按钮
5. 确认中间主列表向左扩展，宽度增加
6. 点击「展开」按钮
7. 确认目录栏恢复约 220px
8. 刷新页面，确认收起状态保持

### 场景 2：卡片点击局部刷新

1. 滚动中间主列表到中部，找到任意卡片
2. 记录当前滚动位置
3. 点击卡片主体（不是底部操作按钮）
4. 确认：页面**不整体刷新**
5. 确认：主列表**滚动位置不跳顶部**
6. 确认：右侧面板内容切换为所点卡片的内容（标题、来源、摘要、洞察）
7. 确认：所点卡片高亮（边框或背景变化）
8. 确认：浏览器地址栏 URL 包含 `item_id=` 参数
9. 再次滚动到另一个位置，点击另一张卡片
10. 确认右侧面板再次刷新，滚动位置保持

### 场景 3：面板操作按钮

1. 在右侧面板中点击「加入生成」按钮
2. 确认提交表单后跳转回 `/radar/today`，面板保持该条目
3. 点击「打开原文」，确认在新窗口打开
4. 如果有条目已完成 InsightCard，点击「查看 InsightCard」，确认进入详情页

### 场景 4：分页与摘要生成

1. 在 toolbar 设置每页数量（如 5）
2. 点击「生成本页前 5 条摘要」
3. 确认出现处理结果统计（成功 N，跳过 N，失败 N）
4. 分页切换后，确认目录选中状态保持

---

## 风险与已知限制

详见 [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)，V1.0-beta.3 相关限制：

1. **最左侧深色全局导航仍是页面级跳转**，不做全站无刷新
2. **今日雷达内部表单提交仍是传统请求**，卡片点击的局部刷新仅针对面板内容
3. **右侧面板是渐进增强**，JS 失败时降级为完整页面跳转
4. **中文摘要与 InsightCard 摘要可能来自不同字段**，后续需要统一语义
5. **source metadata / RSS summary 可能是英文**，不应等同于中文摘要
6. **当前页摘要补齐一次最多处理 5 条**

---

## 相关文档

- [docs/V1_BETA_3_CHINESE_ENTRY_UX_PLAN.md](docs/V1_BETA_3_CHINESE_ENTRY_UX_PLAN.md) — 任务规划
- [docs/V1_BETA_3_ACCEPTANCE_CHECKLIST.md](docs/V1_BETA_3_ACCEPTANCE_CHECKLIST.md) — 验收清单
- [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) — 已知限制
- [docs/V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md](docs/V1_BETA_3_UI_SCHEDULER_STATUS_PLAN.md) — V1.0-beta.3 整体规划
- [docs/V1_BETA_3_FINAL_CHECKPOINT.md](docs/V1_BETA_3_FINAL_CHECKPOINT.md) — 最终 checkpoint、merge-ready 判断
- [docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md](docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md) — 人工验收记录
