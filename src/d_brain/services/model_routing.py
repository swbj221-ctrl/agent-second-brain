"""Model routing policy for reasoning and utility tasks."""

from __future__ import annotations

from dataclasses import dataclass

from d_brain.config import Settings

PROVIDER_OPENAI = "openai"
PROVIDER_LOCAL = "local"
PROVIDER_DETERMINISTIC = "deterministic"

TASK_MAIN_REASONING = "MAIN_REASONING"
TASK_VOICE_REPLY_REASONING = "VOICE_REPLY_REASONING"
TASK_HEARTBEAT = "HEARTBEAT"
TASK_CRON_SUMMARY = "CRON_SUMMARY"
TASK_LIGHT_CLASSIFICATION = "LIGHT_CLASSIFICATION"
TASK_COMMAND_STATUS = "COMMAND_STATUS"
TASK_MAIN_CHAT = TASK_MAIN_REASONING
TASK_VOICE_CHAT = TASK_VOICE_REPLY_REASONING
TASK_CRON = TASK_CRON_SUMMARY
TASK_UTILITY_SEARCH_SUMMARY = TASK_LIGHT_CLASSIFICATION

_ALL_TASKS = {
    TASK_MAIN_REASONING,
    TASK_VOICE_REPLY_REASONING,
    TASK_HEARTBEAT,
    TASK_CRON_SUMMARY,
    TASK_LIGHT_CLASSIFICATION,
    TASK_COMMAND_STATUS,
}
_UTILITY_TASKS = {
    TASK_HEARTBEAT,
    TASK_CRON_SUMMARY,
    TASK_LIGHT_CLASSIFICATION,
}
_REASONING_TASKS = {
    TASK_MAIN_REASONING,
    TASK_VOICE_REPLY_REASONING,
}


@dataclass(slots=True)
class RouteDecision:
    task_type: str
    selected_provider: str
    selected_model: str
    fallback_used: bool
    allowed: bool
    reason: str | None = None

    def to_diagnostics(self) -> dict[str, object]:
        return {
            "task_type": self.task_type,
            "provider": self.selected_provider,
            "model": self.selected_model,
            "fallback_used": self.fallback_used,
            "allowed": self.allowed,
            "reason": self.reason or "",
        }


def _normalize_provider(value: str, default: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {PROVIDER_OPENAI, PROVIDER_LOCAL, PROVIDER_DETERMINISTIC}:
        return lowered
    return default


def _task_provider(task_type: str, settings: Settings) -> str:
    if task_type == TASK_MAIN_REASONING:
        return _normalize_provider(settings.model_route_main_reasoning_provider, PROVIDER_OPENAI)
    if task_type == TASK_VOICE_REPLY_REASONING:
        return _normalize_provider(settings.model_route_voice_reasoning_provider, PROVIDER_OPENAI)
    if task_type == TASK_HEARTBEAT:
        return _normalize_provider(settings.model_route_heartbeat_provider, PROVIDER_LOCAL)
    if task_type == TASK_CRON_SUMMARY:
        return _normalize_provider(settings.model_route_cron_summary_provider, PROVIDER_LOCAL)
    if task_type == TASK_LIGHT_CLASSIFICATION:
        return _normalize_provider(settings.model_route_light_classification_provider, PROVIDER_LOCAL)
    if task_type == TASK_COMMAND_STATUS:
        return _normalize_provider(
            settings.model_route_command_status_provider,
            PROVIDER_DETERMINISTIC,
        )
    return PROVIDER_DETERMINISTIC


def _model_ref(provider: str, *, task_type: str, settings: Settings) -> str:
    if provider == PROVIDER_OPENAI:
        if task_type in _UTILITY_TASKS:
            return settings.openai_utility_model.strip() or settings.openai_main_model.strip() or "openai"
        return settings.openai_main_model.strip() or "openai"
    if provider == PROVIDER_LOCAL:
        return settings.local_utility_model_ref.strip() or "local"
    return "deterministic"


def _provider_available(provider: str, settings: Settings) -> bool:
    if provider == PROVIDER_DETERMINISTIC:
        return True
    if provider == PROVIDER_OPENAI:
        if settings.model_route_force_openai_unavailable:
            return False
        return bool(settings.openai_api_key.strip())
    if provider == PROVIDER_LOCAL:
        return not settings.model_route_force_local_unavailable
    return False


def resolve_route(task_type: str, settings: Settings) -> RouteDecision:
    normalized_task = task_type.strip().upper()
    if normalized_task not in _ALL_TASKS:
        normalized_task = TASK_COMMAND_STATUS

    primary = _task_provider(normalized_task, settings)
    if _provider_available(primary, settings):
        return RouteDecision(
            task_type=normalized_task,
            selected_provider=primary,
            selected_model=_model_ref(primary, task_type=normalized_task, settings=settings),
            fallback_used=False,
            allowed=True,
        )

    if (
        primary == PROVIDER_LOCAL
        and normalized_task in _UTILITY_TASKS
        and settings.model_route_allow_local_to_openai_fallback
        and _provider_available(PROVIDER_OPENAI, settings)
    ):
        return RouteDecision(
            task_type=normalized_task,
            selected_provider=PROVIDER_OPENAI,
            selected_model=_model_ref(
                PROVIDER_OPENAI,
                task_type=normalized_task,
                settings=settings,
            ),
            fallback_used=True,
            allowed=True,
            reason="local_unavailable_fallback_to_openai",
        )

    if (
        primary == PROVIDER_OPENAI
        and normalized_task in _REASONING_TASKS
        and settings.model_route_allow_openai_to_local_fallback
        and _provider_available(PROVIDER_LOCAL, settings)
    ):
        return RouteDecision(
            task_type=normalized_task,
            selected_provider=PROVIDER_LOCAL,
            selected_model=_model_ref(PROVIDER_LOCAL, task_type=normalized_task, settings=settings),
            fallback_used=True,
            allowed=True,
            reason="openai_unavailable_explicit_fallback_to_local",
        )

    return RouteDecision(
        task_type=normalized_task,
        selected_provider=primary,
        selected_model=_model_ref(primary, task_type=normalized_task, settings=settings),
        fallback_used=False,
        allowed=False,
        reason=f"{primary}_unavailable",
    )


def resolve_provider_for_task(task_kind: str, settings: Settings) -> RouteDecision:
    """Resolve provider/model for high-level task kinds."""
    normalized = (task_kind or "").strip().lower()
    mapping = {
        "main_chat": TASK_MAIN_CHAT,
        "voice_chat": TASK_VOICE_CHAT,
        "heartbeat": TASK_HEARTBEAT,
        "cron": TASK_CRON,
        "utility_search_summary": TASK_UTILITY_SEARCH_SUMMARY,
        "light_classification": TASK_LIGHT_CLASSIFICATION,
        "command_status": TASK_COMMAND_STATUS,
    }
    task_type = mapping.get(normalized, task_kind.strip().upper() if task_kind else TASK_COMMAND_STATUS)
    return resolve_route(task_type, settings)
