import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models.post import Post  # noqa: F401
from app.models.user import User  # noqa: F401

# Use an in-memory SQLite DB for tests
TEST_DATABASE_URL = "sqlite:///./test_blog.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True, scope="module")
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    # Seed test users
    users = [
        User(
            username="alice",
            hashed_password=get_password_hash("alice123"),
            role="reader",
        ),
        User(
            username="bob",
            hashed_password=get_password_hash("bob123"),
            role="writer",
        ),
        User(
            username="carol",
            hashed_password=get_password_hash("carol123"),
            role="moderator",
        ),
    ]
    for u in users:
        existing = db.query(User).filter(User.username == u.username).first()
        if not existing:
            db.add(u)
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


def get_token(username: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    return response.json()["access_token"]
