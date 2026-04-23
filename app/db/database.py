from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

AFFILIATION_LABELS: dict[str, str] = {
    "vmk": "С ВМК",
    "mgu_no_pass": "Из МГУ, пропуск не нужен",
    "outside_need_pass": "Вне МГУ, нужен пропуск",
}

GAME_TYPE_LABELS: dict[str, str] = {
    "tournament": "Турнир",
    "funky": "Фанки",
    "training": "Обучающие",
}

ROLE_LIMITS: dict[str, int] = {
    "host": 1,
    "judge": 2,
    "player": 10,
}

ROLE_LABELS: dict[str, str] = {
    "host": "Ведущий",
    "judge": "Судья",
    "player": "Игрок",
}


class Database:
    def __init__(self, dsn: str) -> None:
        self.conn = psycopg.connect(dsn, row_factory=dict_row)
        self.conn.autocommit = True
        self._init_db()
        self._ensure_schema_columns()
        self._ensure_indexes()

    def close(self) -> None:
        self.conn.close()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                tg_id BIGINT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                username TEXT,
                salutation TEXT NOT NULL DEFAULT 'господин',
                full_name TEXT,
                affiliation TEXT NOT NULL DEFAULT 'vmk',
                can_play BOOLEAN NOT NULL DEFAULT TRUE,
                can_staff BOOLEAN NOT NULL DEFAULT TRUE,
                nickname TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id BIGSERIAL PRIMARY KEY,
                tg_id BIGINT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_admins (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id BIGSERIAL PRIMARY KEY,
                starts_at TEXT NOT NULL,
                location TEXT NOT NULL,
                game_type TEXT NOT NULL DEFAULT 'tournament',
                registration_until TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id BIGSERIAL PRIMARY KEY,
                game_id BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('host', 'judge', 'player')),
                available_from TEXT,
                available_until TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (game_id, user_id)
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reserves (
                id BIGSERIAL PRIMARY KEY,
                game_id BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE (game_id, user_id)
            );
            """
        )

    def _column_exists(self, table: str, column: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            """,
            (table, column),
        ).fetchone()
        return row is not None

    def _ensure_schema_columns(self) -> None:
        if not self._column_exists("users", "username"):
            self.conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if not self._column_exists("users", "salutation"):
            self.conn.execute("ALTER TABLE users ADD COLUMN salutation TEXT NOT NULL DEFAULT 'господин'")
        if not self._column_exists("users", "full_name"):
            self.conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        if not self._column_exists("users", "affiliation"):
            self.conn.execute("ALTER TABLE users ADD COLUMN affiliation TEXT NOT NULL DEFAULT 'vmk'")
        if not self._column_exists("users", "can_play"):
            self.conn.execute("ALTER TABLE users ADD COLUMN can_play BOOLEAN NOT NULL DEFAULT TRUE")
        if not self._column_exists("users", "can_staff"):
            self.conn.execute("ALTER TABLE users ADD COLUMN can_staff BOOLEAN NOT NULL DEFAULT TRUE")
        if not self._column_exists("games", "game_type"):
            self.conn.execute("ALTER TABLE games ADD COLUMN game_type TEXT NOT NULL DEFAULT 'tournament'")
        if not self._column_exists("games", "registration_until"):
            self.conn.execute("ALTER TABLE games ADD COLUMN registration_until TEXT NOT NULL DEFAULT ''")
            self.conn.execute("UPDATE games SET registration_until = starts_at WHERE registration_until = ''")
        if not self._column_exists("registrations", "available_until"):
            self.conn.execute("ALTER TABLE registrations ADD COLUMN available_until TEXT")
        if not self._column_exists("registrations", "available_from"):
            self.conn.execute("ALTER TABLE registrations ADD COLUMN available_from TEXT")

    def _ensure_indexes(self) -> None:
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_games_game_type ON games(game_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_games_starts_at_text ON games(starts_at)")
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_games_starts_at_ts
            ON games ((to_timestamp(starts_at, 'DD.MM.YYYY HH24:MI')))
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_registrations_user_id ON registrations(user_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_registrations_game_id ON registrations(game_id)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_registrations_game_role ON registrations(game_id, role)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users(lower(username))"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_nickname_lower ON users(lower(nickname))"
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_phone_digits
            ON users ((regexp_replace(phone, '[^0-9]', '', 'g')))
            """
        )

    # ------------------------------------------------------------------ users
    def user_exists(self, tg_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM users WHERE tg_id = %s", (tg_id,)).fetchone() is not None

    def get_user_by_tg(self, tg_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM users WHERE tg_id = %s", (tg_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_phone(self, phone: str) -> dict[str, Any] | None:
        normalized = "".join(ch for ch in phone if ch.isdigit())
        row = self.conn.execute(
            """
            SELECT *
            FROM users
            WHERE regexp_replace(phone, '[^0-9]', '', 'g') = %s
            """,
            (normalized,),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        clean = username.strip().lstrip("@")
        if not clean:
            return None
        row = self.conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(%s)",
            (clean,),
        ).fetchone()
        return dict(row) if row else None

    def nickname_taken(self, nickname: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM users WHERE lower(nickname) = lower(%s)",
            (nickname.strip(),),
        ).fetchone() is not None

    def nickname_taken_excluding_user(self, nickname: str, user_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM users WHERE lower(nickname) = lower(%s) AND id != %s",
            (nickname.strip(), user_id),
        ).fetchone() is not None

    def create_user(
        self,
        tg_id: int,
        phone: str,
        nickname: str,
        salutation: str,
        full_name: str,
        affiliation: str,
        can_play: bool,
        can_staff: bool,
        username: str | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        row = self.conn.execute(
            """
            INSERT INTO users (
                tg_id, phone, username, salutation, full_name, affiliation, can_play, can_staff, nickname, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (tg_id, phone, username, salutation, full_name, affiliation, can_play, can_staff, nickname, now),
        ).fetchone()
        return int(row["id"])

    def update_user_username(self, tg_id: int, username: str | None) -> None:
        self.conn.execute("UPDATE users SET username = %s WHERE tg_id = %s", (username, tg_id))

    def update_user_profile_field(self, user_id: int, field: str, value: str) -> bool:
        allowed = {"salutation", "full_name", "affiliation", "nickname"}
        if field not in allowed:
            return False
        cur = self.conn.execute(
            f"UPDATE users SET {field} = %s WHERE id = %s",
            (value, user_id),
        )
        return cur.rowcount > 0

    def update_user_preferred_roles(self, user_id: int, can_play: bool, can_staff: bool) -> bool:
        cur = self.conn.execute(
            """
            UPDATE users
            SET can_play = %s, can_staff = %s
            WHERE id = %s
            """,
            (can_play, can_staff, user_id),
        )
        return cur.rowcount > 0

    # ----------------------------------------------------------------- admins
    def is_admin(self, tg_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM admins WHERE tg_id = %s", (tg_id,)).fetchone() is not None

    def add_admin(self, tg_id: int) -> bool:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO admins (tg_id, created_at) VALUES (%s, %s) ON CONFLICT (tg_id) DO NOTHING",
            (tg_id, now),
        )
        return cur.rowcount > 0

    def remove_admin(self, tg_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM admins WHERE tg_id = %s", (tg_id,))
        return cur.rowcount > 0

    def list_admins(self) -> list[int]:
        rows = self.conn.execute("SELECT tg_id FROM admins ORDER BY tg_id").fetchall()
        return [int(r["tg_id"]) for r in rows]

    def add_pending_admin_username(self, username: str) -> bool:
        clean = username.strip().lstrip("@").lower()
        if not clean:
            return False
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO pending_admins (username, created_at) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
            (clean, now),
        )
        return cur.rowcount > 0

    def consume_pending_admin_username(self, username: str) -> bool:
        clean = username.strip().lstrip("@").lower()
        if not clean:
            return False
        cur = self.conn.execute("DELETE FROM pending_admins WHERE username = %s", (clean,))
        return cur.rowcount > 0

    def remove_pending_admin_username(self, username: str) -> bool:
        clean = username.strip().lstrip("@").lower()
        if not clean:
            return False
        cur = self.conn.execute("DELETE FROM pending_admins WHERE username = %s", (clean,))
        return cur.rowcount > 0

    # ------------------------------------------------------------------ games
    def create_game(self, starts_at: str, location: str, game_type: str) -> int:
        now = datetime.utcnow().isoformat()
        row = self.conn.execute(
            """
            INSERT INTO games (starts_at, location, game_type, registration_until, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (starts_at, location, game_type, starts_at, now),
        ).fetchone()
        return int(row["id"])

    def get_game(self, game_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM games WHERE id = %s", (game_id,)).fetchone()
        return dict(row) if row else None

    def list_games(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                g.registration_until,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players,
                (
                    SELECT COUNT(*)
                    FROM reserves rs
                    WHERE rs.game_id = g.id
                ) AS reserves
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            GROUP BY g.id, g.starts_at, g.location, g.game_type, g.registration_until
            ORDER BY g.starts_at
            """
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "starts_at": r["starts_at"],
                "location": r["location"],
                "game_type": r["game_type"],
                "registration_until": r["registration_until"],
                "hosts": int(r["hosts"] or 0),
                "judges": int(r["judges"] or 0),
                "players": int(r["players"] or 0),
                "staff": int(r["hosts"] or 0) + int(r["judges"] or 0),
                "reserves": int(r["reserves"] or 0),
            }
            for r in rows
        ]

    @staticmethod
    def _parse_datetime(raw: str) -> datetime | None:
        try:
            return datetime.strptime(raw, "%d.%m.%Y %H:%M")
        except ValueError:
            return None

    def list_open_games(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                g.registration_until,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players,
                (
                    SELECT COUNT(*)
                    FROM reserves rs
                    WHERE rs.game_id = g.id
                ) AS reserves
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            WHERE to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI') >= NOW()
            GROUP BY g.id, g.starts_at, g.location, g.game_type, g.registration_until
            ORDER BY to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI')
            """
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "starts_at": r["starts_at"],
                "location": r["location"],
                "game_type": r["game_type"],
                "registration_until": r["registration_until"],
                "hosts": int(r["hosts"] or 0),
                "judges": int(r["judges"] or 0),
                "players": int(r["players"] or 0),
                "staff": int(r["hosts"] or 0) + int(r["judges"] or 0),
                "reserves": int(r["reserves"] or 0),
            }
            for r in rows
        ]

    def list_open_days(self, game_type: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT day
            FROM (
                SELECT
                    to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') AS day,
                    MIN(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI')) AS min_start
                FROM games g
                WHERE g.game_type = %s
                  AND to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI') >= NOW()
                GROUP BY to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY')
            ) grouped
            ORDER BY min_start
            """,
            (game_type,),
        ).fetchall()
        return [str(row["day"]) for row in rows]

    def list_user_registration_game_ids(self, user_id: int) -> set[int]:
        rows = self.conn.execute(
            """
            SELECT game_id
            FROM registrations
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()
        return {int(row["game_id"]) for row in rows}

    def list_open_days_for_user(self, game_type: str, user_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT day
            FROM (
                SELECT
                    to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') AS day,
                    MIN(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI')) AS min_start
                FROM games g
                WHERE to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI') >= NOW()
                  AND (%s = 'all' OR g.game_type = %s)
                  AND NOT EXISTS (
                        SELECT 1
                        FROM registrations r
                        WHERE r.game_id = g.id AND r.user_id = %s
                  )
                GROUP BY to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY')
            ) grouped
            ORDER BY min_start
            """,
            (game_type, game_type, user_id),
        ).fetchall()
        return [str(row["day"]) for row in rows]

    def list_open_games_by_type_and_day(self, game_type: str, day: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                g.registration_until,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players,
                (
                    SELECT COUNT(*)
                    FROM reserves rs
                    WHERE rs.game_id = g.id
                ) AS reserves
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            WHERE to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') = %s
              AND to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI') >= NOW()
              AND (%s = 'all' OR g.game_type = %s)
            GROUP BY g.id, g.starts_at, g.location, g.game_type, g.registration_until
            ORDER BY to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI')
            """,
            (day, game_type, game_type),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            starts_at = self._parse_datetime(row["starts_at"])
            result.append(
                {
                    "id": int(row["id"]),
                    "starts_at": row["starts_at"],
                    "location": row["location"],
                    "game_type": row["game_type"],
                    "registration_until": row["registration_until"],
                    "hosts": int(row["hosts"] or 0),
                    "judges": int(row["judges"] or 0),
                    "players": int(row["players"] or 0),
                    "staff": int(row["hosts"] or 0) + int(row["judges"] or 0),
                    "reserves": int(row["reserves"] or 0),
                    "time": starts_at.strftime("%H:%M") if starts_at else "",
                }
            )
        return result

    def list_open_games_by_type_and_day_for_user(
        self, game_type: str, day: str, user_id: int
    ) -> list[dict[str, Any]]:
        registered_game_ids = self.list_user_registration_game_ids(user_id)
        return [
            game
            for game in self.list_open_games_by_type_and_day(game_type=game_type, day=day)
            if int(game["id"]) not in registered_game_ids
        ]

    def list_game_days(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT day
            FROM (
                SELECT
                    to_char(to_timestamp(starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') AS day,
                    MIN(to_timestamp(starts_at, 'DD.MM.YYYY HH24:MI')) AS min_start
                FROM games
                GROUP BY day
            ) grouped
            ORDER BY min_start
            """
        ).fetchall()
        return [str(row["day"]) for row in rows]

    def list_game_day_cards(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') AS day,
                array_agg(DISTINCT g.game_type) AS game_types
            FROM games g
            GROUP BY to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY')
            ORDER BY MIN(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'))
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            game_types = [GAME_TYPE_LABELS.get(gt, str(gt)) for gt in (row["game_types"] or [])]
            result.append({"day": str(row["day"]), "types": sorted(game_types)})
        return result

    def list_game_day_cards_for_scope(self, game_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') AS day,
                array_agg(DISTINCT g.game_type) AS game_types
            FROM games g
            WHERE (%s = 'all' OR g.game_type = %s)
            GROUP BY to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY')
            ORDER BY MIN(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'))
            """,
            (game_type, game_type),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            game_types = [GAME_TYPE_LABELS.get(gt, str(gt)) for gt in (row["game_types"] or [])]
            result.append({"day": str(row["day"]), "types": sorted(game_types)})
        return result

    def list_games_by_day(self, day: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                g.registration_until,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players,
                (
                    SELECT COUNT(*)
                    FROM reserves rs
                    WHERE rs.game_id = g.id
                ) AS reserves
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            WHERE to_char(to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI'), 'DD.MM.YYYY') = %s
            GROUP BY g.id, g.starts_at, g.location, g.game_type, g.registration_until
            ORDER BY to_timestamp(g.starts_at, 'DD.MM.YYYY HH24:MI')
            """,
            (day,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            starts_at = self._parse_datetime(row["starts_at"])
            result.append(
                {
                    "id": int(row["id"]),
                    "starts_at": row["starts_at"],
                    "location": row["location"],
                    "game_type": row["game_type"],
                    "registration_until": row["registration_until"],
                    "hosts": int(row["hosts"] or 0),
                    "judges": int(row["judges"] or 0),
                    "players": int(row["players"] or 0),
                    "staff": int(row["hosts"] or 0) + int(row["judges"] or 0),
                    "reserves": int(row["reserves"] or 0),
                    "time": starts_at.strftime("%H:%M") if starts_at else "",
                }
            )
        return result

    def is_game_open(self, game_id: int) -> bool:
        game = self.get_game_with_counts(game_id)
        if not game:
            return False
        starts_at = self._parse_datetime(game["starts_at"])
        if starts_at is None:
            return True
        return starts_at >= datetime.now()

    def get_game_with_counts(self, game_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                g.registration_until,
                SUM(CASE WHEN r.role = 'host' THEN 1 ELSE 0 END) AS hosts,
                SUM(CASE WHEN r.role = 'judge' THEN 1 ELSE 0 END) AS judges,
                SUM(CASE WHEN r.role = 'player' THEN 1 ELSE 0 END) AS players,
                (
                    SELECT COUNT(*)
                    FROM reserves rs
                    WHERE rs.game_id = g.id
                ) AS reserves
            FROM games g
            LEFT JOIN registrations r ON r.game_id = g.id
            WHERE g.id = %s
            GROUP BY g.id, g.starts_at, g.location, g.game_type, g.registration_until
            """,
            (game_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "starts_at": row["starts_at"],
            "location": row["location"],
            "game_type": row["game_type"],
            "registration_until": row["registration_until"],
            "hosts": int(row["hosts"] or 0),
            "judges": int(row["judges"] or 0),
            "players": int(row["players"] or 0),
            "staff": int(row["hosts"] or 0) + int(row["judges"] or 0),
            "reserves": int(row["reserves"] or 0),
        }

    def find_conflicting_starts(
        self, planned_starts: list[str], excluded_game_ids: set[int] | None = None
    ) -> list[str]:
        if not planned_starts:
            return []
        excluded_ids = sorted(excluded_game_ids or set())
        rows = self.conn.execute(
            """
            SELECT starts_at
            FROM games
            WHERE starts_at = ANY(%s)
              AND NOT (id = ANY(%s))
            ORDER BY to_timestamp(starts_at, 'DD.MM.YYYY HH24:MI')
            """,
            (planned_starts, excluded_ids),
        ).fetchall()
        return [str(row["starts_at"]) for row in rows]

    def update_game(
        self,
        game_id: int,
        starts_at: str | None = None,
        location: str | None = None,
    ) -> bool:
        game = self.get_game(game_id)
        if not game:
            return False
        new_starts_at = starts_at or game["starts_at"]
        new_location = location or game["location"]
        cur = self.conn.execute(
            """
            UPDATE games
            SET starts_at = %s, location = %s, registration_until = %s
            WHERE id = %s
            """,
            (new_starts_at, new_location, new_starts_at, game_id),
        )
        return cur.rowcount > 0

    def update_game_type(self, game_id: int, game_type: str) -> bool:
        cur = self.conn.execute(
            "UPDATE games SET game_type = %s WHERE id = %s",
            (game_type, game_id),
        )
        return cur.rowcount > 0

    def delete_game(self, game_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM games WHERE id = %s", (game_id,))
        return cur.rowcount > 0

    def list_game_registrations(self, game_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT u.nickname, u.username, r.role, r.available_from, r.available_until
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            WHERE r.game_id = %s
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
        return [
            {
                "nickname": row["nickname"],
                "username": row.get("username"),
                "role": row["role"],
                "available_from": row.get("available_from"),
                "available_until": row["available_until"],
            }
            for row in rows
        ]

    def list_game_reserves(self, game_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT u.nickname, u.tg_id
            FROM reserves r
            JOIN users u ON u.id = r.user_id
            WHERE r.game_id = %s
            ORDER BY r.created_at
            """,
            (game_id,),
        ).fetchall()
        return [{"nickname": row["nickname"], "tg_id": int(row["tg_id"])} for row in rows]

    def list_user_games(self, user_id: int) -> list[dict[str, Any]]:
        rows_main = self.conn.execute(
            """
            SELECT g.id, g.starts_at, g.location, g.registration_until, r.role AS role, 'main' AS bucket
            FROM registrations r
            JOIN games g ON g.id = r.game_id
            WHERE r.user_id = %s
            """,
            (user_id,),
        ).fetchall()
        rows_reserve = self.conn.execute(
            """
            SELECT g.id, g.starts_at, g.location, g.registration_until, NULL AS role, 'reserve' AS bucket
            FROM reserves r
            JOIN games g ON g.id = r.game_id
            WHERE r.user_id = %s
            """,
            (user_id,),
        ).fetchall()
        rows = [*rows_main, *rows_reserve]
        rows.sort(key=lambda row: row["starts_at"])
        return [dict(row) for row in rows]

    def list_user_registrations(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                g.starts_at,
                g.location,
                g.game_type,
                r.role,
                COALESCE(rc.total_registered, 0) AS total_registered
            FROM registrations r
            JOIN games g ON g.id = r.game_id
            LEFT JOIN (
                SELECT game_id, COUNT(*) AS total_registered
                FROM registrations
                GROUP BY game_id
            ) rc ON rc.game_id = g.id
            WHERE r.user_id = %s
            ORDER BY g.starts_at
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_game_user_tg_ids(self, game_id: int) -> list[int]:
        rows_main = self.conn.execute(
            """
            SELECT DISTINCT u.tg_id
            FROM registrations r
            JOIN users u ON u.id = r.user_id
            WHERE r.game_id = %s
            """,
            (game_id,),
        ).fetchall()
        rows_reserve = self.conn.execute(
            """
            SELECT DISTINCT u.tg_id
            FROM reserves r
            JOIN users u ON u.id = r.user_id
            WHERE r.game_id = %s
            """,
            (game_id,),
        ).fetchall()
        tg_ids = {int(row["tg_id"]) for row in rows_main}
        tg_ids.update(int(row["tg_id"]) for row in rows_reserve)
        return sorted(tg_ids)

    # --------------------------------------------------------- registrations
    def _user_registration(self, game_id: int, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM registrations WHERE game_id = %s AND user_id = %s",
            (game_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def user_registration(self, game_id: int, user_id: int) -> dict[str, Any] | None:
        return self._user_registration(game_id=game_id, user_id=user_id)

    def unregister_user(self, game_id: int, user_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM registrations WHERE game_id = %s AND user_id = %s",
            (game_id, user_id),
        )
        return cur.rowcount > 0

    def is_reserved(self, game_id: int, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM reserves WHERE game_id = %s AND user_id = %s",
            (game_id, user_id),
        ).fetchone()
        return row is not None

    def add_to_reserve(self, game_id: int, user_id: int) -> tuple[bool, str]:
        if self._user_registration(game_id, user_id):
            return False, "Вы уже записаны на эту игру в основной состав."
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            """
            INSERT INTO reserves (game_id, user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (game_id, user_id) DO NOTHING
            """,
            (game_id, user_id, now),
        )
        if cur.rowcount == 0:
            return False, "Вы уже находитесь в запасе на эту игру."
        return True, "Вы записаны в Наблюдатель/Запас."

    def remove_from_reserve(self, game_id: int, user_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM reserves WHERE game_id = %s AND user_id = %s",
            (game_id, user_id),
        )
        return cur.rowcount > 0

    def promote_next_reserve_to_player(self, game_id: int) -> dict[str, Any] | None:
        with self.conn.transaction():
            row = self.conn.execute(
                """
                SELECT r.id AS reserve_id, u.id AS user_id, u.tg_id, u.nickname
                FROM reserves r
                JOIN users u ON u.id = r.user_id
                WHERE r.game_id = %s
                ORDER BY r.created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                (game_id,),
            ).fetchone()
            if not row:
                return None

            now = datetime.utcnow().isoformat()
            self.conn.execute("DELETE FROM reserves WHERE id = %s", (row["reserve_id"],))
            self.conn.execute(
                """
                INSERT INTO registrations (game_id, user_id, role, available_from, available_until, created_at)
                VALUES (%s, %s, 'player', NULL, NULL, %s)
                ON CONFLICT (game_id, user_id) DO UPDATE
                    SET role = EXCLUDED.role,
                        available_from = EXCLUDED.available_from,
                        available_until = EXCLUDED.available_until,
                        created_at = EXCLUDED.created_at
                """,
                (game_id, row["user_id"], now),
            )
        return {"tg_id": int(row["tg_id"]), "nickname": row["nickname"]}

    def _role_count(self, game_id: int, role: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM registrations WHERE game_id = %s AND role = %s",
            (game_id, role),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def register_user(
        self,
        game_id: int,
        user_id: int,
        role: str,
        available_from: str | None = None,
        available_until: str | None = None,
    ) -> tuple[bool, str]:
        if role not in ROLE_LIMITS:
            return False, "Неизвестная роль."

        existing = self._user_registration(game_id, user_id)
        if existing and existing["role"] == role:
            previous_until = existing.get("available_until")
            previous_from = existing.get("available_from")
            if previous_until == available_until and previous_from == available_from:
                return False, "Вы уже записаны на эту игру с выбранным временем."
            now = datetime.utcnow().isoformat()
            self.conn.execute(
                """
                UPDATE registrations
                SET available_from = %s, available_until = %s, created_at = %s
                WHERE id = %s
                """,
                (available_from, available_until, now, existing["id"]),
            )
            if available_until:
                if available_from:
                    return True, f"Обновили время: вы можете быть с {available_from} до {available_until}."
                return True, f"Обновили время: вы можете быть до {available_until}."
            return True, "Обновили запись: вы без ограничения по времени."

        if self._role_count(game_id, role) >= ROLE_LIMITS[role]:
            return False, f"Роль «{ROLE_LABELS[role]}» уже полностью занята."

        self.remove_from_reserve(game_id=game_id, user_id=user_id)
        now = datetime.utcnow().isoformat()
        if existing:
            self.conn.execute(
                """
                UPDATE registrations
                SET role = %s, available_from = %s, available_until = %s, created_at = %s
                WHERE id = %s
                """,
                (role, available_from, available_until, now, existing["id"]),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO registrations (game_id, user_id, role, available_from, available_until, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (game_id, user_id, role, available_from, available_until, now),
            )
        role_label = ROLE_LABELS[role]
        if available_until:
            if available_from:
                return True, f"Вы успешно записались на игру в роли: {role_label} (с {available_from} до {available_until})."
            return True, f"Вы успешно записались на игру в роли: {role_label} (до {available_until})."
        return True, f"Вы успешно записались на игру в роли: {role_label} (без ограничения по времени)."

    def register_user_for_kind(self, game_id: int, user_id: int, role_kind: str) -> tuple[bool, str]:
        if role_kind == "player":
            return self.register_user(game_id=game_id, user_id=user_id, role="player")
        if role_kind != "staff":
            return False, "Неизвестный тип роли."
        if self._role_count(game_id, "host") < ROLE_LIMITS["host"]:
            return self.register_user(game_id=game_id, user_id=user_id, role="host")
        return self.register_user(game_id=game_id, user_id=user_id, role="judge")
