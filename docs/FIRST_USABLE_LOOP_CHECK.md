# First Usable Loop — Manual Validation Guide

## 目标

验证第一可用闭环的完整体验链路：

```
信息来源 → 运行探测 → 本次探测结果 → 加入生成 → 生成队列 → InsightCard
```

## 前置条件

```bash
# 启动服务
uvicorn app.main:app --reload --port 8779
```

## 验证步骤

### 1. 启动服务

```bash
uvicorn app.main:app --reload --port 8779
```

打开浏览器访问 `http://127.0.0.1:8779/`。

### 2. 打开信息来源页面

访问 `http://127.0.0.1:8779/sources`。

确认：
- 能看到配置的来源列表（RSS / HTML Index 类型）
- 每个来源有"运行探测"按钮

### 3. 选择一个来源点击运行探测

点击任意来源的"运行探测"按钮。

页面会跳转到 `/fetch-runs/{id}`。

### 4. 查看本次探测结果

在 FetchRun 详情页确认：
- 能看到 `发现 / 新增 / 已存在 / 失败` 统计
- 能看到本次抓取的内容列表
- 新增内容有条目时，每条右侧有"加入生成"按钮

### 5. 对一条内容点击"加入生成"

点击"加入生成"后，页面仍然留在当前 FetchRun 详情页（这是正常行为）。

### 6. 打开生成队列

访问 `http://127.0.0.1:8779/generation-queue`。

确认：
- 页面顶部说明"这里查看加入生成后的状态：生成中 / 已完成 / 失败 / 未处理"
- 能看到刚才加入生成的内容条目
- 条目状态为"生成中"、"已完成"、"失败"或"未处理"之一

### 7. 生成完成后打开 InsightCard

当条目状态变为"已完成"时，点击"查看 InsightCard"跳转到卡详情页。

在 InsightCard 详情页确认：
- 能看到中文摘要、关键洞察、产品机会、风险、行动项
- 有中英双语核心理解区块（如果已生成双语报告）

## 重要说明

### 本轮不要求真实网络一定成功

- RSS / HTML 探测可能因为网络问题超时或失败
- 重点是看 **FetchRun 是否正确记录了 `failed` 状态和 `error_message`**
- 只要系统行为符合预期（探测 → 记录结果 → 可加入生成 → 生成队列可见），即为通过

### 预期失败场景

| 步骤 | 可能的失败 | 是否正常 |
|------|-----------|---------|
| 来源探测 | RSS 超时、HTML 解析失败 | ✅ 正常，应看到 failed + error_message |
| 内容生成 | 网络/解析问题 | ✅ 正常，生成队列中显示失败 |
| 探测结果为空 | 某些来源无更新 | ✅ 正常，显示 0 条 |

### 异常情况判断

以下情况才算**异常**：
- 点击"运行探测"后没有任何跳转
- FetchRun 页面空白，没有统计数据
- 加入生成后，生成队列页面看不到对应条目
- InsightCard 页面报错或500

## 测试命令

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
