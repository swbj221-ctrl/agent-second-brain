"""Command handlers for /start, /help, /status."""

from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.keyboards import get_main_keyboard
from d_brain.config import get_settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(
        "<b>d-brain</b> - capture and organize your notes\n\nSend me:\n- voice messages\n- text\n- photos\n- forwarded messages\n\nEverything will be stored and processed.\n\n<b>Commands:</b>\n/status - daily status\n/process - process daily notes\n/do - run an arbitrary request\n/weekly - weekly digest\n/plan - plans and reminders\n/note - ingest text or URL\n/book - books list\n/philosophy - philosophy notes\n/inbox - knowledge inbox\n/word - english words\n/topic - english topics\n/news - latest briefing\n/health - health records\n/reflect - reflection sessions (voice/text mode)\n/digest - latest digest\n/usage - codex usage status\n/tutor - voice English tutor\n/help - help",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "<b>How to use d-brain:</b>\n\n1. Send voice - it will be transcribed and stored\n2. Send text - it will be stored as-is\n3. Send a photo - it will be stored in attachments\n4. Forward a message - it will be stored with source info\n\nUse /process to process daily notes into outputs.\n\n<b>Commands:</b>\n/status - daily status\n/process - process daily notes\n/do - run an arbitrary request\n/weekly - weekly digest\n/plan add <title>\n/plan list\n/reminder list\n/note <text or url>\n/book add <text or url>\n/book list\n/philosophy add <text or url>\n/philosophy list\n/inbox add <text or url>\n/inbox list\n/inbox summarize <id>\n/inbox save <id> [title]\n/word add <word>\n/word list\n/topic add <name>\n/topic list\n/news latest\n/health add <title>\n/health list\n/web search <query>\n/web summarize <url>\n/youtube transcript <url>\n/reflect start (routes voice/text to reflection)\n/reflect add <session_id> <text>\n/reflect close <session_id> [summary]\n/digest latest\n/usage\n/tutor start [target_minutes]\n/tutor stop\n/tutor status"
    )


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
