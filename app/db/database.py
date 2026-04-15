import sqlite3
from datetime import datetime
from typing import Any


ROLE_LIMITS: dict[str, int] = {
    "host": 1,
    "judge": 3,
    "player": 10,
}

ROLE_LABELS: dict[str, str] = {
    "host": "Ведущий",
    "judge": "Судья",
    "player": "Игрок",
}

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id      INTEGER UNIQUE NOT NULL,
    phone      TEXT    NOT NULL,
    username   TEXT,
    salutation TEXT    NOT NULL DEFAULT 'господин',
    nickname   TEXT    UNIQUE NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id      INTEGER UNIQUE NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    starts_at  TEXT    NOT NULL,
    location   TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS registrations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    role       TEXT    NOT NULL CHECK(role IN ('host', 'judge', 'player')),
    created_at TEXT    NOT NULL,
    UNIQUE (game_id, user_id),
    FOREIGN KEY(game_id) REFERENCES games(id)  ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id)  ON DELETE CASCADE
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_INIT_SQL)
        self._ensure_schema_columns()
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema_columns(self) -> None:
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "username" not in columns:
            self.conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if "salutation" not in columns:
            self.conn.execute(
                "ALTER TABLE users ADD COLUMN salutation TEXT NOT NULL DEFAULT 'господин'"
            )

    # ------------------------------------------------------------------ users

    def user_exists(self, tg_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM users WHERE tg_id = ?", (tg_id,)
        ).fetchone() is not None

    def get_user_by_tg(self, tg_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_phone(self, phone: str) -> dict[str, Any] | None:
        normalized = "".join(ch for ch in phone if ch.isdigit())
        row = self.conn.execute(
            "SELECT * FROM users WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', ''), '(', ''), ')', '') = ?",
            (normalized,),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        clean = username.strip().lstrip("@")
        if not clean:
            return None
        row = self.conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(?)",
            (clean,),
        ).fetchone()
        return dict(row) if row else None

    def nickname_taken(self, nickname: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM users WHERE lower(nickname) = lower(?)", (nickname.strip(),)
        ).fetchone() is not None

    def create_user(
        self,
        tg_id: int,
        phone: str,
        nickname: str,
        salutation: str,
        username: str | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO users (tg_id, phone, username, salutation, nickname, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tg_id, phone, username, salutation, nickname, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_user_username(self, tg_id: int, username: str | None) -> None:
        self.conn.execute("UPDATE users SET username = ? WHERE tg_id = ?", (username, tg_id))
        self.conn.commit()

    # ----------------------------------------------------------------- admins

    def is_admin(self, tg_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,)
        ).fetchone() is not None

    def add_admin(self, tg_id: int) -> bool:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO admins (tg_id, created_at) VALUES (?, ?)", (tg_id, now)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def remove_admin(self, tg_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_admins(self) -> list[int]:
        rows = self.conn.execute("SELECT tg_id FROM admins ORDER BY tg_id").fetchall()
        return [int(r["tg_id"]) for r in rows]

    # ------------------------------------------------------------------ games

    def create_game(self, starts_at: str, location: str) -> int:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO games (starts_at, location, created_at) VALUES (?, ?, ?)",
            (starts_at, location, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_game(self, game_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_games(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                SUM(CASE WHEN r.role = 'host'   THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge'  THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            GROUP BY g.id
            ORDER BY g.starts_at
            """
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "starts_at": r["starts_at"],
                "location": r["location"],
                "hosts": int(r["hosts"] or 0),
                "judges": int(r["judges"] or 0),
                "players": int(r["players"] or 0),
            }
            for r in rows
        ]

    def get_game_with_counts(self, game_id: int) -> dict[str, Any] | None:
        for game in self.list_games():
            if game["id"] == game_id:
                return game
        return None

    def list_game_registrations(self, game_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT u.nickname, r.role
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            WHERE r.game_id = ?
            ORDER BY
                CASE r.role
                    WHEN 'host' THEN 1
                    WHEN 'judge' THEN 2
                    WHEN 'player' THEN 3
                    ELSE 4
                END,
                lower(u.nickname)
            """,
            (game_id,),
        ).fetchall()
        return [{"nickname": row["nickname"], "role": row["role"]} for row in rows]

    # --------------------------------------------------------- registrations

    def _user_registration(self, game_id: int, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM registrations WHERE game_id = ? AND user_id = ?",
            (game_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def _role_count(self, game_id: int, role: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM registrations WHERE game_id = ? AND role = ?",
            (game_id, role),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def register_user(self, game_id: int, user_id: int, role: str) -> tuple[bool, str]:
        if role not in ROLE_LIMITS:
            return False, "Неизвестная роль."

        existing = self._user_registration(game_id, user_id)
        if existing and existing["role"] == role:
            return False, "Вы уже записаны на эту игру с выбранной ролью."

        if self._role_count(game_id, role) >= ROLE_LIMITS[role]:
            return False, f"Роль «{ROLE_LABELS[role]}» уже полностью занята."

        now = datetime.utcnow().isoformat()
        if existing:
            self.conn.execute(
                "UPDATE registrations SET role = ?, created_at = ? WHERE id = ?",
                (role, now, existing["id"]),
            )
        else:
            self.conn.execute(
                "INSERT INTO registrations (game_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                (game_id, user_id, role, now),
            )
        self.conn.commit()
        return True, f"Вы успешно записались на игру в роли: {ROLE_LABELS[role]}."
