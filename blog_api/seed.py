"""
Seed script — populates the SQLite database with default users.

Roles:
  - reader   : can only view posts
  - writer   : can view + create posts
  - moderator: can view + create + delete posts

Run:
    python seed.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.core.security import get_password_hash
from app.db.database import Base, SessionLocal, engine
from app.models.user import User  # noqa: F401 — needed for Base.metadata


def seed():
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    users_to_seed = [
        {"username": "alice", "password": "alice123", "role": "reader"},
        {"username": "bob", "password": "bob123", "role": "writer"},
        {"username": "carol", "password": "carol123", "role": "moderator"},
    ]

    for u in users_to_seed:
        existing = db.query(User).filter(User.username == u["username"]).first()
        if existing:
            print(f"  [SKIP] User '{u['username']}' already exists.")
            continue

        user = User(
            username=u["username"],
            hashed_password=get_password_hash(u["password"]),
            role=u["role"],
        )
        db.add(user)
        print(f"  [ADD]  User '{u['username']}' with role '{u['role']}' created.")

    db.commit()
    db.close()
    print("\nSeeding complete!")
    print("\nCredentials:")
    print("  alice  / alice123  -> role: reader")
    print("  bob    / bob123    -> role: writer")
    print("  carol  / carol123  -> role: moderator")


if __name__ == "__main__":
    seed()
