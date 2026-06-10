# V1.0-beta.3 Task 1：今日雷达接入调度状态（非 UI 重构）

## 1. 本任务不是 UI 重构

本任务**不重做** `/radar/today` 的页面布局，只在现有定制 UI 中做最小增强。
现有三栏结构、左侧深色导航、候选内容卡片、右侧智能阅读面板的样式都是多次调整
得到的，本任务**保持原样**。

## 2. 保留现有三栏布局和定制样式

明确不改：

- 左侧深色导航（sidebar）
- 中间今日雷达候选内容卡片
- 右侧智能阅读面板
- 整体配色、grid / flex 比例、滚动区域
- 候选池 / 生成队列 / InsightCard 主流程

## 3. 只增强 /radar/today 的"最近探测状态"

在左侧 `最近探测状态` 区域**追加**一个小块 `调度状态`，以及一个轻量入口
`自动调度说明`。原有字段（运行中 / 成功 / 失败 / 部分失败 / 新增·更新·发现 /
最近启动 / 查看运行记录）全部保留。

## 4. 新增 scheduler_status view model

新增只读 view model：`app/application/radar/status_view.py`

- `RadarSchedulerStatusView`（frozen dataclass）
- `build_radar_scheduler_status_view(db)`：
  - 调用 `compute_due_sources(db)`（只读）
  - 调用 `build_stale_fetch_run_report(db)`（只读）
  - 汇总 due / skipped / running / unsupported / missing / stale / not_due 计数
  - 给出通用 `scheduler_mode_label="外部配置"` 文案
- **只读**：不创建 FetchRun、不触发抓取、不调用 LLM

route 侧降级：view model 计算失败时 `scheduler_status=None`，模板显示
`调度状态暂不可用`，绝不阻塞主阅读视图。

## 5. 新增"自动调度说明"入口

在 `查看运行记录` 旁新增 `自动调度说明`，链接到 project docs：
`/project-docs/v1-beta-2-scheduler-operations`。复用现有 `.btn-sm` 二级按钮样式。

## 6. 不暴露脚本和环境变量给普通用户

主 UI 用用户能懂的词，技术词映射：

| 技术词 | UI 文案 |
|--------|---------|
| due source | 待检查来源 |
| not_due_yet | 冷却中 |
| running | 运行中 |
| stale | 疑似卡住 |
| missing | 来源缺失 |
| unsupported | 暂不支持 |
| FetchRun | 运行记录 |

`run_due_sources_once.py` / `cron` / `Task Scheduler` /
`RADAR_SCHEDULER_ENABLED` / `AUTO_SUMMARY_MAX_PER_FETCH_RUN` **不出现在主 UI**，
只在自动调度说明文档里出现。

## 7. 不触发真实抓取，不调用 LLM

view model 仅做只读聚合。本任务不运行 `/radar/today/update`、
`/sources/{source_key}/fetch`、`run_due_sources_once.py --apply`，不生成摘要 /
InsightCard。

## 8. 样式约束

仅新增少量 class：`.radar-scheduler-status` / `.radar-scheduler-title` /
`.radar-scheduler-row` / `.radar-scheduler-label` / `.radar-scheduler-value` /
`.radar-scheduler-hint`。不改全局、布局、卡片、阅读面板、按钮体系。

## 9. 验收

- `compileall` / `quick_test`（新增第 37 节）/ `acceptance_first_usable_loop` 通过
- `check_due_sources` 正常，`check_stale_fetch_runs` stale_count=0
- 手动打开 `/radar/today` 确认三栏与导航无变化，仅多出"调度状态"小块与"自动调度说明"入口
