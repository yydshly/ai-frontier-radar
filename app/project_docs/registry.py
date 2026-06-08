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
