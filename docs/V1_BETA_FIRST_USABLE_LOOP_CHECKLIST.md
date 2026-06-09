# V1.0-beta First Usable Loop 验收清单

## 1. 环境检查

```bash
python -m compileall app scripts
python scripts/quick_test.py
python scripts/check_sources_health.py
```

## 2. 今日雷达页面验收

访问：

```
/radar/today
```

检查：

- [ ] 页面能正常打开（200 OK）
- [ ] 左侧有"全部 / 今日重点 / 细分类"目录
- [ ] 左侧有"更新今日雷达"按钮
- [ ] 左侧有"最近探测状态"模块
- [ ] 中间是目录式内容列表
- [ ] 分页和每页数量在中间 toolbar
- [ ] 右侧是"智能阅读面板"
- [ ] 左右固定，中间可滚动
- [ ] 无底部巨大空白

## 3. 更新今日雷达验收

点击：

```
更新今日雷达
```

检查：

- [ ] 页面不跳出今日雷达（返回 303 重定向回 /radar/today）
- [ ] 显示"雷达关注源 X 个"
- [ ] 显示启动 / 运行中 / 不支持 / 失败 数量
- [ ] 最近探测状态可以看到数量变化（运行中 → 成功）
- [ ] `/fetch-runs` 能看到运行记录
- [ ] 更新不处理 DB 中的 test_* / orphan_key 测试来源

## 4. 中文摘要验收

点击：

```
补齐当前页中文摘要
```

检查：

- [ ] 页面不跳出今日雷达
- [ ] 保留 section / item_id / page / per_page
- [ ] 显示 success / skipped / failed 数量
- [ ] 右侧摘要状态从"中文摘要未生成"变为已有摘要

## 5. InsightCard 生成验收

点击：

```
加入生成
```

检查：

- [ ] 提交后回到今日雷达（return_to 生效）
- [ ] 保留当前分类和当前 item
- [ ] 状态变为"生成中"或"已完成"
- [ ] 已生成后右侧展示 InsightCard 预览
- [ ] 可打开完整 InsightCard

## 6. OpenAI 403 验收

使用 OpenAI RSS 来源产生的 SourceItem：

- [ ] 即使原文 URL 403，也能基于 RSS / metadata snapshot 生成轻量 InsightCard
- [ ] InsightCard 应提示"非全文解析"（基于快照）

## 7. 左侧分类验收

检查：

- [ ] 点击"全部"显示所有条目
- [ ] 点击"今日重点"显示最新条目
- [ ] 点击细分类显示对应分类条目
- [ ] 分类计数与实际条目数一致

## 8. 分页验收

检查：

- [ ] 可切换每页数量（5 / 10 / 20 / 30 / 50）
- [ ] 切换后 page 重置为 1
- [ ] 上一页 / 下一页 翻页正常
- [ ] 分页保留当前 section

## 9. 不应出现的问题

- [ ] 更新今日雷达不应一次性处理 DB 全部测试来源
- [ ] 不应出现"启动 30 / 暂缓 100+"的异常提示，除非雷达关注源真的超过 30
- [ ] 加入生成后不应跳去 SourceItem 技术详情页
- [ ] 分类分页不应丢 section
- [ ] 页面不应出现底部巨大空白
- [ ] 选中卡片后不应跳到顶部（scrollIntoView）

## 10. 抓取后自动摘要验收

点击"更新今日雷达"，等待后台完成后检查：

- [ ] FetchRun 正常进入 success / partial_failed / failed
- [ ] 抓取成功时，FetchRun.metadata_json 中包含 auto_summary
- [ ] auto_summary 显示 candidate_count / selected_count / success / skipped / failed
- [ ] 新增或更新 SourceItem 中，最多 AUTO_SUMMARY_MAX_PER_FETCH_RUN（默认 5）条会自动生成 zh_one_liner / zh_summary
- [ ] 今日雷达中间卡片优先显示中文概述（zh_one_liner）
- [ ] 右侧阅读面板显示中文详细摘要（zh_summary）
- [ ] 如果 LLM 失败，FetchRun 抓取状态不应因此变 failed
- [ ] 自动摘要失败原因只写入 metadata_json.auto_summary / 日志，不影响抓取结果
- [ ] 不生成 InsightCard（那是"加入生成"按钮的责任）

## 11. InsightCard 预览与内容摘要职责分离验收

已生成 InsightCard 的条目，右侧面板检查：

- [ ] 内容摘要仍显示中文详细摘要（回答"这篇文章说了什么"）
- [ ] InsightCard 预览不再大段重复 summary_zh
- [ ] InsightCard 预览显示相关性分数
- [ ] 如果有 related_user_directions，显示为标签（相关方向）
- [ ] 如果有 relevance_reasons_zh，显示"为什么值得关注"
- [ ] 如果有 technical_insights_zh，显示"技术洞察"
- [ ] 如果有 product_opportunities_zh，显示"产品机会"
- [ ] 如果有 action_items_zh，显示"行动建议"
- [ ] 如果有 risks_zh，显示"风险提醒"
- [ ] 只有在没有任何洞察字段时才 fallback 显示 summary_zh
- [ ] "查看完整 InsightCard"按钮仍可用

## 12. 完整 InsightCard 页面验收

访问 `/cards/{id}`，检查：

- [ ] 页面不再显示 V1.0-alpha 主流程
- [ ] 页面顶部显示"完整 InsightCard"定位
- [ ] 顶部显示四个核心问题说明
- [ ] 第一层是原文信息和内容摘要
- [ ] 内容摘要回答"这篇资料说了什么"
- [ ] 洞察判断回答"为什么值得关注"
- [ ] 相关方向以标签形式显示
- [ ] 技术洞察、产品机会、风险提醒、行动建议区块清晰
- [ ] 双语理解在靠后位置，作为补充阅读
- [ ] 看完后的判断和导出仍可用
- [ ] 生成依据显示"基于来源摘要 / RSS metadata"（RSS/metadata 卡片）而非 unknown
- [ ] 原文信息"类型"不再显示 raw unknown，而是"未标注"或内容类型

## 13. Markdown 导出预览验收

访问 `/cards/{id}/export-markdown`：

- [ ] 页面标题应为"Markdown 行动任务草稿"
- [ ] 页面应显示即将下载的文件名
- [ ] Markdown 预览应自动换行，易读
- [ ] 下载文件名应包含日期、AI前沿雷达、card id、标题和"行动任务"

访问 `/cards/{id}/export-report`：

- [ ] 页面标题应为"完整 InsightCard Markdown 报告"
- [ ] 页面应显示即将下载的文件名
- [ ] 下载文件名应包含日期、AI前沿雷达、card id、标题和"完整报告"
