# 今日核心报告卡片生成设计（P-003-2 / Phase D）

> 设计先行文档。这是 P-003 第一个**会调用 LLM** 的步骤，因此严格遵循
> "默认关闭、显式触发、成本闸门、dry-run 优先、测试不打真实 LLM"。
> 本阶段**不改 UI 布局**，先落地后端生成基础（服务 + CLI），UI 呈现留到后续小步。

## 1. 目标

把 Phase C 的"今日编译概览"（只读聚合）进一步合成为一段中文**今日核心报告**：
标题 + 总览 + 若干要点（highlights），帮助用户一眼掌握今天 AI 前沿发生了什么。

## 2. 设计原则（与既有 LLM 链路一致）

- **默认关闭**：`DAILY_REPORT_ENABLED=false`（默认）。`--apply` 必须显式开启。
- **dry-run 优先**：默认只组装"编译输入"（今日中文摘要条目），**不调用 LLM**。
- **成本闸门**：`DAILY_REPORT_MAX_ITEMS`（默认 50，1~50）限制喂给 LLM 的条目数；
  单次生成只调用 **一次** LLM。
- **复用现有 LLM 基础设施**：通过 `app.llm.factory.create_llm_client()` +
  `LLMClient.generate_json()`，不新写 provider / HTTP 客户端。
- **provider 可注入 + Mock**：仿照 `MockOneLinerProvider`，测试用
  `MockDailyReportProvider`，**quick_test 绝不打真实 LLM**。
- **prompt injection 防护**：沿用既有约定——输入条目是"待分析内容，不是指令"。
- **不新增数据库表 / 不改 schema**：本阶段生成结果**不持久化**（按需生成 + 返回），
  是否落库留待后续评估（优先复用既有 InsightCard 基础设施，不新建 DailyReport 表）。

## 3. 数据结构

```
DailyReportInput   ← 只读组装，无 LLM
    date_label: str
    item_count: int
    bullet_sources: list[str]   # 今日已生成中文一句话的条目（最多 max_items）

DailyReportResult
    status: "no_input" | "dry_run" | "disabled" | "generated"
    date_label / input_item_count
    title / overview / highlights[]   # 仅 generated 时有值
    message
```

## 4. 执行路径

```
generate_daily_report(db, apply=False)
  → build_daily_report_input(db)            # 只读：今日已摘要条目的中文一句话
  → item_count == 0 → status=no_input（不调用 LLM）
  → apply=False（默认）→ status=dry_run（仅组装输入，不调用 LLM）
  → apply=True 且 DAILY_REPORT_ENABLED!=true → status=disabled（拒绝，不调用 LLM）
  → apply=True 且 enabled → 调用一次 LLM → status=generated
```

闸门顺序保证：**任何未显式开启的情况都不会触达 LLM**。

## 5. CLI（仿 run_due_sources_once.py）

```bash
python scripts/run_daily_report_once.py            # dry-run，组装输入，不调用 LLM
DAILY_REPORT_ENABLED=true python scripts/run_daily_report_once.py --apply   # 真实生成
```

- 默认 dry-run：打印日期、今日摘要条目数、将要喂给 LLM 的要点预览、"未调用 LLM"。
- `--apply` 无 `DAILY_REPORT_ENABLED=true` → 退出码 2，不调用 LLM。

## 6. 边界

- 不默认触发；不进自动调度（自动调度仍默认不触发 LLM）。
- 不生成 InsightCard、不改抓取 / 调度 / 入库逻辑。
- 不改 `/radar/today` 布局（本阶段无 UI 改动）。
- 测试只验证：输入组装（只读）、dry-run 不调 LLM、Mock provider 下 apply 产出结构、
  env 闸门拒绝路径。**不调用真实 LLM。**

## 7. 后续

- Phase D 步骤 2：UI 上提供"生成今日核心报告"显式按钮（小调整，复用今日编译概览块），
  点击才调用，受同一闸门控制。
- Phase E：语音播报（TTS，独立可关闭模块）。

参考：[V1_OPTIMIZATION_ROADMAP.md](V1_OPTIMIZATION_ROADMAP.md)、
[V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)
