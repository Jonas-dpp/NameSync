"""Database module for Name Sync.

Handles individual SQLite databases per group, path sanitization, high-entropy group ID generation,
foreign key constraints, gender-based list configuration, admin transparency reporting,
and automatic 7-day cleanup of expired group databases.
"""

import os
import re
import secrets
import sqlite3
import datetime
import hashlib
from typing import Optional, List, Tuple, Dict, Any
from cologne_phonetics import encode

DATA_DIR: str = "groups_data"


def encode_phonetic(name: str) -> str:
    """Generates phonetic code using Cologne Phonetics for a given name string.

    Args:
        name: Name string.

    Returns:
        str: Phonetic code string.
    """
    if not name or not name.strip():
        return ""
    try:
        res = encode(name.strip())
        if res and len(res) > 0:
            return res[0][1]
    except Exception:
        pass
    return ""


def hash_password(password: str) -> str:
    """Hashes a password string using SHA-256.

    Args:
        password: Plain text password.

    Returns:
        str: Hexadecimal SHA-256 hash.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def migrate_db(conn: sqlite3.Connection) -> None:
    """Ensures existing group databases are migrated with password_hash, unique display_name index, and phonetic_code."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(users);")
        columns = [row[1] for row in cursor.fetchall()]
        if "password_hash" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT '';")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name COLLATE NOCASE);")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='names';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(names);")
        columns = [row[1] for row in cursor.fetchall()]
        if "phonetic_code" not in columns:
            cursor.execute("ALTER TABLE names ADD COLUMN phonetic_code TEXT NOT NULL DEFAULT '';")

        cursor.execute("SELECT name_id, suggested_name FROM names WHERE phonetic_code = '' OR phonetic_code IS NULL;")
        rows = cursor.fetchall()
        for name_id, suggested_name in rows:
            code = encode_phonetic(suggested_name)
            cursor.execute("UPDATE names SET phonetic_code = ? WHERE name_id = ?;", (code, name_id))

    conn.commit()


def sanitize_group_id(group_id: str) -> str:
    """Sanitizes group_id to prevent directory traversal attacks.

    Args:
        group_id: Raw group identifier string.

    Returns:
        str: Sanitized group identifier.

    Raises:
        ValueError: If group_id contains unsafe characters or is empty.
    """
    if not group_id or not isinstance(group_id, str):
        raise ValueError("Invalid group_id: must be a non-empty string.")

    # Allow alphanumeric characters, hyphens, and underscores only
    clean_id: str = re.sub(r"[^a-zA-Z0-9_-]", "", group_id)
    if not clean_id or clean_id != group_id:
        raise ValueError("Invalid group_id format: dangerous characters detected.")
    return clean_id


def generate_group_id() -> str:
    """Generates a long, high-entropy random URL parameter for brute-force resistance.

    Returns:
        str: Cryptographically secure random URL safe string.
    """
    return secrets.token_urlsafe(32)


def get_db_path(group_id: str, base_dir: str = DATA_DIR) -> str:
    """Returns the database file path for a given group_id.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        str: Filepath for the group SQLite database.
    """
    clean_id = sanitize_group_id(group_id)
    return os.path.join(base_dir, f"{clean_id}.db")


def get_connection(group_id: str, base_dir: str = DATA_DIR) -> sqlite3.Connection:
    """Establishes a connection to the group's SQLite database and enables foreign keys.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        sqlite3.Connection: Database connection object with foreign keys enabled.
    """
    os.makedirs(base_dir, exist_ok=True)
    db_path = get_db_path(group_id, base_dir=base_dir)
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    migrate_db(conn)
    return conn


def init_db(db_name: str = "deprecated") -> None:
    """Legacy init_db maintained for backward compatibility. Ensures data dir exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def create_group(group_id: str, base_dir: str = DATA_DIR) -> None:
    """Creates a dedicated SQLite database file and tables for a new group.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.
    """
    os.makedirs(base_dir, exist_ok=True)
    clean_id = sanitize_group_id(group_id)
    db_path = get_db_path(clean_id, base_dir=base_dir)

    if os.path.exists(db_path):
        os.remove(db_path)

    with get_connection(clean_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS group_info (
                group_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                gender_lists_enabled BOOLEAN NOT NULL DEFAULT 0
            );
            """
        )

        cursor.execute(
            "INSERT INTO group_info (group_id, gender_lists_enabled) VALUES (?, 0);",
            (clean_id,),
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL DEFAULT '',
                is_admin BOOLEAN NOT NULL DEFAULT 0
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS names (
                name_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                suggested_name TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT 'neutral',
                phonetic_code TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            """
        )

        conn.commit()


def group_exists(group_id: str, base_dir: str = DATA_DIR) -> bool:
    """Checks whether a group's SQLite database file exists and contains valid group_info.

    Args:
        group_id: Group string identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        bool: True if group exists and is valid, False otherwise.
    """
    try:
        clean_id = sanitize_group_id(group_id)
    except ValueError:
        return False

    db_path = get_db_path(clean_id, base_dir=base_dir)
    if not os.path.exists(db_path):
        return False

    try:
        with get_connection(clean_id, base_dir=base_dir) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM group_info WHERE group_id = ?;", (clean_id,))
            return cursor.fetchone() is not None
    except Exception:
        return False


def delete_group(group_id: str, base_dir: str = DATA_DIR) -> bool:
    """Deletes a group's dedicated SQLite database file.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        bool: True if group database was successfully removed, False otherwise.
    """
    try:
        clean_id = sanitize_group_id(group_id)
    except ValueError:
        return False

    db_path = get_db_path(clean_id, base_dir=base_dir)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            return True
        except OSError:
            return False
    return False


def get_gender_lists_enabled(group_id: str, base_dir: str = DATA_DIR) -> bool:
    """Gets whether separate male/female gender lists are enabled for a group.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        bool: True if gender lists option is enabled, False otherwise.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT gender_lists_enabled FROM group_info LIMIT 1;")
        row = cursor.fetchone()
        return bool(row[0]) if row else False


def set_gender_lists_enabled(group_id: str, enabled: bool, base_dir: str = DATA_DIR) -> None:
    """Enables or disables separate gender lists for a group.

    Args:
        group_id: Group identifier.
        enabled: True to enable gender lists, False to disable.
        base_dir: Directory where group database files are stored.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "UPDATE group_info SET gender_lists_enabled = ? WHERE group_id = ?;",
            (1 if enabled else 0, sanitize_group_id(group_id)),
        )
        conn.commit()


def get_user_count(group_id: str, base_dir: str = DATA_DIR) -> int:
    """Gets total count of users registered in a group.

    Args:
        group_id: Group identifier.
        base_dir: Directory where group database files are stored.

    Returns:
        int: Total number of members in the group.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users;")
        row = cursor.fetchone()
        return row[0] if row else 0


def create_user(
    group_id: str, display_name: str, password: str = "", is_admin: bool = False, base_dir: str = DATA_DIR
) -> int:
    """Creates a user within a group's database and returns the generated user_id.

    Args:
        group_id: Group identifier.
        display_name: Display name of the user.
        password: Plain text password for the user.
        is_admin: Admin status flag.
        base_dir: Directory where group database files are stored.

    Returns:
        int: The created user's ID.

    Raises:
        ValueError: If the display name is already taken in this group.
    """
    cleaned_name: str = display_name.strip()
    if not cleaned_name:
        raise ValueError("Bitte gib einen gültigen Namen ein.")

    pwd_hash: str = hash_password(password)
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (display_name, password_hash, is_admin) VALUES (?, ?, ?);",
                (cleaned_name, pwd_hash, 1 if is_admin else 0),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore
        except sqlite3.IntegrityError:
            raise ValueError(f"Der Name '{cleaned_name}' ist in dieser Gruppe bereits vergeben.")


def get_user_by_name(
    group_id: str, display_name: str, base_dir: str = DATA_DIR
) -> Optional[Dict[str, Any]]:
    """Retrieves user info by display_name from the group's database (case-insensitive).

    Args:
        group_id: Group identifier.
        display_name: User display name.
        base_dir: Directory where group database files are stored.

    Returns:
        Optional[dict]: Dictionary with user attributes or None if not found.
    """
    cleaned_name = display_name.strip()
    if not cleaned_name:
        return None

    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, display_name, is_admin, password_hash FROM users WHERE display_name = ? COLLATE NOCASE;",
            (cleaned_name,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "group_id": group_id,
                "display_name": row[1],
                "is_admin": bool(row[2]),
                "password_hash": row[3],
            }
        return None


def authenticate_user(
    group_id: str, display_name: str, password: str, base_dir: str = DATA_DIR
) -> Optional[Dict[str, Any]]:
    """Authenticates a user against display_name and password.

    Args:
        group_id: Group identifier.
        display_name: User display name.
        password: Plain text password.
        base_dir: Directory where group database files are stored.

    Returns:
        Optional[dict]: User dict if credentials match, None otherwise.
    """
    user = get_user_by_name(group_id, display_name, base_dir=base_dir)
    if not user:
        return None

    pwd_hash = hash_password(password)
    if user["password_hash"] == pwd_hash:
        return user
    return None


def get_user(
    group_id: str, user_id: int, base_dir: str = DATA_DIR
) -> Optional[Dict[str, Any]]:
    """Retrieves user info by user_id from the group's database.

    Args:
        group_id: Group identifier.
        user_id: User identifier within the group.
        base_dir: Directory where group database files are stored.

    Returns:
        Optional[dict]: Dictionary with user attributes or None if not found.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, display_name, is_admin FROM users WHERE user_id = ?;",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "group_id": group_id,
                "display_name": row[1],
                "is_admin": bool(row[2]),
            }
        return None


def add_name_suggestion(
    group_id: str, user_id: int, name: str, gender: str = "neutral", base_dir: str = DATA_DIR
) -> Optional[int]:
    """Normalizes and adds a name suggestion for a user in the group.

    Name is trimmed and converted to Title Case. Phonetic code is generated.
    Enforces per-user phonetic uniqueness so a user cannot submit duplicate or phonetically identical names.
    Empty names are ignored. Gender must be 'male', 'female', or 'neutral'.

    Args:
        group_id: Group identifier.
        user_id: User identifier.
        name: Name string input.
        gender: Category ('male', 'female', or 'neutral').
        base_dir: Directory where group database files are stored.

    Returns:
        Optional[int]: Generated name_id, or None if input was empty.

    Raises:
        ValueError: If user has already submitted a phonetically identical name in this list.
    """
    normalized_name: str = name.strip().title()
    if not normalized_name:
        return None

    valid_gender = gender if gender in ("male", "female", "neutral") else "neutral"
    code = encode_phonetic(normalized_name)

    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()

        if code:
            cursor.execute(
                "SELECT suggested_name FROM names WHERE user_id = ? AND gender = ? AND phonetic_code = ?;",
                (user_id, valid_gender, code),
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError(
                    f"Du hast bereits einen ähnlich klingenden Namen ('{existing[0]}') eingereicht."
                )
        else:
            cursor.execute(
                "SELECT suggested_name FROM names WHERE user_id = ? AND gender = ? AND suggested_name = ? COLLATE NOCASE;",
                (user_id, valid_gender, normalized_name),
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError(
                    f"Du hast den Namen '{existing[0]}' bereits eingereicht."
                )

        cursor.execute(
            "INSERT INTO names (user_id, suggested_name, gender, phonetic_code) VALUES (?, ?, ?, ?);",
            (user_id, normalized_name, valid_gender, code),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore


def get_user_names(
    group_id: str, user_id: int, gender: Optional[str] = None, base_dir: str = DATA_DIR
) -> List[str]:
    """Gets all suggested names submitted by a specific user in a group.

    Args:
        group_id: Group identifier.
        user_id: User identifier.
        gender: Optional gender filter ('male', 'female', 'neutral').
        base_dir: Directory where group database files are stored.

    Returns:
        List[str]: List of suggested names.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        if gender:
            cursor.execute(
                "SELECT suggested_name FROM names WHERE user_id = ? AND gender = ? ORDER BY name_id ASC;",
                (user_id, gender),
            )
        else:
            cursor.execute(
                "SELECT suggested_name FROM names WHERE user_id = ? ORDER BY name_id ASC;",
                (user_id,),
            )
        return [row[0] for row in cursor.fetchall()]


def get_representative_spelling_map(
    conn: sqlite3.Connection, gender: Optional[str] = None
) -> Dict[str, str]:
    """Helper to determine representative (most frequent) spelling per phonetic_code.

    Args:
        conn: SQLite database connection.
        gender: Optional gender filter.

    Returns:
        Dict[str, str]: Mapping from phonetic_code to representative name spelling.
    """
    cursor = conn.cursor()
    if gender:
        cursor.execute(
            """
            SELECT phonetic_code, suggested_name, COUNT(*) as cnt, MIN(name_id) as min_id
            FROM names
            WHERE gender = ? AND phonetic_code != '' AND phonetic_code IS NOT NULL
            GROUP BY phonetic_code, suggested_name
            ORDER BY cnt DESC, min_id ASC;
            """,
            (gender,),
        )
    else:
        cursor.execute(
            """
            SELECT phonetic_code, suggested_name, COUNT(*) as cnt, MIN(name_id) as min_id
            FROM names
            WHERE phonetic_code != '' AND phonetic_code IS NOT NULL
            GROUP BY phonetic_code, suggested_name
            ORDER BY cnt DESC, min_id ASC;
            """
        )

    rep_map: Dict[str, str] = {}
    for code, spelling, _, _ in cursor.fetchall():
        if code not in rep_map:
            rep_map[code] = spelling
    return rep_map


def get_group_name_ranking(
    group_id: str, gender: Optional[str] = None, base_dir: str = DATA_DIR
) -> List[Tuple[str, int]]:
    """Retrieves ranked list of names grouped by phonetic_code for a group.

    The displayed label for each phonetic group is the most frequently entered spelling.

    Args:
        group_id: Group identifier.
        gender: Optional gender filter ('male', 'female', 'neutral').
        base_dir: Directory where group database files are stored.

    Returns:
        List[Tuple[str, int]]: List of (representative_name, total_count) tuples.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        rep_map = get_representative_spelling_map(conn, gender=gender)

        if gender:
            cursor.execute(
                """
                SELECT phonetic_code, suggested_name, COUNT(*) as count
                FROM names
                WHERE gender = ?
                GROUP BY CASE WHEN phonetic_code != '' AND phonetic_code IS NOT NULL THEN phonetic_code ELSE suggested_name END
                ORDER BY count DESC;
                """,
                (gender,),
            )
        else:
            cursor.execute(
                """
                SELECT phonetic_code, suggested_name, COUNT(*) as count
                FROM names
                GROUP BY CASE WHEN phonetic_code != '' AND phonetic_code IS NOT NULL THEN phonetic_code ELSE suggested_name END
                ORDER BY count DESC;
                """
            )

        results: List[Tuple[str, int]] = []
        for code, fallback_spelling, count in cursor.fetchall():
            label = rep_map.get(code, fallback_spelling) if code else fallback_spelling
            results.append((label, count))

        results.sort(key=lambda x: (-x[1], x[0]))
        return results


def get_group_user_matches(
    group_id: str, gender: Optional[str] = None, base_dir: str = DATA_DIR
) -> List[Tuple[str, str, int, List[str]]]:
    """Calculates phonetic name intersections between pairs of users in a group.

    Args:
        group_id: Group identifier.
        gender: Optional gender filter ('male', 'female', 'neutral').
        base_dir: Directory where group database files are stored.

    Returns:
        List[Tuple[str, str, int, List[str]]]: Pairwise match tuples (u1_name, u2_name, count, names).
    """
    import itertools

    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT user_id, display_name FROM users ORDER BY user_id ASC;")
        users = cursor.fetchall()

        if len(users) < 2:
            return []

        rep_map = get_representative_spelling_map(conn, gender=gender)

        user_codes_map: Dict[int, Dict[str, str]] = {}
        for uid, _ in users:
            if gender:
                cursor.execute(
                    "SELECT phonetic_code, suggested_name FROM names WHERE user_id = ? AND gender = ?;",
                    (uid, gender),
                )
            else:
                cursor.execute(
                    "SELECT phonetic_code, suggested_name FROM names WHERE user_id = ?;", (uid,)
                )
            user_codes_map[uid] = {}
            for code, name_str in cursor.fetchall():
                key = code if code else name_str
                user_codes_map[uid][key] = name_str

    matches: List[Tuple[str, str, int, List[str]]] = []
    for (u1_id, u1_name), (u2_id, u2_name) in itertools.combinations(users, 2):
        shared_keys: set[str] = set(user_codes_map[u1_id].keys()) & set(user_codes_map[u2_id].keys())
        if shared_keys:
            shared_names = [rep_map.get(k, user_codes_map[u1_id][k]) for k in shared_keys]
            sorted_shared = sorted(shared_names)
            matches.append((u1_name, u2_name, len(shared_keys), sorted_shared))

    matches.sort(key=lambda item: (-item[2], item[0], item[1]))
    return matches


def get_user_submission_statuses(
    group_id: str, gender: Optional[str] = None, base_dir: str = DATA_DIR
) -> List[Dict[str, Any]]:
    """Gets list of group participants showing who has and hasn't picked top names.

    Args:
        group_id: Group identifier.
        gender: Optional gender filter ('male', 'female', or None for all).
        base_dir: Directory where group database files are stored.

    Returns:
        List[Dict[str, Any]]: List of dicts with display_name, is_admin, submitted_count, has_submitted.
    """
    with get_connection(group_id, base_dir=base_dir) as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, display_name, is_admin FROM users ORDER BY display_name ASC;"
        )
        users = cursor.fetchall()

        statuses: List[Dict[str, Any]] = []
        for uid, display_name, is_admin in users:
            if gender:
                cursor.execute(
                    "SELECT COUNT(*) FROM names WHERE user_id = ? AND gender = ?;",
                    (uid, gender),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM names WHERE user_id = ?;", (uid,)
                )
            count = cursor.fetchone()[0]
            statuses.append(
                {
                    "user_id": uid,
                    "display_name": display_name,
                    "is_admin": bool(is_admin),
                    "submitted_count": count,
                    "has_submitted": count > 0,
                }
            )
        return statuses


def cleanup_old_groups(days: int = 7, base_dir: str = DATA_DIR) -> int:
    """Deletes group database files that were created or modified more than `days` ago.

    Args:
        days: Threshold in days for deleting old group databases.
        base_dir: Directory where group database files are stored.

    Returns:
        int: Number of deleted group databases.
    """
    if not os.path.exists(base_dir):
        return 0

    deleted_count: int = 0
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    for filename in os.listdir(base_dir):
        if not filename.endswith(".db"):
            continue

        filepath = os.path.join(base_dir, filename)
        try:
            # First attempt to check inside DB for created_at
            group_id = filename[:-3]
            should_delete = False

            try:
                conn = sqlite3.connect(filepath)
                cursor = conn.cursor()
                cursor.execute("SELECT created_at FROM group_info LIMIT 1;")
                row = cursor.fetchone()
                conn.close()

                if row and row[0]:
                    created_at_dt = datetime.datetime.fromisoformat(
                        row[0].replace("Z", "+00:00")
                    )
                    if created_at_dt.tzinfo is None:
                        created_at_dt = created_at_dt.replace(tzinfo=datetime.timezone.utc)
                    if created_at_dt < cutoff:
                        should_delete = True
            except Exception:
                # Fallback to file modification time
                pass

            if not should_delete:
                mtime = os.path.getmtime(filepath)
                file_dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
                if file_dt < cutoff:
                    should_delete = True

            if should_delete:
                os.remove(filepath)
                deleted_count += 1
        except OSError:
            continue

    return deleted_count
