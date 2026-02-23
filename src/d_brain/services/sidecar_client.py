"""Sidecar client helper for Telegram adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from d_brain.sidecar.dispatcher import handle_request


@dataclass(slots=True)
class SidecarResult:
    """Normalized result from a sidecar action call."""

    request_id: str
    status: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


def call_sidecar_action(
    action: str,
    payload: dict[str, Any] | None,
    user_id: int | str,
    source: str = "telegram",
    request_id: str | None = None,
) -> SidecarResult:
    """Call sidecar dispatcher with the standard request envelope."""

    req_id = request_id or uuid4().hex
    raw_request = {
        "request_id": req_id,
        "user_id": str(user_id),
        "action": action,
        "payload": payload or {},
        "metadata": {"source": source},
    }
    response = handle_request(raw_request)
    error = response.get("error") or {}
    return SidecarResult(
        request_id=response.get("request_id", req_id),
        status=response.get("status", "error"),
        data=response.get("data"),
        error_code=error.get("code"),
        error_message=error.get("message"),
    )
