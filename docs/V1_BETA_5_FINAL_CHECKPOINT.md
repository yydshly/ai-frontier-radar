# V1.0-beta.5 Final Checkpoint

> 版本：V1.0-beta.5
> 分支：`feature/v1-beta-5-summary-write-policy`
> main 基准 commit：`67fe157`（V1.0-beta.4）
> feature 最新有效 commit：`1457be5`
> checkpoint 创建日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.5 聚焦**摘要写入规范**与**摘要策略集中化**。

V1.0-beta.4 已解决"右侧面板摘要标题语义混乱"的展示问题，V1.0-beta.5 继续解决更底层的问题：谁可以写入哪个字段、失败如何记录、`InsightCard.summary_zh` 是否会反向污染 `SourceItem` 摘要。

---

## 二、已完成内容

### Task 1：摘要写入规范文档

**文档**：`docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md`

包含 16 个章节：
1. 背景问题
2. 当前摘要字段总览
3. **L0 / L1 / L2 / L3 字段权威性等级定义**
   - L0：来源原始摘要（永远不是 AI 中文摘要）
   - L1：中文一句话摘要（`zh_one_liner`）
   - L2：中文详细摘要（`zh_summary`）
   - L3：InsightCard 洞察摘要
4. **生成者 / 写入者 / 消费者矩阵**（覆盖 15 个字段）
5. 写入规则（zh_one_liner / zh_summary / L0 / InsightCard）
6. 覆盖规则（默认不覆盖，显式 force 才覆盖）
7. 失败记录规则
8. 展示读取规则
9. 暂不改数据库 schema 的原因
10. 未来 schema migration 判断条件
11. 验收策略
12. 涉及文件
13. 禁止修改范围
14. **Task 2：summary_policy.py 纯函数模块**
15. **Task 3：CandidateOneLinerService 写入行为验证**
16. **Task 3.1：fill_missing_summary 覆盖漏洞修复**

### Task 2：summary_policy.py 纯函数策略模块

**文件**：`app/application/candidates/summary_policy.py`

纯函数模块，不访问 DB，不调用 LLM。提供：
- `ZH_ONE_LINER_KEY` / `ZH_SUMMARY_KEY` 常量
- `SOURCE_SUMMARY_KEYS`（L0 fallback key 元组）
- `SUMMARY_KIND_*` 常量（5 种 detail_summary_kind）
- `SUMMARY_LABELS`（kind → 标签映射）
- `normalize_summary_text()` — 规范化摘要文本
- `has_cjk()` — CJK 字符检测
- `get_first_source_summary()` — L0 字段查找
- `classify_detail_summary_kind()` — 摘要类型判断
- `get_detail_summary_label()` — 标签映射
- `build_detail_summary()` — 按优先级构建 detail_summary

**消费方**：
- `display.py` — 复用 `build_detail_summary()`
- `today.py` — 复用 `classify_detail_summary_kind()` + `get_detail_summary_label()`

### Task 3：CandidateOneLinerService 写入规则固化

**审计发现**：
- ✅ `force=False` 时跳过已有 zh_one_liner（已有逻辑）
- ❌ 缺少 `force` 参数
- ❌ `_write_result()` 错误写入 `zh_summary`

**修复内容**：
1. 新增 `force: bool = False` 参数到 `should_generate()` / `generate_for_item()` / `generate_for_items()`
2. 移除 `_write_result()` 对 `zh_summary` 的写入（zh_summary 属于独立服务）

### Task 3.1：fill_missing_summary 覆盖漏洞修复

**问题**：`should_generate()` 旧逻辑允许 `fill_missing_summary=True` 在 `force=False` 时绕过已有 zh_one_liner 保护。

**修复**：简化 guard 为 `if not force and has_one_liner: return False`。

`fill_missing_summary` 参数保留以兼容旧调用，但不再旁路 `force=False` 保护。

---

## 三、自动验收结果

### compileall
通过，无语法错误。

### quick_test（[48] + [50]）
```
Results: 820+ passed, 0 failed
```
关键验收项：
- `summary_policy.py` 纯函数验证（无 Session / .query() / llm / commit）
- `display.py` 复用 `build_detail_summary()`
- `today.py` 复用 `classify_detail_summary_kind()` / `get_detail_summary_label()`
- `one_liner.py` 新增 `force` 参数
- `one_liner.py` 移除 `zh_summary` 写入
- `one_liner.py` 包含 `not force and has_one_liner` guard
- `[50]` V1.0-beta.5 final checkpoint 文档存在

### acceptance（[20] + [21]）
```
First usable loop acceptance: 101 passed, 0 failed
```
关键验收项：
- `[20]` summary_policy.py 存在且为纯策略模块
- `[20]` `display.py` 和 `today.py` 复用 `summary_policy`
- `[21]` Case A–E（force=False 跳过 / force=True 覆盖 / 无 zh_one_liner 写入 / 失败记录 / fill_missing_summary 不绕过）
- `[21]` `CountingFakeProvider.call_count == 0` 验证 provider 未被错误调用

### check_due_sources
正常输出，无异常。

### check_stale_fetch_runs
```
No stale running FetchRun detected.
```

---

## 四、涉及文件变更

| 文件 | 变更类型 |
|------|---------|
| `docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md` | 新增 |
| `docs/V1_BETA_5_FINAL_CHECKPOINT.md` | 新增 |
| `app/application/candidates/summary_policy.py` | 新增 |
| `app/application/candidates/display.py` | 重构（委托 build_detail_summary） |
| `app/application/radar/today.py` | 重构（委托 classify_detail_summary_kind） |
| `app/application/candidates/one_liner.py` | 修复（force 参数 + 移除 zh_summary 写入） |
| `scripts/quick_test.py` | 增强（[48] / [50]） |
| `scripts/acceptance_first_usable_loop.py` | 增强（[20] / [21]） |
| `docs/NEXT_EXECUTION_PLAN.md` | 更新 |
| `README.md` | 更新 |

---

## 五、禁止修改范围（已遵守）

```
app/models.py              — 未改
app/db.py                  — 未改
数据库 schema              — 未改
抓取逻辑                   — 未改
app/services/insight_compiler.py  — 未改
真实 LLM 调用逻辑           — 未改
```

---

## 六、已知限制

1. **zh_summary 中文详细摘要服务尚未独立实现**
   - `zh_summary` 当前由 `InsightCard` 编译流程间接写入
   - 尚无独立的 zh_summary 生成服务
   - 写入规范已定义，待后续服务实现

2. **仍未做 schema migration**
   - `zh_one_liner` / `zh_summary` 继续存储在 `raw_metadata_json` JSON 字段中
   - 判断标准见 V1_BETA_5_SUMMARY_WRITE_POLICY.md 第十章

3. **英文检测仍是 CJK 启发式**
   - 通过检测是否含 CJK 字符（`一`–`鿿`）判断是否"纯英文"
   - 未来可考虑引入语言检测库

4. **provider prompt 里可能仍保留 zh_summary 输出语义**
   - LLM 系统提示中仍要求输出 `zh_summary` 字段
   - 但 `CandidateOneLinerService` 不再写入该字段
   - 后续由独立 zh_summary 服务接管

---

## 七、merge-ready 判断

**可合并（merge-ready）**。

理由：
1. 所有自动化测试通过，无失败用例
2. 无数据库 schema 变更
3. 无抓取逻辑变更
4. 无 LLM 调用逻辑变更
5. 核心规范已通过 acceptance 隔离测试验证
6. display.py 和 today.py 的重构保持了向后兼容（委托到纯函数，行为完全一致）

---

## 八、下一阶段建议

**V1.0-beta.6 建议转向正文提取质量治理**：

| 方向 | 说明 |
|------|------|
| 正文提取成功率 | 当前探测成功率统计 |
| 正文质量评分 | 基于长度、结构、完整性打分 |
| PDF / HTML 解析失败分类 | 区分 404 / 认证 / 解析错误等 |
| Prompt injection 防护 | 来源内容中指令注入的识别与过滤 |
| 过长正文截断策略 | 超长文章的分块与截断策略 |

---

## 九、相关文档

- [V1_BETA_5_SUMMARY_WRITE_POLICY.md](V1_BETA_5_SUMMARY_WRITE_POLICY.md) — 摘要写入规范定义
- [V1_BETA_4_SUMMARY_SEMANTICS_PLAN.md](V1_BETA_4_SUMMARY_SEMANTICS_PLAN.md) — V1.0-beta.4 展示层规范
- [NEXT_EXECUTION_PLAN.md](NEXT_EXECUTION_PLAN.md) — 下一阶段执行计划
