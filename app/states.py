from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_salutation = State()
    waiting_for_full_name = State()
    waiting_for_affiliation = State()
    waiting_for_preferred_roles = State()
    waiting_for_nickname = State()


class AdminStates(StatesGroup):
    waiting_for_admin_to_add = State()
    waiting_for_admin_to_remove = State()
    waiting_for_game_type = State()
    waiting_for_game_day = State()
    waiting_for_game_location = State()
    waiting_for_game_time_range = State()
    waiting_for_game_id_to_delete = State()
    waiting_for_game_id_to_edit = State()
    waiting_for_game_id_to_hourly = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()


class ProfileStates(StatesGroup):
    waiting_for_edit_field = State()
    waiting_for_new_value = State()
