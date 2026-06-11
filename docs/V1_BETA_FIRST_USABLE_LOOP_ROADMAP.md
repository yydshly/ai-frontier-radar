# V1.0-beta First Usable Loop 路线文档

> 本文档固化当前阶段目标、架构状态和后续开发优先级。
> 不是终局架构设计文档，是开发路线指导文档。
> 最后更新：2026-06-11（Phase 4.4）

---

## 1. 产品总目标

```
全球 AI 前沿资料
  → 稳定获取（来源配置 + 探测链路）
  → 清洗与去重（数据质量 guard）
  → 中文结构化理解（中文摘要 / InsightCard）
  → 判断和用户方向的关系（相关性评分 / 洞察）
  → 生成 InsightCard / 报告 / 行动建议 / 播报
  → 长期沉淀为个人 AI 前沿雷达
```

**当前阶段不是全量资讯平台，不是 RSS 阅读器，不是多用户 SaaS。**

---

## 2. 当前阶段目标（V1.0-beta First Usable Loop）

验证第一条可用链路：

```
Source（YAML 配置 + DB 持久化）
  → FetchRun（探测执行）
  → SourceItem（收件箱）
  → 今日雷达（阅读工作台）
  → 推荐生成候选（规则打分 Top N）
  → 小批量 compile（InsightCard）
  → 日报入口（DailyReportCard）
  → 播报入口（DailyBroadcastScript）
```

**口径：**
- 当前只做第一条可用链路
- 不做复杂 SaaS、推荐算法、向量库、多用户、移动端
- 不做完整 TTS 商业化

---

## 3. 当前已完成能力

### 3.1 来源与探测

| 能力 | 状态 |
|------|------|
| 15 个精选来源配置（YAML） | ✅ |
| RSS 探测链路 | ✅ 已验证 |
| HTML index 探测链路 | ✅ 已验证 |
| 来源调度（due-source 定时 / 手动） | ✅ |
| FetchRun 运行状态跟踪 | ✅ |

已验证来源：
- `openai_news`
- `huggingface_blog`
- `arxiv_cs_ai`

### 3.2 数据清理

| 项目 | 状态 |
|------|------|
| B=0（orphan source_id） | ✅ 已完成 |
| C/D/E/F=0（disabled / no_url / no_title / status 问题） | ✅ 已完成 |
| A 残留不可自动修复项 | ⚠️ 已知异常，需人工 review |
| G（informational） | ✅ 已明确为 informational |
| orphan InsightCard | 暂不阻塞今日雷达 |

**收口原则：**
- A 残留：known exceptions / manual review，不阻塞主链路
- 不再围绕 A/B/G 反复循环清理
- 数据清理是手段，不是产品目标

### 3.3 今日雷达

| 能力 | 状态 |
|------|------|
| 最近 N 小时 SourceItem 列表 | ✅ |
| 左侧分类 sidebar（section） | ✅ |
| 右侧智能阅读面板 | ✅ |
| 数据质量 filter stats | ✅ |
| 来源探测状态（FetchRun summary） | ✅ |
| 调度状态（scheduler status） | ✅ |
| 今日编译概览（daily digest） | ✅ |
| 分页（page / per_page） | ✅ |
| 推荐生成候选区（compile candidates） | ✅ Phase 4.4 |

**当前限制：**
1. 今日重点仍偏"最新"，不是最终重要性排序
2. 推荐候选是规则打分，不是 LLM 评分
3. 候选区仅在 `section=all && page=1` 时计算（性能保护）
4. 候选区不自动 compile，需用户主动触发

### 3.4 InsightCard 编译

| 能力 | 状态 |
|------|------|
| 小批量 compile 已验证（38/39/40） | ✅ |
| InsightCard 页面 `/cards/{id}` | ✅ |
| InsightCard 生成服务 | ✅ |
| compile_selected_insight_cards.py 脚本 | ✅ |

### 3.5 日报与播报

| 能力 | 状态 |
|------|------|
| 日报入口 `/radar/daily-report` | ✅ |
| DailyReportCard 生成服务 | ✅ |
| 播报入口 `/radar/daily-report/broadcast` | ✅ |
| DailyBroadcastScript 生成 | ✅ |
| TTS 播报 | ⚠️ 当前为 stub，未接入真实 TTS |

> **日报依赖 InsightCard**：需先有中文摘要或 InsightCard 才能生成有效日报内容。

---

## 4. 当前架构层

```
┌─────────────────────────────────────────────┐
│  Source Layer（来源配置层）                   │
│  app.sources.config_loader / YAML            │
│  状态：15 个精选来源，RSS/HTML index 探测    │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Fetch / Probe Layer（探测执行层）            │
│  app.application.sources.fetch_service       │
│  app.application.sources.discovery_runs      │
│  状态：FetchRun → SourceItem，due-source 调度│
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  SourceItem Working Set（工作数据集）         │
│  app.models.SourceItem                       │
│  状态：cleaned（无 orphan/broken/invalid）   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Radar Today View（今日雷达）                │
│  app.application.radar.today                  │
│  状态：catalog + 右侧面板 + 候选推荐          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Compile Candidate Selection（候选筛选）      │
│  app.application.candidates.compile_candidates│
│  状态：规则打分 Top N，每来源最多 3 条        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  InsightCard Compile（洞察卡编译）           │
│  app.application.insight.source_item_insight  │
│  app.application.source_items.compile_service  │
│  状态：小批量验证通过，38/39/40 已生成        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Daily Report（日报）                        │
│  app.application.radar.daily_report_card      │
│  状态：入口存在，DAILY_REPORT_ENABLED=false  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Daily Broadcast（播报）                     │
│  app.application.radar.daily_broadcast        │
│  状态：脚本生成存在，TTS 为 stub             │
└─────────────────────────────────────────────┘
```

---

## 5. 后续开发优先级

### Phase A：今日雷达候选区体验小收口

**目标：** 候选推荐从"能用"到"好用"

可选项（不阻塞主链路）：
- 补充摘要预览（候选区显示 zh_one_liner 预览）
- 折叠行为默认关闭（已实现 `<details>`）
- 候选点击后 panel 联动（已实现）

### Phase B：小批量 compile 操作收口

**目标：** 稳定支持手动 / cron 触发 compile

- 继续使用 `scripts/compile_selected_insight_cards.py`
- 保持 `limit` 控制，默认 10 条
- 支持 cron 定时触发（通过 `--apply` flag）
- **不做**：复杂后台队列、优先级调度、大规模批量 compile

### Phase C：日报 dry-run 验证

**目标：** 确认 DailyReportCard 能正常消费现有 InsightCard

- 不强制启用真实 LLM（`DAILY_REPORT_ENABLED=false` 保持）
- 先用 mock 验证日报生成链路
- 输出将进入日报的卡片列表，确认内容质量
- **不做**：强制启用 LLM 调用、自动发送

### Phase D：每日新增语义增强

**目标：** 区分"首次发现"vs"真实发布时间"vs"每日新增"

- 避免初始化历史数据刷屏
- 先用现有字段判断（`first_seen_at` / `published_at`）
- **不急着改 schema**：不新增字段，不引入向量库
- 后续有需要再扩展

### Phase E：真实 TTS / 播报

**目标：** 等日报链路稳定后再接入

- 当前 TTS 为 stub，不阻塞任何主链路
- 等 `DAILY_REPORT_ENABLED` 稳定 + `DailyReportCard` 内容质量确认后
- 再接入真实 TTS provider
- **不做**：在 Phase A-D 未稳定前接入 TTS

---

## 6. 明确不做什么

```
当前不做：
1. 不重构数据库 schema
2. 不引入向量库
3. 不做复杂推荐算法
4. 不批量 compile 超过 50 条（性能保护）
5. 不接真实 TTS（等日报稳定后再说）
6. 不做多用户 SaaS
7. 不做移动端
8. 不继续围绕 A/B/G 清理循环
9. 不重构 RadarTodayService
10. 不做大屏 / 图表可视化
```

---

## 7. 后续任务下发规则

每个开发任务必须明确：

| 字段 | 说明 |
|------|------|
| **服务哪一段主链路** | Feature 必须能定位到 Source/Fetch/Radar/Compile/Report/Broadcast 之一 |
| **修改哪些模块** | 精确到文件名（app/ 或 scripts/） |
| **不做什么** | 明确边界，防止范围蔓延 |
| **验收标准** | 至少能说清楚"怎么看是否工作" |
| **是否影响数据** | 是否写 DB / 是否产生 runtime 文件 |
| **是否调用 LLM** | 明确是 rule-based 还是 LLM 调用 |
| **性能注意事项** | 是否有大循环 / 全表扫描风险 |

---

## 8. 文档关系

```
V1_BETA_FIRST_USABLE_LOOP_ROADMAP.md  ← 本文档（路线指导）
       ↓
V1_BETA_FIRST_USABLE_LOOP_STATUS.md   ← 当前已完成能力状态
       ↓
V1_BETA_FIRST_USABLE_LOOP_CHECKLIST.md ← 验收检查清单
       ↓
docs/PRODUCT_SHAPE_ROADMAP.md          ← 长期产品形态
```

---

## 9. 修改历史

| 日期 | Commit | 说明 |
|------|--------|------|
| 2026-06-11 | ebfef28 | fix: lighten today compile candidates panel |
| 2026-06-11 | ece3881 | feat: show compile candidates on today radar |
| 2026-06-11 | 1d8579e | feat: add today compile candidate selection |
