"""Local faster-whisper STT CLI for Telegram audio files (.ogg/.oga/.m4a/.wav)."""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

from d_brain.integrations.openclaw_bridge import _run_faster_whisper_stt  # noqa: E402


async def run_once(audio_path: Path, pass_token: str) -> int:
    mime_type, _ = mimetypes.guess_type(str(audio_path))
    diagnostics = {
        "mimeType": mime_type or "",
        "request_id": "stt_test_fw",
    }
    transcript, detected_language, language_probability, segments, stt_diag = await _run_faster_whisper_stt(
        audio_path=str(audio_path),
        pass_token=pass_token,
        diagnostics=diagnostics,
    )

    out = {
        "ok": bool(transcript.strip()) and not stt_diag.get("error_code"),
        "audio_path": str(audio_path),
        "transcript": transcript,
        "detected_language": detected_language,
        "language_probability": language_probability,
        "segments_count": len(segments),
        "segments_preview": segments[:5],
        "diagnostics": stt_diag,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local faster-whisper STT for a single audio file.")
    parser.add_argument("audio_path", help="Path to .ogg/.oga/.m4a/.wav file")
    parser.add_argument(
        "--pass-token",
        default="auto",
        choices=["auto", "ru", "en"],
        help="Language pass token for the STT run (default: auto).",
    )
    args = parser.parse_args()

    audio_path = Path(args.audio_path).expanduser().resolve()
    if not audio_path.exists() or not audio_path.is_file():
        print(json.dumps({"ok": False, "error": "audio_file_not_found", "audio_path": str(audio_path)}, ensure_ascii=False))
        return 1
    return asyncio.run(run_once(audio_path, args.pass_token))


if __name__ == "__main__":
    raise SystemExit(main())
