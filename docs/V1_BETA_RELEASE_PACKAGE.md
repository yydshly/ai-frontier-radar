# V1.0-beta First Usable Loop 阶段包

## Tag

`v1.0-beta-first-usable-loop`

## 主链路

```
雷达关注源
→ 更新今日雷达
→ FetchRun 后台探测
→ SourceItem 入库
→ 自动中文摘要
→ 今日雷达中文目录
→ 智能阅读面板
→ 加入生成 InsightCard
→ InsightCard 洞察预览
→ 完整 InsightCard
→ Markdown 导出
```

## 浏览器入口

- `/` — 首页
- `/radar/today` — 今日雷达
- `/sources` — 来源管理
- `/fetch-runs` — 探测记录
- `/source-items` — 来源条目
- `/cards` — InsightCard 列表
- `/project-docs` — 项目文档中心

## 浏览器文档入口

访问 `/project-docs` 应能看到以下 V1.0-beta First Usable Loop 阶段文档：

- **V1.0-beta First Usable Loop Checkpoint** (`v1-beta-checkpoint`)
  阶段稳定点说明，覆盖完整主链路、已完成能力、非目标、已知限制和下一阶段建议。

- **V1.0-beta 人工验收记录** (`v1-beta-manual-acceptance`)
  用于记录 First Usable Loop 的真实人工验收环境、步骤、结果和问题。

- **V1.0-beta First Usable Loop 状态说明** (`v1-beta-status`)
  当前阶段定位、主链路、已完成能力、非目标、已知限制和后续规划。

- **V1.0-beta First Usable Loop 验收清单** (`v1-beta-checklist`)
  页面、抓取、中文摘要、InsightCard、导出和 checkpoint 的验收清单。

## 必要验证命令

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/acceptance_first_usable_loop.py
python scripts/check_sources_health.py
```

## 当前限制

参考：

- `docs/V1_BETA_CHECKPOINT.md`
- `docs/V1_BETA_FIRST_USABLE_LOOP_STATUS.md`
- `docs/V1_BETA_FIRST_USABLE_LOOP_CHECKLIST.md`

## V1.0-beta.1 Source Scheduling

**Tag**: `v1.0-beta-1-source-scheduling`

V1.0-beta.1 已完成：

- due-source 计算服务（`compute_due_sources()`）
- /radar/today/update 接入 due-source
- 单来源工作台 `/sources/{source_key}`（只读）
- stale running FetchRun 诊断（只读）
- stale running 人工恢复脚本（默认 dry-run）
- 单来源手动探测入口（POST-only）
- 真实 openai_news 手动探测验收（run_id=1067, items_found=50）

**真实验收数据**：

```
stale running 恢复：running 8 → 0, stale_count 8 → 0
真实探测：openai_news run_id=1067, status=success
items_found=50, items_new=3, items_updated=47, items_failed=0
SourceItem count: 50 → 53
GET 405, POST 303 → /fetch-runs/1067
```

**文档入口**：

- [V1.0-beta.1 Source Scheduling Acceptance](V1_BETA_1_SOURCE_SCHEDULING_ACCEPTANCE.md)
- [V1.0-beta.1 Source Scheduling Architecture](V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md)
- [V1.0-beta.1 Execution Plan](V1_BETA_1_EXECUTION_PLAN.md)

---

## 下一阶段

V1.0-beta.1 将围绕来源调度和单来源工作台展开：

- due-source 调度（判断哪些来源本轮该探测，并展示跳过原因）
- 单来源工作台 `/sources/{source_key}`（来源状态、FetchRun、SourceItem、摘要、InsightCard 入口）
- 来源池 / 雷达关注源概念分离（SourcePool vs RadarSource）
- 摘要队列演进设计记录（当前 best-effort 与未来 SummaryJob 的关系）

参考：

- `docs/V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md`
- `docs/V1_BETA_1_EXECUTION_PLAN.md`
- `docs/V1_BETA_1_DECISION_RECORD.md`
