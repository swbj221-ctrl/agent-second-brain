"""Sidecar error types."""

from dataclasses import dataclass


@dataclass(slots=True)
class SidecarError(Exception):
    """Structured error for sidecar request handling."""

    code: str
    message: str


INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "Temporary error. Please try again."
