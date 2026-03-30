from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import get_token

client = TestClient(app)


def test_get_posts_authenticated_200():
    """GET /posts with valid token → 200 OK (any role)."""
    token = get_token("alice", "alice123")  # reader
    response = client.get(
        "/posts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_get_posts_no_token_401():
    """GET /posts without token → 401 Unauthorized."""
    response = client.get("/posts")
    assert response.status_code == 401


def test_reader_cannot_create_post_403():
    """POST /posts using reader role → 403 Forbidden."""
    token = get_token("alice", "alice123")  # reader
    response = client.post(
        "/posts",
        json={"title": "My First Post", "content": "This is the content of my post."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_writer_can_create_post_201():
    """POST /posts using writer role → 201 Created."""
    token = get_token("bob", "bob123")  # writer
    response = client.post(
        "/posts",
        json={"title": "Bob's Post", "content": "Content written by bob the writer."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Bob's Post"
    assert body["author_username"] == "bob"


def test_moderator_can_create_post_201():
    """POST /posts using moderator role → 201 Created."""
    token = get_token("carol", "carol123")  # moderator
    response = client.post(
        "/posts",
        json={
            "title": "Carol's Post",
            "content": "Content written by carol the moderator.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


def test_writer_cannot_delete_post_403():
    """DELETE /posts/{id} using writer role → 403 Forbidden."""
    # First create a post as moderator
    mod_token = get_token("carol", "carol123")
    create_resp = client.post(
        "/posts",
        json={
            "title": "To Be Deleted",
            "content": "This post will be deleted eventually.",
        },
        headers={"Authorization": f"Bearer {mod_token}"},
    )
    post_id = create_resp.json()["id"]

    # Writer tries to delete → 403
    writer_token = get_token("bob", "bob123")
    response = client.delete(
        f"/posts/{post_id}",
        headers={"Authorization": f"Bearer {writer_token}"},
    )
    assert response.status_code == 403


def test_moderator_can_delete_post_200():
    """DELETE /posts/{id} using moderator role → 200 OK."""
    # Create a post first
    token = get_token("carol", "carol123")
    create_resp = client.post(
        "/posts",
        json={
            "title": "Delete Me",
            "content": "This post should be deleted by moderator.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    post_id = create_resp.json()["id"]

    # Moderator deletes
    response = client.delete(
        f"/posts/{post_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["deleted_post_id"] == post_id
