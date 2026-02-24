"""Provider-agnostic text-to-speech adapters."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from d_brain.config import Settings

logger = logging.getLogger(__name__)
TTS_TIMEOUT_S = 20.0
TTS_MAX_RETRIES = 1


@dataclass(slots=True)
class TTSResult:
    """Result for a text-to-speech operation."""

    audio_bytes: bytes | None = None
    mime_type: str | None = None
    duration_ms: int | None = None
    provider_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.audio_bytes is not None


class TTSAdapter(Protocol):
    """Protocol for TTS adapters."""

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize speech from text."""


class DisabledTTSAdapter:
    """TTS adapter that returns a structured error when unavailable."""

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        return TTSResult(
            audio_bytes=None,
            provider_ref="none",
            error_code="tts_unavailable",
            error_message="TTS provider is not configured.",
        )


class MockTTSAdapter:
    """Mock TTS adapter for development (no audio output)."""

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        return TTSResult(
            audio_bytes=None,
            provider_ref="mock",
        )


class DeepgramTTSAdapter:
    """TTS adapter for Deepgram (REST speak endpoint)."""

    def __init__(self, api_key: str, model: str, encoding: str, container: str) -> None:
        self.api_key = api_key
        self.model = model
        self.encoding = encoding
        self.container = container

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        if not text.strip():
            return TTSResult(
                audio_bytes=None,
                provider_ref="deepgram",
                error_code="invalid_input",
                error_message="TTS input text is empty.",
            )
        if not self.api_key:
            return TTSResult(
                audio_bytes=None,
                provider_ref="deepgram",
                error_code="tts_unavailable",
                error_message="Deepgram API key is missing.",
            )

        params: dict[str, str] = {}
        active_model = (voice or self.model or "").strip()
        if active_model:
            params["model"] = active_model
        if self.encoding:
            params["encoding"] = self.encoding
        if self.container:
            params["container"] = self.container

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}

        last_error: str | None = None
        for attempt in range(TTS_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TTS_TIMEOUT_S) as client:
                    response = await client.post(
                        "https://api.deepgram.com/v1/speak",
                        params=params,
                        headers=headers,
                        json=payload,
                    )
                if response.status_code >= 400:
                    last_error = response.text.strip() or "TTS request failed."
                    if attempt >= TTS_MAX_RETRIES:
                        return TTSResult(
                            audio_bytes=None,
                            provider_ref="deepgram",
                            error_code="tts_failed",
                            error_message="TTS request failed. Please try again.",
                        )
                    logger.warning(
                        "TTS retrying after HTTP %s: %s", response.status_code, last_error
                    )
                    await asyncio.sleep(0.5)
                    continue
                audio_bytes = response.content
                if not audio_bytes:
                    return TTSResult(
                        audio_bytes=None,
                        provider_ref="deepgram",
                        error_code="tts_failed",
                        error_message="TTS response was empty.",
                    )
                return TTSResult(
                    audio_bytes=audio_bytes,
                    mime_type=response.headers.get("content-type"),
                    provider_ref="deepgram",
                )
            except (asyncio.TimeoutError, httpx.HTTPError, OSError, ConnectionError) as exc:
                last_error = str(exc)
                if attempt >= TTS_MAX_RETRIES:
                    return TTSResult(
                        audio_bytes=None,
                        provider_ref="deepgram",
                        error_code="tts_failed",
                        error_message="TTS request failed. Please try again.",
                    )
                logger.warning("TTS retrying after transient error: %s", exc)
                await asyncio.sleep(0.5)
            except Exception:
                logger.exception("TTS failed with unexpected error")
                return TTSResult(
                    audio_bytes=None,
                    provider_ref="deepgram",
                    error_code="tts_failed",
                    error_message="TTS request failed. Please try again.",
                )

        return TTSResult(
            audio_bytes=None,
            provider_ref="deepgram",
            error_code="tts_failed",
            error_message=last_error or "TTS request failed. Please try again.",
        )


def build_tts_adapter(settings: Settings) -> TTSAdapter:
    """Create a TTS adapter from settings."""
    provider = (settings.tts_provider or "").strip().lower()
    if provider == "mock":
        return MockTTSAdapter()
    if provider in {"", "none"}:
        return DisabledTTSAdapter()
    if provider == "deepgram":
        return DeepgramTTSAdapter(
            api_key=settings.deepgram_api_key,
            model=settings.tts_voice,
            encoding=settings.tts_deepgram_encoding,
            container=settings.tts_deepgram_container,
        )
    return DisabledTTSAdapter()
