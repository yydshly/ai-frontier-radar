# 本地项目健康检查

## 目标

一条命令检查项目是否处于可运行状态。

## 命令

```bash
# 快速检查（默认）
python scripts/health_check.py

# 等价于 --quick
python scripts/health_check.py --quick

# 完整本地检查（包含 smoke_test 和 acceptance）
python scripts/health_check.py --full

# 跳过 smoke_test（配合 --full 使用）
python scripts/health_check.py --full --skip-smoke

# 保留 health check 使用的 isolated DB
python scripts/health_check.py --keep-db
```

## 检查内容

| 模式 | 检查项 |
|------|--------|
| `--quick` (默认) | Python 版本、依赖、目录、sources 配置、isolated DB 初始化、关键表、demo 数据、关键页面 |
| `--full` | 以上全部 + smoke_test + acceptance_demo_data + acceptance_demo_flow |
| `--full --skip-smoke` | quick 全部 + acceptance_demo_data + acceptance_demo_flow（跳过 smoke_test） |

### `--quick` 检查项

1. **Python 版本** — Python >= 3.10
2. **依赖** — fastapi, sqlalchemy, jinja2, httpx, pydantic, yaml, bs4, feedparser
3. **目录** — app/, scripts/, docs/, config/, data/
4. **配置文件** — sources.example.yaml 存在性 + check_sources_config.py 验证
5. **数据库** — isolated DB 初始化 + 6 张关键表存在性
6. **Demo 数据** — Source, SourceItem, InsightCard, BilingualReport, CardDecision
7. **关键页面** — `/`, `/source-items`, `/source-items/{id}`, `/cards`, `/cards/{id}`, `/cards/{id}/export-report`, `/cards/{id}/export-markdown`

> **注意**：`--quick` 模式不运行 smoke_test，也不运行 acceptance 脚本，速度更快，适合日常开发检查。

### `--full` 额外检查项

8. **smoke_test** — `python scripts/smoke_test.py`
9. **acceptance_demo_data** — `python scripts/acceptance_demo_data.py --isolated-db`
10. **acceptance_demo_flow** — `python scripts/acceptance_demo_flow.py --isolated-db`

> **注意**：`--full` 默认运行 smoke_test，如需跳过可加 `--skip-smoke`。`--full --skip-smoke` 等价于 quick + acceptance_demo_data + acceptance_demo_flow。

## 隔离说明

- 默认使用独立的 isolated DB：`data/health_check_<timestamp>.db`
- 不污染真实数据库
- 不访问真实网络
- 不调用真实 LLM
- `--keep-db` 可保留 isolated DB 供排查使用

## 结果说明

| 结果 | 含义 | 退出码 |
|------|------|--------|
| `PASS` | 所有检查通过 | 0 |
| `PASS_WITH_WARNINGS` | 有警告但无失败 | 0 |
| `FAIL` | 至少一项检查失败 | 1 |

## 输出示例

```
============================================================
AI Frontier Radar - Health Check
============================================================

[SECTION] Python
[PASS] Python version: 3.12.8

[SECTION] Dependencies
[PASS] fastapi
[PASS] sqlalchemy
[FAIL] feedparser missing
       fix: pip install -r requirements.txt

[SECTION] Config
[PASS] sources config validation

[SECTION] Database
[PASS] init_db()
[PASS] table sources
...

============================================================
RESULT: FAIL
============================================================

Failures:
  - feedparser missing
```

## 常见失败

| 失败项 | 原因 | 修复方式 |
|--------|------|----------|
| `feedparser missing` | 未安装 feedparser | `pip install -r requirements.txt` |
| `config/sources.example.yaml missing` | 配置文件缺失 | 从版本管理恢复 |
| `database initialization failed` | DB 路径无写权限 | 检查 data/ 目录权限 |
| `demo data creation failed` | 已有脏数据或 DB 损坏 | 使用 `--keep-db` 排查 |
| 页面返回 500 | 代码错误或 import 失败 | 查看堆栈信息 |
| `smoke_test failed` | 基础链路有破坏 | `git status` 检查变更 |

## 和 CI 的关系

`health_check.py` 是本地轻量 CI；未来可以把其中无外部依赖的部分迁移到 GitHub Actions。

GitHub Actions 基础 CI（V1.0-alpha.4 规划）：

```bash
python -m compileall app scripts
python scripts/check_sources_config.py
python scripts/smoke_test.py
python scripts/acceptance_demo_data.py --isolated-db
python scripts/acceptance_demo_flow.py --isolated-db
python scripts/health_check.py
```
