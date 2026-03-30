from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10)


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    author_username: str

    model_config = {"from_attributes": True}
