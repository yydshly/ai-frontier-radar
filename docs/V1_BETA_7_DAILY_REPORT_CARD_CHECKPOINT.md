# V1.0-beta.7 Final Checkpoint

> 版本：V1.0-beta.7
> 分支：`feature/v1-beta-7-daily-report-card`
> main 基准 commit：`cc93ef4`（v1.0-beta.6 merge）
> feature 最新有效 commit：待提交
> checkpoint 创建日期：2026-06-10

---

## 一、阶段定位

V1.0-beta.7 实现**日报卡片（DailyReportCard）**，在今日雷达之上提供每日核心内容索引。

核心目标：以规则打分为基础，将今日新增内容分层为"今日必看"和"其他值得扫一眼"，不调用 LLM。

---

## 二、已完成能力

### 2.1 DailyReportCard 两层结构

- **今日必看**：3-5 条 top -ranked 内容，每条包含：
  - 标题、来源、中文一句话概述（已有时）
  - 为什么重要的中文解释（基于来源权重 + 关键词方向）
  - 相关方向标签（中文化）
  - 操作入口：打开原文、查看详情/InsightCard
- **其他值得扫一眼**：最多 10 条次级内容，保留原文链接和标签

### 2.2 规则打分排序

排序维度（权重依次递减）：
1. **来源权重**：OpenAI/Anthropic/DeepMind ×2.0，其他重要来源 ×1.5-1.8
2. **强信号关键词**：report、benchmark、safety、agent、model、release、evaluation 等
3. **用户关注方向匹配**：RAG、multi-agent、coding、AI safety 等
4. **内容完备性**：已有中文概述/摘要/InsightCard 加分
5. **新鲜度**：48h 半衰期指数衰减

### 2.3 中文方向标签

`DIRECTION_LABELS` 映射将英文关键词转为中文显示：
- `agent` → "多 Agent / Agent 工作流"
- `rag` → "RAG / 知识库"
- `coding` → "AI 编程"
- `ai safety` → "AI 安全"
- `openai` → "OpenAI"
- 等

### 2.4 防漏机制

- 今日必看不强制凑数，内容不足时展示实际数量
- 次级列表始终渲染（即使为空），保留"暂无其他内容"提示
- 提示文案："以下内容未进入今日必看，但仍建议扫一眼，避免错过关键报告。"

### 2.5 路由设计

- `GET /radar/daily-report`：展示日报卡片（只读）
- `POST /radar/daily-report/build`：触发构建并重定向到 GET 页面

---

## 三、当前不做

| 能力 | 原因 |
|------|------|
| LLM 日报总结 | 下一阶段任务 |
| 音频播报 | 下一阶段任务 |
| 真实正文抓取 | 内容获取为 intent-only |
| DB schema 修改 | 不引入 ORM 或表结构变更 |
| 自定义来源 F-2 | 已有 intake 入口 |

---

## 四、已知限制

- 规则排序还不是语义理解，可能不准确
- 中文原因基于标题/来源/已有摘要，非深度理解
- 排序质量需要真实数据验证
- 无个性化：所有用户看到相同排序

---

## 五、涉及文件

- `app/application/radar/daily_report_card.py` — 规则打分与卡片构建
- `app/routes/radar.py` — `/radar/daily-report` 路由
- `app/templates/radar_daily_report.html` — 日报卡片模板
- `app/static/style.css` — `.radar-report-*` 样式

---

## 六、禁止修改范围

- DB schema（models.py / db.py）
- LLM 调用链路
- 已有 InsightCard 生成逻辑

---

## 七、验收测试

- `quick_test.py` [51] V1.0-beta.7 — 965 passed, 0 failed
- `acceptance_first_usable_loop.py` [25] — 148 passed, 0 failed

---

## 八、下一阶段建议

1. **音频播报**：中文概述接入 TTS
2. **真实正文获取**：内容获取从 intent-only 到真实 fetch
3. **LLM 增强日报**：在规则排序基础上增加 LLM 摘要生成
4. **个性化排序**：基于用户关注方向自定义权重
