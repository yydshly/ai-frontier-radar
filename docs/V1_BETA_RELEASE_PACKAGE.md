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
