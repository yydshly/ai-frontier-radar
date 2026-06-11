"""Single source of truth for radar relevance vocabulary (C1 Phase A).

Holds the canonical topic→keyword taxonomy used to categorize today-radar items.
Extracted VERBATIM from ``today.py`` — Phase A/B are behavior-preserving (a pure
relocation, validated by a before/after categorization diff).

Report ranking (``daily_report_card``) and recommendation scoring
(``compile_candidates``) will migrate onto this in later phases (C/D), which DO
change behavior and are gated by an explicit before/after diff + sign-off.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDef:
    key: str
    title: str
    keywords: tuple[str, ...]


# ── Source importance (C1 Phase C) ──────────────────────────────────────────
# Single source of truth for "how important is this source", consumed by both
# the daily report ranking (as a float weight) and the recommendation scorer
# (as an int priority, derived below). Replaces the two drifting tables
# daily_report_card._SOURCE_WEIGHTS and compile_candidates._SOURCE_PRIORITY.
SOURCE_IMPORTANCE: dict[str, float] = {
    "openai_news": 2.0,
    "anthropic_news": 2.0,
    "deepmind_blog": 2.0,
    "huggingface_blog": 1.8,
    "meta_ai_blog": 1.8,
    "nvidia_ai_blog": 1.8,
    "microsoft_ai_source": 1.7,
    "stanford_hai": 1.5,
    "mit_news_ai": 1.5,
    "arxiv_cs_ai": 1.2,
    "arxiv_cs_cl": 1.0,
    "arxiv_cs_lg": 1.0,
    "mistral_ai_news": 1.5,
    "cohere_blog": 1.5,
    "berkeley_bair_blog": 1.3,
}

# Float importance → integer recommendation priority. Reproduces the previous
# compile_candidates._SOURCE_PRIORITY values exactly, EXCEPT deepmind_blog,
# which aligns up (8 → 10) to match its top-tier report weight (the one prior
# disagreement between the two tables; verified no current-data result change).
_IMPORTANCE_TO_PRIORITY: dict[float, int] = {
    2.0: 10, 1.8: 7, 1.7: 6, 1.5: 5, 1.3: 4, 1.2: 4, 1.0: 3,
}


def source_weight(source_key: str) -> float:
    """Float importance weight for ranking. Unknown sources default to 1.0."""
    return SOURCE_IMPORTANCE.get(source_key, 1.0)


def source_priority(source_key: str) -> int:
    """Integer recommendation priority. Unknown sources default to 0."""
    importance = SOURCE_IMPORTANCE.get(source_key)
    if importance is None:
        return 0
    return _IMPORTANCE_TO_PRIORITY.get(round(importance, 1), int(round(importance * 5)))


# Topic taxonomy — evaluated in order; a normal item is placed in the FIRST
# matching category (substring match on a lowercased blob built from
# source_key/title/summary/metadata). Order matters: "AI 编程" must come before
# "模型公司" so a Codex article tagged "openai" still classifies as coding;
# "Agent 工作流" must come before "产品机会 / 商业化".
RELEVANCE_CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef(
        "ai_coding",
        "AI 编程 / 开发者工具",
        (
            "codex", "coding", "code", "developer", "cursor", "copilot",
            "ide", "software engineer", "programming", "devtool",
            "github", "git", "pull request", "cli",
        ),
    ),
    CategoryDef(
        "agent_workflow",
        "Agent 工作流",
        (
            "agent", "agents", "multi-agent", "workflow", "tool use",
            "computer use", "automation", "autonomous", "orchestration",
        ),
    ),
    CategoryDef(
        "rag_knowledge",
        "RAG / 知识库",
        (
            "rag", "retrieval", "knowledge base", "vector", "embedding",
            "search", "index", "semantic search", "memory",
        ),
    ),
    CategoryDef(
        "doc_understanding",
        "文档理解 / 资料处理",
        (
            "document", "pdf", "report", "paper", "reading", "extract",
            "extraction", "ocr", "parser", "markdown", "dataset",
        ),
    ),
    CategoryDef(
        "model_release",
        "模型公司 / 发布动态",
        (
            "openai", "anthropic", "deepmind", "google", "mistral",
            "cohere", "meta", "microsoft", "nvidia", "huggingface",
            "hugging face", "claude", "gpt", "gemini", "llama",
            "model release", "launches", "announces",
        ),
    ),
    CategoryDef(
        "open_model_benchmark",
        "开源模型 / Benchmark",
        (
            "open source", "open-weight", "benchmark", "leaderboard",
            "eval", "evaluation", "mmlu", "swe-bench", "arena",
            "performance", "reasoning model",
        ),
    ),
    CategoryDef(
        "multimodal_video_image",
        "多模态 / 图像 / 视频",
        (
            "multimodal", "vision", "image", "video", "sora", "veo",
            "generate images", "image generation", "video generation",
        ),
    ),
    CategoryDef(
        "voice_audio",
        "语音 / TTS / 音频",
        (
            "voice", "audio", "tts", "speech", "speech-to-text",
            "text-to-speech", "music", "sound", "transcription",
        ),
    ),
    CategoryDef(
        "safety_policy",
        "AI 安全 / 政策",
        (
            "safety", "policy", "regulation", "risk", "alignment",
            "security", "governance", "standard", "youth", "privacy",
        ),
    ),
    CategoryDef(
        "product_business",
        "产品机会 / 商业化",
        (
            "enterprise", "business", "startup", "product", "pricing",
            "revenue", "market", "customer", "use case",
            "case study", "adoption",
        ),
    ),
    CategoryDef(
        "infra_compute",
        "基础设施 / 算力",
        (
            "infrastructure", "compute", "gpu", "datacenter", "data center",
            "cluster", "training", "inference", "chip", "server",
            "stargate",
        ),
    ),
)
