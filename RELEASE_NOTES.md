# AI Frontier Radar Release Notes

## V1.0-alpha

### Release Candidate 信息

- RC branch: `feature/v1.0-alpha.5-release-candidate-cleanup`
- RC commit: `3355e0a0b899ec35138578a0676cb2a2f38ecdbf`
- Base commit: `033a8b7554364fbe35ba66c5dcac4e351d07d5f6`

### Final Release 信息

- Release branch: `main`
- Final candidate commit: `937d47a`（V1.0-alpha.8.6 发布前一致性修复）
- Main CI: `#<run>`（待 CI 通过后更新），success
- Tag: `v1.0-alpha`（待创建）

### 定位

AI Frontier Radar V1.0-alpha 是一个**本地个人 AI 前沿资料中文编译工作台**。

它不是：
- 普通 RSS 阅读器
- 普通翻译器
- 资讯聚合站
- 多用户 SaaS

它的核心目标是：

```
英文 AI 前沿资料 → 中文 InsightCard → 中英双语理解 → 用户判断 → 完整 Markdown 报告 / 行动任务
```

### 当前可用能力

| 能力 | 说明 |
|------|------|
| 5 分钟本地演示 | 一键 demo 数据，无需真实 LLM |
| 首页工作台 | 统计卡片 + 推荐流程引导 |
| 精选 AI 前沿来源 | 15 个来源，含 OpenAI/Anthropic/HuggingFace 等 |
| SourceItem 收件箱 | 发现 → 编译状态追踪 |
| 单条编译 | POST 一个 URL，生成中文 InsightCard |
| 中英双语核心理解 | English Core Summary + 中文解说 |
| 用户判断 | 值得关注 / 与我有关 / 稍后再看 / 暂时忽略 / 转成行动 |
| 完整 Markdown 报告导出 | 含英文原文、中英双语、关键事实、技术洞察、产品机会、风险、行动建议；预览为 HTML 阅读模式，下载为 Markdown 文件 |
| Markdown 行动任务导出 | 为什么值得行动 + 可交给 AI 执行的任务草稿 |
| 本地 health_check | `python scripts/health_check.py` |
| GitHub Actions 基础 CI | push / PR 自动检查 |

### 推荐演示流程（5 分钟）

```bash
# 1. 克隆项目
git clone https://github.com/yydshly/ai-frontier-radar.git
cd ai-frontier-radar

# 2. 创建 demo 数据
python scripts/create_demo_data.py

# 3. 启动服务
uvicorn app.main:app --reload --port 8779

# 4. 打开浏览器
# http://127.0.0.1:8779/

# 5. 体验主流程
# - 首页点击"查看演示资料"
# - 点击关联 InsightCard
# - 查看中英双语核心理解
# - 导出完整 Markdown 报告
# - 导出 Markdown 行动任务
```

### 重要命令

```bash
# 本地健康检查（quick）
python scripts/health_check.py

# 本地健康检查（full，含 smoke_test）
python scripts/health_check.py --full

# Demo 主流程验收
python scripts/acceptance_ui_links.py --isolated-db

# 本地 CI 模拟
python scripts/acceptance_ci_local.py --skip-smoke

# Release Candidate 检查
python scripts/acceptance_release_candidate.py --skip-smoke
```

### 已知限制（详见 docs/KNOWN_LIMITATIONS.md）

- 单用户本地使用，无多用户/登录注册
- SQLite 本地数据库，无高并发支持
- 无数据库迁移系统，模型变更后需重建 DB
- 真实网页抓取可能失败（403/结构变化/RSS 空）
- mock 验收只验证链路，真实 LLM 输出需人工判断
- GitHub Actions 只跑基础 CI，不跑真实网络/LLM
- Windows 下 isolated DB 删除有文件锁 warning（不影响 Linux CI）
- SourceItem 编译逻辑仍在路由层，未抽到 service

### 不包含的能力

- 多用户 / 登录注册
- 后台任务 / 批量编译
- 全网爬虫
- 复杂推荐算法
- 真实生产部署
- 向量数据库
- 知识图谱
- SaaS / 浏览器插件 / 移动 App

### 下一阶段方向（V1.0-beta）

- SourceItem 编译 service 化
- 数据库迁移策略
- 真实来源质量策略
- 页面体验打磨
- 更清晰的错误恢复机制
- 可选：GitHub tag / release 流程

### 文档索引

| 文档 | 用途 |
|------|------|
| [README.md](README.md) | 项目概览、快速上手 |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | 发布说明、能力清单 |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | 发布前逐项检查 |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | 已知限制详细说明 |
| [docs/HEALTH_CHECK.md](docs/HEALTH_CHECK.md) | 本地健康检查说明 |
| [docs/CI.md](docs/CI.md) | GitHub Actions CI 说明 |
| [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) | 整体架构 |
| [docs/IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md) | 代码实现原理 |
