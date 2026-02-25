"""Unified OpenClaw-first E2E smoke (no aiogram polling, no network).

JSONL output: one line per case.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


def ensure_paths() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def load_adapter(root: Path):
    adapter_path = root / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
    spec = importlib.util.spec_from_file_location("openclaw_main_adapter_e2e_smoke", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter: {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@dataclass
class CaseTrace:
    case: str
    route: str
    bridge_handler_used: str = ""
    action_called: bool = False
    action_name: str | None = None
    ingestion_called: bool = False
    ingestion_ok: bool | None = None
    ingestion_indexed: str | None = None
    ingestion_deferred: bool | None = None
    outbound_kind: str = "none"
    fallback_used: bool = False
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self, ok: bool) -> str:
        payload = {
            "case": self.case,
            "ok": bool(ok),
            "route": self.route,
            "bridge_handler_used": self.bridge_handler_used or "",
            "action_called": {"ok": bool(self.action_called), "name": self.action_name},
            "ingestion_called": bool(self.ingestion_called),
            "ingestion_ok": self.ingestion_ok,
            "indexed": self.ingestion_indexed,
            "deferred": self.ingestion_deferred,
            "outbound_kind": self.outbound_kind,
            "fallback_used": bool(self.fallback_used),
            "error": self.error,
        }
        if self.extra:
            payload.update(self.extra)
        return json.dumps(payload, ensure_ascii=True)


class FakeRoute:
    def __init__(self, task_type: str = "smoke", provider: str = "deterministic") -> None:
        self.task_type = task_type
        self.selected_provider = provider
        self.selected_model = "smoke-model"
        self.fallback_used = False
        self.allowed = True
        self.reason = ""


class FakeSTTResult:
    def __init__(self, text: str, language: str | None) -> None:
        self.ok = True
        self.text = text
        self.language = language
        self.provider_ref = "fake-stt"
        self.error_code = None
        self.error_message = None


class FakeTTSResult:
    def __init__(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> None:
        self.ok = True
        self.audio_bytes = audio_bytes
        self.mime_type = mime_type
        self.provider_ref = "fake-tts"
        self.error_code = None
        self.error_message = None


class FakeSTT:
    def __init__(self, text: str, recorder: dict[str, Any]) -> None:
        self._text = text
        self._recorder = recorder

    async def transcribe(self, audio_bytes: bytes, language: str | None = None):  # pragma: no cover - smoke helper
        _ = audio_bytes
        self._recorder["stt_language"] = language
        return FakeSTTResult(self._text, language)


class FakeTTS:
    def __init__(self, audio_bytes: bytes) -> None:
        self._audio_bytes = audio_bytes

    async def speak(self, text: str, voice: str | None = None):  # pragma: no cover - smoke helper
        _ = text, voice
        return FakeTTSResult(self._audio_bytes)


class FakeReflectionService:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        self._recorder["reflection_calls"] = int(self._recorder.get("reflection_calls", 0)) + 1
        self._recorder["last_reflection_user_id"] = user_id
        self._recorder["last_reflection_text"] = text
        return f"Reflection reply: {text}", None


class PatchSet:
    def __init__(self) -> None:
        self._patches: list[tuple[Any, str, Any]] = []

    def set(self, obj: Any, attr: str, value: Any) -> None:
        self._patches.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def restore(self) -> None:
        for obj, attr, old in reversed(self._patches):
            setattr(obj, attr, old)
        self._patches.clear()


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}:{exc}"


def _set_common_env(vault_dir: Path) -> None:
    os.environ["VAULT_PATH"] = str(vault_dir)
    os.environ["TELEGRAM_BOT_TOKEN"] = "openclaw-e2e-smoke-token"
    os.environ["OPENAI_API_KEY"] = "openclaw-e2e-smoke-openai"
    os.environ["MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE"] = "false"
    os.environ["MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE"] = "false"
    os.environ["MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK"] = "false"
    os.environ["MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK"] = "true"


def _build_fake_sidecar(recorder: dict[str, Any]) -> Callable[..., Any]:
    events = recorder.setdefault("events", [])

    def _call_sidecar(action: str, payload: dict[str, Any], user_id: str | int, source: str, request_id: str | None = None):
        _ = request_id
        recorder["last_sidecar_action"] = action
        recorder["last_sidecar_payload"] = dict(payload or {})
        recorder["last_sidecar_user_id"] = str(user_id)
        recorder["last_sidecar_source"] = source
        if action == "event_create":
            title = str((payload or {}).get("title") or "").strip() or "untitled"
            event_id = len(events) + 1
            reminder_id = event_id
            event = {"id": event_id, "title": title, "status": "planned"}
            events.append(event)
            return SimpleNamespace(
                status="ok",
                data={"event_id": event_id, "reminder_id": reminder_id},
                error_code=None,
                error_message=None,
            )
        if action == "event_list":
            return SimpleNamespace(
                status="ok",
                data={"events": list(events)},
                error_code=None,
                error_message=None,
            )
        return SimpleNamespace(status="ok", data={"action": action}, error_code=None, error_message=None)

    return _call_sidecar


def _wrap_bridge_ingestion(bridge_module: Any, trace: CaseTrace, *, force_exception: bool = False, bad_indexer: bool = False):
    original = bridge_module.ingest_message_event

    def _wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        trace.ingestion_called = True
        if force_exception:
            raise RuntimeError("smoke_ingestion_failure")
        if bad_indexer:
            def _failing_indexer(record: dict[str, Any]) -> bool:
                _ = record
                raise RuntimeError("smoke_indexer_down")

            result = original(payload, indexer=_failing_indexer)
        else:
            result = original(payload)
        trace.ingestion_ok = bool(result.get("ok"))
        trace.ingestion_indexed = str(result.get("indexed") or "")
        trace.ingestion_deferred = trace.ingestion_indexed == "deferred"
        return result

    return _wrapped


def _wrap_job_ingestion(jobs_module: Any, trace: CaseTrace):
    original = jobs_module.ingest_job_result

    def _wrapped(payload: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        trace.ingestion_called = True
        result = original(payload, *args, **kwargs)
        trace.ingestion_ok = bool(result.get("ok"))
        trace.ingestion_indexed = str(result.get("indexed") or "")
        trace.ingestion_deferred = trace.ingestion_indexed == "deferred"
        return result

    return _wrapped


def _record_outbound_from_adapter_response(trace: CaseTrace, response: dict[str, Any]) -> None:
    if response.get("audio_intent"):
        trace.outbound_kind = "tts"
    elif str(response.get("text") or ""):
        trace.outbound_kind = "text"
    else:
        trace.outbound_kind = "none"
    meta = response.get("meta") or {}
    diagnostics = response.get("diagnostics") or {}
    trace.fallback_used = bool(meta.get("fallback_reason")) or bool(diagnostics.get("tts_empty_output"))


def _run_command_case(
    *,
    adapter: Any,
    bridge_module: Any,
    trace: CaseTrace,
    text: str,
    recorder: dict[str, Any],
    source_ref: str,
    force_ingest_exception: bool = False,
) -> tuple[bool, dict[str, Any]]:
    patches = PatchSet()
    try:
        patches.set(bridge_module, "call_sidecar_action", _build_fake_sidecar(recorder))
        patches.set(bridge_module, "resolve_route", lambda *args, **kwargs: FakeRoute(task_type="command"))  # noqa: ARG005
        patches.set(bridge_module, "ingest_message_event", _wrap_bridge_ingestion(
            bridge_module,
            trace,
            force_exception=force_ingest_exception,
            bad_indexer=False,
        ))

        def _dispatch_bridge_command(*args: Any, **kwargs: Any):
            trace.bridge_handler_used = "dispatch_command"
            return bridge_module.dispatch_command(*args, **kwargs)

        patches.set(adapter, "dispatch_bridge_command", _dispatch_bridge_command)
        message = {
            "text": text,
            "user_id": 123,
            "chat_id": 123,
            "message_id": 1,
            "request_id": f"e2e:{trace.case}",
            "source_ref": source_ref,
        }
        response = adapter.main_handler_response(message)
        _record_outbound_from_adapter_response(trace, response)

        action_name = recorder.get("last_sidecar_action")
        trace.action_called = bool(action_name)
        trace.action_name = str(action_name) if action_name else None
        if trace.ingestion_ok is None and force_ingest_exception:
            trace.ingestion_ok = False
            trace.ingestion_indexed = None
            trace.ingestion_deferred = None

        ok = bool(response.get("handled")) and response.get("route") == "command" and trace.bridge_handler_used == "dispatch_command"
        return ok, response
    finally:
        patches.restore()


def _run_voice_case(
    *,
    adapter: Any,
    bridge_module: Any,
    trace: CaseTrace,
    recorder: dict[str, Any],
    source_ref: str,
    mode: str | None,
    audio_bytes: bytes | None,
    message_text: str | None,
    tts_audio_bytes: bytes,
    force_bad_indexer: bool = False,
) -> tuple[bool, dict[str, Any]]:
    patches = PatchSet()
    try:
        patches.set(bridge_module, "resolve_route", lambda *args, **kwargs: FakeRoute(task_type="voice"))  # noqa: ARG005
        patches.set(bridge_module, "ingest_message_event", _wrap_bridge_ingestion(
            bridge_module,
            trace,
            force_exception=False,
            bad_indexer=force_bad_indexer,
        ))
        patches.set(bridge_module, "build_stt_adapter", lambda settings=None: FakeSTT("privet smoke", recorder))  # noqa: ARG005
        patches.set(bridge_module, "build_tts_adapter", lambda settings=None: FakeTTS(tts_audio_bytes))  # noqa: ARG005
        patches.set(bridge_module, "ReflectionVoiceService", lambda: FakeReflectionService(recorder))
        patches.set(bridge_module, "get_active_reflection_session", lambda user_id: None)  # noqa: ARG005
        patches.set(bridge_module, "get_active_tutor_session", lambda user_id: None)  # noqa: ARG005

        def _dispatch_voice_from_message(*args: Any, **kwargs: Any):
            trace.bridge_handler_used = "dispatch_voice_from_message"
            return bridge_module.dispatch_voice_from_message(*args, **kwargs)

        patches.set(adapter, "dispatch_voice_from_message", _dispatch_voice_from_message)

        message = {
            "user_id": 123,
            "chat_id": 123,
            "message_id": 2,
            "request_id": f"e2e:{trace.case}",
            "source_ref": source_ref,
        }
        if mode is not None:
            message["mode"] = mode
        if audio_bytes is not None:
            message["audio_bytes"] = audio_bytes
            message["has_media"] = True
        if message_text is not None:
            message["text"] = message_text

        response = adapter.main_handler_response(message)
        _record_outbound_from_adapter_response(trace, response)
        trace.action_called = int(recorder.get("reflection_calls", 0)) > 0
        trace.action_name = "reflection.handle_user_turn" if trace.action_called else None
        trace.extra["stt_language"] = recorder.get("stt_language")
        trace.extra["voice_status"] = response.get("status")
        trace.extra["voice_error_code"] = response.get("error_code")
        trace.extra["diagnostics"] = {
            "transcript_only_warning": bool(((response.get("diagnostics") or {}).get("transcript_only_warning"))),
            "tts_empty_output": bool(((response.get("diagnostics") or {}).get("tts_empty_output"))),
        }
        ok = bool(response.get("handled")) and response.get("route") in {"voice", "text"} and trace.bridge_handler_used == "dispatch_voice_from_message"
        return ok, response
    finally:
        patches.restore()


def _run_job_case(*, jobs_module: Any, trace: CaseTrace) -> tuple[bool, dict[str, Any]]:
    patches = PatchSet()
    try:
        trace.bridge_handler_used = "run_job"
        patches.set(jobs_module, "get_heartbeat_status", lambda settings=None: {  # noqa: ARG005
            "last_status": "ok",
            "last_provider": "local",
            "last_run_at": "2026-02-24T22:00:00+00:00",
        })
        patches.set(jobs_module, "build_daily_digest_text", lambda settings=None: {  # noqa: ARG005
            "text": "Daily digest smoke text",
            "sections_present": ["projects", "tasks"],
        })
        patches.set(jobs_module, "get_digest_target", lambda user_id, settings=None: {  # noqa: ARG005
            "enabled": True,
            "channel": "telegram",
            "chat_id": "123",
        })
        patches.set(jobs_module, "ingest_job_result", _wrap_job_ingestion(jobs_module, trace))

        sent_payloads: list[dict[str, Any]] = []

        def _runtime_sender(channel: str, target: str, text: str) -> dict[str, Any]:
            sent_payloads.append({"channel": channel, "target": target, "text": text})
            return {"ok": True, "delivery_state": "sent", "message_id": f"m{len(sent_payloads)}"}

        heartbeat = jobs_module.run_job(
            jobs_module.JOB_HEARTBEAT_SUMMARY,
            context=jobs_module.JobContext(
                user_id="123",
                channel="telegram",
                target="123",
                source_ref="e2e:job:heartbeat",
                trigger="smoke",
            ),
            runtime_sender=_runtime_sender,
        )
        digest = jobs_module.run_job(
            jobs_module.JOB_DAILY_DIGEST,
            context=jobs_module.JobContext(
                user_id="123",
                channel="telegram",
                target="123",
                source_ref="e2e:job:digest",
                trigger="smoke",
            ),
            runtime_sender=_runtime_sender,
        )
        trace.outbound_kind = "text" if sent_payloads else "none"
        trace.fallback_used = False
        trace.action_called = False
        trace.action_name = None
        trace.extra["job_results"] = [
            {
                "job_type": heartbeat.get("job_type"),
                "ok": heartbeat.get("ok"),
                "outbound_state": (heartbeat.get("outbound_result") or {}).get("delivery_state"),
                "duration_ms": (heartbeat.get("metrics") or {}).get("duration_ms"),
            },
            {
                "job_type": digest.get("job_type"),
                "ok": digest.get("ok"),
                "outbound_state": (digest.get("outbound_result") or {}).get("delivery_state"),
                "duration_ms": (digest.get("metrics") or {}).get("duration_ms"),
            },
        ]
        trace.extra["runtime_sender_calls"] = len(sent_payloads)
        ok = bool(
            heartbeat.get("ok")
            and digest.get("ok")
            and (heartbeat.get("outbound_result") or {}).get("delivery_state") == "sent"
            and (digest.get("outbound_result") or {}).get("delivery_state") == "sent"
            and trace.ingestion_called
        )
        return ok, {"heartbeat": heartbeat, "digest": digest}
    finally:
        patches.restore()


def main() -> int:
    root = ensure_paths()
    adapter = load_adapter(root)
    import d_brain.integrations.openclaw_bridge as bridge  # noqa: WPS433
    import d_brain.integrations.openclaw_jobs as openclaw_jobs  # noqa: WPS433

    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-e2e-smoke-") as tmp:
        vault_dir = Path(tmp) / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        _set_common_env(vault_dir)

        def run_case(trace: CaseTrace, runner: Callable[[], tuple[bool, Any]]) -> None:
            nonlocal failures
            try:
                ok, _ = runner()
            except Exception as exc:
                trace.error = _safe_error(exc)
                ok = False
            if not ok and trace.error is None:
                trace.error = trace.error or "assertion_failed"
            print(trace.to_json(ok))
            if not ok:
                failures += 1

        command_state: dict[str, Any] = {"events": []}

        trace_help = CaseTrace(case="command_help_e2e", route="command")

        def _runner_help():
            ok, response = _run_command_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_help,
                text="/help",
                recorder=command_state,
                source_ref="123:1001",
            )
            trace_help.extra["response_text"] = str(response.get("text") or "")[:200]
            ok = ok and not trace_help.action_called and trace_help.outbound_kind == "text" and trace_help.ingestion_called
            return ok, response

        run_case(trace_help, _runner_help)

        trace_plan_add = CaseTrace(case="command_plan_add_e2e", route="command")

        def _runner_plan_add():
            ok, response = _run_command_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_plan_add,
                text="/plan add e2e smoke plan",
                recorder=command_state,
                source_ref="123:1002",
            )
            trace_plan_add.extra["response_text"] = str(response.get("text") or "")[:200]
            ok = ok and trace_plan_add.action_name == "event_create" and trace_plan_add.ingestion_called
            ok = ok and trace_plan_add.outbound_kind == "text" and len(command_state.get("events") or []) == 1
            return ok, response

        run_case(trace_plan_add, _runner_plan_add)

        trace_plan_list = CaseTrace(case="command_plan_list_e2e", route="command")

        def _runner_plan_list():
            ok, response = _run_command_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_plan_list,
                text="/plan list",
                recorder=command_state,
                source_ref="123:1003",
            )
            response_text = str(response.get("text") or "")
            trace_plan_list.extra["response_text"] = response_text[:200]
            trace_plan_list.extra["events_count"] = len(command_state.get("events") or [])
            ok = ok and trace_plan_list.action_name == "event_list" and trace_plan_list.ingestion_called
            ok = ok and trace_plan_list.outbound_kind == "text" and ("e2e smoke plan" in response_text.lower())
            return ok, response

        run_case(trace_plan_list, _runner_plan_list)

        trace_voice_text = CaseTrace(case="voice_ru_text_reply_e2e", route="voice")

        def _runner_voice_text():
            recorder: dict[str, Any] = {}
            ok, response = _run_voice_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_voice_text,
                recorder=recorder,
                source_ref="123:2001",
                mode="reflection",
                audio_bytes=b"voice-bytes-ru",
                message_text=None,
                tts_audio_bytes=b"",
            )
            ok = ok and response.get("route") == "voice"
            ok = ok and trace_voice_text.action_called and trace_voice_text.ingestion_called
            ok = ok and trace_voice_text.extra.get("stt_language") == "ru"
            ok = ok and trace_voice_text.outbound_kind == "text" and trace_voice_text.fallback_used
            return ok, response

        run_case(trace_voice_text, _runner_voice_text)

        trace_voice_tts = CaseTrace(case="voice_ru_tts_reply_e2e", route="voice")

        def _runner_voice_tts():
            recorder: dict[str, Any] = {}
            ok, response = _run_voice_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_voice_tts,
                recorder=recorder,
                source_ref="123:2002",
                mode="reflection",
                audio_bytes=b"voice-bytes-ru",
                message_text=None,
                tts_audio_bytes=b"ogg-bytes",
            )
            ok = ok and response.get("route") == "voice"
            ok = ok and trace_voice_tts.action_called and trace_voice_tts.ingestion_called
            ok = ok and trace_voice_tts.extra.get("stt_language") == "ru"
            ok = ok and trace_voice_tts.outbound_kind == "tts" and not trace_voice_tts.fallback_used
            return ok, response

        run_case(trace_voice_tts, _runner_voice_tts)

        trace_transcript_warning = CaseTrace(case="transcript_only_warning_e2e", route="voice")

        def _runner_transcript_warning():
            recorder: dict[str, Any] = {}
            ok, response = _run_voice_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_transcript_warning,
                recorder=recorder,
                source_ref="123:2003",
                mode=None,
                audio_bytes=None,
                message_text="Transcript: auto generated text",
                tts_audio_bytes=b"",
            )
            diag = (trace_transcript_warning.extra.get("diagnostics") or {})
            ok = ok and response.get("route") == "text"
            ok = ok and not trace_transcript_warning.action_called and not trace_transcript_warning.ingestion_called
            ok = ok and trace_transcript_warning.outbound_kind == "text"
            ok = ok and bool(diag.get("transcript_only_warning"))
            return ok, response

        run_case(trace_transcript_warning, _runner_transcript_warning)

        trace_job = CaseTrace(case="job_heartbeat_digest_e2e", route="job")

        def _runner_job():
            ok, payload = _run_job_case(
                jobs_module=openclaw_jobs,
                trace=trace_job,
            )
            states = [item.get("outbound_state") for item in (trace_job.extra.get("job_results") or [])]
            ok = ok and trace_job.outbound_kind == "text" and states == ["sent", "sent"]
            return ok, payload

        run_case(trace_job, _runner_job)

        trace_ingest_fail = CaseTrace(case="ingestion_failure_nonfatal_e2e", route="command")

        def _runner_ingest_fail():
            isolated_state: dict[str, Any] = {"events": list(command_state.get("events") or [])}
            ok, response = _run_command_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_ingest_fail,
                text="/help",
                recorder=isolated_state,
                source_ref="123:3001",
                force_ingest_exception=True,
            )
            trace_ingest_fail.extra["response_text"] = str(response.get("text") or "")[:200]
            trace_ingest_fail.fallback_used = False
            ok = ok and not trace_ingest_fail.action_called
            ok = ok and trace_ingest_fail.ingestion_called and trace_ingest_fail.ingestion_ok is False
            ok = ok and trace_ingest_fail.outbound_kind == "text"
            return ok, response

        run_case(trace_ingest_fail, _runner_ingest_fail)

        trace_indexer_deferred = CaseTrace(case="indexer_unavailable_nonfatal_e2e", route="voice")

        def _runner_indexer_deferred():
            recorder: dict[str, Any] = {}
            ok, response = _run_voice_case(
                adapter=adapter,
                bridge_module=bridge,
                trace=trace_indexer_deferred,
                recorder=recorder,
                source_ref="123:3002",
                mode="reflection",
                audio_bytes=b"voice-bytes-ru",
                message_text=None,
                tts_audio_bytes=b"ogg-bytes",
                force_bad_indexer=True,
            )
            ok = ok and response.get("route") == "voice"
            ok = ok and trace_indexer_deferred.action_called and trace_indexer_deferred.ingestion_called
            ok = ok and trace_indexer_deferred.ingestion_deferred is True
            ok = ok and trace_indexer_deferred.ingestion_indexed == "deferred"
            return ok, response

        run_case(trace_indexer_deferred, _runner_indexer_deferred)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
