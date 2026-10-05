"""Accounts: hashing, creation, authentication."""

import sqlite3

from makeros.auth import (
    authenticate,
    create_user,
    hash_password,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    h = hash_password("secreto123")
    assert h != "secreto123"
    assert verify_password(h, "secreto123")
    assert not verify_password(h, "otra cosa")


def test_verify_rejects_garbage_hash():
    assert not verify_password("not-a-hash", "x")


def test_create_user_and_authenticate(conn):
    uid = create_user(conn, "  Maria  ", "clave", role="admin", display_name="María")
    assert uid >= 1

    user = authenticate(conn, "maria", "clave")
    assert user is not None
    assert user["role"] == "admin"
    assert user["display_name"] == "María"

    assert authenticate(conn, "maria", "mala clave") is None
    assert authenticate(conn, "nadie", "clave") is None


def test_duplicate_username_rejected(conn):
    create_user(conn, "jacob", "a")
    try:
        create_user(conn, "jacob", "b")
        raise AssertionError("expected IntegrityError")
    except sqlite3.IntegrityError:
        pass


def test_invalid_role_rejected(conn):
    try:
        create_user(conn, "x", "y", role="superuser")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
