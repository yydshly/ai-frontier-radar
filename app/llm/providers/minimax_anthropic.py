"""MiniMax Anthropic Messages API compatible client."""
import httpx
from typing import Any

from app.llm.base import LLMClient
from app.llm.json_utils import (
    parse_llm_response,
    JSONParseError,
    extract_text_from_anthropic_response,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class MiniMaxAnthropicClient(LLMClient):
    """
    MiniMax client implementing Anthropic Messages API compatible interface.

    MiniMax uses the Anthropic Messages API format with:
    - x-api-key header (not Authorization: Bearer)
    - anthropic-version: 2023-06-01
    - max_tokens (not max_completion_tokens)
    - system + messages (not system + user as combined prompt)
    """

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.base_url = profile["base_url"]
        self.endpoint = profile.get("endpoint", "/v1/messages")
        self.model = profile["model"]
        self.api_key = profile["api_key"]
        self.timeout = profile.get("timeout_seconds", 120)
        self.max_tokens = profile.get("max_tokens", 4000)
        self.temperature = profile.get("temperature", 0.8)
        self.top_p = profile.get("top_p", 0.9)
        self.stream = profile.get("stream", False)
        self.thinking = profile.get("thinking")

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        Call MiniMax Anthropic Messages API and return JSON response.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            Parsed JSON dict from LLM response

        Raises:
            LLMError: On API or parsing failure
        """
        url = f"{self.base_url}{self.endpoint}"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        messages_content = [{"type": "text", "text": user_prompt}]

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": messages_content}],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": self.stream,
        }

        # Add thinking config if specified
        if self.thinking is not None:
            payload["thinking"] = self.thinking

        logger.info(f"MiniMax Anthropic API call: {url} model={self.model}")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            logger.info(f"MiniMax response: {result.get('usage', {})}")

            # Parse response - may need retry on JSON parse failure
            try:
                return parse_llm_response(result, provider="minimax")
            except JSONParseError as e:
                logger.warning(f"First JSON parse failed, retrying: {e}")
                # Retry once
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()

                return parse_llm_response(result, provider="minimax")

        except httpx.HTTPStatusError as e:
            raise Exception(f"MiniMax API HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.TransportError as e:
            raise Exception(f"MiniMax API transport error: {e}")
        except JSONParseError as e:
            raise Exception(f"MiniMax JSON parse failed after retry: {e}")
        except Exception as e:
            raise Exception(f"MiniMax API call failed: {e}")
