from faster_whisper import WhisperModel

PROMPT = (
    "Transcribe verbatim. This audio contains Russian and English. "
    "Keep English words in Latin letters. Do NOT translate or paraphrase."
)

class STT:
    def __init__(self, model_name="medium", device="cuda", compute_type="int8_float32"):
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe_file(self, path: str) -> str:
        segments, info = self.model.transcribe(
            path,
            task="transcribe",
            temperature=0.0,
            beam_size=10,
            best_of=1,
            patience=1.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=200),
            initial_prompt=PROMPT,
        )
        return " ".join(s.text.strip() for s in segments).strip()