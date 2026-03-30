from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.db.database import get_db
from app.models.post import Post
from app.models.user import User
from app.schemas.post import PostCreate, PostResponse

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("", response_model=list[PostResponse])
def get_posts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Any authenticated user (reader, writer, moderator) can view all posts."""
    posts = db.query(Post).all()
    return posts


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    post: PostCreate,
    current_user: User = Depends(require_roles(["writer", "moderator"])),
    db: Session = Depends(get_db),
):
    """Only writer and moderator can create posts."""
    new_post = Post(
        title=post.title,
        content=post.content,
        author_id=current_user.id,
        author_username=current_user.username,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


@router.delete("/{post_id}", status_code=status.HTTP_200_OK)
def delete_post(
    post_id: int,
    current_user: User = Depends(require_roles(["moderator"])),
    db: Session = Depends(get_db),
):
    """Only moderator can delete posts."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    db.delete(post)
    db.commit()
    return {
        "message": "Post deleted successfully",
        "deleted_post_id": post_id,
        "deleted_by": current_user.username,
    }
