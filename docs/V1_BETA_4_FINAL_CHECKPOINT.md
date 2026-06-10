# V1.0-beta.4 Final Checkpoint

> 版本：V1.0-beta.4
> 分支：`feature/v1-beta-4-summary-semantics`
> 基准 commit：`393c2c0`（V1.0-beta.3 merge commit）
> 最新 feature commit：`73661dc`
> 完成日期：2026-06-10

---

## 一、阶段定位

摘要语义统一——解决"中间卡片显示'待生成中文摘要'，右侧面板却显示英文 metadata 摘要"的用户感知混乱。

---

## 二、已完成能力

### Task 1：语义审计与展示规则设计

- [x] 梳理 `zh_one_liner` 字段语义：LLM 生成的中文一句话摘要
- [x] 梳理 `zh_summary` 字段语义：LLM 生成的中文详细摘要
- [x] 梳理 source metadata / RSS summary：外部来源提供，不保证中文，非 LLM 生成
- [x] 梳理 InsightCard summary：结构化中文洞察内容，与 metadata 摘要完全独立
- [x] 定义四类展示标签：`中文摘要` / `中文概述` / `来源摘要` / `英文来源摘要`
- [x] `RadarPanelState` 增加 `detail_summary_label` 和 `detail_summary_kind` 字段
- [x] 右侧面板 detail_summary 区块标题由硬编码"中文摘要"改为动态标签

### Task 2：确定性验收

- [x] 新增 `[19]` section，使用 isolated 测试数据验证四个面板标签
- [x] Case A (`zh_summary`): 面板标题 = `中文摘要`
- [x] Case B (`zh_one_liner` only): 面板标题 = `中文概述`
- [x] Case C (中文 metadata fallback): 面板标题 = `来源摘要`
- [x] Case D (英文 metadata fallback): 面板标题 = `英文来源摘要`
- [x] 所有 case 通过 `/radar/today/panel` fragment 验收
- [x] 测试数据使用 `test_v1_beta_4_summary_*` 前缀，验收后立即清理

---

## 三、展示规则

| 实际内容来源 | 面板标题 | 说明 |
|-------------|---------|------|
| `zh_summary` 存在 | `中文摘要` | AI 生成，内容可信 |
| `zh_summary` 不存在，但 `zh_one_liner` 存在 | `中文概述` | AI 生成的一句话说明 |
| 中文 source metadata 存在 | `来源摘要` | 来自源站 metadata |
| 英文 source metadata 存在 | `英文来源摘要` | 帮助用户识别内容语言 |

---

## 四、自动验收结果

| 测试项 | 结果 |
|--------|------|
| `python -m compileall app scripts` | 通过 |
| `python scripts/quick_test.py` | 755 passed, 0 failed |
| `python scripts/acceptance_first_usable_loop.py` | 67 passed, 0 failed |
| `python -m scripts.acceptance_first_usable_loop` | 67 passed, 0 failed |
| `python scripts/check_due_sources.py` | due=0, skipped=15 |
| `python scripts/check_stale_fetch_runs.py` | stale_count=0 |

---

## 五、已知限制

1. **英文检测是启发式 CJK 检测**：使用 `一<=ch<='鿿'` 范围判断，不使用 NLP 语言检测库。如果 metadata 摘要同时包含中英文，检测可能不准确。
2. **未改数据库 schema**：`zh_one_liner` 和 `zh_summary` 仍存储在 `raw_metadata_json` JSON 字段中，未提升为 SourceItem 一级字段。
3. **未统一存储字段，只统一展示语义**：展示层已统一，但生成链路和存储结构尚未规范化。

---

## 六、merge-ready 判断

**可合并。**

理由：
- 所有验收测试通过
- 展示层修改仅限于 `RadarPanelState` 新增字段（向后兼容，默认值 `内容摘要`）
- 面板模板不再硬编码"中文摘要"，用户感知改善明确
- 文档齐全：语义审计文档 + checkpoint + README 入口

---

## 七、下一阶段建议

**V1.0-beta.5 聚焦"摘要生成链路与字段写入规范"：**

1. 决定是否把 `zh_summary` 提升为 SourceItem 一级字段（独立列 vs JSON 字段）
2. 统一 `zh_one_liner` / `zh_summary` 的写入时机和优先级
3. 如果需要 schema migration，评估从 `v1.0-beta.5` 开始引入 migration 脚本
4. 可选：引入语言检测库替代启发式 CJK 检测

---

## 八、涉及文件

| 文件 | 修改类型 |
|------|---------|
| `app/application/radar/today.py` | 新增 `detail_summary_label` / `detail_summary_kind` 字段 |
| `app/templates/partials/radar_today_panel.html` | 面板标题改为动态 `detail_summary_label` |
| `scripts/quick_test.py` | 新增 [46] 静态验收 + [47] checkpoint 验收 |
| `scripts/acceptance_first_usable_loop.py` | 新增 [19] 四类标签确定性验收 |
| `docs/V1_BETA_4_SUMMARY_SEMANTICS_PLAN.md` | 新增：语义审计文档 |
| `docs/V1_BETA_4_FINAL_CHECKPOINT.md` | 新增：本文件 |
| `README.md` | 更新：V1.0-beta.4 入口 |
