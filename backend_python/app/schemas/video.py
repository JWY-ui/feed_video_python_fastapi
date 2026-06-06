"""视频模块——Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field


# ─── 视频发布 ───
class PublishVideoRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    play_url: str = Field(..., min_length=1)
    cover_url: str = Field(..., min_length=1)


class VideoInfo(BaseModel):
    """视频详情返回"""
    id: int
    author_id: int
    username: str
    title: str
    description: str | None = None
    play_url: str
    cover_url: str
    create_time: str  # ISO 格式时间字符串
    likes_count: int
    popularity: int


class ListByAuthorIDRequest(BaseModel):
    author_id: int


class GetDetailRequest(BaseModel):
    id: int


# ─── 上传响应 ───
class UploadResponse(BaseModel):
    url: str
    play_url: str | None = None  # uploadCover 不返回 play_url


class CoverUploadResponse(BaseModel):
    url: str
    cover_url: str


# ─── 分片上传 ───
class InitChunkRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    chunk_size: int = Field(..., gt=0)
    total_chunks: int = Field(..., gt=0)
    file_hash: str = Field(..., min_length=1)


class InitChunkResponse(BaseModel):
    upload_id: str
    uploaded_chunks: list[int]  # 已上传的分片序号（断点续传用）


class ChunkStatusRequest(BaseModel):
    upload_id: str = Field(..., min_length=1)


class ChunkStatusResponse(BaseModel):
    upload_id: str
    uploaded_chunks: list[int]
    total_chunks: int


class CompleteChunkRequest(BaseModel):
    upload_id: str = Field(..., min_length=1)
