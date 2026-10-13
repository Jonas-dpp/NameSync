"""Database module for Name Sync (Sprint 1).

Handles SQLite initialization, table creation with foreign key constraints,
and automatic 7-day cleanup of expired groups.
"""

import sqlite3
from typing import Optional

DB_NAME: str = "namesync.db"


def get_connection(db_name: str = DB_NAME) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database and enables foreign keys.

    Args:
        db_name: Name of the SQLite database file.

    Returns:
        sqlite3.Connection: Database connection object with foreign keys enabled.
    """
    conn: sqlite3.Connection = sqlite3.connect(db_name)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_name: str = DB_NAME) -> None:
    """Initializes SQLite database tables if they do not exist.

    Creates three tables:
      - groups: group_id, created_at
      - users: user_id, group_id, display_name, is_admin (FK to groups with CASCADE)
      - names: name_id, user_id, suggested_name (FK to users with CASCADE)

    Args:
        db_name: Name of the SQLite database file.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS names (
                name_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                suggested_name TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            """
        )

        conn.commit()


def cleanup_old_groups(days: int = 7, db_name: str = DB_NAME) -> int:
    """Deletes groups created more than `days` ago (default: 7 days).

    Due to ON DELETE CASCADE constraints, associated users and names are automatically removed.

    Args:
        days: Threshold in days for deleting old groups.
        db_name: Name of the SQLite database file.

    Returns:
        int: Number of deleted groups.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        # Parameter binding used for days calculation
        days_str: str = f"-{days} days"
        cursor.execute(
            "DELETE FROM groups WHERE created_at < datetime('now', ?);",
            (days_str,),
        )
        deleted_count: int = cursor.rowcount
        conn.commit()
        return deleted_count


def create_group(group_id: str, db_name: str = DB_NAME) -> None:
    """Creates a new group record.

    Args:
        group_id: Unique string identifier for the group.
        db_name: Name of the SQLite database file.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO groups (group_id) VALUES (?);",
            (group_id,),
        )
        conn.commit()


def group_exists(group_id: str, db_name: str = DB_NAME) -> bool:
    """Checks whether a group exists in the database.

    Args:
        group_id: Group string identifier.
        db_name: Name of the SQLite database file.

    Returns:
        bool: True if group exists, False otherwise.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM groups WHERE group_id = ?;",
            (group_id,),
        )
        return cursor.fetchone() is not None


def get_user_count(group_id: str, db_name: str = DB_NAME) -> int:
    """Gets total count of users registered in a group.

    Args:
        group_id: Group identifier.
        db_name: Name of the SQLite database file.

    Returns:
        int: Total number of members in the group.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE group_id = ?;",
            (group_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def create_user(
    group_id: str, display_name: str, is_admin: bool = False, db_name: str = DB_NAME
) -> int:
    """Creates a user within a group and returns the generated user_id.

    Args:
        group_id: Group identifier.
        display_name: Display name of the user.
        is_admin: Admin status flag.
        db_name: Name of the SQLite database file.

    Returns:
        int: The created user's ID.
    """
    cleaned_name: str = display_name.strip()
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (group_id, display_name, is_admin) VALUES (?, ?, ?);",
            (group_id, cleaned_name, 1 if is_admin else 0),
        )
        conn.commit()
        return cursor.lastrowid


def get_user(user_id: int, db_name: str = DB_NAME) -> Optional[dict]:
    """Retrieves user info by user_id.

    Args:
        user_id: User identifier.
        db_name: Name of the SQLite database file.

    Returns:
        Optional[dict]: Dictionary with user attributes or None if not found.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, group_id, display_name, is_admin FROM users WHERE user_id = ?;",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "group_id": row[1],
                "display_name": row[2],
                "is_admin": bool(row[3]),
            }
        return None


def add_name_suggestion(
    user_id: int, name: str, db_name: str = DB_NAME
) -> Optional[int]:
    """Normalizes and adds a name suggestion for a user.

    Name is trimmed and converted to Title Case. Empty names are ignored.

    Args:
        user_id: User identifier.
        name: Name string input.
        db_name: Name of the SQLite database file.

    Returns:
        Optional[int]: Generated name_id, or None if input was empty.
    """
    normalized_name: str = name.strip().title()
    if not normalized_name:
        return None

    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO names (user_id, suggested_name) VALUES (?, ?);",
            (user_id, normalized_name),
        )
        conn.commit()
        return cursor.lastrowid


def get_user_names(user_id: int, db_name: str = DB_NAME) -> list[str]:
    """Gets all suggested names submitted by a specific user.

    Args:
        user_id: User identifier.
        db_name: Name of the SQLite database file.

    Returns:
        list[str]: List of suggested names.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT suggested_name FROM names WHERE user_id = ? ORDER BY name_id ASC;",
            (user_id,),
        )
        return [row[0] for row in cursor.fetchall()]


def get_group_name_ranking(
    group_id: str, db_name: str = DB_NAME
) -> list[tuple[str, int]]:
    """Retrieves ranked list of names for a group sorted by frequency.

    Args:
        group_id: Group identifier.
        db_name: Name of the SQLite database file.

    Returns:
        list[tuple[str, int]]: List of (suggested_name, count) tuples.
    """
    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            """
            SELECT n.suggested_name, COUNT(*) as count
            FROM names n
            JOIN users u ON n.user_id = u.user_id
            WHERE u.group_id = ?
            GROUP BY n.suggested_name
            ORDER BY count DESC, n.suggested_name ASC;
            """,
            (group_id,),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]


def get_group_user_matches(
    group_id: str, db_name: str = DB_NAME
) -> list[tuple[str, str, int, list[str]]]:
    """Calculates name intersections between pairs of users in a group.

    Args:
        group_id: Group identifier.
        db_name: Name of the SQLite database file.

    Returns:
        list[tuple[str, str, int, list[str]]]: List of tuples containing
        (user_1_name, user_2_name, shared_count, shared_names) sorted by shared_count DESC.
    """
    import itertools

    with get_connection(db_name) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, display_name FROM users WHERE group_id = ? ORDER BY user_id ASC;",
            (group_id,),
        )
        users = cursor.fetchall()

        if len(users) < 2:
            return []

        user_names_map: dict[int, set[str]] = {}
        for uid, _ in users:
            cursor.execute(
                "SELECT suggested_name FROM names WHERE user_id = ?;", (uid,)
            )
            user_names_map[uid] = {row[0] for row in cursor.fetchall()}

    matches: list[tuple[str, str, int, list[str]]] = []
    for (u1_id, u1_name), (u2_id, u2_name) in itertools.combinations(users, 2):
        shared: set[str] = user_names_map[u1_id] & user_names_map[u2_id]
        if shared:
            sorted_shared = sorted(shared)
            matches.append((u1_name, u2_name, len(shared), sorted_shared))

    matches.sort(key=lambda item: (-item[2], item[0], item[1]))
    return matches
