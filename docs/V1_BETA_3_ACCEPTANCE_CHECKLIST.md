# V1.0-beta.3 Acceptance Checklist

## 1. 自动验收

### 编译检查

```bash
python -m compileall app scripts
```

**通过标准**：无编译错误，所有 `.py` 文件字节码生成成功。

---

### 快速自检

```bash
python scripts/quick_test.py
```

**通过标准**：全部 715+ 条断言通过，0 failed。

---

### 今日雷达完整验收（两种运行方式）

```bash
# 方式 1：直接执行
python scripts/acceptance_first_usable_loop.py

# 方式 2：module 执行
python -m scripts.acceptance_first_usable_loop
```

**通过标准**：
- 47 条验收断言全部通过
- `/radar/today` 返回 HTTP 200
- `/radar/today/panel?item_id=<真实ID>` 返回 HTTP 200，fragment 包含 `id="radar-panel"`，不包含 `<html>`/`<body>`

---

### 来源健康检查

```bash
python scripts/check_due_sources.py
```

**通过标准**：脚本正常输出，无异常退出。due count 可能为 0（取决于来源冷却状态）。

---

### Stale Running 检查

```bash
python scripts/check_stale_fetch_runs.py
```

**通过标准**：显示 `stale_count: 0`，无异常退出。

---

## 2. 浏览器人工验收

### 目录栏收起/展开

| # | 检查点 | 通过标准 |
|---|--------|----------|
| 1 | 打开 `/radar/today` | 页面正常加载，左侧目录栏宽度约 220px |
| 2 | 点击「收起目录」 | 目录栏缩成约 52px 窄条，按钮文案变为「展开」 |
| 3 | 主列表宽度 | 向左扩展，增加了可用宽度 |
| 4 | 点击「展开」 | 目录栏恢复约 220px，按钮文案变回「收起目录」 |
| 5 | 刷新页面 | 收起状态保持（localStorage 持久化） |

---

### 卡片点击局部刷新

| # | 检查点 | 通过标准 |
|---|--------|----------|
| 1 | 滚动中间主列表到中部 | 滚动位置在页面中部 |
| 2 | 点击任意卡片主体 | 页面**不整体刷新**（观察浏览器 loading 状态） |
| 3 | 主列表滚动位置 | **不跳顶部**，保持在点击前位置 |
| 4 | 右侧面板内容 | 切换为所点卡片的：标题、来源、时间、状态 |
| 5 | 当前卡片高亮 | 有视觉高亮变化（边框/背景色） |
| 6 | 浏览器地址栏 | URL 包含 `item_id=<所点卡片ID>` |
| 7 | 再次滚动到另一位置 | 再次点击另一卡片 |
| 8 | 右侧面板再次刷新 | 内容切换为新卡片，主列表位置保持 |

---

### 面板操作按钮

| # | 检查点 | 通过标准 |
|---|--------|----------|
| 1 | 「加入生成」按钮 | 点击后出现表单提交，跳转回 `/radar/today`，面板保持该条目 |
| 2 | 「打开原文」按钮 | 在新窗口/标签页打开原始 URL |
| 3 | 「查看 InsightCard」按钮 | 存在且能进入 InsightCard 详情页（仅已编译条目显示） |
| 4 | JS 失败降级 | 禁用 JS 后点击卡片，降级为普通页面跳转（href 可用） |

---

### 摘要生成入口

| # | 检查点 | 通过标准 |
|---|--------|----------|
| 1 | 「生成本页前 5 条摘要」按钮 | 存在且可点击 |
| 2 | 点击后出现处理结果 | 显示：成功 N，跳过 N，失败 N |
| 3 | 分页切换后 section 保持 | 切换分页后，左侧目录「全部/今日重点」高亮状态保持 |

---

## 3. 不应发生的副作用

验收过程中**不应发生**以下行为：

| # | 禁止行为 | 检查方式 |
|---|----------|----------|
| 1 | 触发真实来源抓取 | 验收命令不包含 `/radar/today/update` |
| 2 | 调用 LLM 生成摘要 | 验收命令不包含 `generate-summaries` POST |
| 3 | 写入数据库 schema 变更 | 无 `ALTER TABLE` 或 migration |
| 4 | 改动摘要生成逻辑 | 无 `app/services/insight_compiler.py` 修改 |
| 5 | 改动 InsightCard 编译逻辑 | 无 `app/application/source_items/compile_service.py` 修改 |
| 6 | 改动最左侧深色全局导航 | `app/templates/base.html` 未改动 |
| 7 | 引入 React / Vue / HTMX | `app/templates/radar_today.html` 未引用这些库 |
| 8 | 全站导航拦截 | JS 仅拦截 `.radar-card-main-link`，不拦截全局 `a` 标签 |

---

## 4. 已知可接受限制

以下现象在 V1.0-beta.3 中**可接受**，不需要修复：

| # | 限制 | 说明 |
|---|------|------|
| 1 | 最左侧全局导航整页跳转 | 当前保持 SSR 页面级导航，不做全站无刷新 |
| 2 | 表单提交仍是传统请求 | 卡片点击局部刷新仅针对面板，表单提交仍是 POST 跳转 |
| 3 | JS 失败时降级为完整页面跳转 | 右侧面板 partial 是渐进增强，JS 禁用时通过 href 降级 |
| 4 | 中文摘要与 InsightCard 摘要可能不一致 | 来自不同字段，语义尚未统一 |
| 5 | source metadata / RSS summary 可能是英文 | 英文内容不应等同于中文摘要 |
| 6 | 一次最多处理 5 条摘要 | 由 `summary_limit=5` 控制 |
| 7 | 单用户本地 MVP | 不支持多用户权限 |
| 8 | 当前不做全网爬虫 | 只做配置的雷达关注源探测 |
| 9 | 目录收起后 52px 布局固定 | 不随内容动态调整 |
