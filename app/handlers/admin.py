from aiogram import Bot, F, Router
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database, ROLE_LABELS
from app.keyboards.reply import admin_menu_keyboard, game_edit_field_keyboard
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
        lines.append(
            f"• #{game['id']} | {game['starts_at']} | {game['location']} | рег. до {game['registration_until']}"
        )
    return "\n".join(lines)


def _to_minutes(raw: str) -> int | None:
    try:
        hh, mm = raw.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, TypeError):
        return None


def _time_from_starts_at(starts_at: str) -> str | None:
    dt = _to_dt(starts_at)
    if not dt:
        return None
    return dt.strftime("%H:%M")


def _hourly_intervals(start_time: str) -> list[tuple[str, str]]:
    start_min = _to_minutes(start_time)
    if start_min is None:
        return []
    end_day = 22 * 60
    intervals: list[tuple[str, str]] = []
    current = start_min
    while current < end_day:
        nxt = min(current + 60, end_day)
        intervals.append((f"{current // 60:02d}:{current % 60:02d}", f"{nxt // 60:02d}:{nxt % 60:02d}"))
        current = nxt
    return intervals


def _is_available_on_interval(row: dict, interval_start: str, interval_end: str, game_start: str) -> bool:
    from_raw = row.get("available_from") or game_start
    until_raw = row.get("available_until") or "22:00"
    from_min = _to_minutes(from_raw)
    until_min = _to_minutes(until_raw)
    start_min = _to_minutes(interval_start)
    end_min = _to_minutes(interval_end)
    if None in {from_min, until_min, start_min, end_min}:
        return False
    return from_min <= start_min and until_min >= end_min


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

    await state.set_state(AdminStates.waiting_for_game_datetime)
    await message.answer(
        "Введите дату и время игры в формате ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 21.06.2026 19:30"
    )


@router.message(AdminStates.waiting_for_game_datetime, ~F.text.in_(BACK_BUTTONS))
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
    await state.set_state(AdminStates.waiting_for_game_registration_until)
    await message.answer(
        "Введите время окончания регистрации на игру в формате ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 21.06.2026 16:30"
    )


@router.message(AdminStates.waiting_for_game_registration_until, ~F.text.in_(BACK_BUTTONS))
async def create_game_registration_until(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        await state.clear()
        return

    registration_until = parse_game_datetime(message.text or "")
    if not registration_until:
        await message.answer(
            "Неверный формат даты. Попробуйте снова.\nПример: 21.06.2026 16:30"
        )
        return

    data = await state.get_data()
    starts_at = data.get("starts_at")
    starts_dt = _to_dt(starts_at) if starts_at else None
    reg_dt = _to_dt(registration_until)
    if starts_dt and reg_dt and reg_dt > starts_dt:
        await message.answer("Окончание регистрации должно быть не позже начала игры.")
        return

    await state.update_data(registration_until=registration_until)
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

    data = await state.get_data()
    starts_at = data.get("starts_at")
    registration_until = data.get("registration_until")
    if not starts_at:
        await message.answer("Дата не найдена. Начните создание игры заново.")
        await state.clear()
        return
    if not registration_until:
        await message.answer("Время окончания регистрации не найдено. Начните заново.")
        await state.clear()
        return

    game_id = db.create_game(
        starts_at=starts_at,
        location=location,
        registration_until=registration_until,
    )
    await state.clear()
    await message.answer(
        f"Игра создана! ✅\n"
        f"Номер: #{game_id}\n"
        f"Когда: {starts_at}\n"
        f"Где: {location}\n"
        f"Регистрация до: {registration_until}"
    )


@router.message(F.text.in_({"Редактировать игру", "✏️ Редактировать игру"}))
async def edit_game_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(AdminStates.waiting_for_game_id_to_edit)
    await message.answer(f"{_games_short_list(db)}\n\nВведите ID игры для редактирования.")


@router.message(F.text.in_({"Почасовой состав", "📈 Почасовой состав"}))
async def hourly_roster_start(message: Message, state: FSMContext, db: Database) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет прав администратора.")
        return
    await state.set_state(AdminStates.waiting_for_game_id_to_hourly)
    await message.answer(f"{_games_short_list(db)}\n\nВведите ID игры для просмотра почасового состава.")


@router.message(AdminStates.waiting_for_game_id_to_hourly, ~F.text.in_(BACK_BUTTONS))
async def hourly_roster_show(message: Message, state: FSMContext, db: Database) -> None:
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

    game_start = _time_from_starts_at(game["starts_at"])
    if not game_start:
        await message.answer("Не удалось распознать время игры.")
        await state.clear()
        return

    rows = db.list_game_registrations(game_id)
    intervals = _hourly_intervals(game_start)
    if not intervals:
        await message.answer("Для этой игры нет часовых интервалов до 22:00.")
        await state.clear()
        return

    lines: list[str] = [
        f"📈 Почасовой состав игры #{game_id}",
        f"Когда: {game['starts_at']}",
        f"Где: {game['location']}",
        "",
    ]
    for idx, (start_at, end_at) in enumerate(intervals):
        lines.append(f"с {start_at} до {end_at}")
        for role in ("host", "judge"):
            label = ROLE_LABELS[role]
            names = [
                row["nickname"]
                for row in rows
                if row["role"] == role and _is_available_on_interval(row, start_at, end_at, game_start)
            ]
            lines.append(f"• {label}: {', '.join(names) if names else 'пока никого'}")

        players = [
            row["nickname"]
            for row in rows
            if row["role"] == "player" and _is_available_on_interval(row, start_at, end_at, game_start)
        ]
        if players:
            lines.append("• Игроки:")
            for p_idx, nickname in enumerate(players, start=1):
                lines.append(f"  {p_idx}. {nickname}")
        else:
            lines.append("• Игроки: пока никого")
        if idx < len(intervals) - 1:
            lines.append("____________")

    await state.clear()
    await message.answer("\n".join(lines))


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
