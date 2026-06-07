"""LLM Client protocol definition."""
from typing import Protocol, Any


class LLMClient(Protocol):
    """Protocol for LLM clients. Business logic must only depend on this interface."""

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Generate a JSON response from the LLM."""
        ...
