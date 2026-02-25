"""Reply keyboards for Telegram bot."""

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from d_brain.bot.text_utils import fix_mojibake


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard with common commands."""
    builder = ReplyKeyboardBuilder()
    # Row 1
    builder.button(text=fix_mojibake("рџ“Љ РЎС‚Р°С‚СѓСЃ"))
    builder.button(text=fix_mojibake("рџ§  РќРѕРІРѕСЃС‚Рё"))
    builder.button(text=fix_mojibake("рџ“… РџР»Р°РЅ"))
    # Row 2
    builder.button(text=fix_mojibake("вњЌпёЏ Р—Р°РјРµС‚РєР°"))
    builder.button(text=fix_mojibake("рџ“Ґ РРЅР±РѕРєСЃ"))
    builder.button(text=fix_mojibake("рџЄћ Р РµС„Р»РµРєСЃРёСЏ"))
    # Row 3
    builder.button(text=fix_mojibake("рџ§ѕ Р”Р°Р№РґР¶РµСЃС‚"))
    builder.button(text=fix_mojibake("рџ§­ Р—Р°РїСЂРѕСЃ"))
    builder.button(text=fix_mojibake("вќ“ РџРѕРјРѕС‰СЊ"))
    # Row 4 (optional)
    builder.button(text=fix_mojibake("рџЋ“ РђРЅРіР»РёР№СЃРєРёР№"))
    builder.button(text=fix_mojibake("вќ¤пёЏ Р—РґРѕСЂРѕРІСЊРµ"))
    builder.adjust(3, 3, 3, 2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)
