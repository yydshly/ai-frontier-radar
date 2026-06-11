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
