import sqlite3
from datetime import datetime
from typing import Any


ROLE_LIMITS = {
    "host": 1,
    "judge": 3,
    "player": 10,
}

ROLE_LABELS = {
    "host": "Ведущий",
    "judge": "Судья",
    "player": "Игрок",
}


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                nickname TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                starts_at TEXT NOT NULL,
                location TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('host', 'judge', 'player')),
                created_at TEXT NOT NULL,
                UNIQUE (game_id, user_id),
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def ensure_user(self, tg_id: int, phone: str, nickname: str) -> int:
        now = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users (tg_id, phone, nickname, created_at) VALUES (?, ?, ?, ?)",
            (tg_id, phone, nickname, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def user_exists(self, tg_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        return row is not None

    def get_user_by_tg(self, tg_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        return dict(row) if row else None

    def nickname_taken(self, nickname: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE lower(nickname) = lower(?)",
            (nickname.strip(),),
        ).fetchone()
        return row is not None

    def add_admin(self, tg_id: int) -> bool:
        now = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute("INSERT OR IGNORE INTO admins (tg_id, created_at) VALUES (?, ?)", (tg_id, now))
        self.conn.commit()
        return cur.rowcount > 0

    def remove_admin(self, tg_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def is_admin(self, tg_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,)).fetchone()
        return row is not None

    def list_admins(self) -> list[int]:
        rows = self.conn.execute("SELECT tg_id FROM admins ORDER BY tg_id").fetchall()
        return [int(row["tg_id"]) for row in rows]

    def create_game(self, starts_at: str, location: str) -> int:
        now = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO games (starts_at, location, created_at) VALUES (?, ?, ?)",
            (starts_at, location, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_games(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            GROUP BY g.id
            ORDER BY g.starts_at
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": int(row["id"]),
                    "starts_at": row["starts_at"],
                    "location": row["location"],
                    "hosts": int(row["hosts"] or 0),
                    "judges": int(row["judges"] or 0),
                    "players": int(row["players"] or 0),
                }
            )
        return result

    def get_game(self, game_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return dict(row) if row else None

    def user_registration(self, game_id: int, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM registrations WHERE game_id = ? AND user_id = ?",
            (game_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def role_count(self, game_id: int, role: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM registrations WHERE game_id = ? AND role = ?",
            (game_id, role),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def register_user(self, game_id: int, user_id: int, role: str) -> tuple[bool, str]:
        if role not in ROLE_LIMITS:
            return False, "Неизвестная роль."

        current = self.user_registration(game_id=game_id, user_id=user_id)
        if current and current["role"] == role:
            return False, "Вы уже записаны на эту игру с выбранной ролью."

        role_current_count = self.role_count(game_id=game_id, role=role)
        if role_current_count >= ROLE_LIMITS[role]:
            return False, f"Роль «{ROLE_LABELS[role]}» уже полностью занята."

        now = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        if current:
            cur.execute(
                "UPDATE registrations SET role = ?, created_at = ? WHERE id = ?",
                (role, now, current["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO registrations (game_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                (game_id, user_id, role, now),
            )
        self.conn.commit()
        return True, f"Вы успешно записались на игру в роли: {ROLE_LABELS[role]}."
