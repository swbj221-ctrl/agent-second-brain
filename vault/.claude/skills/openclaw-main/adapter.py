"""OpenClaw main skill adapter (Phase 3 Batch A + Phase 2 command bridging)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from d_brain.bot.formatters import format_calendar_view, format_news_briefing
from d_brain.bot.ux import format_user_error
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.reflection_voice import ReflectionVoiceService
from d_brain.services.sidecar_client import SidecarResult, call_sidecar_action


INVALID_INPUT_REASON = "Некорректный ввод. Используй /help для примеров"
TOO_LONG_REASON = "Сообщение слишком длинное"
NO_RECORDS_TEXT = "Нет записей."

USAGE_CALENDAR = "Использование: /calendar today | /calendar upcoming [N] | /calendar date YYYY-MM-DD"
USAGE_DIGEST = "Использование: /digest latest"
USAGE_NEWS = "Использование: /news latest | /news generate | /news deliver"
USAGE_NOTE = "Использование: /note <text or url>"
USAGE_INBOX = (
    "Использование: /inbox add <text or url> | /inbox list | "
    "/inbox summarize <id> | /inbox save <id> [title]"
)
USAGE_INBOX_ADD = "Использование: /inbox add <text or url>"
USAGE_INBOX_SUMMARIZE = "Использование: /inbox summarize <id>"
USAGE_INBOX_SAVE = "Использование: /inbox save <id> [title]"
USAGE_WORD = "Использование: /word add <word>"
USAGE_WORD_ALL = "Использование: /word add <word> | /word list"
USAGE_TOPIC_ADD = "Использование: /topic add <name>"
USAGE_TOPIC_ALL = "Использование: /topic add <name> | /topic list"
USAGE_HEALTH_ADD = "Использование: /health add <title>"
USAGE_HEALTH_ALL = "Использование: /health add <title> | /health list"
USAGE_PROJECT_ADD = "Использование: /project add <name>"
USAGE_PROJECT_ALL = "Использование: /project add <name> | /project list [status] | /project archive <project_id>"
USAGE_PROJECT_LIST = "Использование: /project list [active|archived]"
USAGE_TASK_ADD = "Использование: /task add <project_id> | <title> | due:YYYY-MM-DD"
USAGE_TASK_ALL = "Использование: /task add <project_id> | <title> | due:YYYY-MM-DD | /task list [project_id] [status]"
USAGE_TASK_LIST = "Использование: /task list [project_id] [status]"
USAGE_TASK_STATUS = "Использование: /task list [project_id] [open|done|canceled]"
USAGE_TUTOR = "Использование: /tutor start [target_minutes] | /tutor stop | /tutor status"
USAGE_REFLECT = "Использование: /reflect start | /reflect add <session_id> <text> | /reflect close <session_id> [summary]"
USAGE_REFLECT_CLOSE = "Использование: /reflect close <session_id> [summary]"
USAGE_REMINDER = "Использование: /reminder list | /reminder deliver"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    args: list[str]
    normalized: str


@dataclass(frozen=True, slots=True)
class AdapterError:
    kind: str
    message: str | None = None
    code: str | None = None


def _source_ref_from_message(message: dict[str, Any]) -> str:
    chat_id = message.get("chat_id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        return "unknown:0"
    return f"{chat_id}:{message_id}"


def _handle_session_command(cmd: ParsedCommand, message: dict[str, Any], user_id: str | int) -> str:
    if cmd.name == "tutor_start":
        target_minutes = int(cmd.args[0]) if cmd.args else None
        service = EnglishTutorService()
        session_id, error = service.start_session(
            int(user_id),
            _source_ref_from_message(message),
            target_minutes=target_minutes,
        )
        if error:
            return error
        return (
            f"Сессия тьютора начата. session_id={session_id}"
            + (f" target_minutes={target_minutes}" if target_minutes else "")
        )
    if cmd.name == "tutor_stop":
        service = EnglishTutorService()
        error = service.close_session(int(user_id), summary_text="Closed by user.")
        if error:
            return error
        return "Сессия тьютора остановлена."
    if cmd.name == "tutor_status":
        state = get_active_tutor_session(int(user_id))
        if not state:
            return "Нет активной сессии тьютора."
        target = f" target_minutes={state.target_minutes}" if state.target_minutes else ""
        return f"Сессия тьютора активна. session_id={state.session_id}{target}"
    if cmd.name == "reflect_start":
        service = ReflectionVoiceService()
        session_id, error = service.start_session(int(user_id), _source_ref_from_message(message))
        if error:
            return error
        return (
            f"Сессия рефлексии начата. id={session_id}. "
            "Голос и текст направляются в режим рефлексии."
        )
    if cmd.name == "reflect_close":
        service = ReflectionVoiceService()
        session_id = int(cmd.args[0])
        summary = cmd.args[1] if len(cmd.args) > 1 else None
        error = service.close_session_by_id(int(user_id), session_id, summary)
        if error:
            return format_user_error(error)
        return f"Сессия рефлексии закрыта. id={session_id}"
    return format_user_error()


def _normalize(text: str) -> str:
    return " ".join(text.strip().split())


def parse_command(text: str) -> tuple[ParsedCommand | None, AdapterError | None]:
    if not text or not text.strip():
        return None, AdapterError("parse_error", message="empty")

    normalized = _normalize(text)
    lowered = normalized.lower()
    tokens = normalized.split(" ")
    lowered_tokens = [t.lower() for t in tokens]

    if lowered_tokens == ["/usage"]:
        return ParsedCommand("usage", [], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/usage":
        return None, AdapterError("parse_error", message="usage_args")

    if lowered_tokens == ["/digest", "latest"]:
        return ParsedCommand("digest_latest", [], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/digest":
        return None, AdapterError("parse_error", message="digest_args")

    if lowered_tokens == ["/news", "latest"]:
        return ParsedCommand("news_latest", [], normalized), None
    if lowered_tokens == ["/news", "generate"]:
        return ParsedCommand("news_generate", [], normalized), None
    if lowered_tokens == ["/news", "deliver"]:
        return ParsedCommand("news_deliver", [], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/news":
        return None, AdapterError("parse_error", message="news_args")

    if lowered_tokens and lowered_tokens[0] == "/tutor":
        if lowered_tokens == ["/tutor", "start"]:
            return ParsedCommand("tutor_start", [], normalized), None
        if lowered_tokens[:2] == ["/tutor", "start"]:
            if len(tokens) != 3 or not tokens[2].isdigit():
                return None, AdapterError("parse_error", message="tutor_args")
            minutes = int(tokens[2])
            if minutes <= 0:
                return None, AdapterError("parse_error", message="tutor_args")
            return ParsedCommand("tutor_start", [str(minutes)], normalized), None
        if lowered_tokens == ["/tutor", "stop"]:
            return ParsedCommand("tutor_stop", [], normalized), None
        if lowered_tokens == ["/tutor", "status"]:
            return ParsedCommand("tutor_status", [], normalized), None
        return None, AdapterError("parse_error", message="tutor_args")

    if lowered_tokens and lowered_tokens[0] == "/reflect":
        if lowered_tokens == ["/reflect", "start"]:
            return ParsedCommand("reflect_start", [], normalized), None
        if lowered_tokens[:2] == ["/reflect", "close"]:
            remainder = normalized[len("/reflect close") :].strip()
            if not remainder:
                return None, AdapterError("parse_error", message="reflect_close_args")
            parts = remainder.split(" ", maxsplit=1)
            if not parts[0].isdigit():
                return None, AdapterError("parse_error", message="reflect_close_args")
            args = [parts[0]]
            if len(parts) > 1 and parts[1].strip():
                args.append(parts[1].strip())
            return ParsedCommand("reflect_close", args, normalized), None
        return None, AdapterError("parse_error", message="reflect_args")

    if lowered_tokens == ["/reminder", "deliver"]:
        return ParsedCommand("reminder_deliver", [], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/reminder":
        return None, AdapterError("parse_error", message="reminder_args")

    if lowered_tokens and lowered_tokens[0] == "/note":
        remainder = normalized[len("/note") :].strip()
        if not remainder:
            return None, AdapterError("parse_error", message="note_args")
        return ParsedCommand("note_add", [remainder], normalized), None

    if lowered_tokens and lowered_tokens[0] == "/inbox":
        if lowered_tokens == ["/inbox", "list"]:
            return ParsedCommand("inbox_list", [], normalized), None
        if lowered_tokens[:2] == ["/inbox", "add"]:
            remainder = normalized[len("/inbox add") :].strip()
            if not remainder:
                return None, AdapterError("parse_error", message="inbox_add_args")
            return ParsedCommand("inbox_add", [remainder], normalized), None
        if lowered_tokens[:2] == ["/inbox", "summarize"]:
            remainder = normalized[len("/inbox summarize") :].strip()
            if not remainder or not remainder.isdigit():
                return None, AdapterError("parse_error", message="inbox_summarize_args")
            return ParsedCommand("inbox_summarize", [remainder], normalized), None
        if lowered_tokens[:2] == ["/inbox", "save"]:
            remainder = normalized[len("/inbox save") :].strip()
            if not remainder:
                return None, AdapterError("parse_error", message="inbox_save_args")
            parts = remainder.split(" ", maxsplit=1)
            if not parts[0].isdigit():
                return None, AdapterError("parse_error", message="inbox_save_args")
            note_title = parts[1].strip() if len(parts) > 1 else None
            args = [parts[0]]
            if note_title:
                args.append(note_title)
            return ParsedCommand("inbox_save", args, normalized), None
        return None, AdapterError("parse_error", message="inbox_args")

    if len(lowered_tokens) >= 2 and lowered_tokens[0] == "/word":
        if lowered_tokens == ["/word", "list"]:
            return ParsedCommand("word_list", [], normalized), None
        if lowered_tokens[:2] == ["/word", "add"]:
            if len(tokens) != 3:
                return None, AdapterError("parse_error", message="word_args")
            word = tokens[2].strip()
            if not word:
                return None, AdapterError("parse_error", message="word_args")
            if len(word) > 64:
                return None, AdapterError("parse_error", message="word_too_long")
            return ParsedCommand("word_add", [word], normalized), None
        return None, AdapterError("parse_error", message="word_args")

    if lowered_tokens == ["/topic", "list"]:
        return ParsedCommand("topic_list", [], normalized), None
    if lowered_tokens[:2] == ["/topic", "add"]:
        remainder = normalized[len("/topic add") :].strip()
        if not remainder:
            return None, AdapterError("parse_error", message="topic_add_args")
        return ParsedCommand("topic_add", [remainder], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/topic":
        return None, AdapterError("parse_error", message="topic_args")

    if lowered_tokens == ["/health", "list"]:
        return ParsedCommand("health_list", [], normalized), None
    if lowered_tokens[:2] == ["/health", "add"]:
        remainder = normalized[len("/health add") :].strip()
        if not remainder:
            return None, AdapterError("parse_error", message="health_add_args")
        return ParsedCommand("health_add", [remainder], normalized), None
    if lowered_tokens and lowered_tokens[0] == "/health":
        return None, AdapterError("parse_error", message="health_args")

    if lowered_tokens and lowered_tokens[0] == "/calendar":
        remainder = normalized[len("/calendar") :].strip()
        if not remainder:
            return None, AdapterError("parse_error", message="calendar_args")
        parts = remainder.split()
        sub = parts[0].lower()
        if sub == "today":
            if len(parts) > 1:
                return None, AdapterError("parse_error", message="calendar_args")
            return ParsedCommand("calendar_today", [], normalized), None
        if sub == "upcoming":
            if len(parts) > 2:
                return None, AdapterError("parse_error", message="calendar_args")
            limit = None
            if len(parts) == 2:
                if not parts[1].isdigit():
                    return None, AdapterError("parse_error", message="calendar_args")
                limit = parts[1]
            args = [limit] if limit is not None else []
            return ParsedCommand("calendar_upcoming", args, normalized), None
        if sub == "date":
            if len(parts) != 2:
                return None, AdapterError("parse_error", message="calendar_date_args")
            date_raw = parts[1].strip()
            try:
                datetime.fromisoformat(date_raw)
            except ValueError:
                return None, AdapterError("parse_error", message="calendar_date_invalid")
            return ParsedCommand("calendar_date", [date_raw], normalized), None
        return None, AdapterError("parse_error", message="calendar_args")

    if lowered_tokens and lowered_tokens[0] == "/project":
        if lowered_tokens[:2] == ["/project", "add"]:
            remainder = normalized[len("/project add") :].strip()
            if not remainder:
                return None, AdapterError("parse_error", message="project_add_args")
            return ParsedCommand("project_add", [remainder], normalized), None
        if lowered_tokens[:2] == ["/project", "list"]:
            remainder = normalized[len("/project list") :].strip()
            if not remainder:
                return ParsedCommand("project_list", [], normalized), None
            parts = remainder.split()
            if len(parts) != 1:
                return None, AdapterError("parse_error", message="project_list_args")
            status = parts[0].lower()
            if status not in {"active", "archived"}:
                return None, AdapterError("parse_error", message="project_list_args")
            return ParsedCommand("project_list", [status], normalized), None
        return None, AdapterError("parse_error", message="project_args")

    if lowered_tokens and lowered_tokens[0] == "/task":
        if lowered_tokens[:2] == ["/task", "add"]:
            remainder = normalized[len("/task add") :].strip()
            if not remainder or "|" not in remainder:
                return None, AdapterError("parse_error", message="task_add_args")
            parts = [part.strip() for part in remainder.split("|")]
            if len(parts) != 2:
                return None, AdapterError("parse_error", message="task_add_args")
            if not parts[0].isdigit():
                return None, AdapterError("parse_error", message="task_add_args")
            if not parts[1]:
                return None, AdapterError("parse_error", message="task_add_args")
            return ParsedCommand("task_add", [parts[0], parts[1]], normalized), None
        if lowered_tokens[:2] == ["/task", "list"]:
            remainder = normalized[len("/task list") :].strip()
            if not remainder:
                return ParsedCommand("task_list", [], normalized), None
            parts = remainder.split()
            if len(parts) > 2:
                return None, AdapterError("parse_error", message="task_list_args")
            project_id = None
            status = None
            if parts[0].isdigit():
                project_id = parts[0]
                if len(parts) == 2:
                    status = parts[1].lower()
            else:
                status = parts[0].lower()
            if status and status not in {"open", "done", "canceled"}:
                return None, AdapterError("parse_error", message="task_status_args")
            args = []
            if project_id is not None:
                args.append(project_id)
            if status is not None:
                args.append(status)
            return ParsedCommand("task_list", args, normalized), None
        return None, AdapterError("parse_error", message="task_args")

    return None, AdapterError("parse_error", message="unknown_command")


def dispatch_command(cmd: ParsedCommand) -> tuple[str, dict[str, Any]]:
    if cmd.name == "usage":
        return "codex_usage_status_get", {"scope_key": "global"}
    if cmd.name == "digest_latest":
        return "digest_get_latest", {}
    if cmd.name == "news_latest":
        return "news_briefing_get", {}
    if cmd.name == "news_generate":
        return "news_briefing_generate", {"limit": 50}
    if cmd.name == "news_deliver":
        return "news_briefing_get", {"briefing_id": None}
    if cmd.name == "reminder_deliver":
        return "reminder_delivery_run", {"chat_id": None, "mode": "manual"}
    if cmd.name == "note_add":
        return "ingest", {
            "source_type": "telegram",
            "content_type": "text",
            "summary_format": "plain",
            "content": cmd.args[0],
        }
    if cmd.name == "inbox_add":
        return "knowledge_inbox_add", {"content": cmd.args[0]}
    if cmd.name == "inbox_list":
        return "knowledge_inbox_list", {"limit": 50, "offset": 0}
    if cmd.name == "inbox_summarize":
        return "knowledge_item_summarize", {"artifact_id": int(cmd.args[0])}
    if cmd.name == "inbox_save":
        note_title = cmd.args[1] if len(cmd.args) > 1 else None
        return "knowledge_item_save_to_db", {"artifact_id": int(cmd.args[0]), "note_title": note_title}
    if cmd.name == "word_add":
        return "english_word_add", {"word": cmd.args[0]}
    if cmd.name == "word_list":
        return "english_word_list", {"limit": 50, "offset": 0}
    if cmd.name == "topic_add":
        return "english_topic_add", {"name": cmd.args[0]}
    if cmd.name == "topic_list":
        return "english_topic_list", {"limit": 50, "offset": 0}
    if cmd.name == "health_add":
        return "health_record_add", {"title": cmd.args[0], "record_type": "note", "source_type": "telegram"}
    if cmd.name == "health_list":
        return "health_record_list", {"limit": 50, "offset": 0}
    if cmd.name == "calendar_today":
        return "calendar_view", {"view": "today", "limit": 50}
    if cmd.name == "calendar_upcoming":
        limit = 10
        if cmd.args:
            limit = int(cmd.args[0])
        return "calendar_view", {"view": "upcoming", "limit": limit}
    if cmd.name == "calendar_date":
        return "calendar_view", {"view": "date", "date": cmd.args[0], "limit": 50}
    if cmd.name == "project_list":
        status = cmd.args[0] if cmd.args else None
        return "project_list", {"status": status, "limit": 50, "offset": 0}
    if cmd.name == "project_add":
        return "project_create", {"name": cmd.args[0]}
    if cmd.name == "task_add":
        return "task_create", {
            "project_id": int(cmd.args[0]),
            "title": cmd.args[1],
            "due_at": None,
            "source_type": "telegram",
        }
    if cmd.name == "task_list":
        project_id = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else None
        status = cmd.args[1] if len(cmd.args) > 1 else None
        if cmd.args and not cmd.args[0].isdigit():
            status = cmd.args[0]
        return "task_list", {"project_id": project_id, "status": status, "limit": 50, "offset": 0}
    raise ValueError(f"Unsupported command: {cmd.name}")


def build_request(
    action: str,
    payload: dict[str, Any],
    user_id: str | int,
    request_id: str | None = None,
) -> dict[str, Any]:
    req_id = request_id or uuid4().hex
    return {
        "request_id": req_id,
        "user_id": str(user_id),
        "action": action,
        "payload": payload,
        "metadata": {"source": "openclaw"},
    }


def send_to_sidecar(request: dict[str, Any]) -> tuple[SidecarResult | None, AdapterError | None]:
    try:
        result = call_sidecar_action(
            request.get("action", ""),
            request.get("payload") or {},
            request.get("user_id") or "0",
            source=(request.get("metadata") or {}).get("source", "openclaw"),
            request_id=request.get("request_id"),
        )
        return result, None
    except Exception:
        return None, AdapterError("transport_error")


def _render_list(items: list[dict[str, Any]], line_builder) -> str:
    if not items:
        return NO_RECORDS_TEXT
    lines = [line_builder(item) for item in items]
    return "\n".join(lines[:50])


def format_response(cmd: ParsedCommand, result: SidecarResult) -> str:
    if cmd.name == "usage":
        data = result.data or {}
        usage = data.get("usage", {})
        limits = data.get("limits", {})
        status_level = data.get("status_level", "unknown")
        return (
            "Статус использования Codex\n"
            f"status: {status_level}\n"
            f"tokens: {usage.get('total_tokens', 0)} / {limits.get('max_tokens', 0)}\n"
            f"requests: {usage.get('total_requests', 0)} / {limits.get('max_requests', 0)}\n"
            f"latency_ms: {usage.get('total_latency_ms', 0)} / {limits.get('max_latency_ms', 0)}"
        )

    if cmd.name == "digest_latest":
        payload = (result.data or {}).get("payload", {})
        counts = payload.get("counts", {})
        if not counts:
            return "Дайджест получен."
        lines = ["Сводка по последнему дайджесту:"]
        for key, value in counts.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    if cmd.name == "news_latest":
        items = (result.data or {}).get("items", [])
        return _render_list(
            items,
            lambda i: f"#{i['news_item_id']} {i.get('title') or 'Без названия'}",
        )

    if cmd.name == "news_generate":
        briefing_id = result.data.get("briefing_id") if result.data else None
        return f"Брифинг сгенерирован. id={briefing_id}"

    if cmd.name == "news_deliver":
        briefing = result.data or {}
        return format_news_briefing(briefing, max_items=5)

    if cmd.name == "note_add":
        summary_text = (result.data or {}).get("summary_text", "")
        summary_text = summary_text.strip()
        if summary_text:
            return f"Сохранено. Кратко: {summary_text}"
        return "Сохранено."

    if cmd.name == "inbox_add":
        artifact_id = result.data.get("artifact_id") if result.data else None
        summary_text = (result.data or {}).get("summary_text", "")
        summary_text = summary_text.strip()
        if summary_text:
            return f"Инбокс сохранен. id={artifact_id}\nКратко: {summary_text}"
        return f"Инбокс сохранен. id={artifact_id}"

    if cmd.name == "inbox_list":
        items = (result.data or {}).get("items", [])
        return _render_list(
            items,
            lambda i: f"#{i['id']} {(i.get('source_ref') or '').strip() or 'inbox item'}",
        )

    if cmd.name == "inbox_summarize":
        summary_text = (result.data or {}).get("summary_text", "")
        return summary_text or "Краткого резюме нет."

    if cmd.name == "inbox_save":
        note_id = result.data.get("note_id") if result.data else None
        return f"Инбокс сохранен в заметки. note_id={note_id}"

    if cmd.name == "reminder_deliver":
        payload = result.data or {}
        attempted = int(payload.get("attempted", 0))
        delivered = int(payload.get("delivered", 0))
        if attempted == 0:
            return "Нет напоминаний к отправке."
        return f"Отправка напоминаний выполнена. reminders={attempted} delivered={delivered}"

    if cmd.name == "word_add":
        word_id = result.data.get("word_id") if result.data else None
        return f"Слово добавлено. id={word_id}"

    if cmd.name == "word_list":
        words = (result.data or {}).get("words", [])
        return _render_list(words, lambda w: f"#{w['id']} {w['word']}")

    if cmd.name == "topic_list":
        topics = (result.data or {}).get("topics", [])
        return _render_list(topics, lambda t: f"#{t['id']} {t['name']}")

    if cmd.name == "topic_add":
        topic_id = result.data.get("topic_id") if result.data else None
        return f"Тема добавлена. id={topic_id}"

    if cmd.name == "health_add":
        record_id = result.data.get("record_id") if result.data else None
        return f"Запись о здоровье добавлена. id={record_id}"

    if cmd.name == "health_list":
        records = (result.data or {}).get("records", [])
        return _render_list(records, lambda r: f"#{r['id']} {r['title']}")

    if cmd.name == "calendar_today" or cmd.name == "calendar_upcoming" or cmd.name == "calendar_date":
        data = result.data or {}
        view = data.get("view", "calendar")
        date_label = data.get("date")
        items = data.get("items", [])
        return format_calendar_view(view, items, date_label=date_label)

    if cmd.name == "project_list":
        projects = (result.data or {}).get("projects", [])
        return _render_list(projects, lambda p: f"#{p['id']} {p['name']} ({p['status']})")

    if cmd.name == "project_add":
        project_id = result.data.get("project_id") if result.data else None
        return f"Проект создан. id={project_id}"

    if cmd.name == "task_add":
        task_id = result.data.get("task_id") if result.data else None
        return f"Задача создана. id={task_id}"

    if cmd.name == "task_list":
        tasks = (result.data or {}).get("tasks", [])
        return _render_list(
            tasks,
            lambda t: (
                f"#{t['id']} {t['title']} (project={t['project_id']}, status={t['status']}"
                + (f", due={t['due_at']}" if t.get("due_at") else "")
                + ")"
            ),
        )

    return format_user_error()


def format_error(error: AdapterError) -> str:
    if error.kind == "parse_error":
        if error.message == "digest_args":
            return USAGE_DIGEST
        if error.message == "news_args":
            return USAGE_NEWS
        if error.message == "tutor_args":
            return USAGE_TUTOR
        if error.message == "reflect_args":
            return USAGE_REFLECT
        if error.message == "reflect_close_args":
            return USAGE_REFLECT_CLOSE
        if error.message == "reminder_args":
            return USAGE_REMINDER
        if error.message == "note_args":
            return USAGE_NOTE
        if error.message == "inbox_args":
            return USAGE_INBOX
        if error.message == "inbox_add_args":
            return USAGE_INBOX_ADD
        if error.message == "inbox_summarize_args":
            return USAGE_INBOX_SUMMARIZE
        if error.message == "inbox_save_args":
            return USAGE_INBOX_SAVE
        if error.message == "word_args":
            return USAGE_WORD
        if error.message == "word_too_long":
            return format_user_error(TOO_LONG_REASON)
        if error.message == "word_list_args":
            return USAGE_WORD_ALL
        if error.message == "topic_add_args":
            return USAGE_TOPIC_ADD
        if error.message == "topic_args":
            return USAGE_TOPIC_ALL
        if error.message == "health_add_args":
            return USAGE_HEALTH_ADD
        if error.message == "health_args":
            return USAGE_HEALTH_ALL
        if error.message == "calendar_args":
            return USAGE_CALENDAR
        if error.message == "calendar_date_args":
            return "Использование: /calendar date YYYY-MM-DD"
        if error.message == "calendar_date_invalid":
            return "Неверная дата. Используй YYYY-MM-DD."
        if error.message == "project_list_args":
            return USAGE_PROJECT_LIST
        if error.message == "project_add_args":
            return USAGE_PROJECT_ADD
        if error.message == "project_args":
            return USAGE_PROJECT_ALL
        if error.message == "task_add_args":
            return USAGE_TASK_ADD
        if error.message == "task_list_args":
            return USAGE_TASK_LIST
        if error.message == "task_status_args":
            return USAGE_TASK_STATUS
        if error.message == "task_args":
            return USAGE_TASK_ALL
        if error.message == "usage_args":
            return format_user_error(INVALID_INPUT_REASON)
        return format_user_error(INVALID_INPUT_REASON)

    if error.kind == "sidecar_error":
        code = error.code
        if code == "not_found":
            return NO_RECORDS_TEXT
        if code == "invalid_payload":
            return format_user_error(INVALID_INPUT_REASON)
        if code == "payload_too_large":
            return format_user_error(TOO_LONG_REASON)
        if code in {"storage_error", "summary_error", "internal_error"}:
            return format_user_error()
        return format_user_error()

    return format_user_error()


def main_handler(message: dict[str, Any]) -> str:
    text = str(message.get("text") or message.get("content") or "")
    user_id = message.get("user_id") or message.get("from_user_id") or "0"
    request_id = message.get("request_id") or uuid4().hex

    cmd, err = parse_command(text)
    if err:
        return format_error(err)

    if cmd is None:
        return format_user_error(INVALID_INPUT_REASON)

    if cmd.name in {"tutor_start", "tutor_stop", "tutor_status", "reflect_start", "reflect_close"}:
        return _handle_session_command(cmd, message, user_id)

    action, payload = dispatch_command(cmd)
    if cmd.name in {"health_add", "task_add", "note_add", "inbox_add", "reminder_deliver"}:
        chat_id = message.get("chat_id")
        message_id = message.get("message_id")
        if chat_id is not None and message_id is not None:
            payload["source_ref"] = f"{chat_id}:{message_id}"
    if cmd.name == "reminder_deliver":
        chat_id = message.get("chat_id")
        if chat_id is None:
            return "Не удалось определить chat_id для доставки."
        payload["chat_id"] = int(chat_id)
    request = build_request(action, payload, user_id, request_id=request_id)
    result, transport_error = send_to_sidecar(request)
    if transport_error:
        return format_error(transport_error)
    if result is None:
        return format_user_error()
    if result.status != "ok":
        return format_error(AdapterError("sidecar_error", code=result.error_code))
    if cmd.name == "news_deliver":
        formatted = format_response(cmd, result)
        briefing = result.data or {}
        chat_id = message.get("chat_id")
        try:
            call_sidecar_action(
                "heartbeat_tick",
                {
                    "event_type": "news_delivery",
                    "event_source": "telegram",
                    "event_details": {
                        "briefing_id": briefing.get("id"),
                        "chat_id": chat_id,
                        "status": "sent",
                        "mode": "manual",
                    },
                },
                user_id,
                source="openclaw",
            )
        except Exception:
            pass
        return formatted
    return format_response(cmd, result)
