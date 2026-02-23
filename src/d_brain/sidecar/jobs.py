"""Job definitions for the sidecar scheduler."""

from __future__ import annotations


def noop_job() -> None:
    """No-op job for scheduler smoke tests."""
    return None
