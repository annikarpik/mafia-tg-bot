import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config, load_config
from db import Database
from keyboards import admin_menu_keyboard, games_keyboard, main_keyboard, request_contact_keyboard, roles_keyboard
from states import AdminStates, RegistrationStates


config: Config = load_config()
db = Database(config.db_path)
bot = Bot(token=config.bot_token)
dp = Dispatcher()


def ensure_superadmin(tg_id: int) -> None:
    if tg_id in config.superadmin_ids:
        db.add_admin(tg_id)


def parse_game_datetime(raw: str) -> str | None:
    try:
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y %H:%M")
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return None


def game_by_id(game_id: int) -> dict | None:
    for game in db.list_games():
        if game["id"] == game_id:
            return game
    return None


@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id)
    await state.clear()

    if db.user_exists(tg_id):
        await message.answer(
            "Вы уже зарегистрированы. Используйте меню ниже.",
            reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
        )
        return

    await message.answer(
        "Добро пожаловать в бота записи на игры Мафии.\n"
        "Сначала зарегистрируйтесь: поделитесь номером телефона.",
        reply_markup=request_contact_keyboard(),
    )
    await state.set_state(RegistrationStates.waiting_for_contact)


@dp.message(Command("admin"))
async def admin_auth_handler(message: Message, command: CommandObject) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id)
    args = (command.args or "").strip()
    if not args:
        await message.answer("Использование: /admin <пароль>")
        return

    if args != config.admin_password:
        await message.answer("Неверный пароль администратора.")
        return

    db.add_admin(tg_id)
    await message.answer("Вы успешно авторизованы как админ.", reply_markup=main_keyboard(is_admin=True))


@dp.message(RegistrationStates.waiting_for_contact, ~F.contact)
async def contact_required_handler(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопку «Поделиться номером телефона».",
        reply_markup=request_contact_keyboard(),
    )


@dp.message(RegistrationStates.waiting_for_contact, F.contact)
async def contact_handler(message: Message, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Нужно отправить именно ваш номер телефона.")
        return

    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(RegistrationStates.waiting_for_nickname)
    await message.answer("Теперь отправьте ваш никнейм (уникальный).")


@dp.message(RegistrationStates.waiting_for_nickname)
async def nickname_handler(message: Message, state: FSMContext) -> None:
    nickname = (message.text or "").strip()
    if len(nickname) < 3 or len(nickname) > 32:
        await message.answer("Никнейм должен быть от 3 до 32 символов.")
        return

    if db.nickname_taken(nickname):
        await message.answer("Такой никнейм уже занят. Введите другой.")
        return

    data = await state.get_data()
    phone = data.get("phone")
    if not phone:
        await message.answer("Телефон не найден. Начните заново: /start")
        await state.clear()
        return

    tg_id = message.from_user.id
    db.ensure_user(tg_id=tg_id, phone=phone, nickname=nickname)
    ensure_superadmin(tg_id)
    await state.clear()
    await message.answer(
        "Регистрация завершена!",
        reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
    )


@dp.message(F.text == "Расписание игр")
async def schedule_handler(message: Message) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id)
    if not db.user_exists(tg_id):
        await message.answer("Сначала пройдите регистрацию через /start.")
        return

    games = db.list_games()
    if not games:
        await message.answer("Пока нет запланированных игр.")
        return

    await message.answer(
        f"Сейчас доступно игр: {len(games)}. Выберите игру:",
        reply_markup=games_keyboard(games),
    )


@dp.callback_query(F.data.startswith("game:"))
async def game_pick_handler(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию через /start.", show_alert=True)
        return

    game_id = int(callback.data.split(":")[1])
    game = game_by_id(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    await callback.message.answer(
        f"Игра #{game['id']}\n"
        f"Когда: {game['starts_at']}\n"
        f"Где: {game['location']}\n\n"
        "Выберите роль:",
        reply_markup=roles_keyboard(game_id, game),
    )
    await callback.answer()


@dp.callback_query(F.data == "role_cancel")
async def role_cancel_handler(callback: CallbackQuery) -> None:
    await callback.answer("Отменено")
    await callback.message.delete()


@dp.callback_query(F.data.startswith("role:"))
async def role_pick_handler(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию через /start.", show_alert=True)
        return

    _, game_id_raw, role = callback.data.split(":")
    game_id = int(game_id_raw)
    game = db.get_game(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    _, text = db.register_user(game_id=game_id, user_id=int(user["id"]), role=role)
    await callback.answer()
    await callback.message.answer(text)

    refreshed = game_by_id(game_id)
    if refreshed:
        await callback.message.edit_reply_markup(reply_markup=roles_keyboard(game_id, refreshed))


@dp.message(F.text == "Админ-меню")
async def admin_menu_handler(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id)
    if not db.is_admin(tg_id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.clear()
    await message.answer("Админ-меню:", reply_markup=admin_menu_keyboard())


@dp.message(F.text == "Назад")
async def back_to_main_handler(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    await state.clear()
    await message.answer("Главное меню.", reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)))


@dp.message(F.text == "Добавить админа")
async def add_admin_start_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(AdminStates.waiting_for_admin_to_add)
    await message.answer("Введите Telegram ID пользователя, которого нужно назначить админом.")


@dp.message(AdminStates.waiting_for_admin_to_add)
async def add_admin_finish_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("ID должен быть числом. Попробуйте снова.")
        return

    target = int(raw)
    created = db.add_admin(target)
    await state.clear()
    if created:
        await message.answer(f"Админ с ID {target} добавлен.")
    else:
        await message.answer(f"Пользователь с ID {target} уже является админом.")


@dp.message(F.text == "Удалить админа")
async def remove_admin_start_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    admins = db.list_admins()
    await state.set_state(AdminStates.waiting_for_admin_to_remove)
    await message.answer(
        "Введите Telegram ID админа для удаления.\n"
        f"Текущие админы: {', '.join(map(str, admins)) if admins else 'нет'}"
    )


@dp.message(AdminStates.waiting_for_admin_to_remove)
async def remove_admin_finish_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("ID должен быть числом. Попробуйте снова.")
        return

    target = int(raw)
    if target == message.from_user.id:
        await message.answer("Нельзя удалить самого себя из админов.")
        return

    removed = db.remove_admin(target)
    await state.clear()
    if removed:
        await message.answer(f"Админ с ID {target} удален.")
    else:
        await message.answer(f"Админ с ID {target} не найден.")


@dp.message(F.text == "Создать игру")
async def create_game_start_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.set_state(AdminStates.waiting_for_game_datetime)
    await message.answer("Введите дату и время игры в формате ДД.ММ.ГГГГ ЧЧ:ММ")


@dp.message(AdminStates.waiting_for_game_datetime)
async def create_game_datetime_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    starts_at = parse_game_datetime(message.text or "")
    if not starts_at:
        await message.answer("Неверный формат. Пример: 21.04.2026 19:30")
        return

    await state.update_data(starts_at=starts_at)
    await state.set_state(AdminStates.waiting_for_game_location)
    await message.answer("Введите место проведения игры.")


@dp.message(AdminStates.waiting_for_game_location)
async def create_game_location_handler(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    location = (message.text or "").strip()
    if len(location) < 3:
        await message.answer("Место должно быть не короче 3 символов.")
        return

    data = await state.get_data()
    starts_at = data.get("starts_at")
    if not starts_at:
        await message.answer("Дата не найдена. Начните создание игры заново.")
        await state.clear()
        return

    game_id = db.create_game(starts_at=starts_at, location=location)
    await state.clear()
    await message.answer(f"Игра создана: #{game_id} | {starts_at} | {location}")


@dp.message()
async def fallback_handler(message: Message) -> None:
    await message.answer("Используйте меню или команду /start.")


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        db.close()
