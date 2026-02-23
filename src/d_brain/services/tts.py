"""Provider-agnostic text-to-speech adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from d_brain.config import Settings


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


def build_tts_adapter(settings: Settings) -> TTSAdapter:
    """Create a TTS adapter from settings."""
    provider = (settings.tts_provider or "").strip().lower()
    if provider == "mock":
        return MockTTSAdapter()
    if provider in {"", "none"}:
        return DisabledTTSAdapter()
    return DisabledTTSAdapter()
