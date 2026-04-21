from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

GAME_TYPE_LABELS = {
    "tournament": "🏆 Турнир",
    "funky": "🎉 Фанки",
    "training": "📚 Обучающие",
}


def game_types_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game_type, label in GAME_TYPE_LABELS.items():
        kb.button(text=label, callback_data=f"reg_type:{game_type}")
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
    for day in days:
        token = day.replace(".", "")
        kb.button(text=day, callback_data=f"reg_day:{game_type}:{role_kind}:{token}")
    kb.adjust(2)
    return kb.as_markup()


def game_slots_keyboard(game_type: str, role_kind: str, games: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for game in games:
        current = int(game.get("players", 0)) if role_kind == "player" else int(game.get("staff", 0))
        limit = 10 if role_kind == "player" else 4
        kb.button(
            text=f"Игра #{game['id']} {game['time']} ({current}/{limit})",
            callback_data=f"reg_game:{game_type}:{role_kind}:{game['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def user_registrations_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        role_label = "Игрок" if item.get("role") == "player" else "Ведущий/судья"
        kb.button(
            text=f"❌ #{item['id']} {item['starts_at']} ({role_label})",
            callback_data=f"myreg_cancel:{item['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()
