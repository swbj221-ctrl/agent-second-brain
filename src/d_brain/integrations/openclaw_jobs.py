"""OpenClaw-first transport-agnostic job runner for heartbeat/cron flows."""

from __future__ import annotations

import logging
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from d_brain.config import Settings, get_settings
from d_brain.integrations.heartbeat_runner import build_daily_digest_text, get_digest_target, get_heartbeat_status
from d_brain.integrations.openclaw_outbound import OutboundDeliveryResult, build_openclaw_outbound
from d_brain.memory.ingestion import ingest_job_result
from d_brain.services.sidecar_client import SidecarResult, call_sidecar_action

logger = logging.getLogger(__name__)

JOB_HEARTBEAT_SUMMARY = "heartbeat_summary"
JOB_DAILY_DIGEST = "daily_digest"
JOB_PLAN_REMINDER_DISPATCH = "plan_reminder_dispatch"

RuntimeSender = Callable[[str, str, str], dict[str, Any]]


def _log_job_event(
    *,
    user_id: str | None,
    source_ref: str,
    handler: str,
    ok: bool,
    latency_ms: int,
    fallback_used: bool,
    error_code: str | None,
) -> None:
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "openclaw_bridge",
                "route": "job",
                "user_id": str(user_id or ""),
                "source_ref": source_ref,
                "handler": handler,
                "ok": bool(ok),
                "latency_ms": int(latency_ms),
                "fallback_used": bool(fallback_used),
                "error_code": error_code or "",
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )


@dataclass(slots=True)
class JobContext:
    user_id: str | None = None
    channel: str = "telegram"
    target: str | None = None
    source_ref: str = "openclaw_jobs"
    dry_run: bool = False
    trigger: str = "manual"


@dataclass(slots=True)
class JobResult:
    ok: bool
    job_type: str
    executed: bool
    skipped_reason: str = ""
    outbound_result: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error: str = ""
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "job_type": self.job_type,
            "executed": self.executed,
            "skipped_reason": self.skipped_reason,
            "outbound_result": self.outbound_result or {},
            "metrics": self.metrics or {},
            "error": self.error,
            "payload": self.payload or {},
        }


def _target_from_context(context: JobContext, settings: Settings) -> tuple[str, str]:
    channel = str(context.channel or "telegram")
    if context.target:
        return channel, str(context.target)
    if context.user_id:
        mapped = get_digest_target(context.user_id, settings=settings)
        if mapped and mapped.get("enabled"):
            return str(mapped.get("channel") or "telegram"), str(mapped.get("chat_id") or "")
    return channel, ""


def _dry_run_outbound(channel: str, target: str) -> OutboundDeliveryResult:
    return OutboundDeliveryResult(
        ok=False,
        delivery_state="deferred",
        channel=channel,
        target=target,
        error="dry_run",
        fallback_used=True,
        fallback_reason="dry_run",
    )


def _safe_call_sidecar(action: str, payload: dict[str, Any], *, user_id: str, source_ref: str) -> SidecarResult:
    return call_sidecar_action(action, payload, user_id=user_id, source=source_ref)


def _run_heartbeat_summary(
    *,
    context: JobContext,
    settings: Settings,
    runtime_sender: RuntimeSender | None,
) -> JobResult:
    hb = get_heartbeat_status(settings=settings)
    summary = (
        "Heartbeat summary\n"
        f"status={hb.get('last_status') or 'never'}\n"
        f"provider={hb.get('last_provider') or '-'}\n"
        f"last_run_at={hb.get('last_run_at') or '-'}"
    )
    channel, target = _target_from_context(context, settings)
    metrics = {"items_count": 1}
    if context.dry_run:
        dry = _dry_run_outbound(channel, target)
        return JobResult(
            ok=True,
            job_type=JOB_HEARTBEAT_SUMMARY,
            executed=False,
            skipped_reason="dry_run",
            outbound_result=dry.to_dict(),
            metrics=metrics,
            payload={"text": summary},
        )
    outbound = build_openclaw_outbound(settings=settings, runtime_sender=runtime_sender)
    send_result = outbound.send_text(
        channel=channel,
        target=target,
        text=summary,
        trigger=context.trigger,
        provider_role="heartbeat",
    )
    state = str(send_result.delivery_state or "")
    skipped_reason = "no_target" if state == "no_target" else ""
    executed = state == "sent"
    return JobResult(
        ok=send_result.ok or state in {"deferred", "no_target"},
        job_type=JOB_HEARTBEAT_SUMMARY,
        executed=executed,
        skipped_reason=skipped_reason,
        outbound_result=send_result.to_dict(),
        metrics=metrics,
        error="" if state != "failed" else str(send_result.error or "outbound_failed"),
        payload={"text": summary},
    )


def _run_daily_digest(
    *,
    context: JobContext,
    settings: Settings,
    runtime_sender: RuntimeSender | None,
) -> JobResult:
    digest = build_daily_digest_text(settings=settings)
    text = str(digest.get("text") or "").strip()
    metrics = {"items_count": len(digest.get("sections_present") or [])}
    if not text:
        return JobResult(
            ok=False,
            job_type=JOB_DAILY_DIGEST,
            executed=False,
            skipped_reason="digest_empty",
            metrics=metrics,
            error="digest_empty",
        )
    channel, target = _target_from_context(context, settings)
    if context.dry_run:
        dry = _dry_run_outbound(channel, target)
        return JobResult(
            ok=True,
            job_type=JOB_DAILY_DIGEST,
            executed=False,
            skipped_reason="dry_run",
            outbound_result=dry.to_dict(),
            metrics=metrics,
            payload={"text_preview": text[:280]},
        )
    outbound = build_openclaw_outbound(settings=settings, runtime_sender=runtime_sender)
    send_result = outbound.send_digest(
        channel=channel,
        target=target,
        text=text,
        trigger=context.trigger,
        provider_role="cron",
    )
    state = str(send_result.delivery_state or "")
    return JobResult(
        ok=send_result.ok or state in {"deferred", "no_target"},
        job_type=JOB_DAILY_DIGEST,
        executed=state == "sent",
        skipped_reason="no_target" if state == "no_target" else "",
        outbound_result=send_result.to_dict(),
        metrics=metrics,
        error="" if state != "failed" else str(send_result.error or "outbound_failed"),
        payload={"text_preview": text[:280]},
    )


def _run_plan_reminder_dispatch(
    *,
    context: JobContext,
    settings: Settings,
    runtime_sender: RuntimeSender | None,
) -> JobResult:
    user_id = context.user_id or "system"
    result = _safe_call_sidecar(
        "event_list",
        {"status": "planned", "limit": 5, "offset": 0},
        user_id=user_id,
        source_ref=context.source_ref,
    )
    if result.status != "ok":
        return JobResult(
            ok=False,
            job_type=JOB_PLAN_REMINDER_DISPATCH,
            executed=False,
            skipped_reason="sidecar_error",
            error=str(result.error_code or "sidecar_error"),
            metrics={"items_count": 0},
        )
    events = list((result.data or {}).get("events") or [])
    if not events:
        return JobResult(
            ok=True,
            job_type=JOB_PLAN_REMINDER_DISPATCH,
            executed=False,
            skipped_reason="no_items",
            metrics={"items_count": 0},
        )
    lines = ["Plan reminders:"]
    for item in events[:5]:
        lines.append(f"- {str(item.get('title') or '').strip() or 'untitled'}")
    message = "\n".join(lines)
    channel, target = _target_from_context(context, settings)
    if context.dry_run:
        dry = _dry_run_outbound(channel, target)
        return JobResult(
            ok=True,
            job_type=JOB_PLAN_REMINDER_DISPATCH,
            executed=False,
            skipped_reason="dry_run",
            outbound_result=dry.to_dict(),
            metrics={"items_count": len(events)},
            payload={"text": message},
        )
    outbound = build_openclaw_outbound(settings=settings, runtime_sender=runtime_sender)
    send_result = outbound.send_text(
        channel=channel,
        target=target,
        text=message,
        trigger=context.trigger,
        provider_role="cron",
    )
    state = str(send_result.delivery_state or "")
    return JobResult(
        ok=send_result.ok or state in {"deferred", "no_target"},
        job_type=JOB_PLAN_REMINDER_DISPATCH,
        executed=state == "sent",
        skipped_reason="no_target" if state == "no_target" else "",
        outbound_result=send_result.to_dict(),
        metrics={"items_count": len(events)},
        error="" if state != "failed" else str(send_result.error or "outbound_failed"),
        payload={"text": message},
    )


def run_job(
    job_type: str,
    *,
    context: JobContext | None = None,
    settings: Settings | None = None,
    runtime_sender: RuntimeSender | None = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    ctx = context or JobContext()
    started = time.perf_counter()
    logger.info(
        "OpenClaw job start: job_type=%s user_id=%s channel=%s target=%s dry_run=%s source_ref=%s",
        job_type,
        ctx.user_id or "",
        ctx.channel,
        ctx.target or "",
        bool(ctx.dry_run),
        ctx.source_ref,
    )
    try:
        if job_type == JOB_HEARTBEAT_SUMMARY:
            result = _run_heartbeat_summary(context=ctx, settings=active_settings, runtime_sender=runtime_sender)
        elif job_type == JOB_DAILY_DIGEST:
            result = _run_daily_digest(context=ctx, settings=active_settings, runtime_sender=runtime_sender)
        elif job_type == JOB_PLAN_REMINDER_DISPATCH:
            result = _run_plan_reminder_dispatch(context=ctx, settings=active_settings, runtime_sender=runtime_sender)
        else:
            result = JobResult(
                ok=False,
                job_type=job_type,
                executed=False,
                skipped_reason="unsupported_job",
                error="unsupported_job",
                metrics={"items_count": 0},
            )
    except Exception as exc:
        result = JobResult(
            ok=False,
            job_type=job_type,
            executed=False,
            skipped_reason="exception",
            error=f"job_exception:{exc}",
            metrics={"items_count": 0},
        )
    duration_ms = int((time.perf_counter() - started) * 1000)
    metrics = dict(result.metrics or {})
    metrics["duration_ms"] = duration_ms
    result.metrics = metrics
    outbound_state = ""
    if result.outbound_result:
        outbound_state = str(result.outbound_result.get("delivery_state") or "")
    logger.info(
        "OpenClaw job end: job_type=%s ok=%s executed=%s skipped_reason=%s outbound_state=%s duration_ms=%s error=%s",
        result.job_type,
        bool(result.ok),
        bool(result.executed),
        result.skipped_reason,
        outbound_state,
        duration_ms,
        result.error,
    )
    _log_job_event(
        user_id=ctx.user_id,
        source_ref=ctx.source_ref,
        handler=f"run_job:{result.job_type}",
        ok=bool(result.ok),
        latency_ms=duration_ms,
        fallback_used=bool(outbound_state in {"deferred", "no_target"} or result.skipped_reason in {"dry_run", "no_items"}),
        error_code=(result.error or result.skipped_reason or ""),
    )
    result_payload = result.to_dict()
    try:
        ingest_job_result(
            {
                **result_payload,
                "user_id": ctx.user_id or "",
                "channel": ctx.channel,
                "source_ref": ctx.source_ref,
                "needs_indexing": True,
            },
            settings=active_settings,
        )
    except Exception:
        pass
    return result_payload
