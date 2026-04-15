from aiogram import Dispatcher

from .admin import router as admin_router
from .common import router as common_router
from .profile import router as profile_router
from .registration import router as registration_router
from .schedule import router as schedule_router


def setup_routers(dp: Dispatcher) -> None:
    # registration states are caught first to avoid state leaks
    dp.include_router(registration_router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)
    dp.include_router(schedule_router)
    # common goes last: contains the catch-all fallback
    dp.include_router(common_router)
