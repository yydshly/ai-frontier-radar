# 输入分类与总结策略

**Date:** 2026-06-08
**Version:** V1.0-alpha.8.2

---

## 背景

AI Frontier Radar 的核心目标是：**把全球英文 AI 前沿资料，转成中文洞察、个人判断和可执行任务。**

但并非所有 URL 都适合直接生成 InsightCard。列表页、分页页、标签页等会产生无意义的总结。

---

## 核心原则

> **AI Frontier Radar 不把所有 URL 都视为可总结对象。**

系统对输入 URL 做分类判断，不同类型走不同策略。

---

## URL 类型分类

| 类型 | 说明 | 示例 | 策略 |
|------|------|------|------|
| `article` | 单篇文章或内容页 | `/blog/sima-2-agent/`, `/news/2024/06/…` | ✅ 可直接编译 |
| `pdf` | PDF 文档 | `https://example.com/report.pdf` | ✅ 可直接编译 |
| `listing` | 列表页 / 索引页 | `/blog/`, `/news/`, `/research/` | ❌ 仅用于发现候选文章 |
| `pagination` | 分页页 | `/blog/page/3/`, `?page=2` | ❌ 仅用于发现候选文章 |
| `tag_or_category` | 标签 / 分类 / 搜索页 | `/tag/agents`, `?category=ai` | ❌ 仅用于发现候选文章 |
| `feed` | RSS / Atom Feed | `/feed.xml`, `/rss` | ❌ 仅用于发现候选文章 |
| `homepage` | 公司/博客首页 | `deepmind.google/blog/` | ❌ 仅用于发现候选文章 |
| `unknown` | 无法判断的 URL | 其他未匹配 URL | ⚠️ 按 article 处理，不确定时走编译路径 |

---

## 哪些可以直接生成 InsightCard

以下类型的 URL 可以直接进入 LLM 总结流程：

1. **单篇文章 URL** — 路径结构看起来是具体内容页（如 `/blog/sima-2-agent/`）
2. **PDF 文件** — 以 `.pdf` 结尾的 URL

---

## 哪些只能用于发现候选文章

以下类型的 URL **不应**直接编译为 InsightCard，而是用于发现具体文章 URL：

- 列表页（`/blog/`, `/news/`）
- 分页页（`/blog/page/3/`, `?page=2`）
- 标签页（`/tag/agents`）
- 分类页（`/category/research`）
- 搜索页（`?q=agent`）
- RSS/Atom Feed（`/feed.xml`）

---

## 为什么列表页不能直接总结

以 Google DeepMind Blog 分页页为例：

```
https://deepmind.google/blog/page/3/
```

这个 URL 的内容是"第 3 页的文章列表"，不是一篇文章。如果直接调用 LLM 总结，会得到类似"这里有 10 篇文章的标题列表..."这样的无意义输出。

**正确做法：** 从这个页面提取所有文章链接，存入 SourceItem 收件箱，再逐个选择单篇编译。

---

## 首次历史整理策略（V1.0-alpha）

V1.0-alpha 允许在首次接入来源时做有限历史整理：

1. 从来源的列表页/feed 发现尽可能多的历史候选 URL
2. 对每个候选 URL 执行 `classify_url_by_pattern`
3. 分类为 `article` 的存入 SourceItem 收件箱
4. 用户从收件箱选择要编译的条目

---

## 后续增量关注策略（V1.0-beta）

> V1.0-alpha 只做最小识别和阻止；V1.0-beta 再做完整时间游标和自动增量扫描。

V1.0-beta 计划改进：

- 基于 `last_seen_at` 时间游标，只处理新增候选文章
- 过滤掉已经处理过的 article URL
- 定期自动探测来源增量
- 根据用户决策方向（`worth_attention` / `related_to_me`）推荐相关新文章

---

## 实现说明

模块位置：`app/intake/`

| 文件 | 说明 |
|------|------|
| `models.py` | `PageType`、`RecommendedStrategy`、`IntakeDecision` 数据类 |
| `url_classifier.py` | 基于 URL 结构的规则分类器（`classify_url_by_pattern`）|

**判断优先级：**

```
URL pattern → content-type → extracted text structure → fallback unknown
```

V1.0-alpha 只用 URL pattern 做规则判断，不调用 LLM，不发 HTTP 请求。

---

## 编译入口拦截点

| 入口 | 拦截逻辑 |
|------|---------|
| `POST /compile`（手动 URL） | 调用 `classify_url_by_pattern`，blocked 时创建 failed card |
| `POST /source-items/{id}/compile` | 同上，blocked 时标记 SourceItem 为 failed |

拦截后的错误信息格式：`[intake:blocked] <reason>`

---

## V1.0-alpha 限制

- URL 分类完全基于规则，无法处理特殊情况
- 不检查 content-type header（需要在 HTTP 请求后才能知道）
- 不检查页面实际内容结构
- 不支持用户自定义规则
- `unknown` 类型默认允许编译，可能漏过部分列表页
