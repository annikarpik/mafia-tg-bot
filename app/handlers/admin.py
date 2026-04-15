from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database
from app.keyboards.reply import admin_menu_keyboard
from app.states import AdminStates
from app.utils import ensure_superadmin, normalize_phone, parse_game_datetime

router = Router(name="admin")


def _resolve_admin_target(raw_value: str, db: Database) -> tuple[int | None, str | None]:
    raw = raw_value.strip()
    if not raw:
        return None, "Введите Telegram ID, номер телефона или @username."

    if raw.lstrip("-").isdigit():
        return int(raw), None

    if raw.startswith("@"):
        user = db.get_user_by_username(raw)
        if not user:
            return None, "Пользователь с таким @username не найден среди зарегистрированных."
        return int(user["tg_id"]), None

    phone = normalize_phone(raw)
    if len(phone) >= 10:
        user = db.get_user_by_phone(phone)
        if not user:
            return None, "Пользователь с таким номером не найден среди зарегистрированных."
        return int(user["tg_id"]), None

    return None, "Неверный формат. Введите Telegram ID, номер телефона или @username."


async def _notify_about_admin_status(bot: Bot, target_tg_id: int) -> None:
    try:
        await bot.send_message(
            target_tg_id,
            "🎉 Вам выданы права администратора.\n"
            "Теперь вам доступно «Админ-меню».",
        )
    except Exception:
        # Пользователь мог ни разу не начать чат с ботом или заблокировать бота.
        pass


@router.message(F.text == "Админ-меню")
async def admin_menu_handler(
    message: Message, state: FSMContext, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)

    if not db.is_admin(tg_id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.clear()
    await message.answer("Админ-меню 🛠️", reply_markup=admin_menu_keyboard())


# ------------------------------------------------------------ add admin flow

@router.message(F.text == "Добавить админа")
async def add_admin_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.set_state(AdminStates.waiting_for_admin_to_add)
    await message.answer(
        "Введите Telegram ID, номер телефона или @username пользователя,\n"
        "которого хотите назначить администратором."
    )


@router.message(AdminStates.waiting_for_admin_to_add, ~F.text.in_({"Назад"}))
async def add_admin_finish(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    if raw.startswith("@"):
        user = db.get_user_by_username(raw)
        if user:
            target = int(user["tg_id"])
            added = db.add_admin(target)
            await state.clear()
            if added:
                await _notify_about_admin_status(bot, target)
                await message.answer(f"Администратор @{raw.lstrip('@')} добавлен ✅")
            else:
                await message.answer(f"Пользователь @{raw.lstrip('@')} уже является администратором.")
            return

        added_to_pending = db.add_pending_admin_username(raw)
        await state.clear()
        if added_to_pending:
            await message.answer(
                f"Пользователь @{raw.lstrip('@')} пока не зарегистрирован.\n"
                "Добавила его в список ожидания: как только он зайдёт в бота —\n"
                "админ-права выдадутся автоматически ✅"
            )
        else:
            await message.answer(
                f"Пользователь @{raw.lstrip('@')} уже есть в списке ожидания."
            )
        return

    target, error = _resolve_admin_target(raw, db)
    if error:
        await message.answer(error)
        return

    added = db.add_admin(target)
    await state.clear()
    if added:
        await _notify_about_admin_status(bot, target)
        await message.answer(f"Администратор с ID {target} добавлен ✅")
    else:
        await message.answer(f"Пользователь с ID {target} уже является администратором.")


# --------------------------------------------------------- remove admin flow

@router.message(F.text == "Удалить админа")
async def remove_admin_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    admins = db.list_admins()
    await state.set_state(AdminStates.waiting_for_admin_to_remove)
    await message.answer(
        "Введите Telegram ID, номер телефона или @username администратора для удаления.\n"
        f"Текущие администраторы: {', '.join(map(str, admins)) if admins else 'нет'}"
    )


@router.message(AdminStates.waiting_for_admin_to_remove, ~F.text.in_({"Назад"}))
async def remove_admin_finish(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    target, error = _resolve_admin_target(message.text or "", db)
    if error:
        await message.answer(error)
        return

    if target == message.from_user.id:
        await message.answer("Нельзя удалить самого себя из администраторов.")
        return

    removed = db.remove_admin(target)
    await state.clear()
    if removed:
        await message.answer(f"Администратор с ID {target} удалён.")
    else:
        await message.answer(f"Администратор с ID {target} не найден.")


# ----------------------------------------------------------- create game flow

@router.message(F.text == "Создать игру")
async def create_game_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.set_state(AdminStates.waiting_for_game_datetime)
    await message.answer(
        "Введите дату и время игры в формате ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 21.06.2026 19:30"
    )


@router.message(AdminStates.waiting_for_game_datetime, ~F.text.in_({"Назад"}))
async def create_game_datetime(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    starts_at = parse_game_datetime(message.text or "")
    if not starts_at:
        await message.answer(
            "Неверный формат даты. Попробуйте снова.\nПример: 21.06.2026 19:30"
        )
        return

    await state.update_data(starts_at=starts_at)
    await state.set_state(AdminStates.waiting_for_game_location)
    await message.answer("Введите место проведения игры.")


@router.message(AdminStates.waiting_for_game_location, ~F.text.in_({"Назад"}))
async def create_game_location(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    location = (message.text or "").strip()
    if len(location) < 3:
        await message.answer("Название места должно содержать не менее 3 символов.")
        return

    data = await state.get_data()
    starts_at = data.get("starts_at")
    if not starts_at:
        await message.answer("Дата не найдена. Начните создание игры заново.")
        await state.clear()
        return

    game_id = db.create_game(starts_at=starts_at, location=location)
    await state.clear()
    await message.answer(
        f"Игра создана! ✅\n"
        f"Номер: #{game_id}\n"
        f"Когда: {starts_at}\n"
        f"Где: {location}"
    )
