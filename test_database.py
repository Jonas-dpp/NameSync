"""Comprehensive unit and edge case tests for Name Sync."""

import os
import secrets
import sqlite3
import pytest
import database
import app


@pytest.fixture
def temp_data_dir(tmp_path):
    """Provides an isolated temporary directory for group databases."""
    d = tmp_path / "groups_data"
    d.mkdir()
    return str(d)


def test_high_entropy_random_url():
    """Verify generated group URLs are long and cryptographically secure."""
    url1 = database.generate_group_id()
    url2 = database.generate_group_id()

    assert isinstance(url1, str)
    assert len(url1) >= 40
    assert url1 != url2


def test_sanitize_group_id_security():
    """Verify path traversal and injection prevention in group IDs."""
    assert database.sanitize_group_id("normal_id_123") == "normal_id_123"

    with pytest.raises(ValueError, match="Invalid group_id"):
        database.sanitize_group_id("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid group_id"):
        database.sanitize_group_id("group; DROP TABLE users;")

    with pytest.raises(ValueError, match="Invalid group_id"):
        database.sanitize_group_id("")


def test_isolated_database_per_group(temp_data_dir):
    """Verify each group gets a separate database file and data is completely isolated."""
    g1 = database.generate_group_id()
    g2 = database.generate_group_id()

    database.create_group(g1, base_dir=temp_data_dir)
    database.create_group(g2, base_dir=temp_data_dir)

    db_path_1 = database.get_db_path(g1, base_dir=temp_data_dir)
    db_path_2 = database.get_db_path(g2, base_dir=temp_data_dir)

    assert db_path_1 != db_path_2
    assert os.path.exists(db_path_1)
    assert os.path.exists(db_path_2)

    # Add user to g1
    u1_g1 = database.create_user(g1, "Alice", password="secretpassword", is_admin=True, base_dir=temp_data_dir)
    database.add_name_suggestion(g1, u1_g1, "Milo", gender="male", base_dir=temp_data_dir)

    # Verify g2 has no users or names
    assert database.get_user_count(g1, base_dir=temp_data_dir) == 1
    assert database.get_user_count(g2, base_dir=temp_data_dir) == 0
    assert len(database.get_group_name_ranking(g2, base_dir=temp_data_dir)) == 0


def test_unique_usernames_and_password_authentication(temp_data_dir):
    """Verify unique username enforcement and password authentication per group."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)

    # Create admin user
    u1_id = database.create_user(gid, "AdminUser", password="adminpass123", is_admin=True, base_dir=temp_data_dir)
    assert u1_id > 0

    # Attempt to create duplicate user with same name (case-insensitive) should raise ValueError
    with pytest.raises(ValueError, match="bereits vergeben"):
        database.create_user(gid, "adminuser", password="anotherpassword", base_dir=temp_data_dir)

    # Test authentication - correct password
    auth_success = database.authenticate_user(gid, "ADMINUSER", "adminpass123", base_dir=temp_data_dir)
    assert auth_success is not None
    assert auth_success["user_id"] == u1_id
    assert auth_success["is_admin"] is True

    # Test authentication - wrong password
    auth_fail = database.authenticate_user(gid, "AdminUser", "wrongpassword", base_dir=temp_data_dir)
    assert auth_fail is None

    # Test non-existent user lookup
    assert database.get_user_by_name(gid, "NonExistent", base_dir=temp_data_dir) is None


def test_parse_group_param_overview_route():
    """Verify parsing of group_id query parameter with and without /overview route."""
    gid = database.generate_group_id()

    clean_id, is_overview = app.parse_group_param(gid)
    assert clean_id == gid
    assert is_overview is False

    overview_param = f"{gid}/overview"
    clean_id_ov, is_overview_ov = app.parse_group_param(overview_param)
    assert clean_id_ov == gid
    assert is_overview_ov is True

    trailing_slash_ov = f"{gid}//overview"
    clean_id_tr, is_overview_tr = app.parse_group_param(trailing_slash_ov)
    assert clean_id_tr == gid
    assert is_overview_tr is True


def test_gender_lists_configuration(temp_data_dir):
    """Verify gender lists toggle defaults to disabled (False) and can be toggled."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)

    # Default = disabled
    assert database.get_gender_lists_enabled(gid, base_dir=temp_data_dir) is False

    # Enable option
    database.set_gender_lists_enabled(gid, True, base_dir=temp_data_dir)
    assert database.get_gender_lists_enabled(gid, base_dir=temp_data_dir) is True

    # Disable option
    database.set_gender_lists_enabled(gid, False, base_dir=temp_data_dir)
    assert database.get_gender_lists_enabled(gid, base_dir=temp_data_dir) is False


def test_gender_differentiable_name_submissions(temp_data_dir):
    """Verify male, female, and neutral name submissions and filtering."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)

    u1 = database.create_user(gid, "Bob", base_dir=temp_data_dir)

    m1 = database.add_name_suggestion(gid, u1, "   liam   ", gender="male", base_dir=temp_data_dir)
    f1 = database.add_name_suggestion(gid, u1, "emma", gender="female", base_dir=temp_data_dir)
    empty = database.add_name_suggestion(gid, u1, "   ", gender="male", base_dir=temp_data_dir)

    assert m1 is not None
    assert f1 is not None
    assert empty is None

    # Verify normalization
    assert database.get_user_names(gid, u1, gender="male", base_dir=temp_data_dir) == ["Liam"]
    assert database.get_user_names(gid, u1, gender="female", base_dir=temp_data_dir) == ["Emma"]


def test_transparency_admin_view(temp_data_dir):
    """Verify admin transparency feature tracks who has and hasn't picked top names."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)

    admin = database.create_user(gid, "Admin User", is_admin=True, base_dir=temp_data_dir)
    p1 = database.create_user(gid, "Anna", is_admin=False, base_dir=temp_data_dir)
    p2 = database.create_user(gid, "Ben", is_admin=False, base_dir=temp_data_dir)

    # Anna submits a male name and a female name
    database.add_name_suggestion(gid, p1, "Leo", gender="male", base_dir=temp_data_dir)
    database.add_name_suggestion(gid, p1, "Maya", gender="female", base_dir=temp_data_dir)

    # General transparency check
    statuses = database.get_user_submission_statuses(gid, base_dir=temp_data_dir)
    status_dict = {s["display_name"]: s for s in statuses}

    assert status_dict["Admin User"]["has_submitted"] is False
    assert status_dict["Admin User"]["submitted_count"] == 0

    assert status_dict["Anna"]["has_submitted"] is True
    assert status_dict["Anna"]["submitted_count"] == 2

    assert status_dict["Ben"]["has_submitted"] is False
    assert status_dict["Ben"]["submitted_count"] == 0

    # Male-specific transparency check
    male_statuses = database.get_user_submission_statuses(gid, gender="male", base_dir=temp_data_dir)
    male_dict = {s["display_name"]: s for s in male_statuses}
    assert male_dict["Anna"]["has_submitted"] is True
    assert male_dict["Anna"]["submitted_count"] == 1

    # Female-specific transparency check
    female_statuses = database.get_user_submission_statuses(gid, gender="female", base_dir=temp_data_dir)
    female_dict = {s["display_name"]: s for s in female_statuses}
    assert female_dict["Ben"]["has_submitted"] is False


def test_group_deletion_and_stale_link(temp_data_dir):
    """Verify group deletion removes DB file and renders URL stale."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)
    assert database.group_exists(gid, base_dir=temp_data_dir) is True

    # Delete
    success = database.delete_group(gid, base_dir=temp_data_dir)
    assert success is True

    # Link stale check
    assert database.group_exists(gid, base_dir=temp_data_dir) is False
    assert not os.path.exists(database.get_db_path(gid, base_dir=temp_data_dir))


def test_auto_cleanup_after_7_days(temp_data_dir):
    """Verify groups older than 7 days are automatically deleted."""
    g_fresh = database.generate_group_id()
    g_old = database.generate_group_id()

    database.create_group(g_fresh, base_dir=temp_data_dir)
    database.create_group(g_old, base_dir=temp_data_dir)

    # Set created_at of g_old to 8 days ago
    db_path_old = database.get_db_path(g_old, base_dir=temp_data_dir)
    conn = sqlite3.connect(db_path_old)
    conn.execute(
        "UPDATE group_info SET created_at = datetime('now', '-8 days') WHERE group_id = ?;",
        (g_old,),
    )
    conn.commit()
    conn.close()

    deleted_count = database.cleanup_old_groups(days=7, base_dir=temp_data_dir)
    assert deleted_count == 1

    assert database.group_exists(g_fresh, base_dir=temp_data_dir) is True
    assert database.group_exists(g_old, base_dir=temp_data_dir) is False


def test_rankings_and_pairwise_matches(temp_data_dir):
    """Verify gender-specific group rankings and pairwise user match calculations."""
    gid = database.generate_group_id()
    database.create_group(gid, base_dir=temp_data_dir)

    u1 = database.create_user(gid, "User1", base_dir=temp_data_dir)
    u2 = database.create_user(gid, "User2", base_dir=temp_data_dir)

    database.add_name_suggestion(gid, u1, "Milo", gender="male", base_dir=temp_data_dir)
    database.add_name_suggestion(gid, u1, "Noah", gender="male", base_dir=temp_data_dir)
    database.add_name_suggestion(gid, u2, "Milo", gender="male", base_dir=temp_data_dir)

    # Rankings
    male_ranking = database.get_group_name_ranking(gid, gender="male", base_dir=temp_data_dir)
    assert male_ranking == [("Milo", 2), ("Noah", 1)]

    # User Matches
    matches = database.get_group_user_matches(gid, gender="male", base_dir=temp_data_dir)
    assert len(matches) == 1
    u1_name, u2_name, shared_count, shared_names = matches[0]
    assert sorted([u1_name, u2_name]) == ["User1", "User2"]
    assert shared_count == 1
    assert shared_names == ["Milo"]
