"""OpenAI-compatible Chat Completions client."""
import httpx
from typing import Any

from app.llm.base import LLMClient
from app.llm.json_utils import parse_llm_response, JSONParseError, parse_json
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
            Exception: On API or parsing failure
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

        raw_text = None
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            # OpenAI-compatible returns {"choices": [{"message": {"content": "..."}}]}
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            logger.info(f"OpenAI-compatible response: {usage}")

            raw_text = content

            # First parse attempt
            data = parse_llm_response(content, provider="openai")
            data["model_name"] = self.model
            return data

        except JSONParseError as e:
            if raw_text is None:
                raise Exception(f"OpenAI-compatible JSON parse failed: {e}")

            logger.warning(f"OpenAI-compatible JSON parse failed, attempting repair: {e}")
            # Second attempt: JSON repair
            try:
                repaired = self._repair_json(raw_text)
                repaired["model_name"] = self.model
                return repaired
            except Exception as repair_err:
                raise Exception(f"OpenAI-compatible JSON parse failed after repair attempt: {repair_err}")

        except httpx.HTTPStatusError as e:
            raise Exception(f"OpenAI-compatible API HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.TransportError as e:
            raise Exception(f"OpenAI-compatible API transport error: {e}")
        except Exception as e:
            raise Exception(f"OpenAI-compatible API call failed: {e}")

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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        repair_user = JSON_REPAIR_USER_PROMPT.format(raw_text=raw_text)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JSON_REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": repair_user},
            ],
            "temperature": 0.1,  # Low temperature for repair
            "top_p": self.top_p,
            "max_completion_tokens": self.max_completion_tokens,
            "stream": False,
        }

        logger.info("OpenAI-compatible JSON repair attempt")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]
        return parse_llm_response(content, provider="openai")
