# V1.0-beta.2 调度 apply 验收（isolated DB + local mock RSS）

## 1. 验收目标

证明 `run_due_sources_once.py --apply` 的真实执行路径可以：

- 通过 `compute_due_sources()` 得到 due source
- 经 `SourceFetchBackgroundService.enqueue_source(..., background_tasks=None)` 同步创建 FetchRun
- 抓取并增量入库 SourceItem
- FetchRun 收敛为 `success`
- 在 `AUTO_SUMMARY_MAX_PER_FETCH_RUN=0` 下不触发 LLM 摘要
- 不生成 InsightCard
- 不产生 stale running

且全程**不污染主数据库、不访问外部网络、不调用 LLM**。

## 2. 为什么用 isolated DB + local mock RSS

- **isolated DB**：在 import 任何 `app.*` 之前把 `DATABASE_URL` 指向临时 SQLite，
  使本脚本与子进程 `run_due_sources_once.py --apply` 都只看到隔离库，主库
  `data/ai_frontier_radar.db` 不受影响。
- **local mock RSS**：用标准库 `ThreadingHTTPServer` 在 `127.0.0.1` 随机端口提供
  静态 RSS，RSS 探测只访问本地回环地址，无外网依赖、可复现。
- **seed 一个 config 中已 enabled 的 source**（`openai_news`）且不建任何 FetchRun，
  使其因 `never_fetched` 成为 due。其余 14 个 config 源在隔离库缺记录，进入 missing。

## 3. 验收链路

```
seed Source(openai_news, feed_url=local mock) [never_fetched]
  → run_due_sources_once.py --apply --max-sources 1 --show-missing
  → compute_due_sources(): due=1 (openai_news), missing=14
  → enqueue_source(openai_news, background_tasks=None)  # 同步
  → probe_rss_source() 抓取 local mock feed
  → SourceItem 增量入库 (2 条)
  → FetchRun success, items_found=2, items_new=2
  → auto_summary.enabled=false (AUTO_SUMMARY_MAX_PER_FETCH_RUN=0)
  → InsightCard=0, running=0, stale_count=0
```

## 4. 验收命令

```bash
python scripts/acceptance_run_due_sources_once_apply.py
# 排查时保留隔离库：
python scripts/acceptance_run_due_sources_once_apply.py --keep-temp --verbose
```

脚本内部对子进程注入的环境变量：

```
DATABASE_URL=sqlite:///<temp>/scheduler_apply_acceptance.db
RADAR_SCHEDULER_ENABLED=true
AUTO_SUMMARY_MAX_PER_FETCH_RUN=0
SOURCE_FETCH_MAX_ITEMS_PER_RUN=5
```

## 5. 预期结果

- scheduler exit 0，stdout 含 `APPLY` / `started=1` / `openai_news` / `run_id=`
- FetchRun count == 1，status == success
- SourceItem count == 2
- auto_summary.enabled == false
- InsightCard count == 0
- running FetchRun == 0，stale_count == 0

## 6. 实际结果

```
source_key=openai_news
mock RSS item count=2
scheduler exit=0
scheduler stdout: due=1, missing=14, started=1
  started_runs: openai_news run_id=1 final_status=success
                items_found=2 items_new=2 items_updated=0 items_failed=0
FetchRun count=1
FetchRun status=success
SourceItem count=2 (Mock AI Article 1 / Mock AI Article 2, status=discovered)
auto_summary.enabled=false
auto_summary.reason=AUTO_SUMMARY_MAX_PER_FETCH_RUN=0
auto_summary.processed_count=0
InsightCard count=0
running FetchRun count=0
stale_count=0
```

全部 11 项检查通过，脚本输出 `ACCEPTANCE_OK`。

并额外验证：运行本脚本前后主库
`data/ai_frontier_radar.db` 的 FetchRun / SourceItem 数量不变（FetchRun=995,
SourceItem=525 → 不变），证明**未污染主 DB**。

## 7. 当前结论

`--apply` 真实执行路径在隔离环境下成立：CLI 单轮调度可复用 FetchRun 作为抓取任务
状态对象，完成 SourceItem 增量入库，且默认不触发 LLM、不生成 InsightCard、不留 stale running。

## 8. 未覆盖项

- 未在主库真实抓取外部来源（按设计仅隔离验收）。
- 未覆盖 `html_index` 策略来源（本验收只用 rss）。
- 未覆盖 `--apply` 在并发 / 多来源 due 下的批量行为（`--max-sources 1`）。
- 未覆盖自动摘要开启路径（本阶段默认禁用 LLM）。

## 9. 下一步

- 外部定时器调用 CLI 的操作文档（Phase B：Windows Task Scheduler / cron）。
- 多 due 来源、每轮上限与失败退避策略。
- TaskRun / JobRun 决策复盘（Task 6）。
