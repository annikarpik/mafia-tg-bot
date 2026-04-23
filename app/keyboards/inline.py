from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

GAME_TYPE_LABELS = {
    "tournament": "🏆 Турнир",
    "funky": "🎉 Фанки",
    "training": "📚 Обучающие",
}
ALL_GAMES_TOKEN = "all"
ALL_GAMES_LABEL = "📋 Показать все игры"


def game_types_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game_type, label in GAME_TYPE_LABELS.items():
        kb.button(text=label, callback_data=f"reg_type:{game_type}")
    kb.button(text=ALL_GAMES_LABEL, callback_data=f"reg_type:{ALL_GAMES_TOKEN}")
    kb.adjust(1)
    return kb.as_markup()


def registration_role_keyboard(can_play: bool, can_staff: bool, game_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_play:
        kb.button(text="🎭 Игрок", callback_data=f"reg_role:{game_type}:player")
    if can_staff:
        kb.button(text="🎙️ Ведущий/судья", callback_data=f"reg_role:{game_type}:staff")
    kb.adjust(1)
    return kb.as_markup()


def game_days_keyboard(game_type: str, role_kind: str, days: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    type_label = "Все форматы" if game_type == ALL_GAMES_TOKEN else GAME_TYPE_LABELS.get(game_type, game_type)
    for day in days:
        token = day.replace(".", "")
        kb.button(text=f"{day} | {type_label}", callback_data=f"reg_day:{game_type}:{role_kind}:{token}")
    kb.adjust(2)
    return kb.as_markup()


def game_slots_keyboard(game_type: str, role_kind: str, games: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game in games:
        current = int(game.get("players", 0)) if role_kind == "player" else int(game.get("staff", 0))
        limit = 10 if role_kind == "player" else 4
        type_label = GAME_TYPE_LABELS.get(game.get("game_type", game_type), str(game.get("game_type", game_type)))
        kb.button(
            text=f"{type_label} | Игра #{game['id']} {game['time']} ({current}/{limit})",
            callback_data=f"reg_game:{game_type}:{role_kind}:{game['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def user_registrations_keyboard(items: list[dict], stage: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    active_label = "🟢 Действующие" if stage == "active" else "Действующие"
    completed_label = "✅ Завершенные" if stage == "completed" else "Завершенные"
    kb.row(
        InlineKeyboardButton(text=active_label, callback_data="myreg_stage:active"),
        InlineKeyboardButton(text=completed_label, callback_data="myreg_stage:completed"),
    )
    for item in items:
        role_label = "Игрок" if item.get("role") == "player" else "Ведущий/судья"
        kb.row(
            InlineKeyboardButton(
            text=f"❌ #{item['id']} {item['starts_at']} ({role_label})",
            callback_data=f"myreg_cancel:{item['id']}",
            )
        )
    return kb.as_markup()


def admin_game_days_keyboard(day_cards: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for card in day_cards:
        day = str(card["day"])
        token = day.replace(".", "")
        types = card.get("types", [])
        if types:
            type_text = ", ".join(types)
            kb.button(text=f"{day} | {type_text}", callback_data=f"adm_day:{token}")
        else:
            kb.button(text=day, callback_data=f"adm_day:{token}")
    kb.adjust(2)
    return kb.as_markup()


def admin_edit_game_days_keyboard(day_cards: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for card in day_cards:
        day = str(card["day"])
        token = day.replace(".", "")
        types = card.get("types", [])
        if types:
            type_text = ", ".join(types)
            kb.button(text=f"{day} | {type_text}", callback_data=f"adm_edit_day:{token}")
        else:
            kb.button(text=day, callback_data=f"adm_edit_day:{token}")
    kb.adjust(2)
    return kb.as_markup()


def admin_games_by_day_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game in games:
        game_type = GAME_TYPE_LABELS.get(game.get("game_type", ""), str(game.get("game_type", "")))
        kb.button(
            text=f"#{game['id']} {game['time']} {game_type}",
            callback_data=f"adm_game:{game['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()
