"""Telegram UX wiring for Stage 11 (text-only MVP)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.formatters import format_news_briefing
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.reflection_voice import ReflectionVoiceService
from d_brain.services.sidecar_client import call_sidecar_action

router = Router(name="telegram_ux")
logger = logging.getLogger(__name__)


def _source_ref(message: Message) -> str:
    chat_id = message.chat.id if message.chat else "unknown"
    return f"{chat_id}:{message.message_id}"


def _user_id(message: Message) -> int:
    return message.from_user.id if message.from_user else 0


def _split_args(text: str, maxsplit: int) -> list[str]:
    return text.strip().split(maxsplit=maxsplit)


def _format_error(code: str | None, message: str | None) -> str:
    if code == "invalid_payload":
        return "Invalid input. Use /help for examples."
    if code == "not_found":
        return "No records found."
    if code == "payload_too_large":
        return "Message too long. Please shorten it."
    if code in {"storage_error", "summary_error"}:
        return "Temporary error. Please try again later."
    if message:
        safe = message.strip().replace("\n", " ")
        return f"Error: {safe[:300]}"
    return "Unexpected error."


def _render_list(items: list[dict[str, Any]], line_builder) -> str:
    if not items:
        return "No records found."
    lines = [line_builder(item) for item in items]
    return "\n".join(lines[:50])


def _note_title(item: dict[str, Any]) -> str:
    title = (item.get("title") or "").strip()
    if title:
        return title
    body = (item.get("body") or "").strip()
    return body[:80] + ("..." if len(body) > 80 else "")


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /plan add <title> | /plan list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /plan add <title>")
            return
        payload = {
            "title": parts[2],
            "source_type": "telegram",
            "source_ref": _source_ref(message),
        }
        result = call_sidecar_action("event_create", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        event_id = result.data.get("event_id") if result.data else None
        reminder_id = result.data.get("reminder_id") if result.data else None
        await message.answer(f"Plan created. event_id={event_id} reminder_id={reminder_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "event_list",
            {"status": "planned", "limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        events = (result.data or {}).get("events", [])
        output = _render_list(
            events,
            lambda e: f"#{e['id']} {e['title']} ({e['status']})",
        )
        await message.answer(output)
        return
    await message.answer("Usage: /plan add <title> | /plan list")


@router.message(Command("reminder"))
async def cmd_reminder(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2 or parts[1].lower() != "list":
        await message.answer("Usage: /reminder list")
        return
    result = call_sidecar_action(
        "reminder_list",
        {"status": "pending", "limit": 50, "offset": 0},
        _user_id(message),
    )
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    reminders = (result.data or {}).get("reminders", [])
    output = _render_list(
        reminders,
        lambda r: f"#{r['id']} event_id={r['event_id']} remind_at={r['remind_at']} ({r['status']})",
    )
    await message.answer(output)


@router.message(Command("note"))
async def cmd_note(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /note <text or url>")
        return
    payload = {
        "source_type": "telegram",
        "content_type": "text",
        "summary_format": "plain",
        "source_ref": _source_ref(message),
        "content": parts[1].strip(),
    }
    result = call_sidecar_action("ingest", payload, _user_id(message))
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    summary_text = (result.data or {}).get("summary_text", "")
    summary_text = summary_text.strip()
    if summary_text:
        await message.answer(f"Saved. Summary: {summary_text}")
    else:
        await message.answer("Saved.")


@router.message(Command("book"))
async def cmd_book(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /book add <text or url> | /book list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /book add <text or url>")
            return
        payload = {"content": parts[2].strip(), "source_ref": _source_ref(message)}
        result = call_sidecar_action("books_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Book added. id={note_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "books_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        books = (result.data or {}).get("books", [])
        output = _render_list(books, lambda b: f"#{b['id']} {_note_title(b)}")
        await message.answer(output)
        return
    await message.answer("Usage: /book add <text or url> | /book list")


@router.message(Command("philosophy"))
async def cmd_philosophy(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /philosophy add <text or url> | /philosophy list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /philosophy add <text or url>")
            return
        payload = {"content": parts[2].strip(), "source_ref": _source_ref(message)}
        result = call_sidecar_action("philosophy_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Philosophy entry added. id={note_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "philosophy_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        items = (result.data or {}).get("items", [])
        output = _render_list(items, lambda i: f"#{i['id']} {_note_title(i)}")
        await message.answer(output)
        return
    await message.answer("Usage: /philosophy add <text or url> | /philosophy list")


@router.message(Command("inbox"))
async def cmd_inbox(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer(
            "Usage: /inbox add <text or url> | /inbox list | /inbox summarize <id> | /inbox save <id> [title]"
        )
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /inbox add <text or url>")
            return
        payload = {"content": parts[2].strip(), "source_ref": _source_ref(message)}
        result = call_sidecar_action("knowledge_inbox_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        artifact_id = result.data.get("artifact_id") if result.data else None
        summary_text = (result.data or {}).get("summary_text", "")
        summary_text = summary_text.strip()
        if summary_text:
            await message.answer(f"Inbox item saved. id={artifact_id}\nSummary: {summary_text}")
        else:
            await message.answer(f"Inbox item saved. id={artifact_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "knowledge_inbox_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        items = (result.data or {}).get("items", [])
        output = _render_list(
            items,
            lambda i: f"#{i['id']} {(i.get('source_ref') or '').strip() or 'inbox item'}",
        )
        await message.answer(output)
        return
    if sub == "summarize":
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer("Usage: /inbox summarize <id>")
            return
        payload = {"artifact_id": int(parts[2])}
        result = call_sidecar_action("knowledge_item_summarize", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        summary_text = (result.data or {}).get("summary_text", "")
        await message.answer(summary_text or "Summary not available.")
        return
    if sub == "save":
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer("Usage: /inbox save <id> [title]")
            return
        note_title = parts[3].strip() if len(parts) > 3 else None
        payload = {"artifact_id": int(parts[2]), "note_title": note_title}
        result = call_sidecar_action("knowledge_item_save_to_db", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Inbox item saved to notes. note_id={note_id}")
        return
    await message.answer(
        "Usage: /inbox add <text or url> | /inbox list | /inbox summarize <id> | /inbox save <id> [title]"
    )


@router.message(Command("word"))
async def cmd_word(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /word add <word> | /word list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /word add <word>")
            return
        result = call_sidecar_action(
            "english_word_add",
            {"word": parts[2].strip()},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        word_id = result.data.get("word_id") if result.data else None
        await message.answer(f"Word added. id={word_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "english_word_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        words = (result.data or {}).get("words", [])
        output = _render_list(words, lambda w: f"#{w['id']} {w['word']}")
        await message.answer(output)
        return
    await message.answer("Usage: /word add <word> | /word list")


@router.message(Command("tutor"))
async def cmd_tutor(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer("Usage: /tutor start [target_minutes] | /tutor stop | /tutor status")
        return
    sub = parts[1].lower()
    service = EnglishTutorService()
    if sub == "start":
        target_minutes = None
        if len(parts) >= 3 and parts[2].isdigit():
            target_minutes = int(parts[2])
        session_id, error = service.start_session(
            _user_id(message),
            source_ref=_source_ref(message),
            target_minutes=target_minutes,
        )
        if error:
            await message.answer(error)
            return
        await message.answer(
            f"Tutor session started. session_id={session_id}"
            + (f" target_minutes={target_minutes}" if target_minutes else "")
        )
        return
    if sub == "stop":
        error = service.close_session(_user_id(message), summary_text="Closed by user.")
        if error:
            await message.answer(error)
            return
        await message.answer("Tutor session stopped.")
        return
    if sub == "status":
        state = get_active_tutor_session(_user_id(message))
        if not state:
            await message.answer("No active tutor session.")
            return
        target = f" target_minutes={state.target_minutes}" if state.target_minutes else ""
        await message.answer(f"Tutor session active. session_id={state.session_id}{target}")
        return
    await message.answer("Usage: /tutor start [target_minutes] | /tutor stop | /tutor status")


@router.message(Command("topic"))
async def cmd_topic(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /topic add <name> | /topic list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /topic add <name>")
            return
        result = call_sidecar_action(
            "english_topic_add",
            {"name": parts[2].strip()},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        topic_id = result.data.get("topic_id") if result.data else None
        await message.answer(f"Topic added. id={topic_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "english_topic_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        topics = (result.data or {}).get("topics", [])
        output = _render_list(topics, lambda t: f"#{t['id']} {t['name']}")
        await message.answer(output)
        return
    await message.answer("Usage: /topic add <name> | /topic list")


@router.message(Command("news"))
async def cmd_news(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /news latest | /news generate | /news deliver")
        return
    sub = parts[1].lower()
    if sub == "latest":
        result = call_sidecar_action(
            "news_briefing_get",
            {"briefing_id": None},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        items = (result.data or {}).get("items", [])
        output = _render_list(
            items,
            lambda i: f"#{i['news_item_id']} {i.get('title') or 'Untitled'}",
        )
        await message.answer(output)
        return
    if sub == "generate":
        result = call_sidecar_action(
            "news_briefing_generate",
            {"limit": 50},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        briefing_id = result.data.get("briefing_id") if result.data else None
        await message.answer(f"Briefing generated. id={briefing_id}")
        return
    if sub == "deliver":
        result = call_sidecar_action(
            "news_briefing_get",
            {"briefing_id": None},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        briefing = result.data or {}
        formatted = format_news_briefing(briefing, max_items=5)
        await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True)
        call_sidecar_action(
            "heartbeat_tick",
            {
                "event_type": "news_delivery",
                "event_source": "telegram",
                "event_details": {
                    "briefing_id": briefing.get("id"),
                    "chat_id": message.chat.id if message.chat else None,
                    "status": "sent",
                    "mode": "manual",
                },
            },
            _user_id(message),
        )
        return
    await message.answer("Usage: /news latest | /news generate | /news deliver")


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /health add <title> | /health list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Usage: /health add <title>")
            return
        payload = {
            "title": parts[2].strip(),
            "record_type": "note",
            "source_type": "telegram",
            "source_ref": _source_ref(message),
        }
        result = call_sidecar_action("health_record_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        record_id = result.data.get("record_id") if result.data else None
        await message.answer(f"Health record added. id={record_id}")
        return
    if sub == "list":
        result = call_sidecar_action(
            "health_record_list",
            {"limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        records = (result.data or {}).get("records", [])
        output = _render_list(records, lambda r: f"#{r['id']} {r['title']}")
        await message.answer(output)
        return
    await message.answer("Usage: /health add <title> | /health list")


@router.message(Command("reflect"))
async def cmd_reflect(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer(
            "Usage: /reflect start | /reflect add <session_id> <text> | /reflect close <session_id> [summary]"
        )
        return
    sub = parts[1].lower()
    if sub == "start":
        service = ReflectionVoiceService()
        session_id, error = service.start_session(_user_id(message), _source_ref(message))
        if error:
            await message.answer(error)
            return
        await message.answer(
            f"Reflection session started. id={session_id}. "
            "Voice or text messages now route to reflection mode."
        )
        return
    if sub == "add":
        if len(parts) < 4:
            await message.answer("Usage: /reflect add <session_id> <text>")
            return
        session_id_raw = parts[2]
        if not session_id_raw.isdigit():
            await message.answer("Invalid session_id. Use an integer.")
            return
        payload = {
            "session_id": int(session_id_raw),
            "role": "user",
            "content": parts[3].strip(),
        }
        result = call_sidecar_action("reflection_turn_append", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        turn_id = result.data.get("turn_id") if result.data else None
        await message.answer(f"Reflection entry added. turn_id={turn_id}")
        return
    if sub == "close":
        if len(parts) < 3:
            await message.answer("Usage: /reflect close <session_id> [summary]")
            return
        session_id_raw = parts[2]
        if not session_id_raw.isdigit():
            await message.answer("Invalid session_id. Use an integer.")
            return
        summary = parts[3].strip() if len(parts) > 3 else None
        service = ReflectionVoiceService()
        error = service.close_session_by_id(_user_id(message), int(session_id_raw), summary)
        if error:
            await message.answer(error)
            return
        await message.answer(f"Reflection session closed. id={session_id_raw}")
        return
    await message.answer(
        "Usage: /reflect start | /reflect add <session_id> <text> | /reflect close <session_id> [summary]"
    )


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=1)
    if len(parts) < 2 or parts[1].lower() != "latest":
        await message.answer("Usage: /digest latest")
        return
    result = call_sidecar_action("digest_get_latest", {}, _user_id(message))
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    payload = (result.data or {}).get("payload", {})
    counts = payload.get("counts", {})
    if not counts:
        await message.answer("Latest digest retrieved.")
        return
    lines = ["Latest digest counts:"]
    for key, value in counts.items():
        lines.append(f"- {key}: {value}")
    await message.answer("\n".join(lines))


@router.message(Command("usage"))
async def cmd_usage(message: Message) -> None:
    result = call_sidecar_action(
        "codex_usage_status_get",
        {"scope_key": "global"},
        _user_id(message),
    )
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    data = result.data or {}
    usage = data.get("usage", {})
    limits = data.get("limits", {})
    status_level = data.get("status_level", "unknown")
    await message.answer(
        "Codex usage status\n"
        f"status: {status_level}\n"
        f"tokens: {usage.get('total_tokens', 0)} / {limits.get('max_tokens', 0)}\n"
        f"requests: {usage.get('total_requests', 0)} / {limits.get('max_requests', 0)}\n"
        f"latency_ms: {usage.get('total_latency_ms', 0)} / {limits.get('max_latency_ms', 0)}"
    )
