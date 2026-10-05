"""Admin CLI: user management and index maintenance.

Usage:
    python -m makeros.cli adduser <username> [--role admin] [--name "Nombre"]
    python -m makeros.cli reindex
"""

from __future__ import annotations

import argparse
import getpass

from . import auth
from .config import Settings
from .db import connect, init_schema
from .indexer import reindex_all


def main() -> None:
    parser = argparse.ArgumentParser(prog="makeros")
    sub = parser.add_subparsers(dest="command", required=True)

    adduser = sub.add_parser("adduser", help="crear una cuenta de usuario")
    adduser.add_argument("username")
    adduser.add_argument("--role", default="member", choices=auth.ROLES)
    adduser.add_argument("--name", default="", help="nombre visible")

    sub.add_parser("reindex", help="reconstruir el índice de búsqueda")

    args = parser.parse_args()
    settings = Settings.from_env()
    conn = connect(settings.db_path)
    init_schema(conn)
    try:
        if args.command == "adduser":
            password = getpass.getpass("Contraseña: ")
            auth.create_user(
                conn, args.username, password, role=args.role, display_name=args.name
            )
            print(f"Usuario creado: {args.username} ({args.role})")
        elif args.command == "reindex":
            total = reindex_all(conn, settings.content_dir)
            print(f"{total} documentos indexados")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
