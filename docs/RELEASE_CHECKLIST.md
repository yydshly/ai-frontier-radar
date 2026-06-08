# V1.0-alpha Release Checklist

## 目标

在合并 main 或打 `v1.0-alpha` tag 前，逐项确认项目处于可演示、可回滚、可继续开发状态。

## 1. 分支与提交

- [ ] 当前 release candidate 分支已 push 到 origin
- [ ] 最新 commit hash 已记录在 RELEASE_NOTES.md
- [ ] `git status --short` 干净
- [ ] 不包含 `data/*.db`
- [ ] 不包含 `.env`
- [ ] 不包含 `__pycache__/`
- [ ] 不包含下载的 `.md` 文件

## 2. 基础检查

- [ ] `python -m compileall app scripts` 通过
- [ ] `python scripts/check_sources_config.py` 通过

## 3. Smoke Test

- [ ] `python scripts/smoke_test.py` 通过

## 4. 本地健康检查

- [ ] `python scripts/health_check.py` 通过（PASS 或 PASS_WITH_WARNINGS）
- [ ] `python scripts/health_check.py --full --skip-smoke` 通过

## 5. Demo 主流程

- [ ] `python scripts/create_demo_data.py --reset-demo` 成功
- [ ] `python scripts/create_demo_data.py` 幂等（跳过已有数据）
- [ ] `python scripts/acceptance_ui_links.py --isolated-db` 通过

## 6. 本地 CI 模拟

- [ ] `python scripts/acceptance_ci_local.py --skip-smoke` 通过
- [ ] 可选：`python scripts/acceptance_ci_local.py` 完整版通过

## 7. Release Candidate 检查

- [ ] `python scripts/acceptance_release_candidate.py --skip-smoke` 通过

## 8. 浏览器手动验收

- [ ] 启动 `uvicorn app.main:app --reload --port 8779`
- [ ] 打开 `/` — 演示数据入口可见
- [ ] 打开 `/source-items/{id}` — 状态 compiled，无 500
- [ ] 打开 `/cards/{id}` — 中英双语核心理解可见
- [ ] 打开 `/cards/{id}/export-report` — 完整报告预览正常
- [ ] 下载完整报告，文件名确认 `insightcard-{id}-report.md`
- [ ] 打开 `/cards/{id}/export-markdown` — 行动任务预览正常

## 9. GitHub Actions

- [ ] CI workflow 可见于 https://github.com/yydshly/ai-frontier-radar/actions
- [ ] 当前 release candidate commit 有 CI run
- [ ] CI run 状态为 success
- [ ] 如果未触发，已记录原因（仓库 Actions 未启用 / 首次 push 需人工确认等）

## 10. 文档完整性

- [ ] README.md Quickstart 部分可读
- [ ] RELEASE_NOTES.md 已更新（能力清单、演示流程、重要命令）
- [ ] docs/KNOWN_LIMITATIONS.md 已更新
- [ ] docs/HEALTH_CHECK.md quick/full 说明准确
- [ ] docs/CI.md CI 步骤准确
- [ ] docs/V1.0_ALPHA_4_3_REAL_BROWSER_AND_CI_ACCEPTANCE.md 已更新

## 11. 代码质量

- [ ] 无明显的 `TODO` 或 `FIXME` 阻塞发布
- [ ] 无硬编码的测试 API key
- [ ] 无敏感信息在代码中明文存储

## 12. Tag / Release 前确认

- [ ] 确认是否合并 main
- [ ] 确认 tag 名称：`v1.0-alpha`
- [ ] 确认 release notes 可作为 GitHub Release 描述
- [ ] 确认不包含敏感信息（API key、真实数据库路径等）

## 通过标准

所有 `[ ]` 项均已勾选后，可进入下一阶段：

```
V1.0-alpha.6：main 合并与 tag 准备
```
