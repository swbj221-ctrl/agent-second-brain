"""Reply keyboards for Telegram bot."""

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard with common commands."""
    builder = ReplyKeyboardBuilder()
    # Row 1
    builder.button(text="📊 Статус")
    builder.button(text="🧠 Новости")
    builder.button(text="📅 План")
    # Row 2
    builder.button(text="✍️ Заметка")
    builder.button(text="📥 Инбокс")
    builder.button(text="🪞 Рефлексия")
    # Row 3
    builder.button(text="🧾 Дайджест")
    builder.button(text="🧭 Запрос")
    builder.button(text="❓ Помощь")
    # Row 4 (optional)
    builder.button(text="🎓 Английский")
    builder.button(text="❤️ Здоровье")
    builder.adjust(3, 3, 3, 2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)
