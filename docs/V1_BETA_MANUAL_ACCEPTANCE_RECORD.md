# V1.0-beta First Usable Loop 人工验收记录

> 参考：docs/V1_BETA_CHECKPOINT.md

## 1. 验收环境

- 分支：
- Commit：
- 本地端口：
- LLM Provider：
- 模型：
- AUTO_SUMMARY_MAX_PER_FETCH_RUN：
- 验收时间：

## 2. 基础检查

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/acceptance_first_usable_loop.py
python scripts/check_sources_health.py
```

- [ ] `python -m compileall app scripts` 成功
- [ ] `python scripts/quick_test.py` 全部通过
- [ ] `python scripts/acceptance_first_usable_loop.py` 全部通过
- [ ] `python scripts/check_sources_health.py` 无严重问题

## 3. 今日雷达验收

访问 `/radar/today`：

- [ ] 页面可以打开（200 OK）
- [ ] 左侧有"全部 / 今日重点 / 细分类"目录
- [ ] 左侧有"更新今日雷达"按钮
- [ ] 左侧有"最近探测状态"模块
- [ ] 中间是目录式内容列表
- [ ] 分页和每页数量在中间 toolbar
- [ ] 右侧是"智能阅读面板"
- [ ] 左右固定，中间可滚动
- [ ] 无底部巨大空白

## 4. 更新今日雷达验收

点击"更新今日雷达"：

- [ ] 页面不跳出今日雷达（返回 303 重定向回 /radar/today）
- [ ] 显示"雷达关注源 X 个"
- [ ] 显示启动 / 运行中 / 不支持 / 失败 数量
- [ ] 最近探测状态可以看到数量变化（运行中 → 成功）
- [ ] `/fetch-runs` 能看到运行记录
- [ ] 更新不处理 DB 中的 test_* / orphan_key 测试来源

## 5. 中文摘要验收

点击"补齐当前页中文摘要"：

- [ ] 页面不跳出今日雷达
- [ ] 保留 section / item_id / page / per_page
- [ ] 显示 success / skipped / failed 数量
- [ ] 右侧摘要状态从"中文摘要未生成"变为已有摘要

新增 SourceItem 自动摘要（观察刚探测到的条目）：

- [ ] 新条目中间卡片优先显示中文概述（zh_one_liner）
- [ ] 有"中文概述"标签
- [ ] 右侧显示中文详细摘要（zh_summary）
- [ ] 自动摘要失败时不影响 FetchRun 状态

## 6. InsightCard 生成验收

点击"加入生成"：

- [ ] 提交后回到今日雷达（return_to 生效）
- [ ] 保留当前分类和当前 item
- [ ] 状态变为"生成中"或"已完成"
- [ ] 已生成后右侧展示 InsightCard 预览
- [ ] 可打开完整 InsightCard

## 7. 完整 Card 验收

访问 `/cards/{id}`：

- [ ] 页面显示"完整 InsightCard"定位（不是 V1.0-alpha）
- [ ] 顶部显示四个核心问题说明
- [ ] 内容摘要回答"这篇资料说了什么"
- [ ] 洞察判断回答"为什么值得关注"
- [ ] 生成依据显示"基于来源摘要 / RSS metadata"（RSS/metadata 卡片）而非 unknown
- [ ] 原文信息"类型"不再显示 raw unknown
- [ ] 相关方向以标签形式显示
- [ ] 技术洞察、产品机会、风险提醒、行动建议区块清晰
- [ ] 双语理解在靠后位置，作为补充阅读
- [ ] 看完后的判断和导出仍可用

## 8. Markdown 导出验收

访问 `/cards/{id}/export-markdown`：

- [ ] 页面标题为"Markdown 行动任务草稿"
- [ ] 页面显示即将下载的文件名
- [ ] 文件名包含日期、AI前沿雷达、card id、标题、"行动任务"
- [ ] Markdown 预览自动换行，易读

访问 `/cards/{id}/export-report`：

- [ ] 页面标题为"完整 InsightCard Markdown 报告"
- [ ] 页面显示即将下载的文件名
- [ ] 文件名包含日期、AI前沿雷达、card id、标题、"完整报告"
- [ ] 下载按钮可正常触发下载

## 9. 验收结论

- [ ] 通过
- [ ] 有条件通过
- [ ] 不通过

## 10. 问题记录

| 问题 | 严重级别 | 是否阻塞 checkpoint | 备注 |
|---|---|---|---|
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |

## 11. 验收人签名

- 验收人：
- 日期：
- 分支 / Commit：
