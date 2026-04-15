from datetime import datetime

from app.config import Config
from app.db.database import Database


def ensure_superadmin(tg_id: int, db: Database, config: Config) -> None:
    if tg_id in config.superadmin_ids:
        db.add_admin(tg_id)


def parse_game_datetime(raw: str) -> str | None:
    try:
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y %H:%M")
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return None
