from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db.database import Database, ROLE_LABELS
from app.keyboards.inline import games_keyboard, roles_keyboard
from app.utils import ensure_superadmin

router = Router(name="schedule")


def _participants_block(db: Database, game_id: int) -> str:
    role_order = ("host", "judge", "player")
    grouped: dict[str, list[str]] = {key: [] for key in role_order}
    for row in db.list_game_registrations(game_id):
        grouped.setdefault(row["role"], []).append(row["nickname"])

    lines: list[str] = ["Уже записались:"]
    for role in role_order:
        label = ROLE_LABELS[role]
        people = grouped.get(role, [])
        lines.append(
            f"• {label}: {', '.join(people) if people else 'пока никого'}"
        )
    return "\n".join(lines)


@router.message(F.text == "Расписание игр")
async def schedule_handler(
    message: Message, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)

    if not db.user_exists(tg_id):
        await message.answer("Сначала пройдите регистрацию: /start")
        return

    games = db.list_games()
    if not games:
        await message.answer("Пока нет запланированных игр 😌")
        return

    await message.answer(
        f"Доступно игр: {len(games)} 🎲 Выберите игру:",
        reply_markup=games_keyboard(games),
    )


@router.callback_query(F.data.startswith("game:"))
async def game_pick_handler(callback: CallbackQuery, db: Database) -> None:
    tg_id = callback.from_user.id
    if not db.user_exists(tg_id):
        await callback.answer("Сначала пройдите регистрацию: /start", show_alert=True)
        return

    game_id = int(callback.data.split(":")[1])
    game = db.get_game_with_counts(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    await callback.message.answer(
        f"Игра #{game['id']} 🎭\n"
        f"Дата и время: {game['starts_at']}\n"
        f"Место: {game['location']}\n\n"
        f"{_participants_block(db, game_id)}\n\n"
        "Выберите роль:",
        reply_markup=roles_keyboard(game_id, game),
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

    if not db.get_game(game_id):
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    user = db.get_user_by_tg(tg_id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    _, text = db.register_user(game_id=game_id, user_id=int(user["id"]), role=role)
    await callback.answer()
    await callback.message.answer(f"{text} ✅")

    refreshed = db.get_game_with_counts(game_id)
    if refreshed:
        await callback.message.edit_reply_markup(
            reply_markup=roles_keyboard(game_id, refreshed)
        )
