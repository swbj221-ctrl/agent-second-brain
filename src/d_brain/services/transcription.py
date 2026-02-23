"""Provider-agnostic speech-to-text adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from deepgram import AsyncDeepgramClient

from d_brain.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class STTResult:
    """Result for a speech-to-text operation."""

    text: str = ""
    language: str | None = None
    duration_ms: int | None = None
    provider_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and bool(self.text.strip())


class STTAdapter(Protocol):
    """Protocol for STT adapters."""

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        """Transcribe audio bytes to text."""


class DisabledSTTAdapter:
    """STT adapter that returns a structured error when unavailable."""

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        return STTResult(
            text="",
            language=language,
            provider_ref="none",
            error_code="stt_unavailable",
            error_message="STT provider is not configured.",
        )


class DeepgramSTTAdapter:
    """STT adapter for Deepgram (Nova-3)."""

    def __init__(self, api_key: str, model: str, default_language: str | None) -> None:
        self.api_key = api_key
        self.model = model
        self.default_language = default_language
        self.client = AsyncDeepgramClient(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        if not self.api_key:
            return STTResult(
                text="",
                language=language or self.default_language,
                provider_ref="deepgram",
                error_code="stt_unavailable",
                error_message="Deepgram API key is missing.",
            )

        active_language = language or self.default_language or "en"
        logger.info("Starting transcription, audio size: %d bytes", len(audio_bytes))

        response = await self.client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model=self.model,
            language=active_language,
            punctuate=True,
            smart_format=True,
        )

        transcript = (
            response.results.channels[0].alternatives[0].transcript
            if response.results
            and response.results.channels
            and response.results.channels[0].alternatives
            else ""
        )

        logger.info("Transcription complete: %d chars", len(transcript))
        return STTResult(
            text=transcript,
            language=active_language,
            provider_ref="deepgram",
        )


def build_stt_adapter(settings: Settings) -> STTAdapter:
    """Create an STT adapter from settings."""
    provider = (settings.stt_provider or "").strip().lower()
    if provider == "deepgram":
        return DeepgramSTTAdapter(
            api_key=settings.deepgram_api_key,
            model=settings.stt_deepgram_model,
            default_language=settings.stt_language_default,
        )
    return DisabledSTTAdapter()
