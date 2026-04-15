from datetime import datetime

from app.config import Config
from app.db.database import Database


def ensure_superadmin(tg_id: int, db: Database, config: Config) -> None:
    if tg_id in config.superadmin_ids:
        db.add_admin(tg_id)


def normalize_phone(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit())


def ensure_admin_by_phone(tg_id: int, phone: str, db: Database, config: Config) -> bool:
    if normalize_phone(phone) == config.admin_phone:
        return db.add_admin(tg_id)
    return False


def parse_game_datetime(raw: str) -> str | None:
    try:
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y %H:%M")
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return None
