from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db.database import AFFILIATION_LABELS, Database
from app.keyboards.reply import (
    affiliation_keyboard,
    main_keyboard,
    profile_edit_field_keyboard,
    salutation_keyboard,
)
from app.states import ProfileStates

router = Router(name="profile")


def _profile_text(user: dict) -> str:
    affiliation = AFFILIATION_LABELS.get(user.get("affiliation", ""), "-")
    return (
        "Ваш профиль:\n"
        f"• Обращение: {user.get('salutation', '-')}\n"
        f"• ФИО: {user.get('full_name') or '-'}\n"
        f"• Статус: {affiliation}\n"
        f"• Никнейм: {user.get('nickname')}\n"
        f"• Телефон: {user.get('phone')}"
    )


@router.message(F.text.in_({"Редактировать профиль", "📝 Редактировать профиль"}))
async def profile_edit_start(message: Message, state: FSMContext, db: Database) -> None:
    tg_id = message.from_user.id
    user = db.get_user_by_tg(tg_id)
    if not user:
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    await state.set_state(ProfileStates.waiting_for_edit_field)
    await message.answer(
        f"{_profile_text(user)}\n\nЧто хотите изменить?",
        reply_markup=profile_edit_field_keyboard(),
    )


@router.message(ProfileStates.waiting_for_edit_field, ~F.text.in_({"Назад", "↩️ Назад"}))
async def profile_pick_field(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    mapping = {
        "Обращение": "salutation",
        "🤵 Обращение": "salutation",
        "ФИО": "full_name",
        "🪪 ФИО": "full_name",
        "Статус по пропуску": "affiliation",
        "🎓 Статус по пропуску": "affiliation",
        "Никнейм": "nickname",
        "🏷️ Никнейм": "nickname",
    }
    field = mapping.get(text)
    if not field:
        await message.answer("Выберите поле кнопкой.")
        return

    await state.update_data(profile_edit_field=field)
    await state.set_state(ProfileStates.waiting_for_new_value)
    if field == "salutation":
        await message.answer("Выберите обращение:", reply_markup=salutation_keyboard())
    elif field == "affiliation":
        await message.answer(
            "Выберите актуальный статус:",
            reply_markup=affiliation_keyboard(),
        )
    elif field == "full_name":
        await message.answer("Введите новое ФИО:")
    else:
        await message.answer("Введите новый никнейм:")


@router.message(ProfileStates.waiting_for_new_value, ~F.text.in_({"Назад", "↩️ Назад"}))
async def profile_save_value(message: Message, state: FSMContext, db: Database) -> None:
    tg_id = message.from_user.id
    user = db.get_user_by_tg(tg_id)
    if not user:
        await state.clear()
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    data = await state.get_data()
    field = data.get("profile_edit_field")
    raw = (message.text or "").strip()
    if field not in {"salutation", "full_name", "affiliation", "nickname"}:
        await state.clear()
        await message.answer("Поле не выбрано. Начните заново.")
        return

    value = raw
    if field == "salutation":
        salutation_map = {
            "господин": "господин",
            "🤵 господин": "господин",
            "госпожа": "госпожа",
            "👒 госпожа": "госпожа",
        }
        value = salutation_map.get(raw.lower(), "")
        if not value:
            await message.answer("Выберите обращение кнопкой: «Господин» или «Госпожа».")
            return
    elif field == "full_name":
        if len(raw) < 5:
            await message.answer("ФИО должно быть не короче 5 символов.")
            return
    elif field == "affiliation":
        affiliation_map = {
            "С ВМК": "vmk",
            "🎓 С ВМК": "vmk",
            "Из МГУ, пропуск не нужен": "mgu_no_pass",
            "🏛️ Из МГУ, пропуск не нужен": "mgu_no_pass",
            "Вне МГУ, нужен пропуск": "outside_need_pass",
            "🪪 Вне МГУ, нужен пропуск": "outside_need_pass",
        }
        value = affiliation_map.get(raw, "")
        if not value:
            await message.answer("Выберите статус одной из кнопок.")
            return
    elif field == "nickname":
        if len(raw) < 3 or len(raw) > 32:
            await message.answer("Никнейм должен быть от 3 до 32 символов.")
            return
        if db.nickname_taken_excluding_user(raw, int(user["id"])):
            await message.answer("Такой никнейм уже занят. Введите другой.")
            return

    db.update_user_profile_field(user_id=int(user["id"]), field=field, value=value)
    await state.clear()
    refreshed = db.get_user_by_tg(tg_id)
    await message.answer(
        f"Профиль обновлён ✅\n\n{_profile_text(refreshed)}",
        reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
    )
