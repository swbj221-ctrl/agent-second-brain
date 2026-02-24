"""Command handlers for /status."""

from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="commands")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    user_id = message.from_user.id if message.from_user else 0
    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    # Log command
    session = SessionStore(settings.vault_path)
    session.append(user_id, "command", cmd="/status")

    today = date.today()
    content = storage.read_daily(today)

    if not content:
        await message.answer(f"рџ“… <b>{today}</b>\n\nР—Р°РїРёСЃРµР№ РїРѕРєР° РЅРµС‚.")
        return

    lines = content.strip().split("\n")
    entries = [line for line in lines if line.startswith("## ")]

    voice_count = sum(1 for e in entries if "[voice]" in e)
    text_count = sum(1 for e in entries if "[text]" in e)
    photo_count = sum(1 for e in entries if "[photo]" in e)
    forward_count = sum(1 for e in entries if "[forward from:" in e)

    total = len(entries)

    # Get weekly stats from session
    week_stats = ""
    stats = session.get_stats(user_id, days=7)
    if stats:
        week_stats = "\n\n<b>Р—Р° 7 РґРЅРµР№:</b>"
        for entry_type, count in sorted(stats.items()):
            week_stats += f"\nвЂў {entry_type}: {count}"

    await message.answer(
        f"рџ“… <b>{today}</b>\n\n"
        f"Р’СЃРµРіРѕ Р·Р°РїРёСЃРµР№: <b>{total}</b>\n"
        f"- рџЋ¤ Р“РѕР»РѕСЃРѕРІС‹С…: {voice_count}\n"
        f"- рџ’¬ РўРµРєСЃС‚РѕРІС‹С…: {text_count}\n"
        f"- рџ“· Р¤РѕС‚Рѕ: {photo_count}\n"
        f"- ↩️ Пересланных: {forward_count}"
        f"{week_stats}"
    )
