# V1 to V2 Migration Roadmap

## 1. 迁移原则

V1 不废弃，V2 不盲目重写。

迁移原则：

```
先冻结 V1
再设计 V2
再重建核心 pipeline
最后迁移 V1 中验证有效的体验和能力
```

## 2. V1 需要保留的资产

- 来源配置
- Source / SourceItem / FetchRun 经验
- RSS-first 策略
- HTML index fallback 经验
- InsightCard 字段设计
- 今日雷达交互经验
- Markdown 导出
- Daily Report 探索
- 音频 / 视频探索
- Docker / scheduler 经验
- 验收脚本经验
- 项目文档

## 3. V1 不建议继续扩展的部分

- 继续堆 raw_metadata_json 状态
- 继续在 route 中增加业务逻辑
- 继续扩展同步抓取和后台抓取两套路
- 继续在 V1 中引入复杂模型状态监控
- 继续在 V1 中做多用户 / SaaS 化
- 继续把日报、音频、视频能力堆进主链路

## 4. V2 阶段规划

### Phase 0：V1 封版

**目标：**

- 当前 V1.0-beta 能运行
- 文档归档
- README 更新
- 打 checkpoint tag

**产出：**

```
docs/V1_BETA_CHECKPOINT_ARCHIVE.md
docs/V2_ARCHITECTURE_PROPOSAL.md
docs/V2_MIGRATION_ROADMAP.md
```

---

### Phase 1：V2 Domain Model

**目标：**

- 重新定义 Source
- 重新定义 SourceItem
- 新增 ContentSnapshot
- 新增 AnalysisRun
- 新增 Pipeline 状态机

不做 UI 大改。

---

### Phase 2：V2 Discovery Pipeline

**目标：**

- RSS Discovery
- HTML Index Discovery
- FetchRun / DiscoveryRun
- 明确 new / seen / updated / failed
- 统一同步和后台执行逻辑

---

### Phase 3：V2 Content Pipeline

**目标：**

- HTML 正文抓取
- PDF 文本抽取
- 正文清洗
- 快照保存
- 内容 hash
- 可重试
- 错误恢复

---

### Phase 4：V2 Analysis Pipeline

**目标：**

- 中文一句话摘要
- 中文详细摘要
- 结构化洞察
- 相关性判断
- 行动建议
- JSON schema 校验
- LLM 输出失败恢复

---

### Phase 5：V2 Workbench

**目标：**

- 今日雷达
- SourceItem 详情
- InsightCard 详情
- 个人判断
- Markdown 导出

---

### Phase 6：V2 Extensions（可选）

```
- 模型状态雷达
- Daily Report
- 中文播报
- TTS
- 视频分享
- 邮件 / 飞书推送
- 长期趋势归档
```

## 5. 推荐执行策略

不要在 V1 main 上大改。

建议：

```
main：保留 V1 checkpoint
v2-design：文档和架构设计
v2-core：重建核心 pipeline
v2-workbench：迁移 UI / 工作台
```

## 6. 风险控制

- 每个阶段必须有验收脚本
- 每个模块必须可单独测试
- 不一次性迁移所有功能
- V1 始终保留可运行版本
- V2 未完成前不删除 V1
