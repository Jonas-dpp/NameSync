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
