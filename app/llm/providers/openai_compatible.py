"""OpenAI-compatible Chat Completions client."""
import httpx
from typing import Any

from app.llm.base import LLMClient
from app.llm.json_utils import parse_llm_response, JSONParseError
from app.logging_config import get_logger

logger = get_logger(__name__)


class OpenAICompatibleClient(LLMClient):
    """
    Generic OpenAI-compatible Chat Completions client.

    Used for:
    - OpenAI
    - Mimo
    - DeepSeek
    - Other OpenAI-compatible endpoints

    Uses max_completion_tokens (not max_tokens).
    """

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.base_url = profile["base_url"]
        self.endpoint = profile.get("endpoint", "/chat/completions")
        self.model = profile["model"]
        self.api_key = profile["api_key"]
        self.timeout = profile.get("timeout_seconds", 120)
        self.max_completion_tokens = profile.get("max_completion_tokens") or profile.get("max_tokens", 4000)
        self.temperature = profile.get("temperature", 0.3)
        self.top_p = profile.get("top_p", 0.95)
        self.stream = profile.get("stream", False)

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        Call OpenAI-compatible Chat Completions API and return JSON response.

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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_completion_tokens": self.max_completion_tokens,
            "stream": self.stream,
        }

        logger.info(f"OpenAI-compatible API call: {url} model={self.model}")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            # OpenAI-compatible returns {"choices": [{"message": {"content": "..."}}]}
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            logger.info(f"OpenAI-compatible response: {usage}")

            # Try parsing as JSON, retry once on failure
            try:
                return parse_llm_response(content, provider="openai")
            except JSONParseError as e:
                logger.warning(f"First JSON parse failed, retrying: {e}")

                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()

                content = result["choices"][0]["message"]["content"]
                return parse_llm_response(content, provider="openai")

        except httpx.HTTPStatusError as e:
            raise Exception(f"OpenAI-compatible API HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.TransportError as e:
            raise Exception(f"OpenAI-compatible API transport error: {e}")
        except JSONParseError as e:
            raise Exception(f"OpenAI-compatible JSON parse failed after retry: {e}")
        except Exception as e:
            raise Exception(f"OpenAI-compatible API call failed: {e}")
