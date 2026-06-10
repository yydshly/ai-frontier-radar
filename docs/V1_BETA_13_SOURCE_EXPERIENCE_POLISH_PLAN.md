# V1.0-beta.13 Plan — 信息来源页与来源工作台体验修复

> 版本：V1.0-beta.13
> 分支：`feature/v1-beta-13-source-experience-polish`
> main 基准 commit：`f2562dd`（v1.0-beta.12 merge）
> 规划日期：2026-06-11

---

## 一、阶段定位

beta12 已打通"摘要 → InsightCard"完整链路。

但信息来源入口页存在明显体验问题：

- 来源卡片策略标签重复（rss/rss、html_index/html_index）
- 来源卡片按钮堆砌，主次不清
- 来源工作台缺少可读失败原因
- 侧边栏"精选来源"列表过长

本轮目标：**让信息来源入口看得懂、点得明白、失败能解释**。

---

## 二、为什么信息来源页需要产品化

用户打开信息来源页时，面对的是：

```
来源名称
分类标签
策略标签（重复）
状态
按钮（5个）
技术详情
```

问题：
1. **策略标签重复**：fetch_strategy 和 source_type 同时显示，造成"rss/rss"的视觉困惑
2. **按钮主次不清**：工作台/运行记录/候选池/原始资料/运行探测全部平铺，用户不知道点哪个
3. **失败原因不清晰**：只显示"失败"二字，用户不知道为什么失败
4. **侧边栏太长**：15个来源全部铺开，挤压主导航空间

---

## 三、来源卡片标签去重规则

### 问题
同时显示 `source_type`（如 rss）和 `fetch_strategy`（如 rss），造成重复感。

### 解决
只显示一个标签：`effective_strategy_label`

生成规则：

```python
effective_strategy = "rss" if feed_url else fetch_strategy
effective_label = describe_fetch_strategy(effective_strategy)
```

结果：

| 来源 | 旧显示 | 新显示 |
|------|--------|--------|
| OpenAI (有 RSS) | company · rss · rss | company · RSS 订阅（结构化、低成本） |
| Anthropic (无 RSS) | company · html_index · html_index | company · 网页索引解析 |
| arXiv (有 RSS) | paper · rss · rss | paper · RSS 订阅（结构化、低成本） |

---

## 四、来源卡片按钮主次规则

### 问题
5个按钮全部平铺，主次不清。

### 解决
主按钮（视觉突出）：

```
进入工作台
运行探测
```

次级入口（折叠在"技术详情"中）：

```
运行记录
候选池
原始资料
配置详情
```

---

## 五、失败状态可读化

### 问题
显示"失败"但用户不知道为什么。

### 解决
`_humanize_fetch_error()` 将原始错误映射为中文描述：

| 关键词 | 显示 |
|--------|------|
| timeout | 请求超时：{原始错误} |
| 404 | 页面不存在（404）：{原始错误} |
| 403 | 页面拒绝访问（403）：{原始错误} |
| no candidates | 未发现任何候选链接：{原始错误} |
| parse | 页面结构解析失败：{原始错误} |
| ... | ... |

---

## 六、来源工作台优化

### 当前问题
缺少清晰的"下一步做什么"指导。

### 优化后结构

```
1. 来源概览（名称、分类、官网、Feed）
2. 探测策略（推荐方式 vs 实际方式）
3. 探测状态（成功/部分失败/失败/0新增）
4. 最近探测（带可读错误）
5. 最近发现内容（20条）
6. 操作入口（运行探测/查看候选/打开官网）
7. 技术详情（折叠）
```

---

## 七、侧边栏精选来源收缩规则

### 问题
15个来源全部铺开，挤压主导航。

### 解决
默认显示5个：

```
精选来源
- OpenAI
- Anthropic
- DeepMind
- Hugging Face
- arXiv AI
全部来源 →
```

---

## 八、当前不做 ViewModel 的原因

beta13 只做模板和路由层面的调整，不做 ViewModel 重构。原因：

1. **ViewModel 重构是较大改动**：涉及数据封装、测试、模板改造
2. **现有改动已能解决核心问题**：去重+简化按钮+可读错误已能大幅改善体验
3. **ViewModel 可作为后续优化**：在 beta13 稳定后再做

---

## 九、禁止事项

- 不做 ViewModel 重构
- 不改 DB schema
- 不新增 migration
- 不做 TTS
- 不做 PDF
- 不新增来源抓取算法
- 不删除 beta9/beta10/beta11/beta12 能力
