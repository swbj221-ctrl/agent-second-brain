"""Button handlers for reply keyboard (DEV transport only)."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from d_brain.bot.states import DoCommandState
from d_brain.bot.text_utils import fix_mojibake, safe_answer
from d_brain.integrations.openclaw_bridge import handle_help

router = Router(name="buttons")


@router.message(F.text == fix_mojibake("рџ“Љ РЎС‚Р°С‚СѓСЃ"))
async def btn_status(message: Message) -> None:
    """Handle Status button."""
    from d_brain.bot.handlers.commands import cmd_status

    await cmd_status(message)


@router.message(F.text == fix_mojibake("рџ§  РќРѕРІРѕСЃС‚Рё"))
async def btn_news(message: Message) -> None:
    """Handle News button."""
    from d_brain.bot.handlers.telegram_ux import cmd_news

    await cmd_news(message)


@router.message(F.text == fix_mojibake("рџ“… РџР»Р°РЅ"))
async def btn_plan(message: Message) -> None:
    """Handle Plan button."""
    from d_brain.bot.handlers.telegram_ux import cmd_plan

    await cmd_plan(message)


@router.message(F.text == fix_mojibake("вњЌпёЏ Р—Р°РјРµС‚РєР°"))
async def btn_note(message: Message) -> None:
    """Handle Note button."""
    from d_brain.bot.handlers.telegram_ux import cmd_note

    await cmd_note(message)


@router.message(F.text == fix_mojibake("рџ“Ґ РРЅР±РѕРєСЃ"))
async def btn_inbox(message: Message) -> None:
    """Handle Inbox button."""
    from d_brain.bot.handlers.telegram_ux import cmd_inbox

    await cmd_inbox(message)


@router.message(F.text == fix_mojibake("рџЄћ Р РµС„Р»РµРєСЃРёСЏ"))
async def btn_reflect(message: Message) -> None:
    """Handle Reflection button."""
    from d_brain.bot.handlers.telegram_ux import cmd_reflect

    await cmd_reflect(message)


@router.message(F.text == fix_mojibake("рџ§ѕ Р”Р°Р№РґР¶РµСЃС‚"))
async def btn_digest(message: Message) -> None:
    """Handle Digest button."""
    from d_brain.bot.handlers.telegram_ux import cmd_digest

    await cmd_digest(message)


@router.message(F.text == fix_mojibake("рџ§­ Р—Р°РїСЂРѕСЃ"))
async def btn_do(message: Message, state: FSMContext) -> None:
    """Handle Do button - set state and wait for input."""
    await state.set_state(DoCommandState.waiting_for_input)
    await safe_answer(
        message,
        "рџЋЇ <b>Р§С‚Рѕ СЃРґРµР»Р°С‚СЊ?</b>\n\n"
        "РћС‚РїСЂР°РІСЊ РіРѕР»РѕСЃРѕРІРѕРµ РёР»Рё С‚РµРєСЃС‚РѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ Р·Р°РїСЂРѕСЃРѕРј.",
    )


@router.message(F.text == fix_mojibake("вќ“ РџРѕРјРѕС‰СЊ"))
async def btn_help(message: Message) -> None:
    """Handle Help button."""
    await safe_answer(message, handle_help(message.from_user.id if message.from_user else 0))


@router.message(F.text == fix_mojibake("рџЋ“ РђРЅРіР»РёР№СЃРєРёР№"))
async def btn_tutor(message: Message) -> None:
    """Handle English tutor status button."""
    from d_brain.services.english_tutor import get_active_tutor_session

    state = get_active_tutor_session(message.from_user.id if message.from_user else 0)
    if not state:
        await safe_answer(message, "РќРµС‚ Р°РєС‚РёРІРЅРѕР№ СЃРµСЃСЃРёРё. РСЃРїРѕР»СЊР·СѓР№ /tutor start.")
        return
    target = f" target_minutes={state.target_minutes}" if state.target_minutes else ""
    await safe_answer(message, f"РЎРµСЃСЃРёСЏ Р°РєС‚РёРІРЅР°. session_id={state.session_id}{target}")


@router.message(F.text == fix_mojibake("вќ¤пёЏ Р—РґРѕСЂРѕРІСЊРµ"))
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
        await safe_answer(message, _format_error(result.error_code, result.error_message))
        return
    records = (result.data or {}).get("records", [])
    if not records:
        await safe_answer(message, "РќРµС‚ Р·Р°РїРёСЃРµР№.")
        return
    lines = [f"#{r['id']} {r['title']}" for r in records]
    await safe_answer(message, "\n".join(lines))
