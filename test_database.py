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


def test_group_creation_and_existence(test_db):
    """Test group creation and group_exists function."""
    group_id = "grp-abc"
    assert not database.group_exists(group_id, db_name=test_db)

    database.create_group(group_id, db_name=test_db)
    assert database.group_exists(group_id, db_name=test_db)


def test_user_creation_lookup_and_count(test_db):
    """Test user creation, lookup, and counting."""
    group_id = "grp-users"
    database.create_group(group_id, db_name=test_db)

    assert database.get_user_count(group_id, db_name=test_db) == 0

    user_id = database.create_user(
        group_id, "  Alice  ", is_admin=True, db_name=test_db
    )
    user_info = database.get_user(user_id, db_name=test_db)

    assert user_info is not None
    assert user_info["user_id"] == user_id
    assert user_info["group_id"] == group_id
    assert user_info["display_name"] == "Alice"
    assert user_info["is_admin"] is True
    assert database.get_user_count(group_id, db_name=test_db) == 1


def test_add_name_suggestion_and_normalization(test_db):
    """Test name suggestion addition and Title-Case normalization."""
    group_id = "grp-names"
    database.create_group(group_id, db_name=test_db)
    user_id = database.create_user(group_id, "Bob", db_name=test_db)

    # Adding whitespace / mixed case
    name_id1 = database.add_name_suggestion(user_id, " anna maria ", db_name=test_db)
    name_id2 = database.add_name_suggestion(user_id, "LUNA", db_name=test_db)
    empty_id = database.add_name_suggestion(user_id, "   ", db_name=test_db)

    assert name_id1 is not None
    assert name_id2 is not None
    assert empty_id is None

    user_names = database.get_user_names(user_id, db_name=test_db)
    assert user_names == ["Anna Maria", "Luna"]


def test_group_name_ranking(test_db):
    """Test aggregated group name ranking sorting."""
    group_id = "grp-ranking"
    database.create_group(group_id, db_name=test_db)

    u1 = database.create_user(group_id, "User1", db_name=test_db)
    u2 = database.create_user(group_id, "User2", db_name=test_db)

    database.add_name_suggestion(u1, "Luna", db_name=test_db)
    database.add_name_suggestion(u1, "Milo", db_name=test_db)

    database.add_name_suggestion(u2, "Luna", db_name=test_db)
    database.add_name_suggestion(u2, "Noah", db_name=test_db)

    ranking = database.get_group_name_ranking(group_id, db_name=test_db)
    # Expected: Luna (2), Milo (1), Noah (1)
    assert ranking == [("Luna", 2), ("Milo", 1), ("Noah", 1)]


def test_group_user_matches(test_db):
    """Test pairwise user matching intersection calculation."""
    group_id = "grp-matches"
    database.create_group(group_id, db_name=test_db)

    u1 = database.create_user(group_id, "Anna", db_name=test_db)
    u2 = database.create_user(group_id, "Thomas", db_name=test_db)
    u3 = database.create_user(group_id, "Clara", db_name=test_db)

    database.add_name_suggestion(u1, "Luna", db_name=test_db)
    database.add_name_suggestion(u1, "Milo", db_name=test_db)
    database.add_name_suggestion(u1, "Leo", db_name=test_db)

    database.add_name_suggestion(u2, "Luna", db_name=test_db)
    database.add_name_suggestion(u2, "Milo", db_name=test_db)

    database.add_name_suggestion(u3, "Luna", db_name=test_db)

    matches = database.get_group_user_matches(group_id, db_name=test_db)
    # Anna & Thomas share 2 names ("Luna", "Milo")
    # Anna & Clara share 1 name ("Luna")
    # Thomas & Clara share 1 name ("Luna")

    assert len(matches) == 3
    first_match = matches[0]
    assert set([first_match[0], first_match[1]]) == {"Anna", "Thomas"}
    assert first_match[2] == 2
    assert first_match[3] == ["Luna", "Milo"]
