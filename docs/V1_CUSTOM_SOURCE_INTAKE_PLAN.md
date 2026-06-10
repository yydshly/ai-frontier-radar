# 自定义来源接入设计（P-004 / Phase F）

目标：让个人用户可以先在 `/sources` 预览自定义 RSS / HTML index / 单篇 URL / PDF 等来源是否可接入。本阶段只做校验和 dry-run 预览，不写库，不触发抓取，不调用 LLM。

## F-1 / F-1.1 范围

- 只做 validation + dry-run preview。
- 不 add Source，不 commit DB，不改数据库 schema。
- 不触发抓取，不调用 LLM。
- 不进入 `/radar/today/update` 的 due-source 调度。
- preview 中所有 custom source 都不承诺自动调度，`enters_scheduling_now=false`。

## 共存模型

现有正式来源由 `config/sources.yaml` 定义，并通过 `sync_sources_config_to_db` 同步到 DB。自定义来源后续如果写入 DB，应使用 `tags_json` 中的 `user-source` 标记区分来源出处，不新增表或字段。

F-1.1 的去重同时检查：

- DB `Source.source_key`
- config sources 的 `source_key`
- DB `feed_url` / `homepage_url`
- config sources 的 `feed_url` / `homepage_url`

个人自用阶段，重复 URL 默认作为 error，避免同一来源重复抓取造成今日雷达重复内容。特殊允许重复的场景以后再设计，不在 F-1.1 实现开关。

## URL 安全校验

F-1.1 只做静态 URL 安全校验，不做 DNS 解析，不做网络 probe。

只允许公网 `http` / `https` URL。静态拒绝：

- `localhost`
- `127.0.0.1`
- `0.0.0.0`
- `::1`
- 内网 IPv4：`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`
- link-local：`169.254.0.0/16`
- metadata service：`169.254.169.254`
- IPv6 loopback / private / link-local
- `.local` host
- `file://`、`ftp://`、`data:`、`javascript:`
- 空 host

## 策略边界

支持策略：

- `rss`：必须有 `feed_url`
- `html_index`：必须有 `homepage_url`

预留策略：

- `single_url`：必须有 `homepage_url` 或 `feed_url`，更适合进入“手动内容导入”，不一定是长期 Source。
- `json_feed`：必须有 `feed_url` 或 `homepage_url`
- `sitemap`：必须有 `feed_url` 或 `homepage_url`
- `api`：必须有 `homepage_url`

受限策略：

- `pdf`：暂不建议作为长期 Source 写入。
- `crawler` / `change_detect` / `newsletter`：默认拒绝，除非显式设置 `CUSTOM_SOURCE_ALLOW_RESTRICTED=true`。

## F-2 调度接入方案选择

F-2 前必须先选择以下方案之一。

方案 A：写入 `config/sources.yaml`

- 优点：复用现有 `compute_due_sources`，无需改调度。
- 缺点：需要安全写 YAML、处理用户配置和示例配置边界。

方案 B：扩展 `compute_due_sources` 读取 DB user-source

- 优点：自定义来源真正本地化，不污染 YAML。
- 缺点：需要严格过滤 `tags_json` 含 `user-source`、`enabled=True`、`fetch_strategy in rss/html_index`，避免测试/历史脏数据进入调度。

F-1.1 不实现方案 A 或 B，不写库，不进入调度。F-2 前必须先选择 A 或 B。

## 验收

- `/sources` 显示“添加自定义来源（预览）”表单。
- POST preview 只返回校验结果和 would-create 信息，不写数据库。
- 合法 `rss` / `html_index` 可通过校验，但 `enters_scheduling_now=false`。
- `localhost`、内网、metadata IP、非 http(s) URL 被拒绝。
- 与 config 或 DB 重复的 key / URL 被拒绝。
