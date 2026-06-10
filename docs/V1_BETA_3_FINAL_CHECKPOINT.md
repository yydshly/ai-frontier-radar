# V1.0-beta.3 Final Checkpoint

## 阶段结论

**V1.0-beta.3 已完成今日雷达体验闭环，当前分支可作为 Release Candidate。**

---

## 基础信息

| 字段 | 内容 |
|------|------|
| 版本 | V1.0-beta.3 |
| 分支 | `feature/v1-beta-3-radar-status-ui` |
| 最终 checkpoint 基准 commit | `6ffe383` |
| 文档修正 commit | 见下方本次最新提交 |
| 阶段定位 | 今日雷达（`/radar/today`）阅读体验闭环 |

---

## 已完成能力

### Task 1：调度状态 UI 接入
- 调度状态展示：待检查来源 / 冷却中 / 疑似卡住 / 来源缺失
- 来源于 `app/application/radar/status_view.py`

### Task 2：中文理解入口优化
- 中文摘要优先展示（`zh_one_liner`）
- 「中文概述」badge 显示

### Task 2.1：无摘要时英文标题显示修复
- 无 `zh_one_liner` 时 fallback 到 `primary_text` 或 `item.title`
- 不暴露弱标题（「Learn More」「FEATURED」）

### Task 4：摘要补齐按页面顺序处理 + 错误信息用户化
- 按视觉页面顺序处理（不按 `last_seen_at` 倒序）
- `summary_limit=5`，每批最多 5 条
- 错误信息用户化：「中文摘要生成失败，可稍后重试」

### Task 5：主列表紧凑布局优化
- 卡片紧凑布局，减少视觉噪音
- `.radar-card-footer` + `.radar-card-meta` + `.radar-card-actions` 同行

### Task 6：卡片主体可点击
- 整个卡片主体区域为 `.radar-card-main-link`
- 点击不触发 actions 区域按钮

### Task 6.1：meta/actions 同一行
- 状态 badge、来源、时间、编号 与 操作按钮在同一行

### Task 7：目录栏可收起/展开
- 点击「收起目录」，目录缩成约 52px 窄条
- 状态保存到 `localStorage`

### Task 7.1：目录栏收起后真正释放主列表空间
- CSS grid `grid-template-columns` 从 `220px` 调整为 `52px`
- 主列表宽度增加

### Task 8：卡片点击局部刷新右侧面板
- 点击卡片主体只刷新右侧智能阅读面板
- `GET /radar/today/panel` 返回 HTML fragment
- `history.pushState` 更新 URL
- JS 失败时 `window.location.href` 降级

### Task 8.1：修复 partial 面板空白
- `_build_radar_today_view_context()` 增加 `sel` 和 `sel_card`
- Partial 渲染时上下文完整

### Task 8.2：acceptance 脚本直接执行稳定
- `sys.path.insert(0, str(ROOT))` 在 imports 前执行
- 支持 `python scripts/acceptance_first_usable_loop.py` 和 `python -m scripts.acceptance_first_usable_loop`

### Release Candidate Cleanup
- `docs/V1_BETA_3_RELEASE_NOTES.md` — 版本说明、已完成能力清单
- `docs/V1_BETA_3_ACCEPTANCE_CHECKLIST.md` — 自动验收、人工验收、已知限制
- `docs/KNOWN_LIMITATIONS.md` — V1.0-beta.3 限制小节
- `README.md` — V1.0-beta.3 入口

---

## 自动验收结果

| 测试 | 命令 | 结果 |
|------|------|------|
| compileall | `python -m compileall app scripts` | ✅ 通过 |
| quick_test | `python scripts/quick_test.py` | ✅ 737 passed, 0 failed |
| direct acceptance | `python scripts/acceptance_first_usable_loop.py` | ✅ 47 passed, 0 failed |
| module acceptance | `python -m scripts.acceptance_first_usable_loop` | ✅ 47 passed, 0 failed |
| check_due_sources | `python scripts/check_due_sources.py` | ✅ 正常（0 个到期来源） |
| check_stale_fetch_runs | `python scripts/check_stale_fetch_runs.py` | ✅ stale_count=0 |

---

## 人工验收结果

- **验收基准 commit**：`c0602b2`
- **验收结论**：手动测试暂未发现明显问题
- **验收范围**：详见 [docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md](docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md)

---

## 已知限制

| # | 限制 | 可接受理由 |
|---|------|------------|
| 1 | 最左侧全局导航仍是页面级跳转 | MVP 保持 SSR 稳定 |
| 2 | 表单提交仍是传统 POST | 不做 SPA 表单 |
| 3 | JS 失败时降级为完整页面跳转 | 渐进增强保证可用 |
| 4 | 中文摘要与 InsightCard 摘要可能不一致 | 来自不同字段，MVP 可接受 |
| 5 | 一次最多处理 5 条摘要 | 有意限制，防止 LLM 超时 |
| 6 | 单用户本地 MVP | 不支持多用户 |
| 7 | 不做全网爬虫 | 只做雷达关注源 |
| 8 | 不做全站无刷新导航 | 不属于本阶段范围 |

---

## merge-ready 判断

当前分支在以下条件**全部满足**后可合并：

| # | 条件 | 状态 |
|---|------|------|
| 1 | quick_test 通过 | ✅ 已满足 |
| 2 | direct acceptance 通过 | ✅ 已满足 |
| 3 | module acceptance 通过 | ✅ 已满足 |
| 4 | check_due_sources 通过 | ✅ 已满足 |
| 5 | check_stale_fetch_runs 通过 | ✅ 已满足 |
| 6 | 人工验收无明显阻塞问题 | ✅ 已满足 |

**结论：当前分支可合并。**

---

## 不建议继续在本分支追加的内容

以下内容**不建议**继续在 `feature/v1-beta-3-radar-status-ui` 分支追加：

| # | 内容 | 原因 |
|---|------|------|
| 1 | 不继续做全站无刷新导航 | 不属于本阶段，会引入 SPA 复杂度 |
| 2 | 不继续做移动端适配 | 需要独立设计，当前 MVP 不做 |
| 3 | 不继续做摘要语义统一 | 需要较大重构，后续版本处理 |
| 4 | 不继续做来源质量算法优化 | 当前够用，后续有数据再优化 |
| 5 | 不继续做复杂推荐 | 当前基于分类固定排序 |
| 6 | 不继续做多用户 | 单用户 MVP 阶段不需要 |

---

## 下一阶段建议

**V1.0-beta.4 建议聚焦「中文摘要 / 英文 metadata / InsightCard 摘要语义统一」。**

当前问题：
- `zh_one_liner`（中文一句话摘要）
- `raw_metadata_json.description`（英文 metadata 摘要）
- `InsightCard.summary`（编译时生成的摘要）

三者可能不一致，用户看到的是不同来源的摘要。

后续版本可考虑：
1. 统一摘要字段语义
2. 明确各字段的用途和展示优先级
3. 增加摘要来源标注

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [docs/V1_BETA_3_RELEASE_NOTES.md](docs/V1_BETA_3_RELEASE_NOTES.md) | 版本说明 |
| [docs/V1_BETA_3_ACCEPTANCE_CHECKLIST.md](docs/V1_BETA_3_ACCEPTANCE_CHECKLIST.md) | 验收清单 |
| [docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md](docs/V1_BETA_3_MANUAL_ACCEPTANCE_RECORD.md) | 人工验收记录 |
| [docs/V1_BETA_3_CHINESE_ENTRY_UX_PLAN.md](docs/V1_BETA_3_CHINESE_ENTRY_UX_PLAN.md) | 任务规划 |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | 已知限制 |
