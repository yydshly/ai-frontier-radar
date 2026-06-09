# V1.0-beta First Usable Loop — 验收文档

## 目标

验证第一可用闭环的完整体验链路。链路打通即视为通过，不要求真实网络成功或 LLM 真实输出。

## 链路总览

```
信息来源 → 后台运行探测 → FetchRun 详情查看本次结果 → 候选池浏览标题/摘要/链接/时间 → 加入生成 → 生成队列查看状态 → InsightCard 查看结果
```

## 前置条件

```bash
# 启动服务
uvicorn app.main:app --reload --port 8779
```

## 验收步骤

### Step 1. 打开信息来源页面

访问 `http://127.0.0.1:8779/sources`。

确认：
- 能看到配置的来源列表（RSS / HTML Index 类型）
- 每个来源有「运行探测」按钮

### Step 2. 点击「运行探测」

点击任意来源的「运行探测」按钮。

页面跳转到 `/fetch-runs/{id}`（FetchRun 详情页）。

### Step 3. 查看本次探测结果

在 FetchRun 详情页确认：
- 能看到「发现 / 新增 / 已存在 / 失败」统计
- 能看到本次抓取的内容列表
- 新增内容有条目时，每条右侧有「加入生成」按钮
- 标题为「标题待修复」的条目表示弱标题已降级处理
- 运行中状态显示「正在探测该来源」横幅

### Step 4. 浏览候选池

访问 `http://127.0.0.1:8779/candidate-pool`。

确认：
- 能看到标题 / 摘要 / 链接 / 时间（发布于 / 发现于）
- 弱标题显示为「标题待修复」，并标注原始标题
- 每条可独立加入生成

### Step 5. 加入生成

在候选池或 FetchRun 详情页，点击一条内容的「加入生成」。

页面仍然留在当前页（这是正常行为）。

### Step 6. 查看生成队列

访问 `http://127.0.0.1:8779/generation-queue`。

确认：
- 页面顶部说明「这里查看加入生成后的状态：生成中 / 已完成 / 失败 / 未处理」
- 能看到刚才加入生成的内容条目
- 条目状态为「生成中」「已完成」「失败」或「未处理」之一

### Step 7. 查看 InsightCard

当条目状态变为「已完成」时，点击「查看 InsightCard」跳转到卡片详情页。

在 InsightCard 详情页确认：
- 能看到中文摘要、关键洞察、产品机会、风险、行动项
- 有中英双语核心理解区块（如果已生成双语报告）

## 当前已完成

1. ✅ 信息来源管理（YAML 配置 + DB 持久化）
2. ✅ 后台来源探测（BackgroundTasks）
3. ✅ FetchRun 运行结果页（含失败横幅 + 错误原因解释）
4. ✅ 候选内容卡片化展示（标题降级、摘要提取、时间标签）
5. ✅ 候选池浏览与加入生成
6. ✅ 生成队列（compiling / compiled / failed / discovered 分区）
7. ✅ InsightCard 深度报告
8. ✅ 测试数据降噪（`test_*` 和 `orphan_key` 来源不污染生产视图）

## 当前未完成

1. ❌ 中文一句话摘要生成（仍主要依赖英文 metadata 摘要）
2. ❌ 每日雷达页面（作为上层内容消费入口）
3. ❌ 新增来源入口（网页表单新增来源）
4. ❌ 单来源工作台（按来源维度组织内容）
5. ❌ 分布式持久任务队列
6. ❌ 脏标题批量修复产品入口
7. ❌ TTS 语音播报

## 预期失败场景（正常）

| 步骤 | 可能的失败 | 是否正常 |
|------|-----------|---------|
| 来源探测 | RSS 超时、HTML 解析失败 | ✅ 正常，应看到 failed + error_message |
| 内容生成 | 网络/解析问题 | ✅ 正常，生成队列中显示失败 |
| 探测结果为空 | 某些来源无更新 | ✅ 正常，显示 0 条 |

## 异常情况判断

以下情况才算**异常**：
- 点击「运行探测」后没有任何跳转
- FetchRun 页面空白，没有统计数据
- 加入生成后，生成队列页面看不到对应条目
- InsightCard 页面报错或 500

## 已知限制（验收时已知，不影响通过）

1. **BackgroundTasks 不是持久队列**：服务重启会丢任务，未完成的任务不会自动恢复
2. **10 分钟 running 去重不是分布式锁**：多进程部署下同一来源可能并发运行
3. **delta new / seen / updated 是时间窗口估算**：不是精确的变更检测
4. **HTML index 仅抓前 15 个候选详情页 metadata**：`MAX_DETAIL_FETCHES_PER_SOURCE = 15`
5. **旧脏标题需要 repair 脚本或重新探测修复**：系统本身不自动修复历史脏标题
6. **当前中文摘要仍主要来自英文 metadata**：尚未完成 AI 中文一句话摘要
7. **真实来源全量验证尚未完成**：部分来源可能抓取失败
8. **新增来源暂时偏配置文件/数据库层**：网页新增入口尚未完成

## 验证命令

```bash
# 开发中快速自检
python -m compileall app scripts
python scripts/quick_test.py

# PR 前完整检查
python scripts/smoke_test.py
python scripts/acceptance_demo_flow.py
python scripts/acceptance_demo_data.py
python scripts/health_check.py --quick
```

## quick_test vs smoke_test vs acceptance 定位说明

| 脚本 | 定位 | 何时跑 |
|------|------|--------|
| `quick_test.py` | 开发中快速自检：import、核心路由、service 可导入性、模板关键字 | 每次 commit 前 |
| `smoke_test.py` | PR-ready 完整回归：health、静态资源、编译流程、配置加载 | PR 前 |
| `acceptance_demo_*.py` | 完整用户链路验收 | 大版本发布前 |
| `health_check.py` | 本地轻量 CI：不访问外网、不调 LLM | 本地开发循环 |

`quick_test.py` **不跑** smoke_test 和 acceptance；这些属于 `smoke_test.py`（PR 前完整回归）和 `acceptance_demo_*.py`（用户流/数据验证）。

## 下一步计划

详见 [docs/NEXT_EXECUTION_PLAN.md](docs/NEXT_EXECUTION_PLAN.md)。
