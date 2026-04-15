from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Config
from app.db.database import Database
from app.keyboards.reply import main_keyboard, request_contact_keyboard
from app.states import RegistrationStates
from app.utils import ensure_superadmin

router = Router(name="common")


@router.message(Command("start"))
async def start_handler(
    message: Message, state: FSMContext, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)
    await state.clear()

    if db.user_exists(tg_id):
        await message.answer(
            "Вы уже зарегистрированы. Используйте меню ниже.",
            reply_markup=main_keyboard(is_admin=db.is_admin(tg_id)),
        )
        return

    await message.answer(
        "Добро пожаловать в бота записи на игры Мафии!\n"
        "Для начала зарегистрируйтесь — поделитесь своим номером телефона.",
        reply_markup=request_contact_keyboard(),
    )
    await state.set_state(RegistrationStates.waiting_for_contact)


@router.message(Command("admin"))
async def admin_auth_handler(
    message: Message, command: CommandObject, db: Database, config: Config
) -> None:
    tg_id = message.from_user.id
    ensure_superadmin(tg_id, db, config)
    args = (command.args or "").strip()

    if not args:
        await message.answer("Использование: /admin <пароль>")
        return

    if args != config.admin_password:
        await message.answer("Неверный пароль администратора.")
        return

    db.add_admin(tg_id)
    await message.answer(
        "Вы успешно авторизованы как админ.",
        reply_markup=main_keyboard(is_admin=True),
    )


@router.message(F.text == "Назад")
async def back_to_main_handler(
    message: Message, state: FSMContext, db: Database
) -> None:
    await state.clear()
    await message.answer(
        "Главное меню.",
        reply_markup=main_keyboard(is_admin=db.is_admin(message.from_user.id)),
    )


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.answer("Используйте меню или команду /start.")
