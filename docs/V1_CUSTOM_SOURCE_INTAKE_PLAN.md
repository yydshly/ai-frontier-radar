# 自定义来源接入设计（P-004 / Phase F）

> 设计先行文档。目标：让用户自定义接入 RSS / HTML index / 单篇 URL / PDF，但
> **抓取策略受白名单约束**。本阶段（F-1）只做**校验 + dry-run 预览（只读，不写库）**；
> 实际写库与 UI 表单留到 F-2，且写入也走显式 gate。

## 1. 现状与关键约束

- 来源目前仅由 `config/sources.yaml` 定义，经 `sync_sources_config_to_db` 同步进 DB。
- **关键发现**：`sync_sources_config_to_db` 只 **create/update** 配置中存在的
  source_key，**从不删除/禁用** DB 中配置外的行。
  ⇒ 用户自定义来源（key 不在 YAML）写入 DB 后，**不会被后续 config 同步清除**。
- 不能新增数据库表 / 字段（纪律）。⇒ 用 `tags_json` 里的标记区分来源出身。

## 2. 共存模型

| 来源出身 | 判定 | 同步影响 |
|----------|------|----------|
| 配置来源 | source_key ∈ config | 受 YAML 同步 create/update |
| 自定义来源 | source_key ∉ config，且 tags 含 `user-source` | **不受同步影响**（DB-only） |

自定义来源写入时：`enabled=True`，`tags_json` 追加标记 `user-source`，
source_key 必须与现有 config / DB key **不冲突**。

## 3. 策略白名单（复用 P-001 能力矩阵）

| 层级 | 策略 | 自定义接入许可 |
|------|------|----------------|
| 轻量/中量（已支持） | `rss` / `html_index` | ✅ 普通用户可选 |
| 中量（预留） | `single_url` / `json_feed` / `sitemap` / `api` | 🔜 预留：允许登记，但 probe 未实现前不进自动调度 |
| 重量/外部 | `crawler` / `change_detect` / `pdf` / `newsletter` | ⛔ 需显式开启（`CUSTOM_SOURCE_ALLOW_RESTRICTED=true`），默认拒绝 |

未知策略一律拒绝。

## 4. F-1 校验 + dry-run 预览（本阶段，只读）

输入草稿 `CustomSourceDraft`：

```
name / homepage_url / feed_url / fetch_strategy / category / relevance_hint /
fetch_interval_hours / source_key(可选，自动从 name/url 派生)
```

`validate_custom_source_draft(db, draft)` → `CustomSourceValidation`（只读）：

1. 必填校验：name、fetch_strategy；rss 需 feed_url，html_index 需 homepage_url。
2. URL 安全：feed_url / homepage_url 必须 http/https，禁止其它 scheme。
3. 策略白名单：按上表分级；受限策略未显式开启则报错。
4. source_key 规范化：缺省时从 name/域名派生 slug（小写、连字符、ASCII 安全）。
5. 去重：规范化 key、feed_url、homepage_url 不得与现有 config / DB 来源冲突。
6. 返回 `ok / errors[] / warnings[] / normalized_key / normalized_draft`。

`preview_custom_source(db, draft)` → 干跑计划（不写库）：返回"将要创建的来源"
摘要（key、获取方式中文文案、策略层级、是否进自动调度），**绝不 add/commit**。

## 5. F-2（后续）写库 + UI（不在本阶段）

- `add_custom_source(db, draft, *, apply=False)`：dry-run 默认；`apply=True` 才写库，
  写前重新校验，写入 `user-source` 标记，commit。
- UI：`/sources` 增加"添加来源"入口（POST 表单 + 预览），小调整不重做布局。
- 隔离验收脚本（仿 `acceptance_run_due_sources_once_apply.py`）在 isolated DB 验证真实写入。

## 6. 边界

- F-1 **只读**：不 add / 不 commit / 不触发抓取 / 不调用 LLM。
- 不新增表 / 不改 schema / 不改 db_sync / 不改 due-source / 不改抓取流程。
- 重量策略默认拒绝；预留策略允许登记但不进自动调度（due-source 仍判 unsupported）。

## 7. 验收（F-1）

- 合法 rss/html_index 草稿 → validation ok，preview 给出将创建摘要，DB 行数不变。
- 缺 feed_url 的 rss、错误 scheme、未知/受限策略、重复 key → validation 报错。
- quick_test 静态 + 只读功能断言；不写库、不调用 LLM。

参考：[V1_OPTIMIZATION_ROADMAP.md](V1_OPTIMIZATION_ROADMAP.md)、
[V1_SOURCE_INGESTION_STRATEGY.md](V1_SOURCE_INGESTION_STRATEGY.md)
