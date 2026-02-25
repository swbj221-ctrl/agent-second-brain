"""Dev check: media input must win over transcript-only text."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.openclaw_bridge import dispatch_voice
from d_brain.services.transcription import STTResult


class FakeSTT:
    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes
        return STTResult(text="media transcript", language=language, provider_ref="fake")


async def _run() -> int:
    result = await dispatch_voice(
        user_id=1,
        source_ref="dev:1",
        message_text="Transcript: this should not be preferred",
        audio_bytes=b"fake-audio",
        media_declared=True,
        stt=FakeSTT(),
    )
    diagnostics = result.get("diagnostics") or {}
    media_won = result.get("handled") and diagnostics.get("transcript_only_warning") is not True
    print("voice_media_preference_check")
    print(f"handled={result.get('handled')}")
    print(f"status={result.get('status')}")
    print(f"transcript_only_warning={diagnostics.get('transcript_only_warning', False)}")
    return 0 if media_won else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
