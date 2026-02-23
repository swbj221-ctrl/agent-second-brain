"""English tutor flow helpers (Stage 12 MVP)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from d_brain.services.sidecar_client import call_sidecar_action


@dataclass(slots=True)
class TutorSessionState:
    """In-memory tutor session state per user."""

    session_id: int
    started_at: datetime
    target_minutes: int | None = None
    topic_id: int | None = None


_ACTIVE_SESSIONS: dict[int, TutorSessionState] = {}


def get_active_tutor_session(user_id: int) -> TutorSessionState | None:
    return _ACTIVE_SESSIONS.get(user_id)


def set_active_tutor_session(
    user_id: int,
    session_id: int,
    target_minutes: int | None = None,
    topic_id: int | None = None,
) -> TutorSessionState:
    state = TutorSessionState(
        session_id=session_id,
        started_at=datetime.now(timezone.utc),
        target_minutes=target_minutes,
        topic_id=topic_id,
    )
    _ACTIVE_SESSIONS[user_id] = state
    return state


def clear_active_tutor_session(user_id: int) -> None:
    _ACTIVE_SESSIONS.pop(user_id, None)


class TutorReplyGenerator(Protocol):
    """Protocol for English tutor reply generation."""

    async def generate_reply(self, user_text: str, session: TutorSessionState) -> str:
        """Generate a reply for the tutor session."""


class PlaceholderTutorReplyGenerator:
    """Simple placeholder generator that keeps conversation flowing."""

    async def generate_reply(self, user_text: str, session: TutorSessionState) -> str:
        cleaned = (user_text or "").strip()
        if not cleaned:
            return "Let's keep going. What would you like to talk about next?"
        if cleaned.endswith("?"):
            return "That is a good question. What do you think is the best answer?"
        if len(cleaned.split()) < 5:
            return "Thanks! Can you say a bit more about that?"
        return "Thanks for sharing. Could you elaborate on that a little more?"


class EnglishTutorService:
    """Coordinator for tutor session storage and reply generation."""

    def __init__(self, reply_generator: TutorReplyGenerator | None = None) -> None:
        self.reply_generator = reply_generator or PlaceholderTutorReplyGenerator()

    def start_session(
        self,
        user_id: int,
        source_ref: str,
        target_minutes: int | None = None,
        topic_id: int | None = None,
    ) -> tuple[int | None, str | None]:
        _ = source_ref
        payload: dict[str, int] = {}
        if topic_id is not None:
            payload["topic_id"] = int(topic_id)
        result = call_sidecar_action("english_session_create", payload, user_id)
        if result.status != "ok":
            return None, result.error_message or "Failed to create session."
        session_id = (result.data or {}).get("session_id")
        if session_id is None:
            return None, "Session creation failed."
        set_active_tutor_session(user_id, session_id, target_minutes, topic_id)
        if target_minutes:
            note = f"Target duration: {target_minutes} minutes."
            call_sidecar_action(
                "english_session_turn_append",
                {"session_id": session_id, "role": "system", "content": note},
                user_id,
            )
        return int(session_id), None

    def close_session(self, user_id: int, summary_text: str | None = None) -> str | None:
        state = get_active_tutor_session(user_id)
        if not state:
            return "No active tutor session."
        payload = {"session_id": state.session_id}
        if summary_text:
            payload["summary_text"] = summary_text
        result = call_sidecar_action("english_session_close", payload, user_id)
        if result.status != "ok":
            return result.error_message or "Failed to close session."
        clear_active_tutor_session(user_id)
        return None

    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        state = get_active_tutor_session(user_id)
        if not state:
            return None, "No active tutor session. Use /tutor start."
        append_result = call_sidecar_action(
            "english_session_turn_append",
            {"session_id": state.session_id, "role": "user", "content": text},
            user_id,
        )
        if append_result.status != "ok":
            return None, append_result.error_message or "Failed to save user turn."
        reply = await self.reply_generator.generate_reply(text, state)
        append_reply = call_sidecar_action(
            "english_session_turn_append",
            {"session_id": state.session_id, "role": "assistant", "content": reply},
            user_id,
        )
        if append_reply.status != "ok":
            return None, append_reply.error_message or "Failed to save assistant turn."
        return reply, None
