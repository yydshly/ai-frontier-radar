"""LLM client for summary generation.

This module handles LLM API calls for summary generation.
It reads configuration from environment variables only.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.application.summary.summary_models import (
    LLMResponse,
    SummarySettings,
)


class SummaryLLMClient:
    """
    OpenAI-compatible LLM client for summary generation.

    Configuration from environment variables:
    - LLM_SUMMARY_ENABLED (default: false)
    - LLM_BASE_URL
    - LLM_API_KEY
    - LLM_MODEL
    - LLM_TIMEOUT_SECONDS (default: 30)
    """

    def __init__(self, settings: SummarySettings | None = None):
        self.settings = settings or SummarySettings.from_env()
        self._enabled = self.settings.enabled
        self._configured = bool(
            self.settings.enabled
            and self.settings.base_url
            and self.settings.api_key
            and self.settings.model
        )

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_configured(self) -> bool:
        return self._configured

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        """
        Call LLM API and return JSON response.

        Returns:
            LLMResponse with status and parsed text/data
        """
        if not self._enabled:
            return LLMResponse(status="disabled", text=None, error="LLM_SUMMARY_ENABLED is not set to true")

        if not self._configured:
            return LLMResponse(
                status="disabled",
                text=None,
                error="LLM not configured: missing LLM_BASE_URL, LLM_API_KEY, or LLM_MODEL",
            )

        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.api_key}",
        }

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        }

        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            content = result["choices"][0]["message"]["content"]
            return LLMResponse(status="ok", text=content, error=None)

        except httpx.TimeoutException:
            return LLMResponse(status="failed", text=None, error="llm_timeout: request timed out")
        except httpx.HTTPStatusError as e:
            return LLMResponse(
                status="failed",
                text=None,
                error=f"llm_error: HTTP {e.response.status_code}",
            )
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return LLMResponse(
                status="failed",
                text=None,
                error=f"llm_error: unexpected response format - {e}",
            )
        except Exception as e:
            return LLMResponse(status="failed", text=None, error=f"llm_error: {e}")


def parse_summary_json(raw_text: str) -> dict[str, Any]:
    """
    Parse LLM response text as JSON.

    Attempts repair if initial parse fails.
    Raises ValueError if repair also fails.
    """
    raw_text = raw_text.strip()

    # Remove markdown code blocks if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first line (```json or ```)
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        # Remove last line (```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to repair: extract JSON object from the text
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw_text[start:end])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Failed to parse JSON from LLM response: {raw_text[:200]}")
