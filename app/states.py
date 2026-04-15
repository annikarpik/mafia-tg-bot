from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_nickname = State()


class AdminStates(StatesGroup):
    waiting_for_admin_to_add = State()
    waiting_for_admin_to_remove = State()
    waiting_for_game_datetime = State()
    waiting_for_game_location = State()
