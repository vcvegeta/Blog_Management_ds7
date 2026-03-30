from sqlalchemy import Column, DateTime, Integer, String, func

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    # role choices: reader, writer, moderator
    role = Column(String(20), nullable=False, default="reader")
    created_at = Column(DateTime, server_default=func.now())
