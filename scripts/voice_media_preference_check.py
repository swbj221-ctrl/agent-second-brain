"""Dev check: media should win over transcript text when both are present."""

from dataclasses import dataclass

from d_brain.bot.handlers import voice as voice_handler


@dataclass
class DummyVoice:
    file_id: str = "voice-file-id"
    mime_type: str = "audio/ogg"
    file_size: int = 1234


@dataclass
class DummyMessage:
    voice: DummyVoice | None = None
    audio: object | None = None
    document: object | None = None
    text: str | None = None


def main() -> int:
    message = DummyMessage(voice=DummyVoice(), text="Transcript: hello")
    media = voice_handler._select_media(message)  # noqa: SLF001

    print("voice_media_preference_check")
    print(f"media_type={media['media_type'] if media else ''}")
    print(f"used_media={bool(media)}")
    return 0 if media and media["media_type"] == "voice" else 1


if __name__ == "__main__":
    raise SystemExit(main())
