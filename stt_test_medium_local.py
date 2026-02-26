from faster_whisper import WhisperModel

audio = r"C:\Users\User\Downloads\test_ru_en.m4a"

model = WhisperModel("medium", device="cuda", compute_type="int8_float32")

segments, info = model.transcribe(
    audio,
    language=None,                 # пусть детектит, но...
    task="transcribe",             # не translate
    temperature=0.0,               # без рандома
    beam_size=10,                  # точнее (медленнее)
    best_of=1,                     # важно: best_of>1 иногда “улучшает” смыслом
    patience=1.0,
    condition_on_previous_text=False,  # чтобы RU контекст не “съедал” EN
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=200),
    # ключ: просим НЕ переводить и НЕ исправлять
    initial_prompt=(
        "Transcribe verbatim. This audio contains Russian and English. "
        "Keep English words in Latin letters. Do NOT translate or paraphrase. "
        "If you hear 'How are you', write exactly: How are you?"
    ),
    suppress_tokens=[-1],          # оставь так; suppress_tokens лучше не трогать
)

print("Language (detected):", info.language, "prob:", info.language_probability)
for s in segments:
    print(f"[{s.start:6.2f} -> {s.end:6.2f}] {s.text}")
