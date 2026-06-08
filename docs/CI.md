# GitHub Actions 基础 CI

## 目标

每次 push / PR 自动检查项目基础链路是否正常。

## 触发条件

- push 到 `main`
- push 到 `feature/**`
- PR 到 `main`

## CI 会运行什么

```bash
python -m compileall app scripts
python scripts/check_sources_config.py
python scripts/smoke_test.py
python scripts/acceptance_demo_data.py --isolated-db
python scripts/acceptance_demo_flow.py --isolated-db
python scripts/health_check.py
```

## CI 不会运行什么

- 真实网络探测
- 真实 LLM
- 需要 API Key 的验收
- 大规模抓取
- 后台任务

## 为什么不跑真实网络和真实 LLM

- 网络不稳定
- LLM 有成本
- API Key 不应该暴露在基础 CI
- MVP 阶段优先保证本地链路稳定

## 本地等价命令

```bash
python -m compileall app scripts
python scripts/check_sources_config.py
python scripts/smoke_test.py
python scripts/acceptance_demo_data.py --isolated-db
python scripts/acceptance_demo_flow.py --isolated-db
python scripts/health_check.py
```

或使用本地 CI 模拟脚本：

```bash
python scripts/acceptance_ci_local.py
```

## 常见失败

| 失败项 | 原因 | 修复方式 |
|--------|------|----------|
| `compileall` 失败 | 语法错误或 import 失败 | 检查 syntax/import |
| `check_sources_config` 失败 | sources.example.yaml 损坏 | git checkout config/sources.example.yaml |
| `smoke_test` 失败 | 基础链路被破坏 | git status 检查变更 |
| `acceptance_demo_data` 失败 | DB 模型或 demo 脚本被破坏 | 检查 scripts/create_demo_data.py |
| `acceptance_demo_flow` 失败 | 页面模板或路由被破坏 | 检查 app/main.py 和 templates |
| `health_check` 失败 | 环境或依赖问题 | 检查 Python 版本和依赖安装 |

## CI 配置

- Python 版本：3.12
- 运行系统：ubuntu-latest
- 超时：10 分钟
- 无需 API Key
- 无需 secrets 配置
