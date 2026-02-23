"""Sidecar error types."""

from dataclasses import dataclass


@dataclass(slots=True)
class SidecarError(Exception):
    """Structured error for sidecar request handling."""

    code: str
    message: str
