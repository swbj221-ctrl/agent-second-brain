"""Button handlers for reply keyboard."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from d_brain.bot.states import DoCommandState

router = Router(name="buttons")


@router.message(F.text == "📊 Статус")
async def btn_status(message: Message) -> None:
    """Handle Status button."""
    from d_brain.bot.handlers.commands import cmd_status

    await cmd_status(message)


@router.message(F.text == "🧠 Новости")
async def btn_news(message: Message) -> None:
    """Handle News button."""
    from d_brain.bot.handlers.telegram_ux import cmd_news

    await cmd_news(message)


@router.message(F.text == "📅 План")
async def btn_plan(message: Message) -> None:
    """Handle Plan button."""
    from d_brain.bot.handlers.telegram_ux import cmd_plan

    await cmd_plan(message)


@router.message(F.text == "✍️ Заметка")
async def btn_note(message: Message) -> None:
    """Handle Note button."""
    from d_brain.bot.handlers.telegram_ux import cmd_note

    await cmd_note(message)


@router.message(F.text == "📥 Инбокс")
async def btn_inbox(message: Message) -> None:
    """Handle Inbox button."""
    from d_brain.bot.handlers.telegram_ux import cmd_inbox

    await cmd_inbox(message)


@router.message(F.text == "🪞 Рефлексия")
async def btn_reflect(message: Message) -> None:
    """Handle Reflection button."""
    from d_brain.bot.handlers.telegram_ux import cmd_reflect

    await cmd_reflect(message)


@router.message(F.text == "🧾 Дайджест")
async def btn_digest(message: Message) -> None:
    """Handle Digest button."""
    from d_brain.bot.handlers.telegram_ux import cmd_digest

    await cmd_digest(message)


@router.message(F.text == "🧭 Запрос")
async def btn_do(message: Message, state: FSMContext) -> None:
    """Handle Do button - set state and wait for input."""
    await state.set_state(DoCommandState.waiting_for_input)
    await message.answer(
        "🎯 <b>Что сделать?</b>

"
        "Отправь голосовое или текстовое сообщение с запросом."
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: Message) -> None:
    """Handle Help button."""
    from d_brain.bot.handlers.commands import cmd_help

    await cmd_help(message)


@router.message(F.text == "🎓 Английский")
async def btn_tutor(message: Message) -> None:
    """Handle English tutor status button."""
    from d_brain.services.english_tutor import get_active_tutor_session

    state = get_active_tutor_session(message.from_user.id if message.from_user else 0)
    if not state:
        await message.answer("Нет активной сессии. Используй /tutor start.")
        return
    target = f" target_minutes={state.target_minutes}" if state.target_minutes else ""
    await message.answer(f"Сессия активна. session_id={state.session_id}{target}")


@router.message(F.text == "❤️ Здоровье")
async def btn_health(message: Message) -> None:
    """Handle Health list button."""
    from d_brain.bot.handlers.telegram_ux import _format_error
    from d_brain.services.sidecar_client import call_sidecar_action

    user_id = message.from_user.id if message.from_user else 0
    result = call_sidecar_action(
        "health_record_list",
        {"limit": 50, "offset": 0},
        user_id,
    )
    if result.status != "ok":
        await message.answer(_format_error(result.error_code, result.error_message))
        return
    records = (result.data or {}).get("records", [])
    if not records:
        await message.answer("Нет записей.")
        return
    lines = [f"#{r['id']} {r['title']}" for r in records]
    await message.answer("
".join(lines))
