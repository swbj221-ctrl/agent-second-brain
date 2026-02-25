"""Legacy compatibility shim for unified OpenClaw outbound delivery layer."""

from __future__ import annotations

from typing import Any, Callable

from d_brain.config import Settings
from d_brain.integrations.openclaw_outbound import OpenClawOutbound, build_openclaw_outbound


class OpenClawOutboundAdapter:
    """Compatibility wrapper preserving the previous adapter interface."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runtime_sender: Callable[[str, str, str], dict[str, Any]] | None = None,
    ) -> None:
        self._client: OpenClawOutbound = build_openclaw_outbound(
            settings=settings,
            runtime_sender=runtime_sender,
        )

    def send_outbound_message(
        self,
        *,
        channel: str,
        target: str,
        text: str,
        trigger: str,
        provider_role: str = "",
        target_resolved: bool | None = None,
    ) -> dict[str, Any]:
        _ = target_resolved
        result = self._client.send_text(
            channel=channel,
            target=target,
            text=text,
            trigger=trigger,
            provider_role=provider_role or "cron",
        )
        return result.to_dict()


def build_outbound_adapter(
    settings: Settings | None = None,
    *,
    runtime_sender: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> OpenClawOutboundAdapter:
    return OpenClawOutboundAdapter(settings=settings, runtime_sender=runtime_sender)

