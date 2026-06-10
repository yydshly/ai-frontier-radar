# V1.0-beta 下一阶段执行计划

## 产品方向

- **手动工作流**：作为底层能力保留，用户自主控制何时探测、何时生成
- **每日雷达**：作为上层内容消费入口，每日定时推送精选内容

## 当前已完成（First Usable Loop）

```
信息来源 → 后台运行探测 → FetchRun 结果页 → 候选池 → 加入生成 → 生成队列 → InsightCard
```

- ✅ 信息来源管理（YAML + DB）
- ✅ 后台来源探测（BackgroundTasks）
- ✅ FetchRun 详情页（含失败横幅、错误原因解释）
- ✅ 候选池卡片化展示（弱标题降级、摘要提取、时间标签）
- ✅ 生成队列（compiling / compiled / failed / discovered 分区）
- ✅ InsightCard 深度报告
- ✅ 测试数据降噪（`test_*` / `orphan_key` 不污染生产视图）

---

## 下一阶段优先级

### P0 — 必须做（下一版本核心）

| 序号 | 任务 | 说明 |
|------|------|------|
| P0-1 | 真实来源全量验证 | 验证所有已配置来源能稳定探测，发现并修复失败来源 |
| P0-2 | SourceFetchService 写入层 error_message 兜底 | 写入 FetchRun 时确保 error_message 不为空，避免 null 导致横幅显示不友好 |
| P0-3 | 中文一句话摘要展示与生成模块 | AI 生成中文一句话摘要，作为核心理解层，接入 TTS 预留 |
| P0-4 | 每日雷达 MVP | 定时探测 + 每日精选推送页面，作为内容消费主入口 |

---

### P1 — 重要（体验与扩展性）

| 序号 | 任务 | 说明 |
|------|------|------|
| P1-1 | 单来源工作台 | 按来源维度组织内容，便于聚焦单一来源深度消费 |
| P1-2 | 新增来源入口 | 网页表单新增来源，降低用户添加来源门槛 |
| P1-3 | 分页与数据治理 | `/cards` 和首页统计引入分页，防止大数据量性能问题 |
| P1-4 | 项目文档更新 | 架构图更新、新增功能文档、README 与文档同步 |

---

### P2 — 优化（长期改进）

| 序号 | 任务 | 说明 |
|------|------|------|
| P2-1 | delta 精准化 | 基于 content hash 的精确去重 + 增量更新，替代时间窗口估算 |
| P2-2 | repair 标题产品化入口 | 脏标题批量修复脚本 + UI 入口，不用重新探测即可修复 |
| P2-3 | 语音播报稿 | 中文一句话摘要生成后，整理为播报稿格式 |
| P2-4 | TTS 音频播报 | 接入 TTS API，实现语音播报功能 |

---

## 不在本轮范围

| 能力 | 原因 |
|------|------|
| 持久任务队列（Celery/BullMQ） | 先用 BackgroundTasks 验证产品，再考虑稳定性投入 |
| 多用户 / 登录注册 | MVP 聚焦单用户主链路 |
| 分布式部署 | 单进程部署足够验证产品假设 |
| 向量数据库 / 语义搜索 | 需要先有真实数据积累 |
| 知识图谱 | 需要先有实体和关系数据 |

---

## 执行原则

1. **不做业务功能扩展**：本轮只做 P0，不新增 P1/P2 范围外的功能
2. **不改数据库结构**：不引入新的 ORM 模型或表结构变更
3. **不改抓取策略**：不改变 RSS / HTML Index 探测的核心逻辑
4. **不改生成流程**：不改变 LLM 编译链路
5. **不改状态机**：InsightCard 和 SourceItem 的状态流转保持不变
6. **不引入新依赖**：不新增 pip 包依赖

---

## V1.0-beta.5：摘要写入规范

> 已完成：V1.0-beta.4 摘要语义统一（展示层），V1.0-beta.5 聚焦写入规范（写入层）

### V1.0-beta.5 目标

定义摘要字段写入规范，解决：

- `zh_one_liner` 和 `zh_summary` 的边界定义
- 字段覆盖规则（默认不覆盖已有非空值）
- L0（来源摘要）永远不能标记为 AI 中文摘要
- `InsightCard.summary_zh` 不反向污染 `SourceItem` 摘要
- 失败记录规范

### V1.0-beta.5 完成项

- ✅ `docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md` — 写入规范定义
- ✅ L0 / L1 / L2 / L3 字段权威性等级定义
- ✅ 生成者 / 写入者 / 消费者矩阵
- ✅ `zh_one_liner` 写入规则（`CandidateOneLinerService`）
- ✅ `zh_summary` 写入规则（待定义服务）
- ✅ `InsightCard.summary_zh` 不自动覆盖 `zh_one_liner` / `zh_summary`
- ✅ `quick_test.py` [48] V1.0-beta.5 summary write policy
- ✅ `acceptance_first_usable_loop.py` [20] V1.0-beta.5 summary write policy
- ✅ `NEXT_EXECUTION_PLAN.md` / `README.md` 包含 V1.0-beta.5

### V1.0-beta.5 暂不改

- ❌ 数据库 schema（Alembic / models.py / db.py）
- ❌ 抓取逻辑
- ❌ LLM 调用逻辑
- ❌ `insight_compiler.py`

---

## V1.0-beta.6：今日雷达主链路

> 分支：`feature/v1-beta-6-today-item-content-chain`

### V1.0-beta.6 目标

打通今日雷达主链路：TodayItemCard 中文概述状态 → 内容获取 intent-only → bootstrap/daily_increment 来源发现入口。

### V1.0-beta.6 完成项

- ✅ TodayItemCard 多维状态（zh_one_liner / zh_summary / content / insight）
- ✅ 右侧面板展示各维度状态标签及操作入口
- ✅ 内容获取 intent-only 链路（POST fetch-content，只写 queued）
- ✅ bootstrap / daily_increment 入口设计（bootstrap 独立，daily_increment 复用 due-source）
- ✅ bootstrap dry-run / apply 语义
- ✅ Web apply background（FastAPI BackgroundTasks）
- ✅ CLI apply sync
- ✅ `SourceDiscoveryRunResult.execution_mode`
- ✅ `docs/V1_BETA_6_TODAY_RADAR_MAIN_CHAIN_CHECKPOINT.md`
- ✅ `docs/V1_BETA_6_SOURCE_DISCOVERY_BOOTSTRAP_AND_DAILY_INCREMENT_PLAN.md`

### V1.0-beta.6 暂不改

- ❌ 自定义来源 F-2
- ❌ 真实正文抓取
- ❌ 自动日报
- ❌ 音频播报
- ❌ DB schema

---

## V1.0-beta.7：日报卡片（进行中）

> 分支：`feature/v1-beta-7-daily-report-card`

### V1.0-beta.7 目标

规则打分分层日报卡片：今日必看 3-5 条 + 其他值得扫一眼，不调用 LLM。

### V1.0-beta.7 完成项

- ✅ DailyReportCard 两层结构（今日必看 / 其他值得扫一眼）
- ✅ 规则打分排序（来源权重 + 关键词 + 新鲜度）
- ✅ 中文方向标签映射（`_DIRECTION_LABELS`）
- ✅ 3-5 条主次分层语义
- ✅ 防漏提示（"避免错过关键报告"）
- ✅ 每条保留原文链接
- ✅ InsightCard 链接（已有时）
- ✅ `docs/V1_BETA_7_DAILY_REPORT_CARD_CHECKPOINT.md`

### V1.0-beta.7 暂不改

- ❌ LLM 日报总结
- ❌ 音频播报
- ❌ 真实正文抓取
- ❌ DB schema

---

## 验收标准

- README 准确反映当前能力
- FIRST_USABLE_LOOP_CHECK 与代码能力一致
- KNOWN_LIMITATIONS 包含真实限制
- NEXT_EXECUTION_PLAN 可见于 /project-docs
- 全部测试通过：compileall / quick_test / smoke_test / acceptance_demo_flow / acceptance_demo_data / health_check --quick
