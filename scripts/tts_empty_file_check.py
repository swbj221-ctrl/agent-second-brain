"""Dev check for empty TTS audio files (should be detected as invalid)."""

from pathlib import Path


def main() -> int:
    out_dir = Path("data") / "tts" / "telegram"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tts_empty_check.ogg"
    out_path.write_bytes(b"")

    exists = out_path.exists()
    size = out_path.stat().st_size if exists else 0
    valid = exists and size > 0

    print("tts_empty_file_check")
    print(f"exists={exists}")
    print(f"size={size}")
    print(f"valid={valid}")
    return 0 if not valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
