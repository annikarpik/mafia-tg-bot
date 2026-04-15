import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_phone: str
    superadmin_ids: frozenset[int]
    db_dsn: str


def _parse_admin_ids(raw: str) -> frozenset[int]:
    result: set[int] = set()
    for chunk in raw.split(","):
        value = chunk.strip()
        if value.lstrip("-").isdigit():
            result.add(int(value))
    return frozenset(result)


def _normalize_phone(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit())


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_phone = _normalize_phone(os.getenv("ADMIN_PHONE", ""))
    db_dsn = (os.getenv("DB_DSN") or os.getenv("DATABASE_URL") or "").strip()
    superadmin_ids = _parse_admin_ids(os.getenv("SUPERADMIN_IDS", ""))

    if not bot_token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    if not admin_phone:
        raise RuntimeError("ADMIN_PHONE не задан в .env")
    if not db_dsn:
        raise RuntimeError("DB_DSN не задан в .env")

    return Config(
        bot_token=bot_token,
        admin_phone=admin_phone,
        superadmin_ids=superadmin_ids,
        db_dsn=db_dsn,
    )
