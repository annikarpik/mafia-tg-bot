from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from datetime import datetime, timedelta

from app.config import Config
from app.db.database import Database, ROLE_LABELS
from app.keyboards.inline import (
    confirm_role_change_keyboard,
    games_keyboard,
    player_until_keyboard,
    role_from_keyboard,
    roles_keyboard,
)
from app.utils import ensure_superadmin

router = Router(name="schedule")


def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return None


def _game_status(starts_at: str, registration_until: str) -> str:
    now = datetime.now()
    start_dt = _parse_dt(starts_at)
    registration_dt = _parse_dt(registration_until)
    if start_dt and now >= start_dt:
        return "🎬 Игра проведена"
    if registration_dt and now >= registration_dt:
        return "⛔ Регистрация закончена"
    return "✅ Регистрация открыта"


def _registered_count_text(game: dict) -> str:
    main_count = int(game.get("hosts", 0)) + int(game.get("judges", 0)) + int(game.get("players", 0))
    reserve_count = int(game.get("reserves", 0))
    total = main_count + reserve_count
    return f"👥 Зарегистрировались: {total} (основа: {main_count}, запас: {reserve_count})"


def _can_cancel_for_user(db: Database, tg_id: int, game_id: int) -> bool:
    user = db.get_user_by_tg(tg_id)
    if not user:
        return False
    user_id = int(user["id"])
    return db.user_registration(game_id, user_id) is not None or db.is_reserved(game_id, user_id)


def _participants_block(db: Database, game_id: int) -> str:
    grouped: dict[str, list[dict]] = {"host": [], "judge": [], "player": []}
    for row in db.list_game_registrations(game_id):
        grouped.setdefault(row["role"], []).append(row)

    lines: list[str] = ["Уже записались:"]
    hosts = grouped.get("host", [])
    judges = grouped.get("judge", [])
    players = grouped.get("player", [])
    reserves = db.list_game_reserves(game_id)

    def _time_suffix(row: dict) -> str:
        available_from = row.get("available_from")
        available_until = row.get("available_until")
        if available_from and available_until:
            return f" (с {available_from} до {available_until})"
        if available_from:
            return f" (с {available_from})"
        if available_until:
            return f" (до {available_until})"
        return ""

    if hosts:
        host = hosts[0]
        lines.append(f"• Ведущий: {host['nickname']}{_time_suffix(host)}")
    else:
        lines.append("• Ведущий: пока никого")

    if judges:
        judge_rows: list[str] = []
        for row in judges:
            judge_rows.append(f"{row['nickname']}{_time_suffix(row)}")
        lines.append(f"• Судьи: {', '.join(judge_rows)}")
    else:
        lines.append("• Судьи: пока никого")
    lines.append("• Игроки:")
    if players:
        for idx, row in enumerate(players, start=1):
            lines.append(f"  {idx}. {row['nickname']}{_time_suffix(row)}")
    else:
        lines.append("  пока никого")
    lines.append("• Наблюдатель/Запас:")
    if reserves:
        for idx, row in enumerate(reserves, start=1):
            lines.append(f"  {idx}. {row['nickname']}")
    else:
        lines.append("  пока никого")
    return "\n".join(lines)


def _game_card_text(db: Database, game: dict, game_id: int, prompt: str = "Выберите роль:") -> str:
    return (
        f"Игра #{game['id']} 🎭\n"
        f"Дата и время: {game['starts_at']}\n"
        f"Место: {game['location']}\n\n"
        f"Регистрация до: {game['registration_until']}\n\n"
        f"{_participants_block(db, game_id)}\n\n"
        f"{prompt}"
    )


async def _refresh_game_card(callback: CallbackQuery, db: Database, game_id: int) -> None:
    game = db.get_game_with_counts(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    can_cancel = _can_cancel_for_user(db=db, tg_id=callback.from_user.id, game_id=game_id)
    try:
        await callback.message.edit_text(
            _game_card_text(db, game, game_id),
            reply_markup=roles_keyboard(game_id, game, can_cancel=can_cancel),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _notify_admins_about_pass_needed(callback: CallbackQuery, db: Database, game_id: int, user: dict) -> None:
    if user.get("affiliation") != "outside_need_pass":
        return
    game = db.get_game(game_id)
    if not game:
        return
    text = (
        "🚨 Нужен пропуск для участника\n"
        f"ФИО: {user.get('full_name') or '-'}\n"
        f"Никнейм: {user['nickname']}\n"
        f"Телефон: {user['phone']}\n"
        f"Игра #{game_id}: {game['starts_at']} | {game['location']}"
    )
    for admin_tg_id in db.list_admins():
        try:
            await callback.bot.send_message(admin_tg_id, text)
        except Exception:
            pass


def _player_until_options(starts_at: str) -> list[str]:
    try:
        start_dt = datetime.strptime(starts_at, "%d.%m.%Y %H:%M")
    except ValueError:
        return []
    end_dt = start_dt.replace(hour=22, minute=30)
    options: list[str] = []
    current = start_dt.replace(second=0, microsecond=0)
    while True:
        current = current + timedelta(hours=1)
        if current > end_dt:
            break
        options.append(current.strftime("%H:%M"))
    return options


def _role_from_options(starts_at: str) -> list[str]:
    try:
        start_dt = datetime.strptime(starts_at, "%d.%m.%Y %H:%M")
    except ValueError:
        return []
    end_dt = start_dt.replace(hour=22, minute=30)
    options: list[str] = []
    current = start_dt.replace(second=0, microsecond=0)
    while current <= end_dt:
        options.append(current.strftime("%H:%M"))
        current = current + timedelta(hours=1)
    return options


def _role_until_options(starts_at: str, available_from: str | None = None) -> list[str]:
    base = _player_until_options(starts_at)
    if not available_from:
        return base
    try:
        from_hour = int(available_from.split(":")[0])
    except (ValueError, IndexError):
        return base
    return [opt for opt in base if int(opt.split(":")[0]) > from_hour]


async def _ask_role_from(callback: CallbackQuery, db: Database, game_id: int, role: str) -> None:
    game = db.get_game_with_counts(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    options = _role_from_options(game["starts_at"])
    prompt = "С какого времени вы можете быть на игре?"
    if not options:
        prompt = "Для этой игры нет доступных слотов времени до 22:30."
    try:
        await callback.message.edit_text(
            _game_card_text(db, game, game_id, prompt=prompt),
            reply_markup=role_from_keyboard(game_id, options, role=role),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.message(F.text.in_({"Расписание игр", "🎭 Расписание игр"}))
async def schedule_handler(
    message: Message, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)

    if not db.user_exists(tg_id):
        await message.answer("Сначала пройдите регистрацию: /start")
        return

    games = db.list_open_games()
    if not games:
        await message.answer("Пока нет игр с открытой регистрацией 😌")
        return

    await message.answer(
        f"Доступно игр: {len(games)} 🎲 Выберите игру:",
        reply_markup=games_keyboard(games),
    )


@router.message(F.text.in_({"Список игр", "📋 Список игр"}))
async def my_games_handler(message: Message, db: Database, config: Config) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)
    if db.is_admin(tg_id):
        games = db.list_games()
        if not games:
            await message.answer("Игр пока нет.")
            return
        lines = ["Все игры:"]
        for game in games:
            status = _game_status(
                starts_at=game["starts_at"],
                registration_until=game["registration_until"],
            )
            registered = _registered_count_text(game)
            lines.append(
                f"• #{game['id']} | {game['starts_at']} | {game['location']} | {status}\n  {registered}"
            )
        await message.answer("\n".join(lines))
        return

    user = db.get_user_by_tg(tg_id)
    if not user:
        await message.answer("Сначала пройдите регистрацию: /start")
        return

    items = db.list_user_games(int(user["id"]))
    if not items:
        await message.answer("Вы пока не зарегистрированы ни на одну игру.")
        return

    lines = ["Ваши игры:"]
    for item in items:
        if item["bucket"] == "reserve":
            role_text = "Наблюдатель/Запас"
        else:
            role = item["role"]
            role_text = ROLE_LABELS.get(role, role)
        status = _game_status(
            starts_at=item["starts_at"],
            registration_until=item["registration_until"],
        )
        game_counts = db.get_game_with_counts(int(item["id"]))
        registered = _registered_count_text(game_counts or {})
        lines.append(
            f"• #{item['id']} | {item['starts_at']} | {item['location']} | {role_text} | {status}\n  {registered}"
        )
    await message.answer("\n".join(lines))


@router.message(F.text.in_({"Статистика", "📊 Статистика"}))
async def statistics_stub_handler(message: Message) -> None:
    await message.answer(
        "📊 Статистика\n"
        "Раздел в разработке.\n"
        "Скоро здесь появятся данные из внешней базы."
    )


@router.callback_query(F.data.startswith("game:"))
async def game_pick_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    game_id = int(callback.data.split(":")[1])
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    game = db.get_game_with_counts(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    can_cancel = _can_cancel_for_user(db=db, tg_id=tg_id, game_id=game_id)
    await callback.message.answer(
        _game_card_text(db, game, game_id),
        reply_markup=roles_keyboard(game_id, game, can_cancel=can_cancel),
    )
    await callback.answer()


@router.callback_query(F.data == "role_cancel")
async def role_cancel_handler(callback: CallbackQuery) -> None:
    await callback.answer("Отменено")
    await callback.message.delete()


@router.callback_query(F.data.startswith("role:"))
async def role_pick_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw, role = callback.data.split(":")
    game_id = int(game_id_raw)
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return

    if not db.get_game(game_id):
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    user_id = int(user["id"])
    current = db.user_registration(game_id=game_id, user_id=user_id)
    if role in {"player", "judge", "host"}:
        if current and current["role"] != role:
            game = db.get_game_with_counts(game_id)
            if not game:
                await callback.answer("Игра не найдена.", show_alert=True)
                return
            current_role = ROLE_LABELS[current["role"]]
            next_role = ROLE_LABELS[role]
            await callback.message.edit_text(
                _game_card_text(
                    db,
                    game,
                    game_id,
                    prompt=(
                        f"Вы точно хотите поменять роль с {current_role.lower()} "
                        f"на {next_role.lower()}?"
                    ),
                ),
                reply_markup=confirm_role_change_keyboard(game_id=game_id, new_role=role),
            )
            await callback.answer()
            return
        await _ask_role_from(callback, db, game_id, role)
        await callback.answer()
        return

    if current and current["role"] != role:
        game = db.get_game_with_counts(game_id)
        if not game:
            await callback.answer("Игра не найдена.", show_alert=True)
            return
        current_role = ROLE_LABELS[current["role"]]
        next_role = ROLE_LABELS[role]
        await callback.message.edit_text(
            _game_card_text(
                db,
                game,
                game_id,
                prompt=(
                    f"Вы точно хотите поменять роль с {current_role.lower()} "
                    f"на {next_role.lower()}?"
                ),
            ),
            reply_markup=confirm_role_change_keyboard(game_id=game_id, new_role=role),
        )
        await callback.answer()
        return

    was_registered = current is not None
    _, text = db.register_user(game_id=game_id, user_id=user_id, role=role)
    await _refresh_game_card(callback, db, game_id)
    if not was_registered:
        await _notify_admins_about_pass_needed(callback, db, game_id, user)
    await callback.answer(f"{text} ✅")


@router.callback_query(F.data.startswith("role_confirm:"))
async def role_confirm_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw, role = callback.data.split(":")
    game_id = int(game_id_raw)
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    if role in {"player", "judge", "host"}:
        await _ask_role_from(callback, db, game_id, role)
        await callback.answer()
        return

    was_registered = db.user_registration(game_id=game_id, user_id=int(user["id"])) is not None
    _, text = db.register_user(game_id=game_id, user_id=int(user["id"]), role=role)
    await _refresh_game_card(callback, db, game_id)
    if not was_registered:
        await _notify_admins_about_pass_needed(callback, db, game_id, user)
    await callback.answer(f"{text} ✅")


@router.callback_query(F.data.startswith("role_back:"))
async def role_back_handler(callback: CallbackQuery, db: Database) -> None:
    _, game_id_raw = callback.data.split(":")
    game_id = int(game_id_raw)
    await _refresh_game_card(callback, db, game_id)
    await callback.answer("Оставили прежнюю роль")


@router.callback_query(F.data.startswith("refresh:"))
async def refresh_game_handler(callback: CallbackQuery, db: Database) -> None:
    _, game_id_raw = callback.data.split(":")
    game_id = int(game_id_raw)
    await _refresh_game_card(callback, db, game_id)
    await callback.answer("Состав обновлён")


@router.callback_query(F.data.startswith("role_from:"))
async def role_from_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw, role, from_token = callback.data.split(":")
    game_id = int(game_id_raw)
    if role not in {"player", "judge", "host"}:
        await callback.answer("Неизвестная роль.", show_alert=True)
        return
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    game = db.get_game(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    from_options = _role_from_options(game["starts_at"])
    available_from = f"{from_token[:2]}:{from_token[2:]}" if len(from_token) == 4 else None
    if available_from not in from_options:
        await callback.answer("Это время недоступно для выбранной игры.", show_alert=True)
        return

    until_options = _role_until_options(game["starts_at"], available_from)
    game_with_counts = db.get_game_with_counts(game_id)
    if not game_with_counts:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            _game_card_text(db, game_with_counts, game_id, prompt="До какого времени вы можете быть на игре? (до 22:30)"),
            reply_markup=player_until_keyboard(game_id, until_options, role=role, from_token=from_token),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("role_until:"))
async def role_until_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw, role, from_token, until_token = callback.data.split(":")
    game_id = int(game_id_raw)
    if role not in {"player", "judge", "host"}:
        await callback.answer("Неизвестная роль.", show_alert=True)
        return
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    game = db.get_game(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    from_options = _role_from_options(game["starts_at"])
    available_from = f"{from_token[:2]}:{from_token[2:]}" if len(from_token) == 4 else None
    if available_from not in from_options:
        await callback.answer("Время начала недоступно для выбранной игры.", show_alert=True)
        return
    options = _role_until_options(game["starts_at"], available_from)
    available_until = f"{until_token[:2]}:{until_token[2:]}" if len(until_token) == 4 else None
    if available_until not in options:
        await callback.answer("Это время недоступно для выбранной игры.", show_alert=True)
        return

    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    was_registered = db.user_registration(game_id=game_id, user_id=int(user["id"])) is not None
    _, text = db.register_user(
        game_id=game_id,
        user_id=int(user["id"]),
        role=role,
        available_from=available_from,
        available_until=available_until,
    )
    await _refresh_game_card(callback, db, game_id)
    if not was_registered:
        await _notify_admins_about_pass_needed(callback, db, game_id, user)
    await callback.answer(f"{text} ✅")


@router.callback_query(F.data.startswith("player_until:"))
async def legacy_player_until_handler(callback: CallbackQuery, db: Database) -> None:
    # Backward compatibility for old inline buttons
    _, game_id_raw, until_token = callback.data.split(":")
    game_id = int(game_id_raw)
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    game = db.get_game(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    options = _player_until_options(game["starts_at"])
    available_until = f"{until_token[:2]}:{until_token[2:]}" if len(until_token) == 4 else None
    if available_until not in options:
        await callback.answer("Это время недоступно для выбранной игры.", show_alert=True)
        return
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return
    was_registered = db.user_registration(game_id=game_id, user_id=int(user["id"])) is not None
    _, text = db.register_user(
        game_id=game_id,
        user_id=int(user["id"]),
        role="player",
        available_until=available_until,
    )
    await _refresh_game_card(callback, db, game_id)
    if not was_registered:
        await _notify_admins_about_pass_needed(callback, db, game_id, user)
    await callback.answer(f"{text} ✅")


@router.callback_query(F.data.startswith("unregister:"))
async def unregister_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw = callback.data.split(":")
    game_id = int(game_id_raw)
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру уже закрыта.", show_alert=True)
        return
    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    user_id = int(user["id"])
    current = db.user_registration(game_id=game_id, user_id=user_id)
    promoted: dict | None = None
    if current:
        removed = db.unregister_user(game_id=game_id, user_id=user_id)
        if removed and current["role"] == "player":
            promoted = db.promote_next_reserve_to_player(game_id=game_id)
    else:
        removed = db.remove_from_reserve(game_id=game_id, user_id=user_id)

    await _refresh_game_card(callback, db, game_id)
    if removed:
        await callback.answer("Регистрация на игру отменена ❌")
        if promoted:
            try:
                await callback.bot.send_message(
                    promoted["tg_id"],
                    "🎉 Кто-то из игроков отменил свою регистрацию,\n"
                    "теперь вы участвуете в игре как Игрок!",
                )
            except Exception:
                pass
    else:
        await callback.answer("Вы не были записаны на эту игру")


@router.callback_query(F.data.startswith("reserve:"))
async def reserve_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    _, game_id_raw = callback.data.split(":")
    game_id = int(game_id_raw)
    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    was_reserved = db.is_reserved(game_id=game_id, user_id=int(user["id"]))
    success, text = db.add_to_reserve(game_id=game_id, user_id=int(user["id"]))
    await _refresh_game_card(callback, db, game_id)
    if success and not was_reserved:
        await _notify_admins_about_pass_needed(callback, db, game_id, user)
    await callback.answer(text)
