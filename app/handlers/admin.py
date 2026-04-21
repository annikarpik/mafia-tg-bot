from aiogram import Bot, F, Router
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database, GAME_TYPE_LABELS, ROLE_LABELS
from app.keyboards.reply import (
    admin_menu_keyboard,
    game_edit_field_keyboard,
    game_type_keyboard,
)
from app.states import AdminStates
from app.utils import ensure_superadmin, normalize_phone, parse_game_datetime

router = Router(name="admin")
BACK_BUTTONS = {"Назад", "↩️ Назад"}


def _to_dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        return None


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


async def _notify_users_about_game_update(
    bot: Bot,
    db: Database,
    game_id: int,
    before: dict,
    after: dict,
) -> None:
    changes: list[str] = []
    if before["starts_at"] != after["starts_at"]:
        changes.append(f"• Время игры: {before['starts_at']} -> {after['starts_at']}")
    if before["location"] != after["location"]:
        changes.append(f"• Место: {before['location']} -> {after['location']}")
    if before["registration_until"] != after["registration_until"]:
        changes.append(
            "• Окончание регистрации: "
            f"{before['registration_until']} -> {after['registration_until']}"
        )

    if not changes:
        return

    text = (
        f"📣 Обновление по игре #{game_id}\n"
        "Админ изменил параметры игры:\n"
        f"{chr(10).join(changes)}"
    )
    for tg_id in db.list_game_user_tg_ids(game_id):
        try:
            await bot.send_message(tg_id, text)
        except Exception:
            pass


def _games_short_list(db: Database) -> str:
    games = db.list_games()
    if not games:
        return "Игр нет."
    lines = ["Текущие игры:"]
    for game in games:
        game_type = GAME_TYPE_LABELS.get(game.get("game_type", ""), game.get("game_type", "-"))
        lines.append(
            f"• #{game['id']} | {game['starts_at']} | {game['location']} | {game_type} | рег. до {game['registration_until']}"
        )
    return "\n".join(lines)


def _to_minutes(raw: str) -> int | None:
    try:
        hh, mm = raw.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, TypeError):
        return None


def _parse_day(raw: str) -> str | None:
    try:
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y")
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        return None


def _parse_time_range(raw: str) -> tuple[str, str] | None:
    text = raw.replace("—", "-").replace("–", "-").strip()
    if "-" not in text:
        return None
    start_raw, end_raw = [part.strip() for part in text.split("-", maxsplit=1)]
    start_min = _to_minutes(start_raw)
    end_min = _to_minutes(end_raw)
    if start_min is None or end_min is None or end_min <= start_min:
        return None
    if (end_min - start_min) < 60:
        return None
    if start_min % 60 != 0 or end_min % 60 != 0:
        return None
    return (f"{start_min // 60:02d}:{start_min % 60:02d}", f"{end_min // 60:02d}:{end_min % 60:02d}")


def _build_hourly_starts(day: str, time_from: str, time_to: str) -> list[str]:
    start_min = _to_minutes(time_from)
    end_min = _to_minutes(time_to)
    if start_min is None or end_min is None:
        return []
    starts: list[str] = []
    current = start_min
    while current < end_min:
        starts.append(f"{day} {current // 60:02d}:{current % 60:02d}")
        current += 60
    return starts


def _username_suffix(username: str | None) -> str:
    if not username:
        return "(без @username)"
    return f"(@{username})"


@router.message(F.text.in_({"Админ-меню", "🛠️ Админ-меню"}))
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

@router.message(F.text.in_({"Добавить админа", "➕ Добавить админа"}))
async def add_admin_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.set_state(AdminStates.waiting_for_admin_to_add)
    await message.answer(
        "Введите Telegram ID, номер телефона или @username пользователя,\n"
        "которого хотите назначить администратором."
    )


@router.message(AdminStates.waiting_for_admin_to_add, ~F.text.in_(BACK_BUTTONS))
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

@router.message(F.text.in_({"Удалить админа", "➖ Удалить админа"}))
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


@router.message(AdminStates.waiting_for_admin_to_remove, ~F.text.in_(BACK_BUTTONS))
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

@router.message(F.text.in_({"Создать игру", "🎮 Создать игру"}))
async def create_game_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return

    await state.set_state(AdminStates.waiting_for_game_type)
    await message.answer("Выберите формат игр:", reply_markup=game_type_keyboard())


@router.message(AdminStates.waiting_for_game_type, ~F.text.in_(BACK_BUTTONS))
async def create_game_type(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    type_map = {
        "🏆 Турнир": "tournament",
        "Турнир": "tournament",
        "🎉 Фанки": "funky",
        "Фанки": "funky",
        "📚 Обучающие": "training",
        "Обучающие": "training",
    }
    game_type = type_map.get((message.text or "").strip())
    if not game_type:
        await message.answer("Выберите формат кнопкой: Турнир, Фанки или Обучающие.")
        return

    await state.update_data(game_type=game_type)
    await state.set_state(AdminStates.waiting_for_game_day)
    await message.answer("Введите день игр в формате ДД.ММ.ГГГГ.\nПример: 21.06.2026")


@router.message(AdminStates.waiting_for_game_day, ~F.text.in_(BACK_BUTTONS))
async def create_game_day(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    day = _parse_day(message.text or "")
    if not day:
        await message.answer("Неверный формат дня. Пример: 21.06.2026")
        return

    await state.update_data(game_day=day)
    await state.set_state(AdminStates.waiting_for_game_location)
    await message.answer("Введите место проведения игры.")


@router.message(AdminStates.waiting_for_game_location, ~F.text.in_(BACK_BUTTONS))
async def create_game_location(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    location = (message.text or "").strip()
    if len(location) < 3:
        await message.answer("Название места должно содержать не менее 3 символов.")
        return

    await state.update_data(location=location)
    await state.set_state(AdminStates.waiting_for_game_time_range)
    await message.answer(
        "Введите временной диапазон в формате ЧЧ:ММ-ЧЧ:ММ.\n"
        "Пример: 18:00-22:00\n"
        "Каждая игра длится 1 час."
    )


@router.message(AdminStates.waiting_for_game_time_range, ~F.text.in_(BACK_BUTTONS))
async def create_game_time_range(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    parsed = _parse_time_range(message.text or "")
    if not parsed:
        await message.answer(
            "Некорректный диапазон. Используйте формат ЧЧ:ММ-ЧЧ:ММ, "
            "границы по часу и минимум 1 час."
        )
        return
    time_from, time_to = parsed
    data = await state.get_data()
    game_type = data.get("game_type")
    game_day = data.get("game_day")
    location = data.get("location")
    if game_type not in GAME_TYPE_LABELS or not game_day or not location:
        await message.answer("Данные создания игры потеряны. Начните заново.")
        await state.clear()
        return

    starts = _build_hourly_starts(day=game_day, time_from=time_from, time_to=time_to)
    if not starts:
        await message.answer("Не удалось собрать слоты по заданному диапазону.")
        return

    created_ids: list[int] = []
    for starts_at in starts:
        created_ids.append(
            db.create_game(
                starts_at=starts_at,
                location=location,
                registration_until=starts_at,
                game_type=game_type,
            )
        )
    await state.set_state(AdminStates.waiting_for_game_type)
    await message.answer(
        "Игры созданы ✅\n"
        f"Формат: {GAME_TYPE_LABELS[game_type]}\n"
        f"День: {game_day}\n"
        f"Место: {location}\n"
        f"Диапазон: {time_from}-{time_to}\n"
        f"Создано игр: {len(created_ids)} (ID: {', '.join(map(str, created_ids))})"
    )
    await message.answer(
        "Можно сразу создать следующий игровой день.\nВыберите формат игр:",
        reply_markup=game_type_keyboard(),
    )


@router.message(F.text.in_({"Редактировать игру", "✏️ Редактировать игру"}))
async def edit_game_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(AdminStates.waiting_for_game_id_to_edit)
    await message.answer(f"{_games_short_list(db)}\n\nВведите ID игры для редактирования.")


@router.message(F.text.in_({"Список игр", "📋 Список игр"}))
async def games_list_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    days = db.list_game_days()
    if not days:
        await message.answer("Игр пока нет.")
        return
    await state.set_state(AdminStates.waiting_for_games_day_to_view)
    await message.answer(
        "Доступные игровые дни:\n"
        f"{chr(10).join(f'• {day}' for day in days)}\n\n"
        "Введите день в формате ДД.ММ.ГГГГ."
    )


@router.message(AdminStates.waiting_for_games_day_to_view, ~F.text.in_(BACK_BUTTONS))
async def games_list_pick_day(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await state.clear()
        await message.answer("У вас нет прав администратора.")
        return

    day = _parse_day(message.text or "")
    if not day:
        await message.answer("Неверный формат дня. Введите ДД.ММ.ГГГГ.")
        return

    games = db.list_games_by_day(day)
    if not games:
        await message.answer("На выбранный день игр нет. Введите другой день.")
        return

    await state.update_data(view_games_day=day)
    await state.set_state(AdminStates.waiting_for_game_id_to_view)
    lines = [f"Игры на {day}:"]
    for game in games:
        game_type = GAME_TYPE_LABELS.get(game.get("game_type", ""), game.get("game_type", "-"))
        lines.append(f"• #{game['id']} | {game['time']} | {game['location']} | {game_type}")
    lines.append("")
    lines.append("Введите ID игры, чтобы посмотреть состав.")
    await message.answer("\n".join(lines))


@router.message(AdminStates.waiting_for_game_id_to_view, ~F.text.in_(BACK_BUTTONS))
async def games_list_show_participants(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await state.clear()
        await message.answer("У вас нет прав администратора.")
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("ID должен быть числом.")
        return

    game_id = int(raw)
    game = db.get_game(game_id)
    if not game:
        await message.answer("Игра с таким ID не найдена.")
        return

    data = await state.get_data()
    selected_day = data.get("view_games_day")
    game_dt = _to_dt(game["starts_at"])
    if selected_day and game_dt and game_dt.strftime("%d.%m.%Y") != selected_day:
        await message.answer("Эта игра не из выбранного дня. Введите ID из списка.")
        return

    rows = db.list_game_registrations(game_id)
    by_role: dict[str, list[dict]] = {"host": [], "judge": [], "player": []}
    for row in rows:
        by_role.setdefault(row["role"], []).append(row)

    lines = [
        f"Состав игры #{game_id}",
        f"Когда: {game['starts_at']}",
        f"Где: {game['location']}",
        "",
    ]
    for role in ("host", "judge", "player"):
        items = by_role.get(role, [])
        lines.append(f"{ROLE_LABELS[role]}:")
        if not items:
            lines.append("• пока никого")
            continue
        for item in items:
            lines.append(f"• {item['nickname']} {_username_suffix(item.get('username'))}")
        lines.append("")

    await state.clear()
    await message.answer("\n".join(lines).strip())


@router.message(AdminStates.waiting_for_game_id_to_edit, ~F.text.in_(BACK_BUTTONS))
async def edit_game_pick_id(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await state.clear()
        await message.answer("У вас нет прав администратора.")
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("ID должен быть числом.")
        return
    game_id = int(raw)
    game = db.get_game(game_id)
    if not game:
        await message.answer("Игра с таким ID не найдена.")
        return
    await state.update_data(edit_game_id=game_id)
    await state.set_state(AdminStates.waiting_for_edit_field)
    await message.answer("Что хотите изменить?", reply_markup=game_edit_field_keyboard())


@router.message(AdminStates.waiting_for_edit_field, ~F.text.in_(BACK_BUTTONS))
async def edit_game_pick_field(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    field_map = {
        "Время игры": "starts_at",
        "🕒 Время игры": "starts_at",
        "Место": "location",
        "📍 Место": "location",
        "Окончание регистрации": "registration_until",
        "⏳ Окончание регистрации": "registration_until",
        "🗑️ Удалить игру": "delete_game",
    }
    field = field_map.get(text)
    if not field:
        await message.answer("Выберите поле кнопкой.")
        return
    if field == "delete_game":
        data = await state.get_data()
        game_id = data.get("edit_game_id")
        if not game_id:
            await state.clear()
            await message.answer("Игра не выбрана. Начните заново.")
            return
        deleted = db.delete_game(int(game_id))
        await state.clear()
        if deleted:
            await message.answer(f"Игра #{game_id} удалена ✅")
        else:
            await message.answer("Игра с таким ID не найдена.")
        return
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.waiting_for_edit_value)
    if field in {"starts_at", "registration_until"}:
        await message.answer("Введите новое значение в формате ДД.ММ.ГГГГ ЧЧ:ММ")
    else:
        await message.answer("Введите новое место проведения.")


@router.message(AdminStates.waiting_for_edit_value, ~F.text.in_(BACK_BUTTONS))
async def edit_game_apply(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        await state.clear()
        await message.answer("У вас нет прав администратора.")
        return
    data = await state.get_data()
    game_id = data.get("edit_game_id")
    field = data.get("edit_field")
    if not game_id or not field:
        await state.clear()
        await message.answer("Данные редактирования потеряны. Начните заново.")
        return

    value_raw = (message.text or "").strip()
    updates: dict[str, str] = {}
    if field in {"starts_at", "registration_until"}:
        parsed = parse_game_datetime(value_raw)
        if not parsed:
            await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ ЧЧ:ММ")
            return
        updates[field] = parsed
    else:
        if len(value_raw) < 3:
            await message.answer("Место должно быть не короче 3 символов.")
            return
        updates[field] = value_raw

    game = db.get_game(game_id)
    if not game:
        await state.clear()
        await message.answer("Игра больше не существует.")
        return
    game_before = dict(game)

    starts_at = updates.get("starts_at", game["starts_at"])
    registration_until = updates.get("registration_until", game["registration_until"])
    starts_dt = _to_dt(starts_at)
    reg_dt = _to_dt(registration_until)
    if starts_dt and reg_dt and reg_dt > starts_dt:
        await message.answer("Окончание регистрации должно быть не позже начала игры.")
        return

    updated = db.update_game(
        game_id=game_id,
        starts_at=updates.get("starts_at"),
        location=updates.get("location"),
        registration_until=updates.get("registration_until"),
    )
    await state.clear()
    if not updated:
        await message.answer("Не удалось обновить игру.")
        return
    refreshed = db.get_game(game_id)
    await _notify_users_about_game_update(
        bot=bot,
        db=db,
        game_id=game_id,
        before=game_before,
        after=refreshed,
    )
    await message.answer(
        "Игра обновлена ✅\n"
        f"#{game_id} | {refreshed['starts_at']} | {refreshed['location']} | рег. до {refreshed['registration_until']}"
    )
