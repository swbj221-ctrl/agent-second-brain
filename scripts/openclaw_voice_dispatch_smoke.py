"""Smoke checks for transport-agnostic OpenClaw voice dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import d_brain.integrations.openclaw_bridge as bridge
from d_brain.integrations.openclaw_bridge import dispatch_command_response, dispatch_voice
from d_brain.services.transcription import STTResult
from d_brain.services.tts import TTSResult


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.last_language: str | None = None

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes
        self.last_language = language
        return STTResult(text=self.text, language=language, provider_ref="fake-stt")


class FakeSequenceSTT:
    def __init__(self, by_language: dict[str, STTResult | str]) -> None:
        self.by_language = by_language
        self.calls: list[str | None] = []

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes
        self.calls.append(language)
        key = str(language or "")
        value = self.by_language.get(key)
        if value is None:
            value = self.by_language.get("*", "")
        if isinstance(value, STTResult):
            return value
        return STTResult(text=str(value or ""), language=language, provider_ref="fake-stt")


class FakeTTS:
    def __init__(self, audio_bytes: bytes) -> None:
        self.audio_bytes = audio_bytes
        self.calls = 0
        self.mime_type = "audio/ogg"

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        _ = text, voice
        self.calls += 1
        return TTSResult(audio_bytes=self.audio_bytes, mime_type=self.mime_type, provider_ref="fake-tts")


class FakeAudioTTS(FakeTTS):
    def __init__(self, audio_bytes: bytes, mime_type: str) -> None:
        super().__init__(audio_bytes)
        self.mime_type = mime_type


class FakeTutorService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        _ = user_id
        return f"Tutor reply: {text}", None


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _find_json_event(messages: list[str], event_name: str, *, stage: str | None = None) -> dict[str, object] | None:
    for raw in reversed(messages):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("event") != event_name:
            continue
        if stage is not None and data.get("stage") != stage:
            continue
        return data
    return None


async def _run() -> int:
    failures = 0
    log_handler = _ListHandler()
    bridge.logger.addHandler(log_handler)
    bridge.logger.setLevel(logging.INFO)
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "voice-dispatch-smoke-token")
    os.environ.setdefault("OPENAI_API_KEY", "voice-smoke-openai-key")
    os.environ.setdefault("MODEL_ROUTE_MAIN_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_VOICE_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK", "false")
    os.environ.setdefault("MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE", "false")
    vault_path = Path(tempfile.mkdtemp(prefix="voice-dispatch-smoke-")) / "vault"
    vault_path.mkdir(parents=True, exist_ok=True)
    os.environ["VAULT_PATH"] = str(vault_path)

    def _restore_env(name: str, prev: str | None) -> None:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev

    ru_stt = FakeSTT("privet")
    ru_result = await dispatch_voice(
        user_id=100,
        source_ref="smoke:ru",
        audio_bytes=b"ru-audio",
        media_declared=True,
        mode_hint="default",
        stt=ru_stt,
    )
    ru_ok = ru_stt.last_language == "ru" and ru_result.get("status") == "ok"
    print("case=ru_default")
    print(f"ok={ru_ok}")
    print(f"stt_language={ru_stt.last_language}")
    if not ru_ok:
        failures += 1

    ru_cyr_sample = "Привет, как дела?"
    ru_cyr_stt = FakeSTT(ru_cyr_sample)
    ru_cyr_result = await dispatch_voice(
        user_id=101,
        source_ref="smoke:ru-cyr",
        audio_bytes=b"ru-cyr-audio",
        media_declared=True,
        mode_hint="default",
        stt=ru_cyr_stt,
    )
    ru_cyr_diag = ru_cyr_result.get("diagnostics") or {}
    ru_cyr_text = str(ru_cyr_result.get("text") or "")
    ru_cyr_ok = (
        ru_cyr_result.get("status") == "ok"
        and ru_cyr_stt.last_language == "ru"
        and ("Привет" in ru_cyr_text or ru_cyr_diag.get("transcript_len") == len(ru_cyr_sample))
    )
    print("case=ru_cyrillic_transcript_preserved")
    print(f"ok={ru_cyr_ok}")
    print(f"stt_language={ru_cyr_stt.last_language}")
    print(f"response_text_preview={ru_cyr_text[:80]}")
    if not ru_cyr_ok:
        failures += 1
    en_stt = FakeSTT("hello")
    en_result = await dispatch_voice(
        user_id=100,
        source_ref="smoke:en",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=en_stt,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    en_ok = (
        en_stt.last_language == "en"
        and en_result.get("audio_intent") == "sendVoice"
        and bool(en_result.get("audio_bytes"))
    )
    print("case=en_tutor_mode")
    print(f"ok={en_ok}")
    print(f"stt_language={en_stt.last_language}")
    print(f"audio_intent={en_result.get('audio_intent')}")
    if not en_ok:
        failures += 1

    transcript_only = await dispatch_voice(
        user_id=100,
        source_ref="smoke:transcript-only",
        message_text="Transcript: hello there",
        media_declared=False,
    )
    transcript_diag = transcript_only.get("diagnostics") or {}
    transcript_ok = transcript_only.get("status") == "ok" and bool(
        transcript_diag.get("transcript_only_warning")
    )
    print("case=transcript_only_warning")
    print(f"ok={transcript_ok}")
    print(f"transcript_only_warning={transcript_diag.get('transcript_only_warning', False)}")
    if not transcript_ok:
        failures += 1

    empty_tts = await dispatch_voice(
        user_id=100,
        source_ref="smoke:empty-tts",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=FakeTTS(b""),
        tutor_service=FakeTutorService(),
    )
    empty_diag = empty_tts.get("diagnostics") or {}
    empty_ok = (
        empty_tts.get("status") == "ok"
        and empty_tts.get("audio_intent") is None
        and bool(empty_diag.get("tts_empty_output"))
        and "Tutor reply:" in str(empty_tts.get("text") or "")
    )
    print("case=empty_tts_fallback")
    print(f"ok={empty_ok}")
    print(f"audio_intent={empty_tts.get('audio_intent')}")
    print(f"tts_empty_output={empty_diag.get('tts_empty_output', False)}")
    if not empty_ok:
        failures += 1

    dispatch_command_response("/prefs voice off", user_id=201, source_ref="smoke:prefs:voice-off")
    tts_off = FakeTTS(b"ogg-bytes")
    voice_off = await dispatch_voice(
        user_id=201,
        source_ref="smoke:voice-off",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=tts_off,
        tutor_service=FakeTutorService(),
    )
    voice_off_diag = voice_off.get("diagnostics") or {}
    voice_off_ok = (
        voice_off.get("status") == "ok"
        and voice_off.get("audio_intent") is None
        and bool(voice_off_diag.get("voice_reply_disabled"))
        and tts_off.calls == 0
    )
    print("case=voice_reply_off_pref")
    print(f"ok={voice_off_ok}")
    print(f"voice_reply_disabled={voice_off_diag.get('voice_reply_disabled', False)}")
    print(f"tts_calls={tts_off.calls}")
    if not voice_off_ok:
        failures += 1

    dispatch_command_response("/prefs lang en_tutor", user_id=202, source_ref="smoke:prefs:lang")
    en_pref_stt = FakeSTT("hello from pref")
    en_pref = await dispatch_voice(
        user_id=202,
        source_ref="smoke:en-pref",
        audio_bytes=b"pref-audio",
        media_declared=True,
        stt=en_pref_stt,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    en_pref_diag = en_pref.get("diagnostics") or {}
    en_pref_ok = (
        en_pref_stt.last_language == "en"
        and en_pref_diag.get("mode") == "tutor"
        and en_pref.get("status") == "ok"
    )
    print("case=language_mode_en_tutor_pref")
    print(f"ok={en_pref_ok}")
    print(f"stt_language={en_pref_stt.last_language}")
    print(f"mode={en_pref_diag.get('mode')}")
    if not en_pref_ok:
        failures += 1

    dispatch_command_response("/prefs brevity short", user_id=203, source_ref="smoke:prefs:brevity")
    short_warning = await dispatch_voice(
        user_id=203,
        source_ref="smoke:brevity-short",
        message_text="Transcript: hello there",
        media_declared=False,
    )
    short_text = str(short_warning.get("text") or "")
    short_ok = short_warning.get("status") == "ok" and len(short_text) <= 64
    print("case=brevity_short_transcript_warning")
    print(f"ok={short_ok}")
    print(f"text_len={len(short_text)}")
    print(f"text={short_text}")
    if not short_ok:
        failures += 1

    media_priority_stt = FakeSTT("real media transcript")
    media_priority = await dispatch_voice(
        user_id=204,
        source_ref="smoke:media-priority",
        message_text="Transcript: auto transcript should lose",
        audio_bytes=b"real-audio",
        media_declared=True,
        stt=media_priority_stt,
    )
    media_priority_diag = media_priority.get("diagnostics") or {}
    media_priority_ok = (
        media_priority.get("handled") is True
        and media_priority_diag.get("transcript_only_warning") is not True
        and media_priority_diag.get("transcript_len") == len("real media transcript")
    )
    print("case=media_over_transcript_priority")
    print(f"ok={media_priority_ok}")
    print(f"transcript_only_warning={media_priority_diag.get('transcript_only_warning', False)}")
    print(f"transcript_len={media_priority_diag.get('transcript_len')}")
    if not media_priority_ok:
        failures += 1

    send_audio = await dispatch_voice(
        user_id=205,
        source_ref="smoke:send-audio-intent",
        audio_bytes=b"audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=FakeAudioTTS(b"mp3-bytes", "audio/mpeg"),
        tutor_service=FakeTutorService(),
    )
    send_audio_ok = send_audio.get("audio_intent") == "sendAudio" and bool(send_audio.get("audio_bytes"))
    print("case=send_audio_intent_selection")
    print(f"ok={send_audio_ok}")
    print(f"audio_intent={send_audio.get('audio_intent')}")
    if not send_audio_ok:
        failures += 1

    # forced Telegram STT language override (non-tutor)
    prev_env_lang = os.environ.get("TELEGRAM_STT_LANGUAGE")
    os.environ["TELEGRAM_STT_LANGUAGE"] = "ru"
    forced_lang_stt = FakeSTT("privet override")
    forced_lang = await dispatch_voice(
        user_id=206,
        source_ref="smoke:forced-lang",
        audio_bytes=b"ru-audio",
        media_declared=True,
        stt=forced_lang_stt,
    )
    if prev_env_lang is None:
        os.environ.pop("TELEGRAM_STT_LANGUAGE", None)
    else:
        os.environ["TELEGRAM_STT_LANGUAGE"] = prev_env_lang
    forced_lang_diag = forced_lang.get("diagnostics") or {}
    forced_lang_ok = forced_lang_stt.last_language == "ru" and forced_lang_diag.get("stt_language_source") in {"env", "default"}
    print("case=telegram_stt_language_env_override")
    print(f"ok={forced_lang_ok}")
    print(f"stt_language={forced_lang_stt.last_language}")
    print(f"stt_language_source={forced_lang_diag.get('stt_language_source')}")
    if not forced_lang_ok:
        failures += 1

    # multipass helpers (parsing)
    parsed_langs = bridge._parse_stt_multipass_langs("auto, ru, en,ru,xx", default_lang="ru")
    parse_langs_ok = parsed_langs == ["auto", "ru", "en"]
    print("case=stt_multipass_langs_parse")
    print(f"ok={parse_langs_ok}")
    print(f"langs={parsed_langs}")
    if not parse_langs_ok:
        failures += 1

    # multipass disabled -> default behavior unchanged (single pass only)
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    os.environ.pop("TELEGRAM_STT_MULTIPASS", None)
    os.environ.pop("TELEGRAM_STT_MIXED_HEURISTIC", None)
    single_seq_stt = FakeSequenceSTT({"ru": "hello one two three"})
    single_pass = await dispatch_voice(
        user_id=209,
        source_ref="smoke:single-pass-default",
        audio_bytes=b"mixed-audio",
        media_declared=True,
        stt=single_seq_stt,
    )
    single_pass_diag = single_pass.get("diagnostics") or {}
    single_pass_ok = (
        single_pass.get("status") == "ok"
        and single_seq_stt.calls == ["ru"]
        and single_pass_diag.get("stt_multipass") is False
    )
    print("case=stt_multipass_disabled_single_pass")
    print(f"ok={single_pass_ok}")
    print(f"calls={single_seq_stt.calls}")
    if not single_pass_ok:
        failures += 1
    _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
    _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)

    # multipass + heuristic: prefer mixed RU+EN transcript over english-only candidate
    log_handler.messages.clear()
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    prev_lang = os.environ.get("TELEGRAM_STT_LANGUAGE")
    os.environ["TELEGRAM_STT_MULTIPASS"] = "1"
    os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = "1"
    os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = "auto,ru,en"
    os.environ.pop("TELEGRAM_STT_LANGUAGE", None)
    multipass_stt = FakeSequenceSTT(
        {
            "ru": "РїСЂРёРІРµС‚ С‚РµСЃС‚РѕРІР°СЏ Р·Р°РїРёСЃСЊ hello one two three РїСЏС‚СЊ РІРѕСЃРµРјСЊ",
            "en": "hello one two three",
        }
    )
    multipass_result = await dispatch_voice(
        user_id=210,
        source_ref="smoke:multipass-mixed",
        audio_bytes=b"mixed-audio",
        media_declared=True,
        stt=multipass_stt,
    )
    multipass_diag = multipass_result.get("diagnostics") or {}
    mp_selected_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_selected") or {}
    mp_candidate_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_candidate") or {}
    multipass_ok = multipass_result.get("status") == "ok"
    multipass_text = str(multipass_result.get("text") or "")
    # dispatch_voice final text is assistant response; verify selected transcript via diagnostics/logs
    multipass_selected_ok = (
        multipass_diag.get("stt_language") == "ru"
        and mp_selected_log.get("selectedLang") == "ru"
        and mp_selected_log.get("stage") == "stt_multipass_selected"
        and mp_candidate_log.get("stage") == "stt_multipass_candidate"
        and "heuristic" in str(mp_selected_log.get("selectionReason") or "")
    )
    print("case=stt_multipass_mixed_prefers_ru_en_candidate")
    print(f"ok={multipass_ok and multipass_selected_ok}")
    print(f"calls={multipass_stt.calls}")
    print(f"selected_lang={multipass_diag.get('stt_language')}")
    print(f"selection_reason={mp_selected_log.get('selectionReason')}")
    print(f"response_status={multipass_result.get('status')}")
    print(f"response_text_preview={multipass_text[:80]}")
    if not (multipass_ok and multipass_selected_ok):
        failures += 1
    _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
    _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)
    _restore_env("TELEGRAM_STT_MULTIPASS_LANGS", prev_mpl)
    _restore_env("TELEGRAM_STT_LANGUAGE", prev_lang)

    # multipass + heuristic: reject transliterated pseudo-RU latin candidate when Cyrillic mixed candidate exists
    log_handler.messages.clear()
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    prev_lang = os.environ.get("TELEGRAM_STT_LANGUAGE")
    os.environ["TELEGRAM_STT_MULTIPASS"] = "1"
    os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = "1"
    os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = "auto,ru,en"
    os.environ.pop("TELEGRAM_STT_LANGUAGE", None)
    mixed_phrase_ru = "РџСЂРёРІРµС‚, how are you, С‚С‹ РјРµРЅСЏ РїРѕРЅРёРјР°РµС€СЊ?"
    mixed_phrase_translit = "priyyyav, how are you, ti menya ponimaesh?"
    translit_seq_stt = FakeSequenceSTT(
        {
            "ru": mixed_phrase_ru,
            "en": mixed_phrase_translit,
        }
    )
    translit_pick = await dispatch_voice(
        user_id=212,
        source_ref="smoke:mixed-translit-penalty",
        audio_bytes=b"mixed-translit-audio",
        media_declared=True,
        stt=translit_seq_stt,
    )
    translit_diag = translit_pick.get("diagnostics") or {}
    translit_selected_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_selected") or {}
    translit_candidate_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_candidate") or {}
    translit_pick_ok = (
        translit_pick.get("status") == "ok"
        and translit_diag.get("stt_language") == "ru"
        and translit_selected_log.get("selectedLang") == "ru"
        and translit_selected_log.get("candidateHasCyrillic") is True
        and translit_selected_log.get("candidateHasLatin") is True
        and "heuristic" in str(translit_selected_log.get("selectionReason") or "")
        and "РџСЂРёРІРµС‚" in str(translit_pick.get("text") or "")
    )
    print("case=stt_multipass_mixed_preserves_ru_en_no_fake_latin")
    print(f"ok={translit_pick_ok}")
    print(f"calls={translit_seq_stt.calls}")
    print(f"selected_lang={translit_selected_log.get('selectedLang')}")
    print(f"candidate_translit_like={translit_candidate_log.get('candidateTranslitLikeLatin')}")
    print(f"response_text_preview={str(translit_pick.get('text') or '')[:120]}")
    if not translit_pick_ok:
        failures += 1
    _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
    _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)
    _restore_env("TELEGRAM_STT_MULTIPASS_LANGS", prev_mpl)
    _restore_env("TELEGRAM_STT_LANGUAGE", prev_lang)

    # multipass + heuristic: keep short RU leading token in mixed RU+EN phrase
    # instead of collapsing to latin-only lookalikes ("priya/riviere how are you").
    log_handler.messages.clear()
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    prev_lang = os.environ.get("TELEGRAM_STT_LANGUAGE")
    os.environ["TELEGRAM_STT_MULTIPASS"] = "1"
    os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = "1"
    os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = "auto,ru,en"
    os.environ.pop("TELEGRAM_STT_LANGUAGE", None)
    ru_lead_seq_stt = FakeSequenceSTT(
        {
            "auto": "priya how are you",
            "ru": "Привет how are you",
            "en": "riviere how are you",
        }
    )
    ru_lead_pick = await dispatch_voice(
        user_id=213,
        source_ref="smoke:mixed-ru-lead-retention",
        audio_bytes=b"mixed-ru-lead",
        media_declared=True,
        stt=ru_lead_seq_stt,
    )
    ru_lead_diag = ru_lead_pick.get("diagnostics") or {}
    ru_lead_selected_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_selected") or {}
    ru_lead_pick_ok = (
        ru_lead_pick.get("status") == "ok"
        and ru_lead_diag.get("stt_language") == "ru"
        and ru_lead_selected_log.get("selectedLang") == "ru"
        and ru_lead_selected_log.get("candidateHasCyrillic") is True
        and "Привет how are you" in str(ru_lead_pick.get("text") or "")
    )
    print("case=stt_multipass_mixed_short_ru_lead_not_collapsed")
    print(f"ok={ru_lead_pick_ok}")
    print(f"calls={ru_lead_seq_stt.calls}")
    print(f"selected_lang={ru_lead_selected_log.get('selectedLang')}")
    print(f"response_text_preview={str(ru_lead_pick.get('text') or '')[:120]}")
    if not ru_lead_pick_ok:
        failures += 1
    _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
    _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)
    _restore_env("TELEGRAM_STT_MULTIPASS_LANGS", prev_mpl)
    _restore_env("TELEGRAM_STT_LANGUAGE", prev_lang)

    # multipass fallback to auto/default when ru is empty/worse
    log_handler.messages.clear()
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    os.environ["TELEGRAM_STT_MULTIPASS"] = "1"
    os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = "1"
    os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = "auto,ru,en"
    fallback_seq_stt = FakeSequenceSTT(
        {
            "ru": "",
            "en": "hello one two three",
        }
    )
    fallback_mp = await dispatch_voice(
        user_id=211,
        source_ref="smoke:multipass-auto-better",
        audio_bytes=b"mixed-audio",
        media_declared=True,
        stt=fallback_seq_stt,
    )
    fallback_diag = fallback_mp.get("diagnostics") or {}
    fallback_selected_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_selected") or {}
    fallback_ok = fallback_mp.get("status") == "ok" and fallback_diag.get("stt_language") in {"ru", "en"}
    # default path lang is ru, but if ru transcript empty and en has text, selected should be en
    fallback_pick_ok = fallback_selected_log.get("selectedLang") == "en"
    print("case=stt_multipass_auto_when_ru_empty")
    print(f"ok={fallback_ok and fallback_pick_ok}")
    print(f"calls={fallback_seq_stt.calls}")
    print(f"selected_lang={fallback_selected_log.get('selectedLang')}")
    if not (fallback_ok and fallback_pick_ok):
        failures += 1
    _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
    _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)
    _restore_env("TELEGRAM_STT_MULTIPASS_LANGS", prev_mpl)

    # conversion failure branch (monkeypatch preprocess hook; no ffmpeg dependency)
    log_handler.messages.clear()
    original_preprocess = bridge._preprocess_audio_for_stt
    try:
        def _fake_preprocess(*, audio_bytes, audio_path, diagnostics):  # type: ignore[no-redef]
            _ = audio_bytes, audio_path
            diagnostics["pipeline_error_code"] = "audio_conversion_failed"
            diagnostics["pipeline_error_message"] = "synthetic conversion failure"
            return None, None, "audio_conversion_failed"

        bridge._preprocess_audio_for_stt = _fake_preprocess  # type: ignore[assignment]
        conv_fail = await dispatch_voice(
            user_id=207,
            source_ref="smoke:conv-fail",
            audio_bytes=b"ogg-like",
            media_declared=True,
            input_context={
                "messageKind": "voice",
                "hasVoice": True,
                "mimeType": "audio/ogg",
                "telegramVoiceNote": True,
                "requestId": "smoke-conv-fail",
            },
            stt=FakeSTT("should not be used"),
        )
    finally:
        bridge._preprocess_audio_for_stt = original_preprocess  # type: ignore[assignment]
    conv_fail_diag = conv_fail.get("diagnostics") or {}
    conv_fail_log = (
        _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_request_error")
        or _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_preprocess_error")
        or {}
    )
    conv_fail_ok = (
        conv_fail.get("status") == "error"
        and conv_fail_diag.get("pipeline_error_code") == "audio_conversion_failed"
        and "traceback" not in str(conv_fail.get("text") or "").lower()
        and "ffmpeg" not in str(conv_fail.get("text") or "").lower()
    )
    print("case=audio_conversion_failed_fallback")
    print(f"ok={conv_fail_ok}")
    print(f"status={conv_fail.get('status')}")
    print(f"pipeline_error_code={conv_fail_diag.get('pipeline_error_code')}")
    print(f"pipeline_log_error_code={conv_fail_log.get('pipelineErrorCode', '')}")
    if conv_fail_diag.get("pipeline_error_code") != "audio_conversion_failed":
        failures += 1
    if "traceback" in str(conv_fail.get("text") or "").lower() or "ffmpeg" in str(conv_fail.get("text") or "").lower():
        failures += 1
    if conv_fail_log and conv_fail_log.get("pipelineErrorCode") not in {"", "audio_conversion_failed"}:
        failures += 1
    if not conv_fail_ok:
        failures += 1

    # ffmpeg missing branch (deterministic via monkeypatch; no ffmpeg dependency)
    log_handler.messages.clear()
    prev_norm = os.environ.get("TELEGRAM_STT_NORMALIZE_AUDIO")
    os.environ["TELEGRAM_STT_NORMALIZE_AUDIO"] = "1"
    original_which = bridge.shutil.which
    try:
        bridge.shutil.which = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        ffmpeg_missing = await dispatch_voice(
            user_id=208,
            source_ref="smoke:ffmpeg-missing",
            audio_bytes=b"compressed-audio",
            media_declared=True,
            input_context={
                "messageKind": "voice",
                "hasVoice": True,
                "mimeType": "audio/ogg",
                "telegramVoiceNote": True,
                "requestId": "smoke-ffmpeg-missing",
            },
            stt=FakeSTT("should not run"),
        )
    finally:
        bridge.shutil.which = original_which  # type: ignore[assignment]
        if prev_norm is None:
            os.environ.pop("TELEGRAM_STT_NORMALIZE_AUDIO", None)
        else:
            os.environ["TELEGRAM_STT_NORMALIZE_AUDIO"] = prev_norm
    ffmpeg_missing_diag = ffmpeg_missing.get("diagnostics") or {}
    ffmpeg_missing_log = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_preprocess_error") or {}
    ffmpeg_missing_text = str(ffmpeg_missing.get("text") or "").lower()
    ffmpeg_missing_ok = (
        ffmpeg_missing.get("status") == "error"
        and ffmpeg_missing_diag.get("pipeline_error_code") == "ffmpeg_missing"
        and "traceback" not in ffmpeg_missing_text
        and "ffmpeg" not in ffmpeg_missing_text
        and ffmpeg_missing_log.get("pipelineErrorCode") == "ffmpeg_missing"
        and ffmpeg_missing_log.get("normalizeAudioEnabled") is True
        and ffmpeg_missing_log.get("ffmpegPathFound") is False
        and ffmpeg_missing_log.get("inputMimeType") == "audio/ogg"
    )
    print("case=ffmpeg_missing_fallback")
    print(f"ok={ffmpeg_missing_ok}")
    print(f"status={ffmpeg_missing.get('status')}")
    print(f"pipeline_error_code={ffmpeg_missing_diag.get('pipeline_error_code')}")
    print(f"pipeline_log_error_code={ffmpeg_missing_log.get('pipelineErrorCode', '')}")
    print(f"normalize_audio_enabled={ffmpeg_missing_log.get('normalizeAudioEnabled')}")
    print(f"ffmpeg_path_found={ffmpeg_missing_log.get('ffmpegPathFound')}")
    if not ffmpeg_missing_ok:
        failures += 1

    # transcript-only safety: translit-like garbage asks for clarification in RU (no hallucinated normalization)
    translit_only = await dispatch_voice(
        user_id=213,
        source_ref="smoke:translit-only",
        message_text="priyyyav kagdela",
        media_declared=False,
    )
    translit_only_diag = translit_only.get("diagnostics") or {}
    translit_only_text = str(translit_only.get("text") or "").lower()
    translit_only_ok = (
        translit_only.get("status") == "ok"
        and translit_only_diag.get("transcript_only_clarify_reason") == "translit_like_latin"
        and ("?" in translit_only_text or "повтор" in translit_only_text or "имели в виду" in translit_only_text)
    )
    print("case=transcript_only_translit_garbage_clarification_ru")
    print(f"ok={translit_only_ok}")
    print(f"clarify_reason={translit_only_diag.get('transcript_only_clarify_reason')}")
    print(f"text={str(translit_only.get('text') or '')[:120]}")
    if not translit_only_ok:
        failures += 1

    layout_ru = await dispatch_voice(
        user_id=214,
        source_ref="smoke:layout-en-to-ru",
        message_text="ghbdtn",
        media_declared=False,
    )
    layout_ru_diag = layout_ru.get("diagnostics") or {}
    layout_ru_text = str(layout_ru.get("text") or "").lower()
    layout_ru_ok = (
        layout_ru.get("status") == "ok"
        and layout_ru_diag.get("transcript_only_clarify_reason") == "layout_en_to_ru"
        and ("привет" in layout_ru_text or "имели в виду" in layout_ru_text)
    )
    print("case=text_layout_typo_ghbdtn_confirmation")
    print(f"ok={layout_ru_ok}")
    print(f"clarify_reason={layout_ru_diag.get('transcript_only_clarify_reason')}")
    print(f"text={str(layout_ru.get('text') or '')[:120]}")
    if not layout_ru_ok:
        failures += 1

    layout_en = await dispatch_voice(
        user_id=215,
        source_ref="smoke:layout-ru-to-en",
        message_text="\u0440\u0443\u0434\u0434\u0449",
        media_declared=False,
    )
    layout_en_diag = layout_en.get("diagnostics") or {}
    layout_en_text = str(layout_en.get("text") or "").lower()
    layout_en_ok = (
        layout_en.get("status") == "ok"
        and layout_en_diag.get("transcript_only_clarify_reason") == "layout_ru_to_en"
        and "hello" in layout_en_text
    )
    print("case=text_layout_typo_layout_ru_to_en_confirmation")
    print(f"ok={layout_en_ok}")
    print(f"clarify_reason={layout_en_diag.get('transcript_only_clarify_reason')}")
    print(f"text={str(layout_en.get('text') or '')[:120]}")
    if not layout_en_ok:
        failures += 1

    english_text_only = await dispatch_voice(
        user_id=216,
        source_ref="smoke:text-english-valid",
        message_text="hello how are you",
        media_declared=False,
    )
    english_text_only_diag = english_text_only.get("diagnostics") or {}
    english_text_only_text = str(english_text_only.get("text") or "").lower()
    english_text_only_ok = (
        english_text_only.get("status") in {"ok", ""}
        and not bool(english_text_only_diag.get("transcript_only_clarification"))
        and "имели в виду" not in english_text_only_text
        and "повтор" not in english_text_only_text
    )
    print("case=transcript_only_valid_english_kept")
    print(f"ok={english_text_only_ok}")
    print(f"transcript_only_clarification={bool(english_text_only_diag.get('transcript_only_clarification'))}")
    print(f"text={str(english_text_only.get('text') or '')[:120]}")
    if not english_text_only_ok:
        failures += 1

    bridge.logger.removeHandler(log_handler)

    return 0 if failures == 0 else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())

