from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database
from app.keyboards.reply import (
    affiliation_keyboard,
    main_keyboard,
    request_contact_keyboard,
    salutation_keyboard,
)
from app.states import RegistrationStates
from app.utils import ensure_admin_by_phone, ensure_superadmin

router = Router(name="registration")


@router.message(RegistrationStates.waiting_for_contact, ~F.contact)
async def contact_required_handler(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопку «Поделиться номером телефона». 📱",
        reply_markup=request_contact_keyboard(),
    )


@router.message(RegistrationStates.waiting_for_contact, F.contact)
async def contact_handler(message: Message, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Необходимо отправить свой номер телефона.")
        return

    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(RegistrationStates.waiting_for_salutation)
    await message.answer(
        "Отлично! Как к вам обращаться?",
        reply_markup=salutation_keyboard(),
    )


@router.message(RegistrationStates.waiting_for_salutation)
async def salutation_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    salutation_map = {
        "господин": "господин",
        "🤵 господин": "господин",
        "госпожа": "госпожа",
        "👒 госпожа": "госпожа",
    }
    salutation = salutation_map.get(text)
    if not salutation:
        await message.answer("Выберите обращение кнопкой: «Господин» или «Госпожа».")
        return

    await state.update_data(salutation=salutation)
    await state.set_state(RegistrationStates.waiting_for_full_name)
    await message.answer("Отлично! Теперь введите ваше ФИО.")


@router.message(RegistrationStates.waiting_for_full_name)
async def full_name_handler(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 5:
        await message.answer("Пожалуйста, введите полное ФИО (минимум 5 символов).")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_affiliation)
    await message.answer(
        "Укажите, пожалуйста, ваш статус по проходу:",
        reply_markup=affiliation_keyboard(),
    )


@router.message(RegistrationStates.waiting_for_affiliation)
async def affiliation_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    affiliation_map = {
        "С ВМК": "vmk",
        "🎓 С ВМК": "vmk",
        "Из МГУ, пропуск не нужен": "mgu_no_pass",
        "🏛️ Из МГУ, пропуск не нужен": "mgu_no_pass",
        "Вне МГУ, нужен пропуск": "outside_need_pass",
        "🪪 Вне МГУ, нужен пропуск": "outside_need_pass",
    }
    affiliation = affiliation_map.get(text)
    if not affiliation:
        await message.answer(
            "Выберите один из вариантов кнопками:\n"
            "• С ВМК\n"
            "• Из МГУ, пропуск не нужен\n"
            "• Вне МГУ, нужен пропуск"
        )
        return

    await state.update_data(affiliation=affiliation)
    await state.set_state(RegistrationStates.waiting_for_nickname)
    await message.answer("Супер! Теперь придумайте и введите свой уникальный никнейм ✍️")


@router.message(RegistrationStates.waiting_for_nickname)
async def nickname_handler(
    message: Message, state: FSMContext, db: Database, config: Config
) -> None:
    nickname = (message.text or "").strip()

    if len(nickname) < 3 or len(nickname) > 32:
        await message.answer("Никнейм должен содержать от 3 до 32 символов. Попробуйте ещё раз.")
        return

    if db.nickname_taken(nickname):
        await message.answer("Такой никнейм уже занят. Введите другой.")
        return

    data = await state.get_data()
    phone = data.get("phone")
    salutation = data.get("salutation")
    full_name = data.get("full_name")
    affiliation = data.get("affiliation")
    if not phone:
        await message.answer("Что-то пошло не так. Начните заново: /start")
        await state.clear()
        return
    if salutation not in {"господин", "госпожа"}:
        await message.answer("Обращение не выбрано. Начните заново: /start")
        await state.clear()
        return
    if not full_name:
        await message.answer("ФИО не найдено. Начните заново: /start")
        await state.clear()
        return
    if affiliation not in {"vmk", "mgu_no_pass", "outside_need_pass"}:
        await message.answer("Статус прохода не выбран. Начните заново: /start")
        await state.clear()
        return

    tg_id = message.from_user.id
    db.create_user(
        tg_id=tg_id,
        phone=phone,
        nickname=nickname,
        salutation=salutation,
        full_name=full_name,
        affiliation=affiliation,
        username=message.from_user.username,
    )
    ensure_superadmin(tg_id, db, config)
    ensure_admin_by_phone(tg_id=tg_id, phone=phone, db=db, config=config)
    if message.from_user.username and db.consume_pending_admin_username(message.from_user.username):
        db.add_admin(tg_id)
    await state.clear()
    is_admin = db.is_admin(tg_id)
    await message.answer(
        f"Регистрация завершена! 🎉 Добро пожаловать, {salutation} {nickname}.",
        reply_markup=main_keyboard(is_admin=is_admin),
    )
    if is_admin:
        await message.answer("🛠️ Вы переведены в статус администратора.")
