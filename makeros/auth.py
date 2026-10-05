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


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
