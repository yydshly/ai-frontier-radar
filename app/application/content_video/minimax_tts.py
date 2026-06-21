"""content_video — MiniMax T2A v2 TTS provider with subtitle timestamps.

Unlike the MiMo TTS client, MiniMax T2A v2 can return a ``subtitle_file`` URL
containing sentence-level timestamps. We use it so the video can carry real,
synced subtitles. The provider conforms to the content_video ``TTSProvider``
interface (``synthesize(text) -> bytes``) and additionally records the segments
of the most recent call on ``self.last_subtitles`` so the caller can build an SRT.

Config (env): MINIMAX_API_KEY (required), optional
MINIMAX_T2A_BASE_URL (default https://api.minimaxi.com/v1/t2a_v2),
MINIMAX_T2A_MODEL (default speech-02-hd),
MINIMAX_T2A_VOICE (default male-qn-qingse).
"""
from __future__ import annotations

import os

import httpx

from app.application.content_video.audio_renderer import TTSProvider, TTSProviderError


class MiniMaxT2AProvider(TTSProvider):
    """MiniMax T2A v2 provider that also captures subtitle timestamps."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        voice_id: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = (api_key or os.getenv("MINIMAX_API_KEY", "")).strip()
        if not self.api_key:
            raise TTSProviderError("MINIMAX_API_KEY 未配置")
        self.base_url = (base_url or os.getenv("MINIMAX_T2A_BASE_URL")
                         or "https://api.minimaxi.com/v1/t2a_v2").strip()
        self.model = (model or os.getenv("MINIMAX_T2A_MODEL") or "speech-02-hd").strip()
        self.voice_id = (voice_id or os.getenv("MINIMAX_T2A_VOICE") or "male-qn-qingse").strip()
        self.timeout = timeout
        # Segments of the most recent synthesize() call:
        # list of {"text": str, "begin_ms": float, "end_ms": float}
        self.last_subtitles: list[dict] = []

    def synthesize(self, text: str) -> bytes:
        self.last_subtitles = []
        body = {
            "model": self.model,
            "text": text,
            "stream": False,
            "subtitle_enable": True,
            "voice_setting": {"voice_id": self.voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": 24000, "format": "mp3"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = httpx.post(self.base_url, headers=headers, json=body, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise TTSProviderError(f"MiniMax T2A 请求失败: {exc}") from exc

        base_resp = payload.get("base_resp") or {}
        if base_resp.get("status_code") not in (0, None):
            raise TTSProviderError(f"MiniMax T2A 返回错误: {base_resp.get('status_msg')}")

        data = payload.get("data") or {}
        audio_hex = data.get("audio")
        if not audio_hex:
            raise TTSProviderError("MiniMax T2A 未返回音频")
        try:
            audio_bytes = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise TTSProviderError(f"MiniMax T2A 音频解码失败: {exc}") from exc

        # Subtitles: a URL to a JSON list of segments with ms timestamps.
        sub_url = payload.get("subtitle_file") or data.get("subtitle_file")
        if sub_url:
            try:
                self.last_subtitles = self._fetch_segments(sub_url)
            except Exception:
                self.last_subtitles = []  # subtitles are best-effort
        return audio_bytes

    def _fetch_segments(self, url: str) -> list[dict]:
        raw = httpx.get(url, timeout=self.timeout).json()
        segments: list[dict] = []
        for item in raw if isinstance(raw, list) else []:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            try:
                begin = float(item.get("time_begin"))
                end = float(item.get("time_end"))
            except (TypeError, ValueError):
                continue
            segments.append({"text": text, "begin_ms": begin, "end_ms": end})
        return segments


def build_content_video_tts_provider() -> MiniMaxT2AProvider:
    """Factory: the subtitle-capable provider used for content videos."""
    return MiniMaxT2AProvider()
