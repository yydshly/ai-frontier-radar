"""LLM client factory."""
from app.llm.base import LLMClient
from app.llm.config_loader import get_active_profile, validate_profile


def create_llm_client() -> LLMClient:
    """
    Create an LLM client based on the active LLM_PROFILE environment variable.

    Returns:
        An LLMClient implementation

    Raises:
        ValueError: On unsupported provider/protocol or missing config
    """
    profile = get_active_profile()
    validate_profile(profile)

    provider = profile.get("provider", "")
    protocol = profile.get("protocol", "")

    if provider == "minimax" and protocol == "anthropic_messages":
        from app.llm.providers.minimax_anthropic import MiniMaxAnthropicClient

        return MiniMaxAnthropicClient(profile)

    if protocol == "openai_chat_completions":
        from app.llm.providers.openai_compatible import OpenAICompatibleClient

        return OpenAICompatibleClient(profile)

    raise ValueError(
        f"Unsupported LLM provider/protocol: {provider}/{protocol}"
    )
