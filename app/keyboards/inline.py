from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.database import ROLE_LABELS, ROLE_LIMITS

_ROLE_COUNT_KEY = {"host": "hosts", "judge": "judges", "player": "players"}


def games_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game in games:
        kb.button(
            text=f"#{game['id']}  {game['starts_at']}  |  {game['location']}",
            callback_data=f"game:{game['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def roles_keyboard(game_id: int, game: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for role, label in ROLE_LABELS.items():
        taken = game[_ROLE_COUNT_KEY[role]]
        limit = ROLE_LIMITS[role]
        kb.button(
            text=f"{label}  ({taken}/{limit})",
            callback_data=f"role:{game_id}:{role}",
        )
    kb.button(text="Отмена", callback_data="role_cancel")
    kb.adjust(1)
    return kb.as_markup()
