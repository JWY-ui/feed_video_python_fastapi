"""评论模块——Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field


class PublishCommentRequest(BaseModel):
    video_id: int = Field(..., gt=0)
    content: str = Field(..., min_length=1)


class DeleteCommentRequest(BaseModel):
    comment_id: int = Field(..., gt=0)


class GetAllCommentsRequest(BaseModel):
    video_id: int = Field(..., gt=0)


class CommentInfo(BaseModel):
    id: int
    username: str
    video_id: int
    author_id: int
    content: str
    created_at: str
