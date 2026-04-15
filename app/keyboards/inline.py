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


def roles_keyboard(game_id: int, game: dict, can_cancel: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for role, label in ROLE_LABELS.items():
        taken = game[_ROLE_COUNT_KEY[role]]
        limit = ROLE_LIMITS[role]
        kb.button(
            text=f"{label}  ({taken}/{limit})",
            callback_data=f"role:{game_id}:{role}",
        )
    kb.button(
        text=f"Наблюдатель/Запас ({game.get('reserves', 0)})",
        callback_data=f"reserve:{game_id}",
    )
    if can_cancel:
        kb.button(text="Отменить регистрацию", callback_data=f"unregister:{game_id}")
    kb.button(text="Отмена", callback_data="role_cancel")
    kb.adjust(1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def confirm_role_change_keyboard(game_id: int, new_role: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, поменять", callback_data=f"role_confirm:{game_id}:{new_role}")
    kb.button(text="Нет, оставить как есть", callback_data=f"role_back:{game_id}")
    kb.adjust(1)
    return kb.as_markup()


def player_until_keyboard(game_id: int, options: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for option in options:
        token = option.replace(":", "")
        kb.button(text=f"До {option}", callback_data=f"player_until:{game_id}:{token}")
    kb.button(text="Назад", callback_data=f"role_back:{game_id}")
    if options:
        kb.adjust(2, 2, 2, 1)
    else:
        kb.adjust(1)
    return kb.as_markup()
