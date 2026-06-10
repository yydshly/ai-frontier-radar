# V1.0-beta.6 Final Checkpoint

> 版本：V1.0-beta.6
> 分支：`feature/v1-beta-6-today-item-content-chain`
> main 基准 commit：`d48eddb`（V1.0-beta.6 bootstrap）
> feature 最新有效 commit：待提交
> checkpoint 创建日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.6 打通**今日雷达主链路**：从 TodayItemCard 中文概述状态 → 内容获取链路 → bootstrap/daily_increment 来源发现入口。

核心变化：
- `TodayItemCard` 新增 `zh_preview` / `summary_state` / `content_note` 字段
- 右侧面板展示中文概述（中文摘要）和正文状态
- bootstrap/daily_increment 作为独立入口，不走 due-source 调度
- Web apply 由 FastAPI `BackgroundTasks` 执行，不阻塞 UI
- CLI apply 保持同步执行

---

## 二、已完成能力

### 2.1 TodayItemCard 中文概述状态

- `TodayItemCard` dataclass 新增 `zh_preview`、`summary_state`、`content_note` 字段
- `summary_state` 推导逻辑：
  - `zh_one_liner` 有值 → `"chinese_overview"`（中文概述）
  - `zh_summary` 有值 → `"chinese_summary"`（中文摘要）
  - 否则 → `"pending"`（待生成）
- 模板渲染三种状态：中文概述 / 中文摘要 / 待生成

### 2.2 右侧面板状态

- `radar_today.html` 面板展示 `summary_state` 对应标签
- `zh_preview` 优先于 `primary_text` 展示
- `content_note` 说明正文状态（intent-only，不真实抓取）

### 2.3 内容获取链路

- `POST /radar/today/items/<id>/fetch-content` 接收请求
- 写入 `queued_metadata`（intent-only），不调用 LLM
- UI 提示"内容获取需要稍后刷新查看"
- GET fetch-content 返回 405 Method Not Allowed

### 2.4 Bootstrap / Daily Increment 设计

**文档**：`docs/V1_BETA_6_SOURCE_DISCOVERY_BOOTSTRAP_AND_DAILY_INCREMENT_PLAN.md`

- `POST /radar/today/bootstrap`：初始化入口
- `POST /radar/today/update`：复用 due-source 更新入口（不变）
- bootstrap 默认 dry-run，需要 `action=apply` 才执行
- `run_source_discovery_once.py --mode bootstrap/daily_increment --dry-run/--apply`

### 2.5 Bootstrap Dry-run / Apply 语义

- dry-run：不写库、不 enqueue、不创建 FetchRun，不触发网络抓取
- apply：复用 `SourceFetchBackgroundService`，禁用 auto summary（`AUTO_SUMMARY_MAX_PER_FETCH_RUN=0`）
- bootstrap 默认最近 20 条，最大 50 条
- `SourceDiscoveryRunResult` 新增 `execution_mode` 字段

### 2.6 Web Apply Background

- `BackgroundTasks` 在 UI 线程外执行 apply
- bootstrap route inject `BackgroundTasks`
- UI 提示"后台已启动，稍后刷新今日雷达或查看来源抓取记录获取新增内容"

### 2.7 CLI Apply Sync

- CLI apply 不使用 BackgroundTasks，保持同步执行
- `discovery_apply_environment()` 设置 `AUTO_SUMMARY_MAX_PER_FETCH_RUN=0`

---

## 三、当前不做

| 能力 | 原因 |
|------|------|
| 自定义来源 F-2 | 已有 intake 入口，不在本轮范围 |
| 真实正文抓取 | 内容获取为 intent-only，不实现真实 fetch |
| 自动日报 | 下一阶段任务 |
| 音频播报 | 下一阶段任务 |
| DB schema 修改 | 不引入 ORM 或表结构变更 |

---

## 四、当前已知限制

- bootstrap apply 会真实抓取外部来源，不在自动验收中执行 apply
- daily_increment UI 复用 due-source 更新入口，文案已调整
- 新增内容数需要 FetchRun 完成后刷新查看
- 内容获取为 intent-only 标记，不触发真实抓取

---

## 五、涉及文件

- `app/application/radar/daily_digest.py` — TodayItemCard dataclass
- `app/application/radar/daily_report.py` — summary_state 推导
- `app/routes/radar.py` — bootstrap/update 路由
- `app/templates/radar_today.html` — 面板状态渲染
- `scripts/run_source_discovery_once.py` — CLI 入口
- `app/services/source_discovery.py` — 发现服务

---

## 六、禁止修改范围

- DB schema（models.py / db.py）
- 已有 InsightCard 生成链路
- 已有 due-source 调度逻辑
- LLM 调用逻辑

---

## 七、验收测试

- `quick_test.py` — 945 passed, 0 failed
- `acceptance_first_usable_loop.py` — 135 passed, 0 failed
- `check_due_sources.py` — due=0，正常 cooldown
- `check_stale_fetch_runs.py` — stale_count=0，无卡住任务

---

## 八、下一阶段建议

1. **DailyReportCard**：日报卡片聚合今日发现内容
2. **音频播报**：中文概述接入 TTS
3. **真实正文获取能力接入**：内容获取从 intent-only 到真实 fetch
4. **自定义来源 F-2**：网页表单新增来源
