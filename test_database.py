"""Unit tests for database module in Name Sync (Sprint 1)."""

import sqlite3
import pytest
import database


@pytest.fixture
def test_db(tmp_path):
    """Provides a temporary database file path and initializes schema."""
    db_file = str(tmp_path / "test_namesync.db")
    database.init_db(db_file)
    return db_file


def test_init_db_creates_tables(test_db):
    """Test that groups, users, and names tables are created correctly."""
    with database.get_connection(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

    assert "groups" in tables
    assert "users" in tables
    assert "names" in tables


def test_foreign_key_cascade_deletion(test_db):
    """Test that deleting a group cascades deletion to users and names."""
    group_id = "test-group-123"

    with database.get_connection(test_db) as conn:
        cursor = conn.cursor()

        # Insert group
        cursor.execute("INSERT INTO groups (group_id) VALUES (?);", (group_id,))

        # Insert user
        cursor.execute(
            "INSERT INTO users (group_id, display_name, is_admin) VALUES (?, ?, ?);",
            (group_id, "Alice", True),
        )
        user_id = cursor.lastrowid

        # Insert name suggestion
        cursor.execute(
            "INSERT INTO names (user_id, suggested_name) VALUES (?, ?);",
            (user_id, "Luna"),
        )
        conn.commit()

        # Verify data exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE group_id = ?;", (group_id,))
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM names WHERE user_id = ?;", (user_id,))
        assert cursor.fetchone()[0] == 1

        # Delete group
        cursor.execute("DELETE FROM groups WHERE group_id = ?;", (group_id,))
        conn.commit()

        # Verify cascade deletion
        cursor.execute("SELECT COUNT(*) FROM users WHERE group_id = ?;", (group_id,))
        assert cursor.fetchone()[0] == 0

        cursor.execute("SELECT COUNT(*) FROM names WHERE user_id = ?;", (user_id,))
        assert cursor.fetchone()[0] == 0


def test_cleanup_old_groups(test_db):
    """Test that groups older than 7 days are deleted by cleanup_old_groups."""
    with database.get_connection(test_db) as conn:
        cursor = conn.cursor()

        # Insert new group (created now)
        cursor.execute("INSERT INTO groups (group_id) VALUES (?);", ("new-group",))

        # Insert old group (created 8 days ago)
        cursor.execute(
            "INSERT INTO groups (group_id, created_at) VALUES (?, datetime('now', '-8 days'));",
            ("old-group",),
        )

        # Insert old group user and name
        cursor.execute(
            "INSERT INTO users (group_id, display_name) VALUES (?, ?);",
            ("old-group", "Bob"),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO names (user_id, suggested_name) VALUES (?, ?);",
            (user_id, "Milo"),
        )
        conn.commit()

    # Run cleanup
    deleted_count = database.cleanup_old_groups(days=7, db_name=test_db)
    assert deleted_count == 1

    # Verify remaining database state
    with database.get_connection(test_db) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT group_id FROM groups;")
        groups = [row[0] for row in cursor.fetchall()]
        assert "new-group" in groups
        assert "old-group" not in groups

        cursor.execute("SELECT COUNT(*) FROM users;")
        assert cursor.fetchone()[0] == 0

        cursor.execute("SELECT COUNT(*) FROM names;")
        assert cursor.fetchone()[0] == 0
