"""Minimal scheduler skeleton with a job registry."""

from __future__ import annotations

from collections.abc import Callable

from .jobs import (
    noop_job,
    reminder_tick_job,
    news_briefing_deliver_telegram_job,
    news_briefing_generate_daily_job,
)

JobFunc = Callable[[], None]


class JobRegistry:
    """Registry for sidecar jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobFunc] = {}

    def register(self, name: str, func: JobFunc) -> None:
        if not name:
            raise ValueError("Job name must be non-empty.")
        self._jobs[name] = func

    def get(self, name: str) -> JobFunc:
        if name not in self._jobs:
            raise KeyError(f"Job not registered: {name}")
        return self._jobs[name]

    def list_jobs(self) -> list[str]:
        return sorted(self._jobs.keys())


class Scheduler:
    """Minimal scheduler runner."""

    def __init__(self, registry: JobRegistry) -> None:
        self._registry = registry

    def run_once(self, job_name: str) -> None:
        job = self._registry.get(job_name)
        job()


def build_default_registry() -> JobRegistry:
    registry = JobRegistry()
    registry.register("noop", noop_job)
    registry.register("reminder_tick", reminder_tick_job)
    registry.register("news_briefing_generate_daily", news_briefing_generate_daily_job)
    registry.register("news_briefing_deliver_telegram", news_briefing_deliver_telegram_job)
    return registry
