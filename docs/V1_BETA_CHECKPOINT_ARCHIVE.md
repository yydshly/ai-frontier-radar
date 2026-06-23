# V1.0-beta First Usable Loop Checkpoint Archive

## 1. 阶段结论

当前版本是 AI Frontier Radar 的**第一可用闭环 checkpoint**。

它已经验证以下完整链路可行：

```
来源配置
  → RSS / HTML index 探测
  → SourceItem 候选池
  → 中文摘要
  → 今日雷达阅读
  → InsightCard
  → 个人判断
  → Markdown / 报告导出
```

当前版本可以作为个人 AI 前沿信息工作台使用，但不是正式 SaaS、不是多用户系统、不是完整商业产品。

## 2. 已验证价值

- 证明官方 AI 前沿来源具有持续追踪价值
- 证明 RSS-first + HTML-index fallback 可以支撑最小信息获取链路
- 证明 SourceItem → 中文摘要 → InsightCard 的产品形态成立
- 证明中文洞察卡比普通翻译更有价值
- 证明结合个人关注方向生成行动建议是核心差异点
- 证明每日雷达 / 工作台形态值得继续探索

## 3. 当前可用能力

- 来源配置加载
- Source 同步到 DB
- RSS 探测
- HTML index 探测
- FetchRun 记录
- SourceItem 列表与详情
- 今日雷达页面
- 中文一句话摘要
- 中文详细摘要
- InsightCard 生成
- InsightCard 详情页
- 个人判断
- Markdown 行动任务导出
- 完整报告导出
- Daily cycle 脚本
- Docker 基础打包

## 4. 当前非目标

当前不做：

- 多用户
- 登录注册
- 付费系统
- 全网爬虫
- Twitter/X 抓取
- 复杂推荐算法
- 企业权限
- 完整知识图谱
- 复杂 Multi-Agent
- 正式任务队列
- 正式商业化部署

## 5. 已知限制

- 当前架构是探索式演进，不是最终长期架构
- 路由、服务、脚本、状态字段存在一定历史堆叠
- `raw_metadata_json` 承担了过多状态
- SourceItem 生命周期还不是严格状态机
- 同步抓取与后台抓取仍有部分重复逻辑
- HTML index fallback 不如 RSS 稳定
- Daily cycle 依赖外部 scheduler
- 当前系统适合个人使用和产品验证，不适合直接扩展成复杂 SaaS

## 6. 当前版本定位

```
V1 = 技术探针成功后的可用样机
V2 = 基于 V1 经验重新设计的可靠产品架构
```

## 7. 封版建议

建议将当前状态打为 tag：

```
v1.0-beta-checkpoint
```

封版后，主链路不再继续堆功能。后续优化和 V2 设计全部走独立分支。

## 8. 关联文档

- [docs/V2_ARCHITECTURE_PROPOSAL.md](docs/V2_ARCHITECTURE_PROPOSAL.md) — V2 重新设计方向
- [docs/V2_MIGRATION_ROADMAP.md](docs/V2_MIGRATION_ROADMAP.md) — V1 到 V2 迁移路线图
- [docs/V1_BETA_FIRST_USABLE_LOOP_STATUS.md](docs/V1_BETA_FIRST_USABLE_LOOP_STATUS.md) — 阶段详细状态说明
- [docs/V1_BETA_CHECKPOINT.md](docs/V1_BETA_CHECKPOINT.md) — 早期 checkpoint 记录
