from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.db.database import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author_username = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
