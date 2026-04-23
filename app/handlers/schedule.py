from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db.database import Database, GAME_TYPE_LABELS
from app.keyboards.inline import (
    game_days_keyboard,
    game_slots_keyboard,
    game_types_keyboard,
    registration_role_keyboard,
    user_registrations_keyboard,
)
from app.utils import ensure_superadmin

router = Router(name="schedule")


def _restore_day(token: str) -> str | None:
    if len(token) != 8 or not token.isdigit():
        return None
    return f"{token[:2]}.{token[2:4]}.{token[4:]}"


def _role_kind_label(role: str) -> str:
    return "Игрок" if role == "player" else "Ведущий/судья"


def _my_registrations_text(items: list[dict]) -> str:
    lines = ["Ваши регистрации:"]
    for item in items:
        game_type = GAME_TYPE_LABELS.get(item.get("game_type", ""), item.get("game_type", "-"))
        role = _role_kind_label(item["role"])
        lines.append(f"• #{item['id']} | {item['starts_at']} | {item['location']} | {game_type} | {role}")
    return "\n".join(lines)


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
    if game_type not in GAME_TYPE_LABELS:
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
            f"{GAME_TYPE_LABELS[game_type]}: выберите роль для регистрации.",
            reply_markup=registration_role_keyboard(can_play=True, can_staff=True, game_type=game_type),
        )
    elif can_play:
        days = db.list_open_days(game_type=game_type)
        if not days:
            await callback.message.answer(f"Для формата «{GAME_TYPE_LABELS[game_type]}» пока нет открытых дней.")
        else:
            await callback.message.answer(
                f"{GAME_TYPE_LABELS[game_type]}: выберите день.",
                reply_markup=game_days_keyboard(game_type=game_type, role_kind="player", days=days),
            )
    elif can_staff:
        days = db.list_open_days(game_type=game_type)
        if not days:
            await callback.message.answer(f"Для формата «{GAME_TYPE_LABELS[game_type]}» пока нет открытых дней.")
        else:
            await callback.message.answer(
                f"{GAME_TYPE_LABELS[game_type]}: выберите день.",
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
    if game_type not in GAME_TYPE_LABELS or role_kind not in {"player", "staff"}:
        await callback.answer("Некорректный выбор.", show_alert=True)
        return
    days = db.list_open_days(game_type=game_type)
    if not days:
        await callback.answer("Открытых дней пока нет.", show_alert=True)
        return
    await callback.message.answer(
        f"{GAME_TYPE_LABELS[game_type]} ({_role_kind_label(role_kind)}): выберите день.",
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
    games = db.list_open_games_by_type_and_day(game_type=game_type, day=day)
    if not games:
        await callback.answer("На выбранный день нет открытых игр.", show_alert=True)
        return
    await callback.message.answer(
        f"{GAME_TYPE_LABELS[game_type]}, {day}. Выберите игру:",
        reply_markup=game_slots_keyboard(game_type=game_type, role_kind=role_kind, games=games),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reg_game:"))
async def register_for_game(callback: CallbackQuery, db: Database) -> None:
    if not db.user_exists(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return
    _, game_type, role_kind, game_id_raw = callback.data.split(":")
    game_id = int(game_id_raw)
    game = db.get_game_with_counts(game_id)
    if not game or game.get("game_type") != game_type:
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
    games = db.list_open_games_by_type_and_day(game_type=game_type, day=day)
    try:
        await callback.message.edit_text(
            f"{GAME_TYPE_LABELS[game_type]}, {day}. Выберите игру:",
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
    data = await state.get_data()
    previous_message_id = data.get("my_registrations_message_id")
    items = db.list_user_registrations(int(user["id"]))
    text = "У вас пока нет активных регистраций."
    markup = None
    if not items:
        await state.update_data(my_registrations_message_id=None)
    else:
        text = _my_registrations_text(items)
        markup = user_registrations_keyboard(items)

    if previous_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=int(previous_message_id),
                text=text,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest:
            pass

    sent = await message.answer(text, reply_markup=markup)
    await state.update_data(my_registrations_message_id=sent.message_id)


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
        if not items:
            await callback.message.edit_text("У вас пока нет активных регистраций.")
            await state.update_data(my_registrations_message_id=None)
            return
        await callback.message.edit_text(
            _my_registrations_text(items),
            reply_markup=user_registrations_keyboard(items),
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
