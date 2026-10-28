"""Local user accounts (Argon2 password hashing).

Accounts are the identity anchor of the whole system: task/project
assignment, activity attribution, personal spaces and per-user
integrations all key off the users table.
"""

from __future__ import annotations

import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()

ROLES = ("admin", "member", "viewer")


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2 (never store plaintext)."""
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a plaintext password against an Argon2 hash."""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    role: str = "member",
    display_name: str = "",
) -> int:
    """Create a user account and return its id."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (username.strip().lower(), hash_password(password), display_name or username, role),
    )
    conn.commit()
    return int(cur.lastrowid)


def authenticate(
    conn: sqlite3.Connection, username: str, password: str
) -> sqlite3.Row | None:
    """Return the user row if credentials match, else None."""
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
    ).fetchone()
    if row is None or not verify_password(row["password_hash"], password):
        return None
    return row


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_display_name(conn: sqlite3.Connection, user_id: int, display_name: str) -> None:
    conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
    conn.commit()


def set_avatar(conn: sqlite3.Connection, user_id: int, media_path: str) -> None:
    """Store the /media/ path of the user's picture ("" removes it)."""
    conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (media_path, user_id))
    conn.commit()


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def list_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All accounts, oldest first (never includes password hashes in use)."""
    return conn.execute(
        "SELECT id, username, display_name, role, created_at FROM users ORDER BY id"
    ).fetchall()


def _admin_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]


def update_role(conn: sqlite3.Connection, user_id: int, role: str) -> None:
    """Change an account's role; the last admin cannot be demoted."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    row = get_user(conn, user_id)
    if row is None:
        raise LookupError("user not found")
    if row["role"] == "admin" and role != "admin" and _admin_count(conn) == 1:
        raise PermissionError("cannot demote the only admin")
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()


def set_password(conn: sqlite3.Connection, user_id: int, password: str) -> None:
    """Admin-driven password reset (Argon2 hash, never plaintext)."""
    if get_user(conn, user_id) is None:
        raise LookupError("user not found")
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(password), user_id),
    )
    conn.commit()


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Remove an account; the last admin cannot be deleted."""
    row = get_user(conn, user_id)
    if row is None:
        raise LookupError("user not found")
    if row["role"] == "admin" and _admin_count(conn) == 1:
        raise PermissionError("cannot delete the only admin")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
