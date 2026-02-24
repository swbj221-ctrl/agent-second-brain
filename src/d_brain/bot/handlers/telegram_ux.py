"""Telegram UX wiring for Stage 11 (text-only MVP)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.formatters import format_calendar_view, format_news_briefing
from d_brain.bot.ux import format_user_error, run_with_ack
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.reflection_voice import ReflectionVoiceService
from d_brain.services.sidecar_client import call_sidecar_action
from d_brain.services.web_tools import search_web, summarize_url, youtube_transcript

router = Router(name="telegram_ux")
logger = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "Временная ошибка. Попробуйте позже."


def _source_ref(message: Message) -> str:
    chat_id = message.chat.id if message.chat else "unknown"
    return f"{chat_id}:{message.message_id}"


def _user_id(message: Message) -> int:
    return message.from_user.id if message.from_user else 0


def _split_args(text: str, maxsplit: int) -> list[str]:
    return text.strip().split(maxsplit=maxsplit)


def _format_error(code: str | None, message: str | None) -> str:
    if code == "not_found":
        return "Нет записей."
    if code == "invalid_payload":
        return format_user_error("Некорректный ввод. Используй /help для примеров")
    if code == "payload_too_large":
        return format_user_error("Сообщение слишком длинное")
    if code in {"storage_error", "summary_error", "internal_error"}:
        return format_user_error()
    return format_user_error()


def _render_list(items: list[dict[str, Any]], line_builder) -> str:
    if not items:
        return "Нет записей."
    lines = [line_builder(item) for item in items]
    return "\n".join(lines[:50])


def _note_title(item: dict[str, Any]) -> str:
    title = (item.get("title") or "").strip()
    if title:
        return title
    body = (item.get("body") or "").strip()
    return body[:80] + ("..." if len(body) > 80 else "")


def _parse_due_date(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        return None
    return cleaned


def _parse_task_add(raw: str) -> tuple[int, str, str | None] | None:
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 2 or len(parts) > 3:
        return None
    if not parts[0].isdigit():
        return None
    project_id = int(parts[0])
    title = parts[1].strip()
    if not title:
        return None
    due_at = None
    if len(parts) == 3:
        token = parts[2].strip()
        if not token.lower().startswith("due:"):
            return None
        due_raw = token[4:].strip()
        due_at = _parse_due_date(due_raw)
        if due_at is None:
            return None
    return project_id, title, due_at


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _format_search_results(items: list[Any]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        title = (item.title or "").strip()
        url = (item.url or "").strip()
        snippet = (item.snippet or "").strip()
        line = f"{idx}. {title or 'Без названия'} - {url}".strip()
        lines.append(line)
        if snippet:
            lines.append(_truncate(snippet, 200))
    return "\n".join(lines) if lines else "Ничего не найдено."


@router.message(Command("web"))
async def cmd_web(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /web search <query> | /web summarize <url>")
        return
    sub = parts[1].lower()
    if sub == "search":
        if len(parts) < 3 or not parts[2].strip():
            await message.answer("Использование: /web search <query>")
            return

        async def work() -> None:
            result = search_web(parts[2].strip(), max_results=5)
            if not result.ok:
                await message.answer(format_user_error(result.error_message))
                return
            await message.answer(_format_search_results(result.items))

        await run_with_ack(message, "🔎 Принято. Ищу в интернете...", work)
        return
    if sub == "summarize":
        if len(parts) < 3 or not parts[2].strip():
            await message.answer("Использование: /web summarize <url>")
            return

        async def work() -> None:
            result = summarize_url(parts[2].strip())
            if not result.ok:
                await message.answer(format_user_error(result.error_message))
                return
            await message.answer(result.text)

        await run_with_ack(message, "📄 Принято. Суммаризирую страницу...", work)
        return
    await message.answer("Использование: /web search <query> | /web summarize <url>")
@router.message(Command("youtube"))
async def cmd_youtube(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /youtube transcript <url>")
        return
    sub = parts[1].lower()
    if sub != "transcript":
        await message.answer("Использование: /youtube transcript <url>")
        return
    if len(parts) < 3 or not parts[2].strip():
        await message.answer("Использование: /youtube transcript <url>")
        return

    async def work() -> None:
        result = youtube_transcript(parts[2].strip())
        if not result.ok:
            await message.answer(format_user_error(result.error_message))
            return
        suffix = "source=summarize"
        if result.truncated:
            await message.answer(f"{result.text}

[{suffix}, truncated]")
        else:
            await message.answer(f"{result.text}

[{suffix}]")

    await run_with_ack(message, "🎬 Принято. Получаю транскрипт...", work)
@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /plan add <title> | /plan list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /plan add <title>")
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
        await message.answer(f"План создан. event_id={event_id} reminder_id={reminder_id}")
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
    await message.answer("Использование: /plan add <title> | /plan list")


@router.message(Command("reminder"))
async def cmd_reminder(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /reminder list | /reminder deliver")
        return
    sub = parts[1].lower()
    if sub == "list":
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
        return
    if sub == "deliver":
        chat_id = message.chat.id if message.chat else None
        if chat_id is None:
            await message.answer("Не удалось определить chat_id для доставки.")
            return
        result = call_sidecar_action(
            "reminder_delivery_run",
            {"chat_id": int(chat_id), "mode": "manual"},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        payload = result.data or {}
        attempted = int(payload.get("attempted", 0))
        delivered = int(payload.get("delivered", 0))
        if attempted == 0:
            await message.answer("Нет напоминаний к отправке.")
            return
        await message.answer(
            f"Отправка напоминаний выполнена. reminders={attempted} delivered={delivered}"
        )
        return
    await message.answer("Использование: /reminder list | /reminder deliver")


@router.message(Command("note"))
async def cmd_note(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /note <text or url>")
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
        await message.answer(f"Сохранено. Кратко: {summary_text}")
    else:
        await message.answer("Сохранено.")


@router.message(Command("project"))
async def cmd_project(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /project add <name> | /project list [status] | /project archive <project_id>")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3 or not parts[2].strip():
            await message.answer("Использование: /project add <name>")
            return
        payload = {"name": parts[2].strip()}
        result = call_sidecar_action("project_create", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        project_id = result.data.get("project_id") if result.data else None
        await message.answer(f"Проект создан. id={project_id}")
        return
    if sub == "list":
        status = None
        if len(parts) > 2 and parts[2].strip():
            status = parts[2].strip().lower()
            if status not in {"active", "archived"}:
                await message.answer("Использование: /project list [active|archived]")
                return
        result = call_sidecar_action(
            "project_list",
            {"status": status, "limit": 50, "offset": 0},
            _user_id(message),
        )
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        projects = (result.data or {}).get("projects", [])
        output = _render_list(projects, lambda p: f"#{p['id']} {p['name']} ({p['status']})")
        await message.answer(output)
        return
    if sub == "archive":
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer("Использование: /project archive <project_id>")
            return
        payload = {"project_id": int(parts[2]), "status": "archived"}
        result = call_sidecar_action("project_update_status", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        await message.answer(f"Проект архивирован. id={parts[2]}")
        return
    await message.answer("Использование: /project add <name> | /project list [status] | /project archive <project_id>")


@router.message(Command("task"))
async def cmd_task(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование: /task add <project_id> | <title> | due:YYYY-MM-DD | /task list [project_id] [status]"
        )
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3 or not parts[2].strip():
            await message.answer("Использование: /task add <project_id> | <title> | due:YYYY-MM-DD")
            return
        parsed = _parse_task_add(parts[2])
        if parsed is None:
            await message.answer("Использование: /task add <project_id> | <title> | due:YYYY-MM-DD")
            return
        project_id, title, due_at = parsed
        payload = {
            "project_id": project_id,
            "title": title,
            "due_at": due_at,
            "source_type": "telegram",
            "source_ref": _source_ref(message),
        }
        result = call_sidecar_action("task_create", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        task_id = result.data.get("task_id") if result.data else None
        await message.answer(f"Задача создана. id={task_id}")
        return
    if sub == "list":
        project_id = None
        status = None
        if len(parts) > 2 and parts[2].strip():
            tokens = parts[2].strip().split()
            if tokens[0].isdigit():
                project_id = int(tokens[0])
                if len(tokens) > 1:
                    status = tokens[1].lower()
                if len(tokens) > 2:
                    await message.answer("Использование: /task list [project_id] [status]")
                    return
            else:
                status = tokens[0].lower()
                if len(tokens) > 1:
                    await message.answer("Использование: /task list [project_id] [status]")
                    return
        if status and status not in {"open", "done", "canceled"}:
            await message.answer("Использование: /task list [project_id] [open|done|canceled]")
            return
        payload = {"project_id": project_id, "status": status, "limit": 50, "offset": 0}
        result = call_sidecar_action("task_list", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        tasks = (result.data or {}).get("tasks", [])
        output = _render_list(
            tasks,
            lambda t: (
                f"#{t['id']} {t['title']} (project={t['project_id']}, status={t['status']}"
                + (f", due={t['due_at']}" if t.get("due_at") else "")
                + ")"
            ),
        )
        await message.answer(output)
        return
    if sub in {"done", "reopen", "cancel"}:
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer(f"Использование: /task {sub} <task_id>")
            return
        status_map = {"done": "done", "reopen": "open", "cancel": "canceled"}
        payload = {"task_id": int(parts[2]), "status": status_map[sub]}
        result = call_sidecar_action("task_update_status", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        await message.answer(f"Задача обновлена. id={parts[2]} status={status_map[sub]}")
        return
    if sub == "move":
        if len(parts) < 3:
            await message.answer("Использование: /task move <task_id> <project_id>")
            return
        tokens = parts[2].strip().split()
        if len(tokens) != 2 or not tokens[0].isdigit() or not tokens[1].isdigit():
            await message.answer("Использование: /task move <task_id> <project_id>")
            return
        payload = {"task_id": int(tokens[0]), "project_id": int(tokens[1])}
        result = call_sidecar_action("task_update_project", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        await message.answer(f"Задача перемещена. id={tokens[0]} project_id={tokens[1]}")
        return
    if sub == "note":
        if len(parts) < 3:
            await message.answer("Использование: /task note <task_id> <text>")
            return
        tokens = parts[2].strip().split(maxsplit=1)
        if len(tokens) < 2 or not tokens[0].isdigit():
            await message.answer("Использование: /task note <task_id> <text>")
            return
        payload = {"task_id": int(tokens[0]), "text": tokens[1].strip()}
        result = call_sidecar_action("task_note_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Заметка к задаче добавлена. note_id={note_id}")
        return
    await message.answer(
        "Использование: /task add <project_id> | <title> | due:YYYY-MM-DD | /task list [project_id] [status]"
    )


@router.message(Command("book"))
async def cmd_book(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /book add <text or url> | /book list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /book add <text or url>")
            return
        payload = {"content": parts[2].strip(), "source_ref": _source_ref(message)}
        result = call_sidecar_action("books_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Книга добавлена. id={note_id}")
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
    await message.answer("Использование: /book add <text or url> | /book list")


@router.message(Command("philosophy"))
async def cmd_philosophy(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /philosophy add <text or url> | /philosophy list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /philosophy add <text or url>")
            return
        payload = {"content": parts[2].strip(), "source_ref": _source_ref(message)}
        result = call_sidecar_action("philosophy_add", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Запись философии добавлена. id={note_id}")
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
    await message.answer("Использование: /philosophy add <text or url> | /philosophy list")


@router.message(Command("inbox"))
async def cmd_inbox(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer(
            "Использование: /inbox add <text or url> | /inbox list | /inbox summarize <id> | /inbox save <id> [title]"
        )
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /inbox add <text or url>")
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
            await message.answer(f"Инбокс сохранен. id={artifact_id}\nКратко: {summary_text}")
        else:
            await message.answer(f"Инбокс сохранен. id={artifact_id}")
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
            await message.answer("Использование: /inbox summarize <id>")
            return
        payload = {"artifact_id": int(parts[2])}
        result = call_sidecar_action("knowledge_item_summarize", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        summary_text = (result.data or {}).get("summary_text", "")
        await message.answer(summary_text or "Краткого резюме нет.")
        return
    if sub == "save":
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer("Использование: /inbox save <id> [title]")
            return
        note_title = parts[3].strip() if len(parts) > 3 else None
        payload = {"artifact_id": int(parts[2]), "note_title": note_title}
        result = call_sidecar_action("knowledge_item_save_to_db", payload, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        note_id = result.data.get("note_id") if result.data else None
        await message.answer(f"Инбокс сохранен в заметки. note_id={note_id}")
        return
    await message.answer(
        "Использование: /inbox add <text or url> | /inbox list | /inbox summarize <id> | /inbox save <id> [title]"
    )


@router.message(Command("word"))
async def cmd_word(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /word add <word> | /word list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /word add <word>")
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
        await message.answer(f"Слово добавлено. id={word_id}")
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
    await message.answer("Использование: /word add <word> | /word list")


@router.message(Command("tutor"))
async def cmd_tutor(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer("Использование: /tutor start [target_minutes] | /tutor stop | /tutor status")
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
            f"Сессия тьютора начата. session_id={session_id}"
            + (f" target_minutes={target_minutes}" if target_minutes else "")
        )
        return
    if sub == "stop":
        error = service.close_session(_user_id(message), summary_text="Closed by user.")
        if error:
            await message.answer(error)
            return
        await message.answer("Сессия тьютора остановлена.")
        return
    if sub == "status":
        state = get_active_tutor_session(_user_id(message))
        if not state:
            await message.answer("Нет активной сессии тьютора.")
            return
        target = f" target_minutes={state.target_minutes}" if state.target_minutes else ""
        await message.answer(f"Сессия тьютора активна. session_id={state.session_id}{target}")
        return
    await message.answer("Использование: /tutor start [target_minutes] | /tutor stop | /tutor status")


@router.message(Command("topic"))
async def cmd_topic(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /topic add <name> | /topic list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /topic add <name>")
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
        await message.answer(f"Тема добавлена. id={topic_id}")
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
    await message.answer("Использование: /topic add <name> | /topic list")


@router.message(Command("news"))
async def cmd_news(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /news latest | /news generate | /news deliver")
        return
    sub = parts[1].lower()
    if sub == "latest":
        async def work() -> None:
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
                lambda i: f"#{i['news_item_id']} {i.get('title') or 'Без названия'}",
            )
            await message.answer(output)

        await run_with_ack(message, "📰 Принято. Получаю брифинг...", work)
        return
    if sub == "generate":
        async def work() -> None:
            result = call_sidecar_action(
                "news_briefing_generate",
                {"limit": 50},
                _user_id(message),
            )
            if result.status != "ok":
                await message.answer(_format_error(result.error_code, result.error_message))
                return
            briefing_id = result.data.get("briefing_id") if result.data else None
            await message.answer(f"Брифинг сгенерирован. id={briefing_id}")

        await run_with_ack(message, "📰 Принято. Генерирую брифинг...", work)
        return
    if sub == "deliver":
        async def work() -> None:
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

        await run_with_ack(message, "📨 Принято. Отправляю брифинг...", work)
        return
    await message.answer("Использование: /news latest | /news generate | /news deliver")
@router.message(Command("calendar"))
async def cmd_calendar(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование: /calendar today | /calendar upcoming [N] | /calendar date YYYY-MM-DD"
        )
        return
    sub = parts[1].lower()
    if sub == "today":
        payload = {"view": "today", "limit": 50}
    elif sub == "upcoming":
        limit = 10
        if len(parts) > 2 and parts[2].isdigit():
            limit = int(parts[2])
        payload = {"view": "upcoming", "limit": limit}
    elif sub == "date":
        if len(parts) < 3:
            await message.answer("Использование: /calendar date YYYY-MM-DD")
            return
        date_raw = parts[2].strip()
        try:
            datetime.fromisoformat(date_raw)
        except ValueError:
            await message.answer("Неверная дата. Используй YYYY-MM-DD.")
            return
        payload = {"view": "date", "date": date_raw, "limit": 50}
    else:
        await message.answer(
            "Использование: /calendar today | /calendar upcoming [N] | /calendar date YYYY-MM-DD"
        )
        return

    result = call_sidecar_action("calendar_view", payload, _user_id(message))
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    data = result.data or {}
    view = data.get("view", "calendar")
    date_label = data.get("date")
    items = data.get("items", [])
    message_text = format_calendar_view(view, items, date_label=date_label)
    await message.answer(message_text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /health add <title> | /health list")
        return
    sub = parts[1].lower()
    if sub == "add":
        if len(parts) < 3:
            await message.answer("Использование: /health add <title>")
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
        await message.answer(f"Запись о здоровье добавлена. id={record_id}")
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
    await message.answer("Использование: /health add <title> | /health list")


@router.message(Command("reflect"))
async def cmd_reflect(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=3)
    if len(parts) < 2:
        await message.answer(
            "Использование: /reflect start | /reflect add <session_id> <text> | /reflect close <session_id> [summary]"
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
            f"Сессия рефлексии начата. id={session_id}. "
            "Голос и текст направляются в режим рефлексии."
        )
        return
    if sub == "add":
        if len(parts) < 4:
            await message.answer("Использование: /reflect add <session_id> <text>")
            return
        session_id_raw = parts[2]
        if not session_id_raw.isdigit():
            await message.answer("Неверный session_id. Используй целое число.")
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
        await message.answer(f"Запись рефлексии добавлена. turn_id={turn_id}")
        return
    if sub == "close":
        if len(parts) < 3:
            await message.answer("Использование: /reflect close <session_id> [summary]")
            return
        session_id_raw = parts[2]
        if not session_id_raw.isdigit():
            await message.answer("Неверный session_id. Используй целое число.")
            return
        summary = parts[3].strip() if len(parts) > 3 else None

        async def work() -> None:
            service = ReflectionVoiceService()
            error = service.close_session_by_id(_user_id(message), int(session_id_raw), summary)
            if error:
                await message.answer(format_user_error(error))
                return
            await message.answer(f"Сессия рефлексии закрыта. id={session_id_raw}")

        await run_with_ack(message, "🪞 Принято. Завершаю сессию и готовлю summary...", work)
        return
    await message.answer(
        "Использование: /reflect start | /reflect add <session_id> <text> | /reflect close <session_id> [summary]"
    )


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    text = message.text or ""
    parts = _split_args(text, maxsplit=1)
    if len(parts) < 2 or parts[1].lower() != "latest":
        await message.answer("Использование: /digest latest")
        return

    async def work() -> None:
        result = call_sidecar_action("digest_get_latest", {}, _user_id(message))
        if result.status != "ok":
            await message.answer(_format_error(result.error_code, result.error_message))
            return
        payload = (result.data or {}).get("payload", {})
        counts = payload.get("counts", {})
        if not counts:
            await message.answer("Дайджест получен.")
            return
        lines = ["Сводка по последнему дайджесту:"]
        for key, value in counts.items():
            lines.append(f"- {key}: {value}")
        await message.answer("
".join(lines))

    await run_with_ack(message, "🧾 Принято. Собираю дайджест...", work)
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
        "Статус использования Codex\n"
        f"status: {status_level}\n"
        f"tokens: {usage.get('total_tokens', 0)} / {limits.get('max_tokens', 0)}\n"
        f"requests: {usage.get('total_requests', 0)} / {limits.get('max_requests', 0)}\n"
        f"latency_ms: {usage.get('total_latency_ms', 0)} / {limits.get('max_latency_ms', 0)}"
    )
