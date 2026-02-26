from faster_whisper import WhisperModel

audio = r"C:\Users\User\Downloads\test_ru_en.m4a"

model = WhisperModel("medium", device="cuda", compute_type="int8")  # для GTX 1060 чаще норм

segments, info = model.transcribe(
    audio,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
    task="transcribe",
    temperature=0.0,

    # ВАЖНО: не фиксируем language="ru"
    language=None,

    # (2) подсказка — как ты просил
    initial_prompt=(
        "1) This audio contains BOTH Russian and English.\n"
        "2) Keep English words in Latin letters (do NOT transliterate into Cyrillic).\n"
        "Do not drop Russian words."
    ),

    beam_size=5,
    best_of=5,
    condition_on_previous_text=False,
)

print("Language (detected):", info.language, "prob:", info.language_probability)
for s in segments:
    print(f"[{s.start:6.2f} -> {s.end:6.2f}] {s.text}")