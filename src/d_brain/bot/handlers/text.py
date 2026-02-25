"""Text message handler."""

import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message

from d_brain.bot.text_utils import safe_answer
from d_brain.config import get_settings
from d_brain.integrations.openclaw_bridge import dispatch_voice
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="text")
logger = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "Р’СЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ."
@router.message(lambda m: m.text is not None and not m.text.startswith("/"))
async def handle_text(message: Message) -> None:
    """Handle text messages (excluding commands)."""
    if not message.text or not message.from_user:
        return

    try:
        routed = await dispatch_voice(
            user_id=message.from_user.id,
            source_ref=f"{message.chat.id}:{message.message_id}",
            message_text=message.text,
            media_declared=False,
        )
        if routed.get("handled"):
            await safe_answer(message, str(routed.get("text") or ""))
            return

        settings = get_settings()
        storage = VaultStorage(settings.vault_path)

        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(message.text, timestamp, "[text]")

        # Log to session
        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "text",
            text=message.text,
            msg_id=message.message_id,
        )

        await safe_answer(message, "вњ… РЎРѕС…СЂР°РЅРµРЅРѕ")
        logger.info("Text message saved: %d chars", len(message.text))
    except Exception:
        logger.exception("Error processing text message")
        await safe_answer(message, INTERNAL_ERROR_MESSAGE)
