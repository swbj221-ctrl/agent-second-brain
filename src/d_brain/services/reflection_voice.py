"""Reflection voice loop helpers (Stage 13 MVP)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from d_brain.services.sidecar_client import call_sidecar_action


@dataclass(slots=True)
class ReflectionSessionState:
    """In-memory reflection session state per user."""

    session_id: int
    started_at: datetime


_ACTIVE_SESSIONS: dict[int, ReflectionSessionState] = {}


def get_active_reflection_session(user_id: int) -> ReflectionSessionState | None:
    return _ACTIVE_SESSIONS.get(user_id)


def set_active_reflection_session(user_id: int, session_id: int) -> ReflectionSessionState:
    state = ReflectionSessionState(
        session_id=session_id,
        started_at=datetime.now(timezone.utc),
    )
    _ACTIVE_SESSIONS[user_id] = state
    return state


def clear_active_reflection_session(user_id: int) -> None:
    _ACTIVE_SESSIONS.pop(user_id, None)


class ReflectionReplyGenerator(Protocol):
    """Protocol for reflection reply generation."""

    async def generate_reply(self, user_text: str, session: ReflectionSessionState) -> str:
        """Generate a reply for the reflection session."""


class PlaceholderReflectionReplyGenerator:
    """Objective, calm placeholder replies for reflection."""

    async def generate_reply(self, user_text: str, session: ReflectionSessionState) -> str:
        _ = session
        cleaned = (user_text or "").strip()
        if not cleaned:
            return "Let's keep it concrete. What happened, and what is one verifiable detail?"
        if cleaned.endswith("?"):
            return (
                "Here is a neutral take: there may be multiple explanations. "
                "What evidence supports the most likely one?"
            )
        if len(cleaned.split()) < 5:
            return "Keep it specific. What happened right before this, and what changed after?"
        if "feel" in cleaned.lower():
            return "Noted. What triggered that feeling, and what is one observable fact?"
        return "Summarize the key facts in one sentence, then name the main uncertainty."


class ReflectionVoiceService:
    """Coordinator for reflection session storage and reply generation."""

    def __init__(self, reply_generator: ReflectionReplyGenerator | None = None) -> None:
        self.reply_generator = reply_generator or PlaceholderReflectionReplyGenerator()

    def start_session(self, user_id: int, source_ref: str) -> tuple[int | None, str | None]:
        _ = source_ref
        result = call_sidecar_action("reflection_session_create", {}, user_id)
        if result.status != "ok":
            return None, result.error_message or "Failed to create reflection session."
        session_id = (result.data or {}).get("session_id")
        if session_id is None:
            return None, "Reflection session creation failed."
        set_active_reflection_session(user_id, int(session_id))
        return int(session_id), None

    def close_session_by_id(
        self, user_id: int, session_id: int, summary_text: str | None = None
    ) -> str | None:
        payload = {"session_id": int(session_id)}
        if summary_text:
            payload["summary_text"] = summary_text
        result = call_sidecar_action("reflection_session_close", payload, user_id)
        if result.status != "ok":
            return result.error_message or "Failed to close reflection session."
        state = get_active_reflection_session(user_id)
        if state and state.session_id == int(session_id):
            clear_active_reflection_session(user_id)
        return None

    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        state = get_active_reflection_session(user_id)
        if not state:
            return None, "No active reflection session. Use /reflect start."
        append_result = call_sidecar_action(
            "reflection_turn_append",
            {"session_id": state.session_id, "role": "user", "content": text},
            user_id,
        )
        if append_result.status != "ok":
            return None, append_result.error_message or "Failed to save reflection turn."
        reply = await self.reply_generator.generate_reply(text, state)
        append_reply = call_sidecar_action(
            "reflection_turn_append",
            {"session_id": state.session_id, "role": "assistant", "content": reply},
            user_id,
        )
        if append_reply.status != "ok":
            return None, append_reply.error_message or "Failed to save assistant turn."
        return reply, None
