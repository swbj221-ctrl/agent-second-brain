"""Unified OpenClaw-first outbound delivery layer (transport-agnostic)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from d_brain.config import Settings, get_settings

logger = logging.getLogger(__name__)

DeliveryState = str
RuntimeSender = Callable[[str, str, str], dict[str, Any]]
_RUNTIME_SENDER: RuntimeSender | None = None


@dataclass(slots=True)
class OutboundDeliveryResult:
    ok: bool
    delivery_state: DeliveryState
    channel: str
    target: str
    message_id: str | None = None
    error: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "delivery_state": self.delivery_state,
            "channel": self.channel,
            "target": self.target,
            "message_id": self.message_id,
            "error": self.error,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(slots=True)
class OutboundTarget:
    channel: str
    target: str


class OpenClawOutbound:
    """Transport-agnostic outbound sender for OpenClaw-first runtime paths."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runtime_sender: RuntimeSender | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._runtime_sender = runtime_sender

    def deliver(
        self,
        *,
        target: OutboundTarget,
        text: str,
        trigger: str,
        provider_role: str,
        allow_empty_text: bool = False,
    ) -> OutboundDeliveryResult:
        channel = str(target.channel or "telegram")
        target_id = str(target.target or "")
        if not target_id:
            return OutboundDeliveryResult(
                ok=False,
                delivery_state="no_target",
                channel=channel,
                target=target_id,
                error="target_missing",
            )
        if not text and not allow_empty_text:
            return OutboundDeliveryResult(
                ok=False,
                delivery_state="failed",
                channel=channel,
                target=target_id,
                error="empty_text",
            )

        if self._runtime_sender is None:
            logger.info(
                "Outbound deliver deferred: trigger=%s provider_role=%s channel=%s target=%s delivery_state=deferred",
                trigger,
                provider_role or "n/a",
                channel,
                target_id,
            )
            return OutboundDeliveryResult(
                ok=False,
                delivery_state="deferred",
                channel=channel,
                target=target_id,
                error="runtime_sender_unavailable",
            )

        try:
            payload = self._runtime_sender(channel, target_id, text)
        except Exception as exc:
            logger.warning(
                "Outbound deliver failed: trigger=%s provider_role=%s channel=%s target=%s error=%s",
                trigger,
                provider_role or "n/a",
                channel,
                target_id,
                str(exc),
            )
            return OutboundDeliveryResult(
                ok=False,
                delivery_state="failed",
                channel=channel,
                target=target_id,
                error=f"runtime_sender_exception:{exc}",
            )

        ok = bool(payload.get("ok"))
        state = str(payload.get("delivery_state") or ("sent" if ok else "failed"))
        error = str(payload.get("error") or "")
        logger.info(
            "Outbound deliver: trigger=%s provider_role=%s channel=%s target=%s delivery_state=%s ok=%s",
            trigger,
            provider_role or "n/a",
            channel,
            target_id,
            state,
            ok,
        )
        return OutboundDeliveryResult(
            ok=ok,
            delivery_state=state,
            channel=channel,
            target=target_id,
            message_id=str(payload.get("message_id") or "") or None,
            error=error,
        )

    def send_text(
        self,
        *,
        channel: str,
        target: str | int | None,
        text: str,
        trigger: str = "manual",
        provider_role: str = "cron",
    ) -> OutboundDeliveryResult:
        return self.deliver(
            target=OutboundTarget(channel=str(channel or "telegram"), target=str(target or "")),
            text=text,
            trigger=trigger,
            provider_role=provider_role,
        )

    def send_digest(
        self,
        *,
        channel: str,
        target: str | int | None,
        text: str,
        trigger: str,
        provider_role: str = "cron",
    ) -> OutboundDeliveryResult:
        return self.send_text(
            channel=channel,
            target=target,
            text=text,
            trigger=trigger,
            provider_role=provider_role,
        )

    def send_tts(
        self,
        *,
        channel: str,
        target: str | int | None,
        audio_bytes: bytes | None,
        fallback_text: str = "",
        trigger: str = "manual",
        provider_role: str = "voice_chat",
    ) -> OutboundDeliveryResult:
        if not audio_bytes:
            if not fallback_text:
                return OutboundDeliveryResult(
                    ok=False,
                    delivery_state="failed",
                    channel=str(channel or "telegram"),
                    target=str(target or ""),
                    error="tts_empty_output",
                )
            result = self.send_text(
                channel=channel,
                target=target,
                text=fallback_text,
                trigger=trigger,
                provider_role=provider_role,
            )
            result.fallback_used = True
            result.fallback_reason = "tts_empty_output"
            return result

        # Current sender contract is text-only in this repo path.
        if fallback_text:
            result = self.send_text(
                channel=channel,
                target=target,
                text=fallback_text,
                trigger=trigger,
                provider_role=provider_role,
            )
            result.fallback_used = True
            result.fallback_reason = "tts_transport_unsupported"
            return result

        return OutboundDeliveryResult(
            ok=False,
            delivery_state="failed",
            channel=str(channel or "telegram"),
            target=str(target or ""),
            error="tts_transport_unsupported",
        )


def build_openclaw_outbound(
    settings: Settings | None = None,
    *,
    runtime_sender: RuntimeSender | None = None,
) -> OpenClawOutbound:
    sender = runtime_sender if runtime_sender is not None else _RUNTIME_SENDER
    return OpenClawOutbound(settings=settings, runtime_sender=sender)


def register_runtime_sender(runtime_sender: RuntimeSender | None) -> None:
    """Register runtime outbound sender used by default bridge/scheduler paths."""
    global _RUNTIME_SENDER
    _RUNTIME_SENDER = runtime_sender
    if runtime_sender is None:
        logger.info("OpenClaw outbound runtime sender cleared")
        return
    logger.info("OpenClaw outbound runtime sender registered")


def get_runtime_sender() -> RuntimeSender | None:
    return _RUNTIME_SENDER
