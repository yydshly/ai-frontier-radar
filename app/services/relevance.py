"""Relevance scoring and user direction matching."""
from typing import List

USER_DIRECTIONS = [
    "AI 编程工具",
    "多 Agent 工作流",
    "知识库 / RAG",
    "文档理解",
    "资料转换为知识产品",
    "MiniMax 能力整理",
    "AI 小镇生活",
    "情绪 MV 生成器",
    "TTS / 语音产品",
    "视频生成",
    "AI 安全",
    "Claude / Anthropic",
    "OpenAI",
    "Google DeepMind",
    "MiniMax",
    "Mimo",
    "独立开发者变现",
    "全球 AI 前沿报告",
]


def get_user_directions() -> List[str]:
    """Return the list of user focus directions."""
    return USER_DIRECTIONS.copy()


# Note: The actual relevance scoring is done by the LLM in llm_client.py
# This module is reserved for any local relevance logic if needed
# The LLM receives the user directions list and incorporates it into the response
