from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from datetime import datetime

from app.config import Config
from app.db.database import Database, GAME_TYPE_LABELS
from app.keyboards.inline import (
    ALL_GAMES_TOKEN,
    game_days_keyboard,
    game_slots_keyboard,
    game_types_keyboard,
    my_registrations_actions_keyboard,
    registration_role_keyboard,
    user_registrations_keyboard_by_mode,
)
from app.utils import ensure_superadmin

router = Router(name="schedule")


def _restore_day(token: str) -> str | None:
    if len(token) != 8 or not token.isdigit():
        return None
    return f"{token[:2]}.{token[2:4]}.{token[4:]}"


def _role_kind_label(role: str) -> str:
    return "Игрок" if role == "player" else "Ведущий/судья"


def _game_type_title(game_type: str) -> str:
    if game_type == ALL_GAMES_TOKEN:
        return "Все форматы"
    return GAME_TYPE_LABELS[game_type]


def _is_valid_game_type(game_type: str) -> bool:
    return game_type == ALL_GAMES_TOKEN or game_type in GAME_TYPE_LABELS


def _parse_starts_at(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        return None


def _filter_registrations_by_stage(items: list[dict], stage: str) -> list[dict]:
    now = datetime.now()
    filtered: list[dict] = []
    for item in items:
        starts_at = _parse_starts_at(str(item.get("starts_at", "")))
        if starts_at is None:
            continue
        is_completed = starts_at <= now
        if stage == "completed" and is_completed:
            filtered.append(item)
        if stage == "active" and not is_completed:
            filtered.append(item)
    return filtered


def _my_registrations_mode_text(mode: str, stage: str, visible_items: list[dict]) -> str:
    stage_label = "действующие" if stage == "active" else "завершенные"
    if mode == "view":
        lines = [
            "Составы ваших игр.",
            "Нажмите на игру, чтобы открыть состав участников.",
            f"Сейчас показаны: {stage_label}.",
        ]
    else:
        lines = [
            "Ваши регистрации.",
            "Если хотите отменить регистрацию, нажмите на крестик рядом с нужной игрой.",
            f"Сейчас показаны: {stage_label}.",
        ]
    if not visible_items:
        lines.append("В этом разделе пока нет игр.")
    return "\n".join(lines)


def _game_participants_text(game: dict, rows: list[dict]) -> str:
    by_role: dict[str, list[dict]] = {"host": [], "judge": [], "player": []}
    for row in rows:
        by_role.setdefault(row["role"], []).append(row)
    game_type = GAME_TYPE_LABELS.get(game.get("game_type", ""), game.get("game_type", "-"))
    lines = [
        f"Состав игры #{game['id']}",
        f"Когда: {game['starts_at']}",
        f"Где: {game['location']}",
        f"Тип: {game_type}",
        "",
    ]
    role_titles = {
        "host": "Ведущий",
        "judge": "Судья",
        "player": "Игроки",
    }
    for role in ("host", "judge", "player"):
        items = by_role.get(role, [])
        lines.append(f"{role_titles[role]}:")
        if not items:
            lines.append("• пока никого")
            continue
        for idx, item in enumerate(items, start=1):
            if role == "player":
                lines.append(f"{idx}. {item['nickname']}")
            else:
                lines.append(f"• {item['nickname']}")
        lines.append("")
    return "\n".join(lines).strip()


@router.message(F.text.in_({"📝 Регистрация на игры", "🎭 Расписание игр", "Расписание игр"}))
async def start_registration_menu(message: Message, db: Database, config: Config) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)
    if not db.user_exists(tg_id):
        await message.answer("Сначала пройдите регистрацию: /start")
        return
    await message.answer("Выберите формат игр:", reply_markup=game_types_keyboard())


@router.callback_query(F.data.startswith("reg_type:"))
async def pick_game_type(callback: CallbackQuery, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    _, game_type = callback.data.split(":")
    if not _is_valid_game_type(game_type):
        await callback.answer("Неизвестный формат игр.", show_alert=True)
        return
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    can_play = bool(user.get("can_play"))
    can_staff = bool(user.get("can_staff"))
    if can_play and can_staff:
        await callback.message.answer(
            f"{_game_type_title(game_type)}: выберите роль для регистрации.",
            reply_markup=registration_role_keyboard(can_play=True, can_staff=True, game_type=game_type),
        )
    elif can_play:
        days = db.list_open_days_for_user(game_type=game_type, user_id=int(user["id"]))
        if not days:
            await callback.message.answer(
                f"Для формата «{_game_type_title(game_type)}» нет доступных дней для новой регистрации."
            )
        else:
            await callback.message.answer(
                f"{_game_type_title(game_type)}: выберите день.",
                reply_markup=game_days_keyboard(game_type=game_type, role_kind="player", days=days),
            )
    elif can_staff:
        days = db.list_open_days_for_user(game_type=game_type, user_id=int(user["id"]))
        if not days:
            await callback.message.answer(
                f"Для формата «{_game_type_title(game_type)}» нет доступных дней для новой регистрации."
            )
        else:
            await callback.message.answer(
                f"{_game_type_title(game_type)}: выберите день.",
                reply_markup=game_days_keyboard(game_type=game_type, role_kind="staff", days=days),
            )
    else:
        await callback.message.answer(
            "У вас не выбраны роли для регистрации. Обратитесь к администратору."
        )
    await callback.answer()


@router.callback_query(F.data.startswith("reg_role:"))
async def pick_registration_role(callback: CallbackQuery, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    _, game_type, role_kind = callback.data.split(":")
    if not _is_valid_game_type(game_type) or role_kind not in {"player", "staff"}:
        await callback.answer("Некорректный выбор.", show_alert=True)
        return
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    days = db.list_open_days_for_user(game_type=game_type, user_id=int(user["id"]))
    if not days:
        await callback.answer("Нет доступных дней для новой регистрации.", show_alert=True)
        return
    await callback.message.answer(
        f"{_game_type_title(game_type)} ({_role_kind_label(role_kind)}): выберите день.",
        reply_markup=game_days_keyboard(game_type=game_type, role_kind=role_kind, days=days),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reg_day:"))
async def pick_registration_day(callback: CallbackQuery, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    _, game_type, role_kind, day_token = callback.data.split(":")
    day = _restore_day(day_token)
    if not day:
        await callback.answer("Некорректный день.", show_alert=True)
        return
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    games = db.list_open_games_by_type_and_day_for_user(
        game_type=game_type,
        day=day,
        user_id=int(user["id"]),
    )
    if not games:
        await callback.answer("На выбранный день нет доступных игр для новой регистрации.", show_alert=True)
        return
    await callback.message.answer(
        f"{_game_type_title(game_type)}, {day}. Выберите игру:",
        reply_markup=game_slots_keyboard(game_type=game_type, role_kind=role_kind, games=games),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reg_game:"))
async def register_for_game(callback: CallbackQuery, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    _, game_type, role_kind, game_id_raw = callback.data.split(":")
    if not _is_valid_game_type(game_type):
        await callback.answer("Некорректный формат игр.", show_alert=True)
        return
    game_id = int(game_id_raw)
    game = db.get_game_with_counts(game_id)
    if not game or (game_type != ALL_GAMES_TOKEN and game.get("game_type") != game_type):
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    if not db.is_game_open(game_id):
        await callback.answer("Регистрация на эту игру закрыта.", show_alert=True)
        return
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    if role_kind == "player" and not user.get("can_play"):
        await callback.answer("У вас нет доступа к роли «Игрок».", show_alert=True)
        return
    if role_kind == "staff" and not user.get("can_staff"):
        await callback.answer("У вас нет доступа к роли «Ведущий/судья».", show_alert=True)
        return
    _, text = db.register_user_for_kind(game_id=game_id, user_id=int(user["id"]), role_kind=role_kind)
    day = str(game["starts_at"]).split(" ")[0]
    games = db.list_open_games_by_type_and_day_for_user(
        game_type=game_type,
        day=day,
        user_id=int(user["id"]),
    )
    if not games:
        try:
            await callback.message.edit_text(
                f"{_game_type_title(game_type)}, {day}. Все доступные игры на этот день уже выбраны ✅",
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        await callback.answer(text)
        return
    try:
        await callback.message.edit_text(
            f"{_game_type_title(game_type)}, {day}. Выберите игру:",
            reply_markup=game_slots_keyboard(game_type=game_type, role_kind=role_kind, games=games),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer(text)


@router.message(F.text.in_({"📋 Ваши регистрации", "📋 Список игр"}))
async def my_registrations(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    ensure_superadmin(message.from_user.id, db, config)
    user = db.get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer("Сначала пройдите регистрацию: /start")
        return
    sent = await message.answer(
        "Что хотите сделать с вашими регистрациями?",
        reply_markup=my_registrations_actions_keyboard(),
    )
    await state.update_data(
        my_registrations_message_id=sent.message_id,
        my_registrations_stage="active",
        my_registrations_mode=None,
    )


async def _render_my_registrations_mode(
    callback: CallbackQuery, state: FSMContext, db: Database, mode: str, stage: str | None = None
) -> None:
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    effective_stage = stage or "active"
    if effective_stage not in {"active", "completed"}:
        effective_stage = "active"
    items = db.list_user_registrations(int(user["id"]))
    if not items:
        await callback.message.edit_text("У вас пока нет активных регистраций.")
        await state.update_data(my_registrations_stage="active", my_registrations_mode=mode)
        await callback.answer()
        return
    visible_items = _filter_registrations_by_stage(items, effective_stage)
    await callback.message.edit_text(
        _my_registrations_mode_text(mode, effective_stage, visible_items),
        reply_markup=user_registrations_keyboard_by_mode(visible_items, effective_stage, mode),
    )
    await state.update_data(my_registrations_stage=effective_stage, my_registrations_mode=mode)
    await callback.answer()


@router.callback_query(F.data.startswith("myreg_action:"))
async def choose_my_registrations_action(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    mode = callback.data.split(":")[1]
    if mode not in {"view", "cancel"}:
        await callback.answer("Некорректное действие.", show_alert=True)
        return
    await _render_my_registrations_mode(callback=callback, state=state, db=db, mode=mode, stage="active")


@router.callback_query(F.data.startswith("myreg_stage:"))
async def switch_my_registrations_stage(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    stage = callback.data.split(":")[1]
    if stage not in {"active", "completed"}:
        await callback.answer("Некорректный этап.", show_alert=True)
        return
    data = await state.get_data()
    mode = data.get("my_registrations_mode")
    if mode not in {"view", "cancel"}:
        await callback.answer("Сначала выберите действие: составы или отмена.", show_alert=True)
        return
    await _render_my_registrations_mode(callback=callback, state=state, db=db, mode=mode, stage=stage)


@router.callback_query(F.data.startswith("myreg_view:"))
async def show_my_registration_game_participants(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    game_id = int(callback.data.split(":")[1])
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    if not db.user_registration(game_id=game_id, user_id=int(user["id"])):
        await callback.answer("Вы не зарегистрированы на эту игру.", show_alert=True)
        return
    game = db.get_game(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    rows = db.list_game_registrations(game_id)
    await callback.message.answer(_game_participants_text(game, rows))
    await callback.answer()


@router.callback_query(F.data.startswith("myreg_cancel:"))
async def cancel_my_registration(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    game_id = int(callback.data.split(":")[1])
    user = db.get_user_by_tg(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    removed = db.unregister_user(game_id=game_id, user_id=int(user["id"]))
    if removed:
        await callback.answer("Регистрация отменена.")
        items = db.list_user_registrations(int(user["id"]))
        data = await state.get_data()
        current_stage = data.get("my_registrations_stage", "active")
        if current_stage not in {"active", "completed"}:
            current_stage = "active"
        if not items:
            await callback.message.edit_text("У вас пока нет активных регистраций.")
            await state.update_data(my_registrations_message_id=None, my_registrations_stage="active")
            return
        visible_items = _filter_registrations_by_stage(items, current_stage)
        mode = data.get("my_registrations_mode", "cancel")
        if mode not in {"view", "cancel"}:
            mode = "cancel"
        await callback.message.edit_text(
            _my_registrations_mode_text(mode, current_stage, visible_items),
            reply_markup=user_registrations_keyboard_by_mode(visible_items, current_stage, mode),
        )
    else:
        await callback.answer("Вы не зарегистрированы на эту игру.", show_alert=True)


@router.message(F.text.in_({"Статистика", "📊 Статистика"}))
async def statistics_stub_handler(message: Message) -> None:
    await message.answer(
        "📊 Статистика\n"
        "Раздел в разработке.\n"
        "Скоро здесь появятся данные из внешней базы."
    )
