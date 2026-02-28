"""Create an admin user for SignalForge.

Usage:
    python -m app.scripts.create_user --username admin --password <password>
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth import create_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SignalForge user")
    parser.add_argument("--username", required=True, help="Username for the new user")
    parser.add_argument("--password", required=True, help="Password for the new user")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Check if user already exists
        existing = db.query(User).filter(User.username == args.username).first()
        if existing:
            print(f"User '{args.username}' already exists.")
            sys.exit(1)

        user = create_user(db, args.username, args.password)
        print(f"User '{user.username}' created successfully (id={user.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
