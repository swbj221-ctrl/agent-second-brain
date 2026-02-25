"""Thin OpenClaw cron adapter wrapper with safe local fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from d_brain.config import Settings, get_settings
from d_brain.integrations.heartbeat_runner import (
    list_registered_jobs,
    record_scheduler_sync,
    run_registered_job,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SchedulerAdapterResult:
    ok: bool
    status: str
    execution_mode: str
    trigger_source: str
    job: str
    payload: dict[str, Any]


class OpenClawSchedulerAdapter:
    """Adapter boundary for OpenClaw cron runtime integration.

    If a direct OpenClaw runtime callable is unavailable, it falls back to the
    in-process registered job execution path.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runtime_invoker: Callable[[str], dict[str, Any]] | None = None,
        runtime_syncer: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._runtime_invoker = runtime_invoker
        self._runtime_syncer = runtime_syncer

    def register_default_jobs(self) -> int:
        # No-op in this repo: OpenClaw runtime registration happens outside d_brain.
        return len(list_registered_jobs(settings=self._settings))

    def list_jobs(self) -> list[dict[str, Any]]:
        return list_registered_jobs(settings=self._settings)

    def sync_jobs(
        self,
        job_specs: list[dict[str, Any]],
        *,
        trigger_source: str = "manual_bridge",
    ) -> dict[str, Any]:
        if self._runtime_syncer is not None:
            payload = self._runtime_syncer(job_specs)
            execution_mode = "scheduled_openclaw"
            status = str(payload.get("status") or "unknown")
            ok = bool(payload.get("ok"))
        else:
            payload = {
                "ok": True,
                "status": "ok",
                "jobs": job_specs,
                "note": "runtime_syncer_unavailable",
            }
            execution_mode = "stub_fallback"
            status = "ok"
            ok = True

        record_scheduler_sync(
            settings=self._settings,
            trigger_source=trigger_source,
            execution_mode=execution_mode,
            status=status,
            synced_jobs=job_specs,
        )
        logger.info(
            "OpenClaw scheduler adapter sync: trigger=%s execution_mode=%s status=%s jobs=%s",
            trigger_source,
            execution_mode,
            status,
            len(job_specs),
        )
        return {
            "ok": ok,
            "status": status,
            "execution_mode": execution_mode,
            "trigger_source": trigger_source,
            "jobs": job_specs,
            "payload": payload,
        }

    def run_job_now(self, job_name: str, *, user_id: int | str | None = None) -> SchedulerAdapterResult:
        return self._run(job_name, trigger_source="manual_bridge", user_id=user_id)

    def run_job_scheduled(self, job_name: str, *, user_id: int | str | None = None) -> SchedulerAdapterResult:
        return self._run(job_name, trigger_source="scheduled_openclaw", user_id=user_id)

    def _run(self, job_name: str, *, trigger_source: str, user_id: int | str | None) -> SchedulerAdapterResult:
        if self._runtime_invoker is not None:
            payload = self._runtime_invoker(job_name)
            logger.info(
                "OpenClaw scheduler adapter: trigger=%s job=%s execution_mode=scheduled_openclaw status=%s",
                trigger_source,
                job_name,
                payload.get("status", "unknown"),
            )
            return SchedulerAdapterResult(
                ok=bool(payload.get("ok")),
                status=str(payload.get("status") or "unknown"),
                execution_mode="scheduled_openclaw",
                trigger_source=trigger_source,
                job=job_name,
                payload=payload,
            )

        payload = run_registered_job(
            job_name,
            settings=self._settings,
            trigger_source=trigger_source,
            user_id=user_id,
        )
        logger.info(
            "OpenClaw scheduler adapter: trigger=%s job=%s execution_mode=stub_fallback status=%s",
            trigger_source,
            job_name,
            payload.get("status", "unknown"),
        )
        return SchedulerAdapterResult(
            ok=bool(payload.get("ok")),
            status=str(payload.get("status") or "unknown"),
            execution_mode="stub_fallback",
            trigger_source=trigger_source,
            job=job_name,
            payload=payload,
        )


def build_scheduler_adapter(
    settings: Settings | None = None,
    *,
    runtime_invoker: Callable[[str], dict[str, Any]] | None = None,
    runtime_syncer: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
) -> OpenClawSchedulerAdapter:
    return OpenClawSchedulerAdapter(
        settings=settings,
        runtime_invoker=runtime_invoker,
        runtime_syncer=runtime_syncer,
    )
