"""Xiaomi MiMo V2.5 TTS adapter."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import httpx


class MiMoTTSError(RuntimeError):
    """Raised when MiMo TTS cannot produce audio."""


@dataclass(frozen=True)
class MiMoTTSSettings:
    api_key: str
    base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"
    model: str = "mimo-v2.5-tts"
    voice: str = "冰糖"
    audio_format: str = "wav"
    style: str = "使用清晰、专业、自然的中文新闻播报语气，语速适中，重点明确。"
    timeout_seconds: float = 180.0
    max_text_chars: int = 12000

    @classmethod
    def from_env(cls) -> "MiMoTTSSettings":
        api_key = os.getenv("MIMO_API_KEY", "").strip()
        if not api_key:
            raise MiMoTTSError("缺少 MIMO_API_KEY，无法调用 MiMo 语音合成。")

        audio_format = os.getenv("MIMO_TTS_FORMAT", "wav").strip().lower()
        if audio_format != "wav":
            raise MiMoTTSError("当前仅支持 MIMO_TTS_FORMAT=wav。")

        base_url = os.getenv(
            "MIMO_TTS_BASE_URL",
            "https://token-plan-cn.xiaomimimo.com/v1",
        ).strip().rstrip("/")
        if api_key.startswith("tp-") and "token-plan-" not in base_url:
            raise MiMoTTSError("tp- API Key 必须配合 Token Plan Base URL 使用。")
        if api_key.startswith("sk-") and "token-plan-" in base_url:
            raise MiMoTTSError("sk- API Key 不能配合 Token Plan Base URL 使用。")

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=os.getenv("MIMO_TTS_MODEL", "mimo-v2.5-tts").strip(),
            voice=os.getenv("MIMO_TTS_VOICE", "冰糖").strip(),
            audio_format=audio_format,
            style=os.getenv(
                "MIMO_TTS_STYLE",
                "使用清晰、专业、自然的中文新闻播报语气，语速适中，重点明确。",
            ).strip(),
            timeout_seconds=_env_float("MIMO_TTS_TIMEOUT_SECONDS", 180.0),
            max_text_chars=_env_int("MIMO_TTS_MAX_TEXT_CHARS", 12000),
        )


class MiMoTTSClient:
    """Small synchronous client for non-streaming MiMo WAV generation."""

    def __init__(
        self,
        settings: MiMoTTSSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or MiMoTTSSettings.from_env()
        self.transport = transport

    def synthesize(self, text: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            raise MiMoTTSError("播报文稿为空，无法生成音频。")
        if len(clean_text) > self.settings.max_text_chars:
            raise MiMoTTSError(
                "播报文稿过长，当前上限为 "
                f"{self.settings.max_text_chars} 个字符，请缩短报告后重试。"
            )

        messages: list[dict[str, str]] = []
        if self.settings.style:
            messages.append({"role": "user", "content": self.settings.style})
        messages.append({"role": "assistant", "content": clean_text})

        payload = {
            "model": self.settings.model,
            "messages": messages,
            "audio": {
                "format": self.settings.audio_format,
                "voice": self.settings.voice,
            },
        }
        headers = {
            "api-key": self.settings.api_key,
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(
                timeout=self.settings.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                message = "MiMo 鉴权失败，请检查 API Key、套餐状态和 Base URL。"
            elif status_code == 429:
                message = "MiMo 请求过于频繁，请稍后重试。"
            elif status_code in {402, 422}:
                message = "MiMo 拒绝了本次请求，请检查套餐额度和请求参数。"
            elif status_code >= 500:
                message = "MiMo 服务暂时不可用，请稍后重试。"
            else:
                message = f"MiMo 语音合成请求失败（HTTP {status_code}）。"
            raise MiMoTTSError(message) from exc
        except httpx.TimeoutException as exc:
            raise MiMoTTSError("MiMo 语音生成超时，请稍后重试。") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise MiMoTTSError("MiMo 语音合成请求失败，请检查网络和配置。") from exc

        try:
            encoded_audio = data["choices"][0]["message"]["audio"]["data"]
            audio_bytes = base64.b64decode(encoded_audio, validate=True)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MiMoTTSError("MiMo 返回结果中缺少有效的音频数据。") from exc
        if (
            len(audio_bytes) < 44
            or not audio_bytes.startswith(b"RIFF")
            or audio_bytes[8:12] != b"WAVE"
        ):
            raise MiMoTTSError("MiMo 返回的音频不是有效的 WAV 文件。")
        return audio_bytes


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default
