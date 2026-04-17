from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="🎭 Расписание игр"), KeyboardButton(text="📋 Список игр")]]
    rows.append([KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📝 Редактировать профиль")])
    if is_admin:
        rows.append([KeyboardButton(text="🛠️ Админ-меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def request_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def salutation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤵 Господин"), KeyboardButton(text="👒 Госпожа")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def affiliation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎓 С ВМК"), KeyboardButton(text="🏛️ Из МГУ, пропуск не нужен")],
            [KeyboardButton(text="🪪 Вне МГУ, нужен пропуск"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить админа"), KeyboardButton(text="➖ Удалить админа")],
            [KeyboardButton(text="🎮 Создать игру"), KeyboardButton(text="✏️ Редактировать игру")],
            [KeyboardButton(text="📈 Почасовой состав"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
    )


def game_edit_field_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕒 Время игры"), KeyboardButton(text="📍 Место")],
            [KeyboardButton(text="⏳ Окончание регистрации"), KeyboardButton(text="🗑️ Удалить игру")],
            [KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def profile_edit_field_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤵 Обращение"), KeyboardButton(text="🪪 ФИО")],
            [KeyboardButton(text="🎓 Статус по пропуску"), KeyboardButton(text="🏷️ Никнейм")],
            [KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
