import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_password: str
    superadmin_ids: set[int]
    db_path: str


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value:
            continue
        if value.lstrip("-").isdigit():
            result.add(int(value))
    return result


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    db_path = os.getenv("DB_PATH", "mafia_bot.db").strip()
    superadmin_ids = _parse_admin_ids(os.getenv("SUPERADMIN_IDS", ""))

    if not bot_token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD не задан в .env")

    return Config(
        bot_token=bot_token,
        admin_password=admin_password,
        superadmin_ids=superadmin_ids,
        db_path=db_path,
    )
