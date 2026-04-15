from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import ROLE_LABELS, ROLE_LIMITS


def main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Расписание игр")]]
    if is_admin:
        rows.append([KeyboardButton(text="Админ-меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def request_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться номером телефона", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить админа"), KeyboardButton(text="Удалить админа")],
            [KeyboardButton(text="Создать игру")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
    )


def games_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game in games:
        title = f"#{game['id']} {game['starts_at']} | {game['location']}"
        kb.button(text=title, callback_data=f"game:{game['id']}")
    kb.adjust(1)
    return kb.as_markup()


def roles_keyboard(game_id: int, game: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    role_to_key = {"host": "hosts", "judge": "judges", "player": "players"}
    for role, label in ROLE_LABELS.items():
        taken = game[role_to_key[role]]
        limit = ROLE_LIMITS[role]
        kb.button(
            text=f"{label} ({taken}/{limit})",
            callback_data=f"role:{game_id}:{role}",
        )
    kb.button(text="Отмена", callback_data="role_cancel")
    kb.adjust(1)
    return kb.as_markup()
