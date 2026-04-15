from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database
from app.keyboards.reply import main_keyboard, request_contact_keyboard
from app.states import RegistrationStates
from app.utils import ensure_superadmin

router = Router(name="registration")


@router.message(RegistrationStates.waiting_for_contact, ~F.contact)
async def contact_required_handler(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопку «Поделиться номером телефона».",
        reply_markup=request_contact_keyboard(),
    )


@router.message(RegistrationStates.waiting_for_contact, F.contact)
async def contact_handler(message: Message, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Необходимо отправить свой номер телефона.")
        return

    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(RegistrationStates.waiting_for_nickname)
    await message.answer("Отлично! Теперь придумайте и введите свой уникальный никнейм.")


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
    if not phone:
        await message.answer("Что-то пошло не так. Начните заново: /start")
        await state.clear()
        return

    tg_id = message.from_user.id
    db.create_user(tg_id=tg_id, phone=phone, nickname=nickname)
    ensure_superadmin(tg_id, db, config)
    await state.clear()
    await message.answer(
        f"Регистрация завершена! Добро пожаловать, {nickname}.",
        reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
    )
