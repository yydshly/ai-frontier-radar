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

JSON_REPAIR_SYSTEM_PROMPT = """你是 JSON 修复器。你只负责把输入内容修复为合法 JSON。
不要添加解释。
不要添加 Markdown。
不要改变字段语义。
如果字段缺失，保留已有字段，不要编造事实。
只输出 JSON，不要其他文字。"""

JSON_REPAIR_USER_PROMPT = """以下是模型输出，但不是合法 JSON。请修复为合法 JSON object：

{raw_text}

只输出 JSON，不要任何解释或 Markdown。"""


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
            Exception: On API or parsing failure
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

        raw_text = None
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            logger.info(f"MiniMax response: {result.get('usage', {})}")

            # Extract raw text for repair use
            raw_text = extract_text_from_anthropic_response(result)

            # First parse attempt
            data = parse_llm_response(result, provider="minimax")
            data["model_name"] = self.model
            return data

        except JSONParseError as e:
            if raw_text is None:
                raise Exception(f"MiniMax JSON parse failed: {e}")

            logger.warning(f"MiniMax JSON parse failed, attempting repair: {e}")
            # Second attempt: JSON repair
            try:
                repaired = self._repair_json(raw_text)
                repaired["model_name"] = self.model
                return repaired
            except Exception as repair_err:
                raise Exception(f"MiniMax JSON parse failed after repair attempt: {repair_err}")

        except httpx.HTTPStatusError as e:
            raise Exception(f"MiniMax API HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.TransportError as e:
            raise Exception(f"MiniMax API transport error: {e}")
        except Exception as e:
            raise Exception(f"MiniMax API call failed: {e}")

    def _repair_json(self, raw_text: str) -> dict[str, Any]:
        """
        Attempt to repair malformed JSON by sending it back to the LLM.

        Args:
            raw_text: The malformed JSON text from the first attempt

        Returns:
            Repaired JSON dict
        """
        url = f"{self.base_url}{self.endpoint}"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        repair_user = JSON_REPAIR_USER_PROMPT.format(raw_text=raw_text)
        messages_content = [{"type": "text", "text": repair_user}]

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": JSON_REPAIR_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": messages_content}],
            "temperature": 0.1,  # Low temperature for repair
            "top_p": self.top_p,
            "stream": False,
        }

        logger.info("MiniMax JSON repair attempt")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

        # Extract repaired text and parse
        repaired_text = extract_text_from_anthropic_response(result)
        return parse_llm_response(result, provider="minimax")
