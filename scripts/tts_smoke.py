"""Stage 12/13 Deepgram TTS smoke test."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

from d_brain.config import get_settings  # noqa: E402
from d_brain.services.tts import build_tts_adapter  # noqa: E402


async def run_tts_smoke() -> int:
    settings = get_settings()
    adapter = build_tts_adapter(settings)
    text = "This is a Stage 12/13 TTS smoke test."

    result = await adapter.speak(text, voice=settings.tts_voice)
    if not result.ok:
        print("tts_smoke_fail")
        print(f"error_code={result.error_code}")
        print(f"error_message={result.error_message}")
        return 1

    out_dir = Path("data") / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tts_smoke.ogg"
    out_path.write_bytes(result.audio_bytes or b"")

    print("tts_smoke_ok")
    print(f"provider={result.provider_ref}")
    print(f"audio_path={out_path}")
    print(f"audio_exists={out_path.exists()}")
    print(f"audio_size={out_path.stat().st_size}")
    print(f"extension={out_path.suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_tts_smoke()))
