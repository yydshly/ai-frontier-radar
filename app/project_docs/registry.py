"""White-listed document registry for Project Docs Hub.

All documents must be registered here. Users can only access documents
that exist in this registry — no arbitrary file access is allowed.
"""
from dataclasses import dataclass
from pathlib import Path

# Base directory for project docs (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class DocEntry:
    key: str                      # URL-safe identifier, e.g. "architecture"
    title: str                    # Display title in Chinese
    path: str                    # Relative path from project root, e.g. "docs/ARCHITECTURE_OVERVIEW.md"
    category: str                 # Grouping category
    description: str              # Short description


# ── Registry ──────────────────────────────────────────────────────────────────

PROJECT_DOCS_REGISTRY: dict[str, DocEntry] = {
    # 项目定位与理念
    "readme": DocEntry(
        key="readme",
        title="项目定位",
        path="README.md",
        category="项目定位与理念",
        description="AI Frontier Radar 项目定位、目标用户、核心能力和 5 分钟快速上手指南。",
    ),
    "product-shape": DocEntry(
        key="product-shape",
        title="产品形态路线",
        path="docs/PRODUCT_SHAPE_ROADMAP.md",
        category="项目定位与理念",
        description="产品形态从 V0.1 到 V1.0 的演进历史和当前阶段判断。",
    ),

    # 架构与技术设计
    "architecture": DocEntry(
        key="architecture",
        title="架构总览",
        path="docs/ARCHITECTURE_OVERVIEW.md",
        category="架构与技术设计",
        description="系统三层架构、模块边界和数据流说明。",
    ),
    "system-design": DocEntry(
        key="system-design",
        title="系统设计说明",
        path="docs/SYSTEM_DESIGN_AND_TECH_DECISIONS.md",
        category="架构与技术设计",
        description="完整系统设计、数据模型关系、技术选型和未来方向。",
    ),
    "implementation-guide": DocEntry(
        key="implementation-guide",
        title="实现指南",
        path="docs/IMPLEMENTATION_GUIDE.md",
        category="架构与技术设计",
        description="代码实现原理、关键模块说明和开发注意事项。",
    ),
    "input-classification": DocEntry(
        key="input-classification",
        title="输入识别与策略路由",
        path="docs/INPUT_CLASSIFICATION_AND_SUMMARY_STRATEGY.md",
        category="架构与技术设计",
        description="URL 类型识别（listing/pagination/article）和编译策略路由逻辑。",
    ),
    "llm-pipeline": DocEntry(
        key="llm-pipeline",
        title="LLM Pipeline 与质量",
        path="docs/LLM_PIPELINE_AND_QUALITY.md",
        category="架构与技术设计",
        description="LLM 调用流程、Prompt 设计策略和质量保障机制。",
    ),

    # 版本与发布
    "release-notes": DocEntry(
        key="release-notes",
        title="发布说明",
        path="RELEASE_NOTES.md",
        category="版本与发布",
        description="V1.0-alpha 当前版本能力清单、已知限制和下一阶段方向。",
    ),
    "release-checklist": DocEntry(
        key="release-checklist",
        title="发布检查清单",
        path="docs/RELEASE_CHECKLIST.md",
        category="版本与发布",
        description="发布前逐项检查内容，确保所有关键功能可正常工作。",
    ),

    # 运行与验收
    "health-check": DocEntry(
        key="health-check",
        title="本地健康检查",
        path="docs/HEALTH_CHECK.md",
        category="运行与验收",
        description="health_check.py 脚本的使用方法、输出说明和警告处理建议。",
    ),
    "ci": DocEntry(
        key="ci",
        title="GitHub Actions CI",
        path="docs/CI.md",
        category="运行与验收",
        description="CI 工作流说明、本地 CI 模拟和常见问题处理。",
    ),
    "known-limitations": DocEntry(
        key="known-limitations",
        title="已知限制",
        path="docs/KNOWN_LIMITATIONS.md",
        category="运行与验收",
        description="当前版本的已知限制、无法支持的场景和变通方案。",
    ),

    "first-usable-loop-check": DocEntry(
        key="first-usable-loop-check",
        title="First Usable Loop 验收",
        path="docs/FIRST_USABLE_LOOP_CHECK.md",
        category="运行与验收",
        description="V1.0-beta First Usable Loop 完整链路验收步骤与预期说明。",
    ),

    # Beta 规划
    "beta-roadmap": DocEntry(
        key="beta-roadmap",
        title="Beta 路线图",
        path="docs/V1.0_BETA_SIGNAL_RADAR_ROADMAP.md",
        category="Beta 规划",
        description="V1.0-beta Signal Radar 目标：从单篇编译器演进到高质量来源接入与候选池。",
    ),
    "beta-architecture": DocEntry(
        key="beta-architecture",
        title="Beta 架构决策",
        path="docs/V1.0_BETA_ARCHITECTURE_DECISIONS.md",
        category="Beta 规划",
        description="V1.0-beta 分层架构、UI 技术选型、性能约束和禁止事项。",
    ),
    "next-execution-plan": DocEntry(
        key="next-execution-plan",
        title="下一阶段执行计划",
        path="docs/NEXT_EXECUTION_PLAN.md",
        category="Beta 规划",
        description="V1.0-beta 下一阶段优先级规划：P0/P1/P2 分级落地路径。",
    ),

    # V1.0-beta First Usable Loop 阶段包
    "v1-beta-checkpoint": DocEntry(
        key="v1-beta-checkpoint",
        title="V1.0-beta First Usable Loop Checkpoint",
        path="docs/V1_BETA_CHECKPOINT.md",
        category="Beta 规划",
        description="阶段稳定点说明，覆盖完整主链路、已完成能力、非目标、已知限制和下一阶段建议。",
    ),
    "v1-beta-manual-acceptance": DocEntry(
        key="v1-beta-manual-acceptance",
        title="V1.0-beta 人工验收记录",
        path="docs/V1_BETA_MANUAL_ACCEPTANCE_RECORD.md",
        category="Beta 规划",
        description="用于记录 First Usable Loop 的真实人工验收环境、步骤、结果和问题。",
    ),
    "v1-beta-status": DocEntry(
        key="v1-beta-status",
        title="V1.0-beta First Usable Loop 状态说明",
        path="docs/V1_BETA_FIRST_USABLE_LOOP_STATUS.md",
        category="Beta 规划",
        description="当前阶段定位、主链路、已完成能力、非目标、已知限制和后续规划。",
    ),
    "v1-beta-checklist": DocEntry(
        key="v1-beta-checklist",
        title="V1.0-beta First Usable Loop 验收清单",
        path="docs/V1_BETA_FIRST_USABLE_LOOP_CHECKLIST.md",
        category="Beta 规划",
        description="页面、抓取、中文摘要、InsightCard、导出和 checkpoint 的验收清单。",
    ),

    # V1.0-beta.1 来源调度与来源工作台
    "v1-beta-1-source-scheduling-architecture": DocEntry(
        key="v1-beta-1-source-scheduling-architecture",
        title="V1.0-beta.1 来源调度与来源工作台架构",
        path="docs/V1_BETA_1_SOURCE_SCHEDULING_ARCHITECTURE.md",
        category="V1.0-beta.1",
        description="due-source 调度、单来源工作台、来源池与雷达关注源分离、摘要队列演进的架构设计。",
    ),
    "v1-beta-1-execution-plan": DocEntry(
        key="v1-beta-1-execution-plan",
        title="V1.0-beta.1 执行计划",
        path="docs/V1_BETA_1_EXECUTION_PLAN.md",
        category="V1.0-beta.1",
        description="V1.0-beta.1 任务拆分、推荐顺序、测试策略和风险说明。",
    ),
    "v1-beta-1-decision-record": DocEntry(
        key="v1-beta-1-decision-record",
        title="V1.0-beta.1 架构决策记录",
        path="docs/V1_BETA_1_DECISION_RECORD.md",
        category="V1.0-beta.1",
        description="V1.0-beta.1 六条关键架构决策：不定时任务、config 雷达源、due-source 基于 FetchRun 等。",
    ),
    "v1-beta-1-source-scheduling-acceptance": DocEntry(
        key="v1-beta-1-source-scheduling-acceptance",
        title="V1.0-beta.1 Source Scheduling Acceptance",
        path="docs/V1_BETA_1_SOURCE_SCHEDULING_ACCEPTANCE.md",
        category="V1.0-beta.1",
        description="来源调度、stale running 恢复、单来源手动探测与真实抓取验收记录。",
    ),
}


def get_doc_path(entry: DocEntry) -> Path:
    """Resolve a DocEntry path to an absolute Path, relative to project root."""
    return _PROJECT_ROOT / entry.path


def is_path_safe(entry: DocEntry) -> bool:
    """Verify the resolved path is under the project root (no traversal)."""
    try:
        resolved = get_doc_path(entry).resolve()
        root_resolved = _PROJECT_ROOT.resolve()
        return str(resolved).startswith(str(root_resolved))
    except Exception:
        return False
