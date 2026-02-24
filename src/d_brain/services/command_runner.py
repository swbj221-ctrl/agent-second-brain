"""Command runner with timeouts and bounded output."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import subprocess
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int | None
    error_code: str | None = None
    error_message: str | None = None
    truncated: bool = False


def _truncate(text: str, max_len: int) -> tuple[str, bool]:
    if max_len <= 0 or len(text) <= max_len:
        return text, False
    return text[: max_len - 3].rstrip() + "...", True


def run_command(
    cmd: Sequence[str],
    *,
    timeout_sec: int = 60,
    max_output_chars: int = 8000,
) -> CommandResult:
    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            ok=False,
            stdout="",
            stderr="",
            returncode=None,
            error_code="timeout",
            error_message="Command timed out.",
        )
    except FileNotFoundError:
        return CommandResult(
            ok=False,
            stdout="",
            stderr="",
            returncode=None,
            error_code="not_found",
            error_message="Command not found.",
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Command execution failed")
        return CommandResult(
            ok=False,
            stdout="",
            stderr="",
            returncode=None,
            error_code="execution_failed",
            error_message=str(exc),
        )

    stdout, stdout_truncated = _truncate(result.stdout or "", max_output_chars)
    stderr, stderr_truncated = _truncate(result.stderr or "", max_output_chars)
    truncated = stdout_truncated or stderr_truncated

    if result.returncode != 0:
        return CommandResult(
            ok=False,
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
            error_code="nonzero_exit",
            error_message="Command failed.",
            truncated=truncated,
        )

    return CommandResult(
        ok=True,
        stdout=stdout,
        stderr=stderr,
        returncode=result.returncode,
        truncated=truncated,
    )
