from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database
from app.keyboards.reply import main_keyboard, request_contact_keyboard
from app.states import RegistrationStates
from app.utils import ensure_admin_by_phone, ensure_superadmin

router = Router(name="common")


@router.message(Command("start"))
async def start_handler(
    message: Message, state: FSMContext, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)
    await state.clear()

    if db.user_exists(tg_id):
        user = db.get_user_by_tg(tg_id)
        if user:
            db.update_user_username(tg_id=tg_id, username=message.from_user.username)
            ensure_admin_by_phone(tg_id=tg_id, phone=user["phone"], db=db, config=config)
        await message.answer(
            "Вы уже зарегистрированы ✅ Используйте меню ниже.",
            reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
        )
        return

    await message.answer(
        "Добро пожаловать в бота записи на игры Мафии! 🎭\n"
        "Для начала зарегистрируйтесь — поделитесь своим номером телефона.",
        reply_markup=request_contact_keyboard(),
    )
    await state.set_state(RegistrationStates.waiting_for_contact)


@router.message(F.text == "Назад")
async def back_to_main_handler(
    message: Message, state: FSMContext, db: Database
) -> None:
    await state.clear()
    await message.answer(
        "Главное меню 🧭",
        reply_markup=main_keyboard(is_admin=db.is_admin(message.from_user.id)),
    )


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.answer("Используйте меню или команду /start.")
