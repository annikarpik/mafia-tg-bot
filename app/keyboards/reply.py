from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Расписание игр")]]
    if is_admin:
        rows.append([KeyboardButton(text="Админ-меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def request_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться номером телефона", request_contact=True)]],
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
