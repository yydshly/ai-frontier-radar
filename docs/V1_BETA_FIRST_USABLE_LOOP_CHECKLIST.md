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
