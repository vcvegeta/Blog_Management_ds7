from fastapi import FastAPI

from app.db.database import Base, engine
from app.routers import auth, posts, users

# Create all tables in SQLite on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Blog Management System",
    version="1.0.0",
    description="FastAPI Blog API with JWT authentication, role-based authorization "
    "(reader, writer, moderator), and SQLite database.",
)


@app.get("/")
def root():
    return {
        "message": "Blog Management System API is running",
        "docs": "/docs",
        "roles": ["reader", "writer", "moderator"],
    }


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
