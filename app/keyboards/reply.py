from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="📝 Регистрация на игры"), KeyboardButton(text="📋 Ваши регистрации")]]
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


def preferred_roles_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎭 Игрок"), KeyboardButton(text="🎙️ Ведущий/судья")],
            [KeyboardButton(text="🎭+🎙️ Оба"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def game_type_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏆 Турнир"), KeyboardButton(text="🎉 Фанки")],
            [KeyboardButton(text="📚 Обучающие"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def game_type_with_all_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏆 Турнир"), KeyboardButton(text="🎉 Фанки")],
            [KeyboardButton(text="📚 Обучающие"), KeyboardButton(text="📋 Все игры")],
            [KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить админа"), KeyboardButton(text="➖ Удалить админа")],
            [KeyboardButton(text="🎮 Создать игру"), KeyboardButton(text="✏️ Редактировать игру")],
            [KeyboardButton(text="📋 Список игр"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
    )


def back_only_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↩️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def game_edit_field_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕒 Время"), KeyboardButton(text="📅 Дата")],
            [KeyboardButton(text="📍 Место"), KeyboardButton(text="🎮 Формат игры")],
            [KeyboardButton(text="🗑️ Удалить игровой день")],
            [KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def profile_edit_field_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤵 Обращение"), KeyboardButton(text="🪪 ФИО")],
            [KeyboardButton(text="🎓 Статус по пропуску"), KeyboardButton(text="🎭 Роль")],
            [KeyboardButton(text="🏷️ Никнейм"), KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
