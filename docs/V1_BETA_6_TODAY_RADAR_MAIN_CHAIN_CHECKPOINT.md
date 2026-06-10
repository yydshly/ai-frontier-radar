# V1.0-beta.6 Final Checkpoint

> 版本：V1.0-beta.6
> 分支：`feature/v1-beta-6-today-item-content-chain`
> main 基准 commit：`d48eddb`（V1.0-beta.6 bootstrap）
> feature 最新有效 commit：`43dc6e9`
> checkpoint 创建日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.6 打通**今日雷达主链路**：从 TodayItemCard 卡片状态 → 内容获取 intent-only → bootstrap/daily_increment 来源发现入口。

核心变化：
- `TodayItemCard` 拆分多维状态字段（中文概述 / 中文摘要 / 正文 / InsightCard）
- 右侧面板展示各维度状态及操作入口
- bootstrap 不走 due-source 冷却，daily_increment 复用 due-source 逻辑
- Web apply 由 FastAPI `BackgroundTasks` 执行，不阻塞 UI
- CLI apply 保持同步执行

---

## 二、已完成能力

### 2.1 TodayItemCard 多维状态字段

`TodayItemCard` dataclass 包含以下状态字段：

| 字段 | 说明 |
|------|------|
| `zh_one_liner_state` / `zh_one_liner_label` | 中文一句话状态（generated/missing） |
| `zh_summary_state` / `zh_summary_label` | 中文详细摘要状态（generated/missing） |
| `overview_state` / `overview_label` | 概览状态（= zh_one_liner_state） |
| `detailed_summary_state` / `detailed_summary_label` | 详细摘要状态（= zh_summary_state） |
| `content_state` / `content_label` / `content_note` | 正文状态（queued/not_fetched/fetched/fetch_failed） |
| `insight_state` / `insight_label` | InsightCard 状态 |
| `summary_state` / `summary_label` | 综合摘要状态 |

数据来源：
- 中文概述：来自 `raw_metadata_json.zh_one_liner`
- 中文摘要：来自 `raw_metadata_json.zh_summary`
- 正文状态：来自 `content_fetch_status` 或正文快照线索
- InsightCard 状态：来自 `SourceItem.status` / `insight_card_id`

### 2.2 右侧面板状态

- `radar_today.html` 面板展示 `zh_one_liner_label` / `zh_summary_label` / `content_label` / `insight_label`
- 各状态标签对应操作入口（fetch-content / generate insight）
- `content_note` 说明正文状态意图（intent-only）

### 2.3 内容获取链路（intent-only）

- `POST /radar/today/items/<id>/fetch-content` 只写 `content_fetch_status=queued`
- 不执行真实正文抓取
- UI 文案为"标记待获取正文"
- GET fetch-content 返回 405 Method Not Allowed

### 2.4 Bootstrap / Daily Increment 设计

**文档**：`docs/V1_BETA_6_SOURCE_DISCOVERY_BOOTSTRAP_AND_DAILY_INCREMENT_PLAN.md`

- `bootstrap`：不走 due-source 冷却，读取 enabled YAML 来源，适合初始化最近 20/50 条
- `daily_increment`：复用 due-source 逻辑，只处理到期来源
- `POST /radar/today/bootstrap`：初始化入口，默认 dry-run，需要 `action=apply` 才执行
- `POST /radar/today/update`：复用 due-source 更新入口（不变）
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
| 真实正文抓取 | 内容获取为 intent-only 标记，不实现真实 fetch |
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

- `app/application/radar/today_item_card.py` — `TodayItemCard` dataclass 与多维状态推导
- `app/application/radar/today.py` — `RadarTodayView` / `today_card_map` / panel_state
- `app/application/sources/discovery_runs.py` — bootstrap / daily_increment 来源发现入口
- `app/routes/radar.py` — 今日雷达 bootstrap / update / panel / intent-only content routes
- `app/templates/radar_today.html` — 今日雷达卡片、bootstrap 结果、操作入口
- `app/templates/partials/radar_today_panel.html` — 右侧处理链路面板
- `scripts/run_source_discovery_once.py` — CLI discovery 入口

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
